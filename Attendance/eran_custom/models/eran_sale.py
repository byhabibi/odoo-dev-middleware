from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError, ValidationError, AccessError
from datetime import date, datetime
import logging
_logger = logging.getLogger(__name__)
from itertools import groupby
import json
class SaleORder(models.Model):
    _inherit = 'sale.order'
    
    state = fields.Selection(
        selection=[
            ('draft', "Draft"),
            ('sent', "Quotation Sent"),
            ('sale', "Sales Order"),
            ('done', "Locked"),
            ('cancel', "Cancelled"),
        ],
        string="Status",
        readonly=True, copy=False, index=True,
        tracking=3,
        default='draft')
    po_ref = fields.Char('PO Customer', required=True, copy=True)
    order_sheet_count = fields.Integer('History', compute='_order_sheet_count')
    picking_count_delivery = fields.Integer('Delivery', compute='_picking_count_delivery_order')
    check_osheet_so = fields.Boolean('Order Sheet All', commpute='_compute_all_create_order_sheet', store=True, copy=False)
    note = fields.Html('Terms and Conditions', compute="_compute_notes")
    sequence_number = fields.Integer(string='Sequence Number')
    parent_revision_name = fields.Char('Parent Revision Name')
    start_date = fields.Date('Start Date')
    # expiration_date = fields.Datetime('Expiration Date', tracking=True)
    # def update_expired_sale_order(self):
    #     datetime_today = datetime.combine(date.today(), datetime.min.time())
    #     order_ids = self.env['sale.order'].search([('expiration_date', '<', datetime_today)])
    #     for order in order_ids:
    #         order.action_done()

    dpp = fields.Float(string="DPP", compute='_compute_dpp', store=True)
    order_date = fields.Date('Date Order', default= lambda self: fields.Date.today(), help="Order date use for report.")

    def _create_invoices(self, grouped=False, final=False, date=None, picking=False):
        """ Create invoice(s) for the given Sales Order(s).

        :param bool grouped: if True, invoices are grouped by SO id.
            If False, invoices are grouped by keys returned by :meth:`_get_invoice_grouping_keys`
        :param bool final: if True, refunds will be generated if necessary
        :param date: unused parameter
        :returns: created invoices
        :rtype: `account.move` recordset
        :raises: UserError if one of the orders has no invoiceable lines.
        """
        if not self.env['account.move'].check_access_rights('create', False):
            try:
                self.check_access_rights('write')
                self.check_access_rule('write')
            except AccessError:
                return self.env['account.move']

        # 1) Create invoices.
        invoice_vals_list = []
        invoice_item_sequence = 0 # Incremental sequencing to keep the lines order on the invoice.
        for order in self:
            order = order.with_company(order.company_id)

            invoice_vals = order._prepare_invoice()
            _logger.info("----------------------")
            _logger.info(json.dumps(invoice_vals,indent=4,default=str))
            _logger.info("----------------------")
            invoiceable_lines = order._get_invoiceable_lines(final)
            if picking:
                invoiceable_lines = invoiceable_lines.filtered(lambda sol: sol.is_downpayment or sol.id in picking.mapped("move_ids_without_package.sale_line_id.id"))
            if not any(not line.display_type for line in invoiceable_lines):
                continue

            invoice_line_vals = []
            down_payment_section_added = False
            for line in invoiceable_lines:
                # if not down_payment_section_added and line.is_downpayment:
                #     # Create a dedicated section for the down payments
                #     # (put at the end of the invoiceable_lines)
                #     invoice_line_vals.append(
                #         Command.create(
                #             order._prepare_down_payment_section_line(sequence=invoice_item_sequence)
                #         ),
                #     )
                #     down_payment_section_added = True
                #     invoice_item_sequence += 1
                if not picking:
                    invoice_line_vals.append(
                        Command.create(
                            line._prepare_invoice_line(sequence=invoice_item_sequence)
                        ),
                    )
                else:
                    for pick in picking:
                        if line.is_downpayment:
                            invoice_line_vals.append(
                                Command.create(
                                    line._prepare_invoice_line(
                                        picking=pick,
                                        deduct_down_payments=final,
                                        sequence=invoice_item_sequence
                                    )
                                ),
                            )
                            continue

                        if line.id not in pick.mapped("move_ids_without_package.sale_line_id.id"):
                            continue

                        invoice_line_vals.append(
                            Command.create(
                                line._prepare_invoice_line(
                                    picking=pick,
                                    deduct_down_payments=final,
                                    sequence=invoice_item_sequence
                                )
                            ),
                        )

                invoice_item_sequence += 1

            invoice_vals['invoice_line_ids'] += invoice_line_vals
            invoice_vals['picking_ids'] = [(6, 0, picking.ids)]
            invoice_vals_list.append(invoice_vals)
        
        # _logger.info(invoiceable_lines)
        # _logger.info(json.dumps(invoice_vals_list,indent=4, default=str))
        # _logger.info("1234567890")
        # adadasfav
        if not invoice_vals_list and self._context.get('raise_if_nothing_to_invoice', True):
            raise UserError(self._nothing_to_invoice_error_message())

        # 2) Manage 'grouped' parameter: group by (partner_id, currency_id).
        if not grouped:
            new_invoice_vals_list = []
            invoice_grouping_keys = self._get_invoice_grouping_keys()
            invoice_vals_list = sorted(
                invoice_vals_list,
                key=lambda x: [
                    x.get(grouping_key) for grouping_key in invoice_grouping_keys
                ]
            )
            for _grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: [x.get(grouping_key) for grouping_key in invoice_grouping_keys]):
                origins = set()
                payment_refs = set()
                refs = set()
                ref_invoice_vals = None
                for invoice_vals in invoices:
                    if not ref_invoice_vals:
                        ref_invoice_vals = invoice_vals
                    else:
                        ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                    origins.add(invoice_vals['invoice_origin'])
                    payment_refs.add(invoice_vals['payment_reference'])
                    refs.add(invoice_vals['ref'])
                ref_invoice_vals.update({
                    'ref': ', '.join(refs)[:2000],
                    'invoice_origin': ', '.join(origins),
                    'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
                })
                new_invoice_vals_list.append(ref_invoice_vals)
            invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.

        # As part of the invoice creation, we make sure the sequence of multiple SO do not interfere
        # in a single invoice. Example:
        # SO 1:
        # - Section A (sequence: 10)
        # - Product A (sequence: 11)
        # SO 2:
        # - Section B (sequence: 10)
        # - Product B (sequence: 11)
        #
        # If SO 1 & 2 are grouped in the same invoice, the result will be:
        # - Section A (sequence: 10)
        # - Section B (sequence: 10)
        # - Product A (sequence: 11)
        # - Product B (sequence: 11)
        #
        # Resequencing should be safe, however we resequence only if there are less invoices than
        # orders, meaning a grouping might have been done. This could also mean that only a part
        # of the selected SO are invoiceable, but resequencing in this case shouldn't be an issue.
        if len(invoice_vals_list) < len(self):
            SaleOrderLine = self.env['sale.order.line']
            for invoice in invoice_vals_list:
                sequence = 1
                for line in invoice['invoice_line_ids']:
                    line[2]['sequence'] = SaleOrderLine._get_invoice_line_sequence(new=sequence, old=line[2]['sequence'])
                    sequence += 1

        # Manage the creation of invoices in sudo because a salesperson must be able to generate an invoice from a
        # sale order without "billing" access rights. However, he should not be able to create an invoice from scratch.
        moves = self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals_list)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        if final:
            moves.sudo().filtered(lambda m: m.amount_total < 0).action_switch_invoice_into_refund_credit_note()
        for move in moves:
            move.message_post_with_view(
                'mail.message_origin_link',
                values={'self': move, 'origin': move.line_ids.sale_line_ids.order_id},
                subtype_id=self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note'))
        return moves

    # @api.constrains('po_ref')
    def _check_unique_po_ref(self):
        for record in self:
            if self.search_count([('po_ref', '=', record.po_ref), ('id', '!=', record.id)]) > 0:
                raise ValidationError(f"The PO Customer '{record.po_ref}' already exists. Please choose a different PO Customer.")
            
    @api.depends('amount_untaxed')
    def _compute_dpp(self):
        for po in self:
            po.dpp = (11/12) * po.amount_untaxed
    
    @api.onchange('date_order')
    def _onchange_date_order(self):
        for rec in self:
            if rec.date_order:
                rec.order_date = rec.date_order
    
    @api.depends('payment_term_id')
    def _compute_notes(self):
        for rec in self:
            if rec.payment_term_id:
                rec.note = rec.payment_term_id.description

    def compute_global_discount(self):
        context = {
            'default_order_type': 'sale',
            'default_sale_id': self.id,
            'default_untaxed_amount': self.amount_untaxed,
        }

        return {
            'name': "Detail Discount",
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'eran.global.discount.wiz',
            'view_id': self.env.ref('eran_custom.eran_global_discount_view').id,
            'target': 'new',
            'context':context
        }
    
    def name_get(self):
        res = []
        for order in self:
            name = order.name
            if order.partner_id.name:
                name = '%s - %s' % (name, order.po_ref)
            res.append((order.id, name))
        return res
    
    
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('po_ref', operator, name)]
        
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
    
    
    @api.depends('state')
    def _order_sheet_count(self):
      for order in self:
            ks = [('sale_ids', '=', order.id)]
            osl = self.env['eran.order.sheet'].search(ks)
            order.order_sheet_count = len(osl.mapped('id'))
            
    def action_view_order_sheet(self):
        ks = [('sale_ids', '=', self.id)]
        name = 'Order Sheet Customer'
        action_vals = {
            'name': name,
            'domain': ks,
            'view_mode': 'tree,form',
            'res_model': 'eran.order.sheet',
            'type': 'ir.actions.act_window',
            'context': {}
        }
        return action_vals
    
    def _picking_count_delivery_order(self):
      for rec in self:
            domain = [('sale_order_id', '=', rec.id)]
            ids = self.env['stock.picking'].search(domain)
            rec.picking_count_delivery = len(ids.mapped('id'))
            
    def action_view_delivery_order_on_picking(self):
        domain = [('sale_order_id', '=', self.id)]
        name = 'Transfer'
        action_vals = {
            'name': name,
            'domain': domain,
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'type': 'ir.actions.act_window',
            'context': {}
        }
        return action_vals
    
    def action_confirm(self):
        """ Confirm the given quotation(s) and set their confirmation date.

        If the corresponding setting is enabled, also locks the Sale Order.

        :return: True
        :rtype: bool
        :raise: UserError if trying to confirm locked or cancelled SO's
        """
        self._check_unique_po_ref()
        if self._get_forbidden_state_confirm() & set(self.mapped('state')):
            raise UserError(_(
                "It is not allowed to confirm an order in the following states: %s",
                ", ".join(self._get_forbidden_state_confirm()),
            ))

        self.order_line._validate_analytic_distribution()

        for order in self:
            if order.partner_id in order.message_partner_ids:
                continue
            order.message_subscribe([order.partner_id.id])

        self.write(self._prepare_confirmation_values())

        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)

        # self.with_context(context)._action_confirm()
        if self.env.user.has_group('sale.group_auto_done_setting'):
            self.action_done()

        return True
    
    @api.depends('order_line')
    def _compute_all_create_order_sheet(self):
        for rec in self:
            qty_order = sum([x.product_uom_qty for x in rec.order_line])
            qty_order_sheet = sum([x.order_sheet_line_qty for x in rec.order_line])
            rec.check_osheet_so = True if qty_order == qty_order_sheet else False
    
    def set_value_inv_picking(self):
        domain = [('sale_order_id', '=', self.id)]
        related_invoices = self.env['stock.picking'].search(domain)
        
        for picking in related_invoices.filtered(lambda x: x.state != 'cancel' and x.is_return == False):
            _logger.info('pickingsss: %s', picking.move_ids_without_package)
            inv_state_list = []
            for sm in picking.move_ids_without_package:
                quantity = sm.quantity_done - sm.qty_return

                if sm.qty_invoice_remind >= quantity and sm.qty_return < sm.quantity_done:
                    inv_state_list.append('invoiced')
                elif sm.qty_invoice_remind < quantity and sm.qty_return < sm.quantity_done:
                    inv_state_list.append('partial_invoice')
                elif sm.qty_return >= sm.quantity_done or sm.qty_invoice_remind == 0 and sm.qty_return > 0:
                    inv_state_list.append('nothing_to_invoice')
                elif sm.qty_invoice_remind == 0 and sm.qty_return == 0:
                    inv_state_list.append('2binvoiced')
            
            if '2binvoiced' in inv_state_list and 'partial_invoice' not in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': '2binvoiced'})
                
            elif '2binvoiced' in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' not in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' not in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})
            
            elif '2binvoiced' not in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})
            
            elif '2binvoiced' not in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})
            
            elif '2binvoiced' not in inv_state_list and 'partial_invoice' not in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'nothing_to_invoice'})

            elif '2binvoiced' not in inv_state_list and 'partial_invoice'  not in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' in inv_state_list:
                picking.sudo().write({'invoice_state': 'invoiced'})
            
            elif '2binvoiced' not in inv_state_list and 'partial_invoice'  not in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' in inv_state_list:
                picking.sudo().write({'invoice_state': 'invoiced'})

            else:
                picking.sudo().write({'invoice_state': '2binvoiced'})

        for picking in self.picking_ids.filtered(lambda x: x.state != 'cancel' and x.is_return != False):
            picking.sudo().write({'invoice_state': '2binvoiced'})

        for picking in self.picking_ids.filtered(lambda x: x.state == 'cancel'):
            picking.sudo().write({'invoice_state': '2binvoiced'})
                
    
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    order_sheet_line_qty = fields.Float(string="OS Line Qty", compute="_compute_order_sheet_line_qty", store=True, copy=False)
    discount_line = fields.Boolean(string="Is Discount Line", default=False)
    product_name = fields.Char('Product Name', related="product_id.name")
    product_code = fields.Char('Product Code', related="product_id.default_code")
    po_ref = fields.Char(related='order_id.po_ref')
    date_order = fields.Datetime(related='order_id.date_order')
    balance_quantity = fields.Float('Balance Qty', compute="_compute_balance_quantity")
    quantity_delivery = fields.Float('Quantity Delivery', compute="_compute_quantity_delivery")
    delivery_amount = fields.Monetary('Amount Delivery', compute="_compute_quantity_delivery" )
    is_downpayment_created = fields.Boolean(string="Down Payment Created", copy=False, help="Technical field used to prevent the creation of multiple down payments.")

    @api.depends('order_id', 'product_id')
    def _compute_order_sheet_line_qty(self):
        for line in self:
            line.order_sheet_line_qty = 0
            if line.order_id:
                order_sheet_lines = line.env['eran.order.sheet.line'].search([('sale_line_id', '=', line.id), ('state', '!=', 'cancel')])
                line.order_sheet_line_qty = sum([x.qty_receipt for x in order_sheet_lines])

                line.order_id._compute_all_create_order_sheet()

    @api.depends('po_ref', 'balance_quantity')
    def _compute_balance_quantity(self):
        for rec in self:
            rec._compute_order_sheet_line_qty()
            rec.balance_quantity = rec.product_uom_qty - rec.qty_delivered

        
    def _prepare_invoice_line(self, picking=False, deduct_down_payments=False, **optional_values):
        """Prepare the values to create the new invoice line for a sales order line.

        :param optional_values: any parameter that should be added to the returned invoice line
        :rtype: dict
        """
        self.ensure_one()
        if not picking:
            qty_to_invoice = self.qty_to_invoice
        if picking and not self.is_downpayment:
            qty_to_invoice = 0
            for pick in picking:
                for mv in pick.move_ids_without_package.filtered(lambda x: x.sale_line_id.id == self.id):
                    qty_to_invoice += (mv.quantity_done - mv.qty_invoiced - mv.qty_return)
        else:
            qty_to_invoice = self.qty_to_invoice
        # qty_to_invoice = self.quantity_delivery - self.qty_invoiced
        _logger.info("seijgsl")
        # asefhesif
        res = {
            'display_type': self.display_type or 'product',
            'sequence': self.sequence,
            'name': self.name if not self.is_downpayment else f'Down Payment: {self.order_id.name}',
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': qty_to_invoice,
            'discount': self.discount,
            'price_unit': self.price_unit,
            'tax_ids': [Command.set(self.tax_id.ids)],
            'analytic_distribution': self.analytic_distribution,
            'sale_line_ids': [Command.link(self.id)],
            'is_downpayment': self.is_downpayment,
            'sale_line_id': self.id,
            'picking_id': picking.id if picking else False,
            'stock_move_id': picking.move_ids_without_package.filtered(lambda x: x.sale_line_id.id == self.id).id if picking else False,
        }
        analytic_account_id = self.order_id.analytic_account_id.id
        if analytic_account_id and not self.display_type:
            res['analytic_distribution'] = res['analytic_distribution'] or {}
            if self.analytic_distribution:
                res['analytic_distribution'][analytic_account_id] = self.analytic_distribution.get(analytic_account_id, 0) + 100
            else:
                res['analytic_distribution'][analytic_account_id] = 100
        if optional_values:
            res.update(optional_values)
        if self.display_type:
            res['account_id'] = False
        if deduct_down_payments and self.is_downpayment:
            self.write({'is_downpayment_created': True})
        return res

    def _compute_quantity_delivery(self):
        for rec in self:
            total_delivery = 0
            stock_move_ids = self.env['stock.move'].search([('sale_line_id', '=', rec.id)])

            total_delivery = sum(stock_move_ids.filtered(lambda pick: pick.picking_type_id.code == 'outgoing').mapped('quantity_done'))
            total_return = sum(stock_move_ids.filtered(lambda pick: pick.picking_type_id.code == 'incoming').mapped('quantity_done'))
            delivery_amount = (total_delivery - total_return) * rec.price_unit
            
            rec.quantity_delivery = total_delivery - total_return
            rec.delivery_amount = delivery_amount
            
class EranSalesSequenceSetting(models.Model):
    _name = 'eran.sales.sequence.setting'
    _description = 'Eran Sales Sequence Setting'
    