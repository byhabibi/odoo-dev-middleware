from odoo import api, fields, models, _
from datetime import datetime, timedelta
import logging
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    date_order = fields.Datetime('Order Deadline', required=True, index=True, tracking=True, copy=False, default=fields.Datetime.now,
        help="Depicts the date within which the Quotation should be confirmed and converted into a purchase order.")
    date_planned = fields.Datetime(
        string='Expected Arrival', index=True, copy=False, compute='_compute_date_planned', tracking=True, store=True, readonly=False,
        help="Delivery date promised by vendor. This date is used to determine expected arrival of products.")
    order_sheet_count = fields.Integer('History', compute='_order_sheet_count')
    subcon_product = fields.Boolean('Is Subcont ?', compute='_depends_subcon_product')
    order_sheet_qty = fields.Float('OS Qty', compute="_get_order_sheet_qty", store=True)
    check_osv = fields.Boolean('Order Sheet All', compute='_compute_all_create_osv', store=True, copy=False)
    picking_count_delivery = fields.Integer('Delivery', compute='_picking_count_delivery_order')
    invoice_count = fields.Integer(string="Invoice Count", compute='_get_invoiced_count')
    purchase_type = fields.Selection([
        ('project', 'Project'),
        ('reguler', 'Reguler'),
        ('import', 'Import'),
        ('raw_material', 'Raw Material'),
        ('non_operational', 'Non Operational'),
        ('component', 'Component'),
        ('sparepart_tools', 'Sparepart & Tools'),
        ('purchase_part', 'Purchase Part'),
        ('subcont', 'Subcont'),
        ('factory_supply_consumable', 'Factory Supply & Consumables'),
        ('dieshop', 'Dieshop '),
        ('metrans', 'Metrans'),
        ('shipment', 'Shipment'),
        ('others', 'Others'),
    ], string='Purchase Type')
    categ_id = fields.Many2one(
        comodel_name='product.category',
        string="Purchase Category",
        )
    lock_state = fields.Selection([
        ('lock', 'Lock'),
        ('unlock', 'Unlock'),
    ], string='Lock State', compute="_get_lock_state", store=True)

    dpp = fields.Float(string="DPP", compute='_compute_dpp', store=True)


    def action_update_qty_received(self):
        for rec in self:
            for line in rec.order_line:
                line._compute_qty_received_method()
                line._compute_qty_received()
                line._compute_total_qty_recv()
                line._compute_received_amt()
                line._compute_total_balance_qty()
                line._compute_balance_qty()
                
    @api.depends('state')
    def _get_lock_state(self):
        for po in self:
            if po.state == 'purchase':
                po.lock_state = 'unlock'
            elif po.state == 'done':
                po.lock_state = 'lock'
            else:
                po.lock_state = False

    # notes = fields.Html('Terms and Conditions', compute="_compute_notes")

    @api.depends('amount_untaxed')
    def _compute_dpp(self):
        for po in self:
            po.dpp = (11/12) * po.amount_untaxed

    def print_delivery_schedule(self):
        # action = self.env['ir.actions.actions']._for_xml_id('eran_custom.action_report_delivery_schedule')
        delivery_schedule = self.env['eran.delivery.schedule.report'].create({
            'purchase_id': self.id,
        })
        action = self.env['ir.actions.actions']._for_xml_id('eran_custom.eran_delivery_schedule_report_action')
        action['res_id'] = delivery_schedule.id
        return action

    def button_done(self):
        if not self.filtered(lambda po: po.state == 'purchase'):
            return
        for purchase in self.filtered(lambda po: po.state == 'purchase'):
            res = super(PurchaseOrder, purchase).button_done()
        return res

    def button_unlock(self):
        if not self.filtered(lambda po: po.state == 'done'):
            return
        for purchase in self.filtered(lambda po: po.state == 'done'):
            res = super(PurchaseOrder, purchase).button_unlock()
        return res

    # @api.depends('payment_term_id')
    # def _compute_notes(self):
    #     for rec in self:
    #         if rec.payment_term_id:
    #             rec.notes = rec.payment_term_id.description
    #         else:
    #             rec.notes = False

    def _picking_count_delivery_order(self):
      for rec in self:
            domain = [('purchase_order_id', '=', rec.id)]
            ids = self.env['stock.picking'].search(domain)
            rec.picking_count_delivery = len(ids.mapped('id'))

    @api.depends('order_line.invoice_lines')
    def _get_invoiced_count(self):
        for order in self:
            invoices = order.order_line.invoice_lines.move_id.filtered(lambda r: r.move_type in ('in_invoice', 'in_refund'))
            order.invoice_ids = invoices
            order.invoice_count = len(invoices)

    def compute_global_discount(self):
        context = {
            'default_order_type': 'purchase',
            'default_purchase_id': self.id,
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

    @api.depends('order_line')
    def _depends_subcon_product(self):
        for rec in self:
            vendor_list = []
            res = []
            for line in rec.order_line:
                bom_ids = line.env['mrp.bom'].sudo().search([('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)])
                for bom in bom_ids:
                    res.append(bom.type)
                    for vendor in bom.subcontractor_ids:
                        vendor_list.append(vendor.id)
            
            if len(res) != 0 and vendor_list != 0:
                if ('subcontract' in res) and (rec.partner_id.id in vendor_list):
                    rec.subcon_product = True
                else:
                    rec.subcon_product = False
            else:
                rec.subcon_product = False

    def _get_order_sheet(self):
        ks = [('purchase_ids', 'in', self.ids), ('state','=','done')]
        osl = self.env['eran.order.sheet'].search(ks)
        return osl

    @api.depends('state')
    def _order_sheet_count(self):
        for order in self:
            ks = [('purchase_ids', '=', order.id)]
            osl = self.env['eran.order.sheet'].search(ks)
            order.order_sheet_count = len(osl.mapped('id'))
            
            
    def _get_order_sheet_qty(self):
        for rec in self:
            res = 0
            qty_order = sum([x.product_qty for x in rec.order_line])
            os_ids = rec.env['eran.order.sheet'].search([('purchase_id.id', '=', rec.id), ('state', '!=', 'cancel')])
            for os in os_ids:
                res += os.order_qty_sheet
                
            rec.order_sheet_qty = res
        

    def action_view_order_sheet(self):
        ks = [('purchase_ids', '=', self.id)]
        name = 'Order Sheet Vendor'
        action_vals = {
            'name': name,
            'domain': ks,
            'view_mode': 'tree,form',
            'res_model': 'eran.order.sheet',
            'type': 'ir.actions.act_window',
            'context': {}
        }
        return action_vals
    
    
    @api.depends('order_line')
    def _compute_all_create_osv(self):
        for rec in self:
            qty_order = sum([x.product_qty for x in rec.order_line])
            qty_order_sheet = sum([x.order_sheet_line_qty for x in rec.order_line])
            rec.check_osv = True if qty_order == qty_order_sheet else False

    @api.depends('order_line.taxes_id', 'order_line.price_subtotal', 'amount_total', 'amount_untaxed')
    def  _compute_tax_totals(self):
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            order.tax_totals = self.env['account.tax']._prepare_tax_totals(
                [x._convert_to_tax_base_line_dict() for x in order_lines],
                order.currency_id,
            )
            _logger.info(order.tax_totals)

    def eran_button_approve(self, force=False):
        self = self.filtered(lambda order: order._approval_allowed())
        self.write({'state': 'purchase', 'date_approve': fields.Datetime.now()})
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        return {}

    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent', 'to approve']:
                continue
            order.order_line._validate_analytic_distribution()
            order._add_supplier_to_product()
            # Deal with double validation process
            if order._approval_allowed():
                if self.subcon_product:
                    # order.button_approve()
                    order.write({'state': 'purchase'})
                else:
                    # order.eran_button_approve()
                    order.write({'state': 'purchase'})
            else:
                order.write({'state': 'purchase'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True

    def get_signatures(self):
        # get approver's signature for PO report
        approvers = list()
        if self.approval_line_ids:
            for i in self.approval_line_ids:
                approvers.append([i.user_id.name,i.signature,i.is_approved])
            return approvers[:2]
        
        return []
    

    def get_down_payment(self):
        product_down_payment_ids = self.env['res.config.settings'].sudo().search([], order='id desc', limit=1).po_deposit_default_product_id.id
        return product_down_payment_ids
    
    def set_value_inv_picking(self):
        related_bills = self.invoice_ids
        
        for picking in self.picking_ids.filtered(lambda x: x.state != 'cancel' and x.id in related_bills.mapped('picking_ids').ids):
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

                _logger.info('inv_state_listsssssssss = %s' % inv_state_list)
            
            if '2binvoiced' in inv_state_list and 'partial_invoice' not in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': '2binvoiced'})
                
            elif '2binvoiced' in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' in inv_state_list and 'invoiced' in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' not in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' not in inv_state_list:
                picking.sudo().write({'invoice_state': 'partial_invoice'})

            elif '2binvoiced' not in inv_state_list and 'partial_invoice' in inv_state_list and 'nothing_to_invoice' not in inv_state_list and 'invoiced' in inv_state_list:
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

        for picking in self.picking_ids.filtered(lambda x: x.state != 'cancel' and x.id not in related_bills.mapped('picking_ids').ids):
            picking.sudo().write({'invoice_state': '2binvoiced'})

        for picking in self.picking_ids.filtered(lambda x: x.state == 'cancel'):
            picking.sudo().write({'invoice_state': '2binvoiced'})

    def _create_invoices(self, final=False, picking=False, deduct_down_payments=False):
        """
        Custom create invoices for purchase orders, with optional down payment deduction
        :param final: bool, whether this is the final invoice
        :param picking: stock.picking, optional related picking
        :param deduct_down_payments: bool, whether to deduct down payments
        """
        invoices = self.env['account.move']

        for order in self:
            if all(line.qty_invoiced >= line.product_qty for line in order.order_line.filtered(lambda x: x.is_downpayment == False)):
                raise UserError(_("The purchase order %s is already fully invoiced.") % order.name)

            invoice_vals = order._prepare_invoice()
            if len(picking) > 1:
                invoice_vals.update({'picking_ids': [(6, 0, picking.ids)]})
            else:
                invoice_vals.update({'picking_ids': [(4, picking.id)]})

            invoice = self.env['account.move'].create(invoice_vals)

            if picking:
                stock_moves = picking.mapped('move_ids_without_package').filtered(lambda m: m.quantity_done > 0 and (m.quantity_done - m.qty_return) - m.qty_invoiced > 0)
                for move in stock_moves:
                    qty = (move.quantity_done - move.qty_return) - move.qty_invoiced
                    price_unit = move.purchase_line_id.price_unit
                    account_id = move.purchase_line_id.product_id.property_account_expense_id.id \
                        or move.purchase_line_id.product_id.categ_id.property_account_expense_categ_id.id

                    line_vals = {
                        'move_id': invoice.id,
                        'stock_move_id': move.id,
                        'name': move.name or move.product_id.display_name,
                        'product_id': move.product_id.id,
                        'quantity': qty,
                        'price_unit': price_unit,
                        'tax_ids': [(6, 0,  move.purchase_line_id.taxes_id.ids)],
                        'account_id': account_id,
                        'purchase_line_id': move.purchase_line_id.id,
                    }
                    self.env['account.move.line'].create(line_vals)

            else:
                for order_line in order.order_line.filtered(lambda l: not l.is_downpayment):
                    line_vals = order_line._prepare_account_move_line(invoice)
                    self.env['account.move.line'].create(line_vals)


            if picking:
                invoice.write({
                    'invoice_origin': '%s / %s' % (order.name, ', '.join(picking.mapped('name')))
                })

            if final:
                downpayment_lines = order.order_line.filtered(lambda l: l.is_downpayment and not l.is_downpayment_created)
                for dp_line in downpayment_lines:
                    account_id = dp_line.product_id.property_account_expense_id.id \
                        or dp_line.product_id.categ_id.property_account_expense_categ_id.id

                    self.env['account.move.line'].create({
                        'move_id': invoice.id,
                        'name': _(f"Down Payment: {order.name}, {', '.join(picking.mapped('name')) if picking else ''}"),
                        'quantity': 1,
                        'price_unit': -dp_line.price_unit,
                        'account_id': account_id,
                        'product_id': dp_line.product_id.id,
                        'purchase_line_id': dp_line.id,
                    })

                    dp_line.write({'is_downpayment_created': True})

            invoices += invoice

        return invoices
        
    
class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    partner_id = fields.Many2one(
        related='order_id.partner_id',
        string="Vendor")
    po_number = fields.Char('Order No.', related="order_id.name")
    confirmation_date = fields.Datetime(status="Order Date", related="order_id.date_approve")
    receipt_status = fields.Selection(related='order_id.receipt_status', string='Receipt Status')
    category_ids = fields.Many2many(related='order_id.partner_id.category_id', string="Vendor Tags")
    # total_qty_recv: total qty done item dari seluruh receipt PO terkait 
    total_qty_recv = fields.Float(string="Total Qty Reveiced", compute="_compute_total_qty_recv")
    total_balance_qty = fields.Float(string="Total Balance Qty", compute="_compute_total_balance_qty", store=True)
    total_balance_qty_convert = fields.Float(string="Total Balance Qty Convert", compute="_compute_total_balance_qty_convert", store=True)
    received_amt = fields.Float(string="Recv. Amt ", compute="_compute_received_amt", store=True)
    balance_qty = fields.Float(string="Balance Qty", compute="_compute_balance_qty", store=True)
    discount = fields.Float(string="Discount (%)", digits='Discount', store=True, readonly=False, precompute=True)
    request_line_qty = fields.Float(string="Request Line Qty", compute="_compute_request_line_qty")
    
    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request id", copy=False)
    qty_edit = fields.Float(string="Update Qty", default=1)
    additional_uom_id = fields.Many2one(related="product_id.additional_uom_id", string='Alternative Uom')
    # ..... code yang saya ubah ......
    # additional_qty = fields.Float(string="Alternative Qty", compute="_compute_additional_qty", store=True)
    additional_qty = fields.Float(string="Alternative Qty")
    # .................................
    order_sheet_line_qty = fields.Float(string="OS Line Qty", compute="_compute_order_sheet_line_qty", store=True, copy=False)
    discount_line = fields.Boolean(string="Is Discount Line", default=False)
    outstanding_po = fields.Float(string='Outstanding PO', compute='compute_outstanding', store=True)
    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)

    internal_transfer = fields.Char(string="Internal Transfer", related='product_id.default_code', store=True)
    product_name = fields.Char(string="Product", related='product_id.name', store=True)
    resuply_qty = fields.Float(string="Resupply Qty", compute="_compute_resuply_qty")
    balance_qty_subcont = fields.Float(string="Balance Qty Subcont", compute="_compute_resuply_qty", store=True)

    date_order = fields.Datetime(string='Order Date', related='order_id.date_order', store=True)
    purchase_type = fields.Selection([
        ('project', 'Project'),
        ('reguler', 'Reguler'),
        ('import', 'Import'),
        ('raw_material', 'Raw Material'),
        ('non_operational', 'Non Operational'),
        ('component', 'Component'),
        ('sparepart_tools', 'Sparepart & Tools'),
        ('purchase_part', 'Purchase Part'),
        ('subcont', 'Subcont'),
        ('factory_supply_consumable', 'Factory Supply & Consumables'),
        ('dieshop', 'Dieshop '),
        ('metrans', 'Metrans'),
        ('shipment', 'Shipment'),
        ('others', 'Others'),
    ], string='Purchase Type', related='order_id.purchase_type', store=True)
    is_downpayment_created = fields.Boolean(string="Down Payment Created", copy=False, help="Technical field used to prevent the creation of multiple down payments.")
    received_convert = fields.Float(string="Received Convert", compute="_compute_received_convert", store=True)
    origin = fields.Char(string='Source Document', related='order_id.origin', store=True)
    request_date = fields.Date(string='Request Date',related="purchase_request_id.date_start", store=True)

    @api.depends('product_qty', 'qty_received', 'additional_qty')
    def _compute_received_convert(self):
        for line in self:
            if line.product_qty:
                line.received_convert = (line.additional_qty / line.product_qty) * line.qty_received
            else:
                line.received_convert = 0.0

    #............. code yang saya ubah .............
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'product_id' in vals:
                product = self.env['product.product'].browse(vals['product_id'])

                if product:
                    vals.setdefault('additional_uom_id', product.additional_uom_id.id if product.additional_uom_id else False)

                    if 'product_qty' in vals and product.additional_uom_id:
                        alt_qty = product.additional_qty or 0
                        vals.setdefault('additional_qty', alt_qty * vals['product_qty'])
        return super().create(vals_list)
    
    def write(self, vals):
        if 'additional_uom_id' in vals:
            for line in self:
                if line.create_date and line.create_date < fields.Datetime.now() - timedelta(days=1):
                    raise ValidationError("Alternative UoM cannot be changed after PO line is created.")
        return super().write(vals)
    # ..............................................

    def _compute_resuply_qty(self):
        for rec in self:
            resupply_qty = 0
            moves_subcontracted = rec.move_ids.filtered(lambda m: m.is_subcontract)
            bom_ids = rec.env['mrp.bom'].sudo().search([('product_tmpl_id', '=', rec.product_id.product_tmpl_id.id), ('type', '=', 'subcontract')])
            bom_line_ids = rec.env['mrp.bom.line'].sudo().search([('bom_id', 'in', [x.id for x in bom_ids])])
                        
            if moves_subcontracted:
                subcontracted_productions = moves_subcontracted.move_orig_ids.production_id
                if subcontracted_productions:
                    picking_resupply_ids = subcontracted_productions.picking_ids
                    if picking_resupply_ids:
                        move_resupply_ids = rec.env['stock.move'].sudo().search([
                            ('picking_id', 'in', [x.id for x in picking_resupply_ids]),
                            ('product_id', 'in', [x.product_id.id for x in bom_line_ids]),
                            ('state', 'not in', ['cancel']),
                        ])

                        for move in move_resupply_ids:
                            resupply_qty += move.product_uom_qty

            if not resupply_qty:
                resupply_qty = 0

            balance_qty = 0
            if resupply_qty != 0:
                balance_qty = rec.product_qty - resupply_qty
                
            rec.resuply_qty = resupply_qty
            rec.balance_qty_subcont = balance_qty

    @api.depends('order_id', 'product_id')
    def _compute_order_sheet_line_qty(self):
        for line in self:
            line.order_sheet_line_qty = 0
            if line.order_id:
                order_sheet_lines = line.env['eran.order.sheet.line'].search([('purchase_line_id', '=', line.id), ('state', '!=', 'cancel')])
                line.order_sheet_line_qty = sum([x.qty_receipt for x in order_sheet_lines])

                line.order_id._compute_all_create_osv()

    @api.depends('product_qty','qty_received')
    def compute_outstanding(self):
        for line in self:
            line._compute_order_sheet_line_qty()
            line._compute_resuply_qty()
            line._compute_balance_qty()
            line._compute_received_amt()
            line._compute_total_balance_qty()

            line.outstanding_po = line.product_qty - line.qty_received
            if line.outstanding_po < 0:
                line.outstanding_po = 0

    @api.ondelete(at_uninstall=False)
    def _unlink_except_purchase_or_done(self):
        for line in self:
            if line.order_id.state in ['done', 'purchase']:
                if not line.discount_line:
                    state_description = {state_desc[0]: state_desc[1] for state_desc in self._fields['state']._description_selection(self.env)}
                    raise UserError(_('Cannot delete a purchase order line which is in state \'%s\'.') % (state_description.get(line.state),))
            
    @api.depends('product_id', 'product_qty', 'qty_edit')
    def _compute_additional_qty(self):
        for rec in self:
            rec._compute_order_sheet_line_qty()
            rec.additional_qty = rec.product_id.additional_qty * rec.product_qty
    
    @api.onchange('qty_edit')
    def onchange_qty_edit(self):
        for rec in self:
            if rec.purchase_request_id:
                if rec.qty_edit > rec.purchase_request_id.qty_request:
                    raise ValidationError(_("The %s purchase quantity cannot be greater than the PR quantity [%s]." %(rec.product_id.name, int(rec.purchase_request_id.qty_request))))
                else:
                    rec.product_qty = rec.qty_edit
            else:
                rec.product_qty = rec.qty_edit
            
            # date = rec.order_id.date_order
            # val = 1
            # temp = []
            # round_vals = []
            # round_ids = rec.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', rec.product_id.product_tmpl_id.id), ('partner_id.id', '=', rec.partner_id.id), ('date_start', '<=', date), ('date_end', '>=',date), ('state', '=', 'done')])
            # for ids in round_ids:
            #     if ids.rounding_value!=0 and rec.product_qty < ids.rounding_value:
            #         raise ValidationError(_("The %s purchase quantity cannot be Less than the Rounding Value [%s]." %(rec.product_id.name, int(ids.rounding_value))))
                
            #     round_vals.append(ids.rounding_value)
            #     while val <= rec.product_qty:
            #         if (val % ids.rounding_value) == 0:
            #             temp.append(val)
            #         val += 1
            # if len(temp)!=0:
            #     if rec.product_qty in temp:
            #         pass
            #     else:
            #         raise ValidationError(_("The quantity of Purchase %s must be a multiple of either %s." %(rec.product_id.name, round_vals)))
                

    def _convert_to_tax_base_line_dict(self):
        """ Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=self.product_id,
            taxes=self.taxes_id,
            price_unit=self.price_unit,
            quantity=self.product_qty,
            discount=self.discount,
            price_subtotal=self.price_subtotal,
        )

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount')
    def _compute_amount(self):
        for line in self:
            line._compute_order_sheet_line_qty()
            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
            totals = list(tax_results['totals'].values())[0]
            amount_untaxed = totals['amount_untaxed']
            amount_tax = totals['amount_tax']

            line.update({
                'price_subtotal': amount_untaxed,
                'price_tax': amount_tax,
                'price_total': amount_untaxed + amount_tax,
            })

    # - vendor group -> field tags 
    @api.depends('order_id.picking_ids', 'product_id', 'qty_received') # add trigger qty_received
    def _compute_total_qty_recv(self):
        quantity_done = 0
        for receipt_line in self.order_id.picking_ids:
            for move_line in receipt_line.move_ids_without_package:
                if move_line.product_id == self.product_id:
                    quantity_done += move_line.quantity_done
        self.total_qty_recv = quantity_done

    @api.depends('order_id.picking_ids', 'product_id', 'qty_received') # add trigger qty_received
    def _compute_total_balance_qty(self):
        for line in self:
            line.total_balance_qty = line.product_qty - line.qty_received

    @api.depends('order_id.picking_ids', 'additional_qty', 'received_convert')
    def _compute_total_balance_qty_convert(self):
        for line in self:
            line.total_balance_qty_convert = line.additional_qty - line.received_convert

    @api.depends('order_id.picking_ids', 'product_id', 'qty_received') # add trigger qty_received
    def _compute_received_amt(self):
        for line in self:
            # line.received_amt = line.price_unit * line.qty_received
            if line.product_qty:
                line.received_amt = line.price_total / line.product_qty * line.qty_received

    def call_compute_received_amt(self):
        for line in self:
            if line.product_qty:
                line.received_amt = line.price_total / line.product_qty * line.qty_received

    @api.depends('order_id.picking_ids', 'product_id', 'qty_received') # add trigger qty_received
    def _compute_balance_qty(self):
        for line in self:
            line.balance_qty = line.total_balance_qty * line.price_unit

    @api.depends('product_qty')
    def _compute_request_line_qty(self):
        for rec in self:
            total_qty_pr = 0
            total_qty_po = 0 
            for line in self.purchase_request_lines:
                if line.product_id == rec.product_id:
                    total_qty_pr += line.product_qty
                    total_qty_po += line.purchased_qty
        
            rec.request_line_qty = total_qty_pr

    @api.onchange('product_qty', 'product_id')
    def onchange_qty_alternative(self):
        for rec in self:
            if rec.product_id:
                rec.additional_qty = rec.product_qty * rec.product_id.additional_qty
                
    def _prepare_account_move_line(self, move=False):
        self.ensure_one()
        aml_currency = move and move.currency_id or self.currency_id
        date = move and move.date or fields.Date.today()
        return {
            'display_type': self.display_type or 'product',
            'name': '%s: %s' % (self.order_id.name, self.name),
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': self.qty_to_invoice,
            'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id, date, round=False),
            'tax_ids': [(6, 0, self.taxes_id.ids)],
            'analytic_distribution': self.analytic_distribution,
            'purchase_line_id': self.id,
            'discount':self.discount,
        }
            