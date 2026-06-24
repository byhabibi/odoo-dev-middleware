from odoo import api, fields, models, _
from odoo.tools import is_html_empty
from odoo.exceptions import ValidationError, UserError
import json
import logging
_logger = logging.getLogger(__name__)
import re

class AccountMove(models.Model):
    _inherit = 'account.move'

    name = fields.Char(required=False,default='/')
    tax_invoice_date = fields.Datetime(string="Tax Invoice Date")
    invoice_exchange_date = fields.Datetime(string="Exchange Date of Invoice")
    no_faktur_pajak = fields.Char('No. Faktur Pajak')
    note = fields.Text('Note')
    dpp = fields.Float(string="DPP", compute='_compute_dpp', store=True)
    l10n_id_tax_number = fields.Char(string="Tax Number", copy=False, size=20)
    dpp_print = fields.Boolean('DPP Printout')
    po_customers = fields.Char('PO Customer', compute="_compute_po_customers", store=True)
    picking_ids = fields.Many2many('stock.picking', string="Picking References", 
        domain="""[
            ('partner_id', '=', partner_id), 
            ('invoice_state', 'in', move_type in ['out_refund', 'in_refund'] and ['invoiced'] or ['2binvoiced', 'partial_invoice']),
            ('state', '=', 'done'),
            ('picking_type_code', 'in', 
                move_type in ['out_invoice', 'out_refund'] and ['outgoing'] or 
                move_type in ['in_invoice', 'in_refund'] and ['incoming'] or [])
        ]""")

    # tax_details_per_record = fields.Binary(
    #     string='Tax Details per Record',
    #     compute='_compute_tax_details_per_record',
    #     help='Berisi detail perhitungan pajak untuk setiap record tax yang ada di invoice lines'
    # )

    pph22_amount = fields.Float(string="PPh 22", compute='_compute_tax_details_per_record')
    pph23_amount = fields.Float(string="PPh 23", compute='_compute_tax_details_per_record')
    ppn_amount = fields.Float(string="PPn", compute='_compute_tax_details_per_record')
    discount = fields.Float(string="Discount", compute='_compute_tax_details_per_record')

    @api.onchange('picking_ids')
    def _onchange_fill_data_from_picking_ids(self):
        for move in self:
            removed_picking_list = [x for x in move._origin.picking_ids.ids if x not in move.picking_ids.ids]
            
            if removed_picking_list:
                removed_pickings = self.env['stock.picking'].browse(removed_picking_list)
                stock_move_ids = removed_pickings.mapped('move_ids_without_package').ids
                move.invoice_line_ids = [(2, line.id) for line in move.invoice_line_ids 
                                       if line.stock_move_id and line.stock_move_id.id in stock_move_ids]
                                       
                removed_pickings.write({'invoice_state': '2binvoiced'})
                return
            
            new_picking_list = [x for x in move.picking_ids.ids if x not in move._origin.picking_ids.ids]
            if not new_picking_list:
                return
            
            context = dict(self.env.context)
            context.update({'skip_vat_validation': True})
            move = move.with_context(context)
            
            vals = []
            new_pickings = self.env['stock.picking'].browse(new_picking_list)
            processed_products = set()
            
            for picking in new_pickings:
                for stock_move in picking.move_ids_without_package:
                    product_key = (stock_move.product_id.id, stock_move.id)
                    if product_key in processed_products:
                        continue
                        
                    existing_line = False
                    for line in move.invoice_line_ids:
                        if line.product_id and line.product_id.id == stock_move.product_id.id and line.stock_move_id.id == stock_move.id:
                            existing_line = True
                            break
                    
                    if existing_line:
                        continue
                    
                    processed_products.add(product_key)
                    
                    if move.move_type == 'out_invoice':
                        account = stock_move.product_id.property_account_income_id or stock_move.product_id.categ_id.property_account_income_categ_id
                    elif move.move_type == 'in_invoice':
                        account = stock_move.product_id.property_account_expense_id or stock_move.product_id.categ_id.property_account_expense_categ_id
                    else:
                        continue
                    
                    # Pastikan account valid
                    if not account:
                        _logger.warning("No account found for product %s", stock_move.product_id.name)
                        continue
                    
                    # Dapatkan harga unit
                    taxes = move.env['account.tax']
                    price_unit = 0.0
                    if move.move_type in ('out_invoice', 'out_refund') and stock_move.sale_line_id:
                        sale_line = stock_move.sale_line_id
                        taxes = sale_line.tax_id
                        price_unit = sale_line.price_unit
                    elif move.move_type in ('in_invoice', 'in_refund') and stock_move.purchase_line_id:
                        purchase_line = stock_move.purchase_line_id
                        taxes = purchase_line.taxes_id
                        price_unit = purchase_line.price_unit
                    
                    # Dapatkan pajak
                    if not taxes:
                        taxes = stock_move.product_id.taxes_id if move.move_type in ('out_invoice', 'out_refund') else stock_move.product_id.supplier_taxes_id
                    if not price_unit:
                        price_unit = stock_move.product_id.standard_price if move.move_type in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund') else stock_move.product_id.list_price
                    
                    quantity = stock_move.quantity_done
                    line_subtotal = quantity * price_unit

                    # Tambahkan line baru
                    vals.append((0, 0, {
                        'move_id': move.id,
                        'display_type': 'product',
                        'account_id': account.id,
                        'partner_id': move.partner_id.id,
                        'name': stock_move.product_id.name,
                        'currency_id': move.currency_id.id,
                        'product_id': stock_move.product_id.id,
                        'product_uom_id': stock_move.product_uom.id,
                        'quantity': stock_move.quantity_done,
                        'price_unit': price_unit,
                        'price_subtotal': line_subtotal,
                        'tax_ids': [(6, 0, taxes.ids)] if taxes else False,
                        'discount': stock_move.purchase_line_id.discount if stock_move.purchase_line_id else 0.0,
                        'purchase_line_id': stock_move.purchase_line_id.id if stock_move.purchase_line_id else False,
                        'sale_line_ids': [(6, 0, stock_move.sale_line_id.ids)] if stock_move.sale_line_id else [(6, 0, [])],
                        'stock_move_id': stock_move.id,
                        'picking_id': picking.id,
                    }))
                
                if vals:
                    move.invoice_line_ids = vals
            move.set_value_inv_picking()

    @api.model
    def create(self, vals):
        res = super(AccountMove, self).create(vals)
        if 'picking_ids' in vals:
            res.set_value_inv_picking()
        return res

    def write(self, vals):
        """Override write untuk memastikan tidak ada duplikasi lines"""
        res = super(AccountMove, self).write(vals)
        
        if 'picking_ids' in vals:
            for rec in self:
                lines_to_remove = []
                processed_lines = set()
                
                for line in rec.invoice_line_ids:
                    if line.display_type == 'product' and not line.product_id:
                        lines_to_remove.append(line.id)
                    elif line.display_type == 'product' and line.product_id and line.stock_move_id:
                        line_key = (line.product_id.id, line.stock_move_id.id)
                        if line_key in processed_lines:
                            lines_to_remove.append(line.id)
                        else:
                            processed_lines.add(line_key)
                
                if lines_to_remove:
                    rec.write({'invoice_line_ids': [(2, line_id) for line_id in lines_to_remove]})

                rec.set_value_inv_picking()
        return res

    def unlink(self):
        for rec in self:
            if rec.state != 'cancel':
                if rec.move_type == 'out_invoice':
                    raise UserError(_('You cannot delete an invoice which is not in \'Cancelled\' state.'))
                
                if rec.move_type == 'in_invoice':
                    raise UserError(_('You cannot delete an bill which is not in \'Cancelled\' state.'))
                    
            return super(AccountMove, self).unlink()

    @api.depends('display_type', 'stock_move_id')
    def _compute_quantity(self):
        for line in self:
            line.quantity = 1 if line.display_type == 'product' and not line.stock_move_id else (
                line.stock_move_id.quantity_done if line.stock_move_id else False
            )

    def get_faktur_pajak_grouped_line(self):
        vals = []
        grouped_line = self.env['account.move.line']
        no = 1
        dp_product_id = self.get_downpayment_product()
        product_lines = self.invoice_line_ids.filtered(lambda l: l.display_type not in ['line_section','line_note'] and l.product_id.id != dp_product_id and l.product_id.is_global_discount == False).sorted(key=lambda x:x.product_id.name)
        for line in product_lines:
            to_be_grouped = product_lines.filtered(lambda li: li.product_id.id == line.product_id.id and li.price_unit == line.price_unit and  li.id != line.id)
            grouped_line |= to_be_grouped
            if line not in grouped_line:
                vals.append({
                    'nomor': no,
                    'product_id': line.product_id.name,
                    'price_unit': line.price_unit,
                    'quantity': line.quantity + sum(to_be_grouped.mapped("quantity")),
                    'product_uom_id': line.product_uom_id.name,
                    'price_subtotal': line.price_subtotal + sum(to_be_grouped.mapped("price_subtotal")),
                })
        res = json.dumps(vals)
        return res

    @api.depends('invoice_line_ids.tax_ids', 'invoice_line_ids.price_subtotal')
    def _compute_tax_details_per_record(self):
        for move in self:
            tax_details = {}
            pph22_total = 0.0
            pph23_total = 0.0
            ppn_total = 0.0
            discount = 0.0
            for line in move.invoice_line_ids:
                price_subtotal = line.price_subtotal
                discount += (line.quantity * line.price_unit) * (line.discount / 100.0)
                for tax in line.tax_ids:
                    tax_amount = price_subtotal * (tax.amount / 100.0)
                    if '22' in tax.tax_group_id.name:
                        pph22_total += tax_amount
                    if '23' in tax.tax_group_id.name:
                        pph23_total += tax_amount
                    if 'PPN' in tax.tax_group_id.name.upper():
                        ppn_total += tax_amount
                    if tax.id not in tax_details:
                        tax_details[tax.id] = {
                            'name': tax.name,
                            'tax_group_name': tax.tax_group_id.name,
                            'amount': tax_amount,
                            'rate': tax.amount
                        }
                    else:
                        tax_details[tax.id]['amount'] += tax_amount
            move.pph22_amount = abs(pph22_total)
            move.pph23_amount = abs(pph23_total)
            move.ppn_amount = abs(ppn_total)
            move.discount = discount


    @api.depends('sale_order_count')
    def _compute_po_customers(self):
        for move in self:
            po_ref = []
            for rec in move.line_ids.sale_line_ids:
                if rec.order_id.po_ref:
                    po_ref.append(rec.order_id.po_ref)
            po_ref = ", ".join(list(set(po_ref))) if po_ref else ""
            move.po_customers = po_ref
    

    @api.onchange('l10n_id_tax_number')
    def _onchange_l10n_id_tax_number(self):
        for record in self:
            if record.l10n_id_tax_number and record.move_type not in self.get_purchase_types():
                pass

    def check_tax_number(self):
        datas = self.search([('l10n_id_tax_number', '=', self.l10n_id_tax_number),('company_id', '=', self.company_id.id)])
        if len(datas) > 1 and self.l10n_id_tax_number:
            raise UserError(_('Tax Number %s Already Exist!', self.l10n_id_tax_number))

    @api.constrains('l10n_id_tax_number')
    def _check_tax_number(self):
        try:
            l10n_id_tax_number = int(self.l10n_id_tax_number)
        except:
            raise ValidationError(_('Please enter numeric value only in Tax Number.'))
        self.check_tax_number()

    @api.constrains('l10n_id_tax_number')
    def _constrains_l10n_id_tax_number(self):
        for record in self.filtered('l10n_id_tax_number'):
            if record.l10n_id_tax_number != re.sub(r'\D', '', record.l10n_id_tax_number):
                record.l10n_id_tax_number = re.sub(r'\D', '', record.l10n_id_tax_number)
            if len(record.l10n_id_tax_number) < 16:
                raise UserError(_('A tax number should have 16 digits or more.'))
            elif record.l10n_id_tax_number[:2] not in dict(self._fields['l10n_id_kode_transaksi'].selection).keys():
                raise UserError(_('A tax number must begin by a valid Kode Transaksi'))
            elif record.l10n_id_tax_number[2] not in ('0', '1'):
                raise UserError(_('The third digit of a tax number must be 0 or 1'))

    def group_invoice_based_po(self, records):
        records = records.sorted(key=lambda x:x.product_id.name)
        data, blacklist = [], []
        for list in records:
            if list.id in blacklist:
                continue
            data.append(list)
            if len(records.filtered(lambda rec: rec.product_id.name == list.product_id.name)) > 1:
                for i, p in enumerate(records.filtered(lambda rec: rec.product_id.name == list.product_id.name )):
                    if list.sale_line_id.order_id.po_ref == p.sale_line_id.order_id.po_ref:
                        data.append(p)
                        blacklist.append(p.id)
        return set(data)

    def set_value_inv_picking(self):
        # related_bills = self.invoice_ids
        
        for picking in self.picking_ids.filtered(lambda x: x.state != 'cancel'):
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
                else:
                    inv_state_list.append('2binvoiced')

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

        # for picking in self.picking_ids.filtered(lambda x: x.state != 'cancel' and x.id not in related_bills.mapped('picking_ids').ids):
        #     picking.sudo().write({'invoice_state': '2binvoiced'})

        for picking in self.picking_ids.filtered(lambda x: x.state == 'cancel'):
            picking.sudo().write({'invoice_state': '2binvoiced'})
    
    def invoice_all_cancel(self):
        for picking in self.picking_ids.filtered(lambda x: x.state != 'cancel'):
            qty_all_invoice = 0
            for sm in picking.move_ids_without_package:
                qty_all_invoice += sm.qty_invoiced
            
            if qty_all_invoice == 0:
                picking.sudo().write({'invoice_state': '2binvoiced'})



    def action_post(self):
        res = super(AccountMove, self).action_post()

        self.set_value_inv_picking()

        if sum(self.env['l10n_id_efaktur.efaktur.range'].search([]).mapped('available')) <= 10:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'title': _('Warning!'),
                    'message': _("Available e-faktur is equal to or less than 10."),
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window_close'
                    },
                }
            }
        return res

    def button_cancel(self):
        res = super(AccountMove, self).button_cancel()
        self.invoice_all_cancel()
        return res

    def button_draft(self):
        res = super(AccountMove, self).button_draft()
        self.set_value_inv_picking()
        return res
    
    @api.depends('amount_untaxed')
    def _compute_dpp(self):
        for po in self:
            po.dpp = (11/12) * po.amount_untaxed
    
    @api.depends('move_type', 'partner_id', 'company_id', 'invoice_payment_term_id')
    def _compute_narration(self):
        """ 
        jika default invoice term telah diatur maka gunakan nilai default tersebut,
        namun jika belum gunakan description pada payment term
        """
        use_invoice_terms = self.env['ir.config_parameter'].sudo().get_param('account.use_invoice_terms')
        for move in self:
            if not move.is_sale_document(include_receipts=True):
                continue
            if not use_invoice_terms:
                move.narration = move.invoice_payment_term_id.description
            else:
                lang = move.partner_id.lang or self.env.user.lang
                if not move.company_id.terms_type == 'html':
                    narration = move.company_id.with_context(lang=lang).invoice_terms if not is_html_empty(move.company_id.invoice_terms) else ''
                else:
                    baseurl = self.env.company.get_base_url() + '/terms'
                    context = {'lang': lang}
                    narration = _('Terms & Conditions: %s', baseurl)
                    del context
                move.narration = narration or False

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res["note"] = 'Mohon di "FAX" setelah ditanda tangani (8671150)'
        return res

    @api.onchange('invoice_payment_term_id')
    def _onchange_fill_description_invoice_payment_term_id(self):
        for record in self:
            if record.invoice_payment_term_id:
                record.narration = record.invoice_payment_term_id.description

    def get_downpayment_product(self):
        sys_param = self.env['ir.config_parameter'].sudo().get_param('sale.default_deposit_product_id')
        dp_product_id = int(sys_param) if sys_param else 0
        return dp_product_id

    def eran_get_faktur_pajak_data_reports(self):
        down_payment = discount = 0
        tax_groups = []
        dp_product_id = self.get_downpayment_product()

        for line in self.invoice_line_ids.filtered(lambda l: l.display_type not in ['line_section','line_note']):
            if line.product_id.id == dp_product_id:
                down_payment += line.price_unit
            else:
                discount += line.price_unit * line.quantity * line.discount / 100
        for group in self.tax_totals['groups_by_subtotal']['Untaxed Amount']:
            tax_groups.append((group['tax_group_name'],group['tax_group_amount']))
        data = {
            'discount': discount,
            'tax_groups': tax_groups,
            'down_payment':down_payment,
        }
        res = json.dumps(data)
        return res


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    stock_move_id = fields.Many2one('stock.move', string="Stock Move")
    sale_line_ids = fields.Many2many(
        'sale.order.line',
        'sale_order_line_invoice_rel',
        'invoice_line_id', 'order_line_id',
        string='Sales Order Lines', copy=False)
    picking_id = fields.Many2one('stock.picking', string='Picking')
    po_ref = fields.Char(string="PO Customer", related='picking_id.po_ref', store=True)
    picking_dn_supplier = fields.Char(string="DN Supplier", compute="_compute_picking_info", store=True)
    picking_purchase_ref = fields.Many2one(comodel_name='purchase.order', string="Purchase Reference", compute="_compute_picking_info", store=True)
    # ........... code baru ..............
    alternative_quantity = fields.Float('Alternative Quantity', compute="_get_alternative_quantity", inverse="_inverse_alternative_quantity", store=True)
    alternative_uom_id = fields.Many2one(related="product_id.additional_uom_id", string='Alternative Uom')
    additional_qty = fields.Float(string="Alternative UoM", help="Alternative UoM for product", related='product_id.additional_qty')

    
    @api.depends('quantity')
    def _get_alternative_quantity(self):
        for rec in self:
            rec.alternative_quantity = rec.quantity * rec.product_id.additional_qty if rec.product_id.additional_qty else 0

    # @api.onchange('alternative_quantity')
    # def _inverse_alternative_quantity(self):
    #     for rec in self:
    #         is_rounded = rec.product_id.uom_id.is_rounded
    #         if rec.additional_qty > 0:
    #             rec.quantity = rec.alternative_quantity / rec.additional_qty if is_rounded != True else round(rec.alternative_quantity / rec.additional_qty)
    #         else:
    #             rec.quantity = rec.alternative_quantity

    @api.onchange('alternative_quantity')
    def _inverse_alternative_quantity(self):
        for rec in self:
            if rec.additional_qty > 0:
                raw_quantity = rec.alternative_quantity / rec.additional_qty
                rec.quantity = float(round(raw_quantity)) if raw_quantity % 1 != 0 else raw_quantity
            else:
                rec.quantity = 0.0
    # .........................

    @api.depends('stock_move_id', 'stock_move_id.picking_id')
    def _compute_picking_info(self):
        for line in self:
            picking = line.stock_move_id.picking_id
            line.picking_dn_supplier = picking.dn_supplier if picking else False
            line.picking_purchase_ref = picking.purchase_ref_id if picking else False


    def write(self, vals):
        res = super(AccountMoveLine, self).write(vals)
        if 'quantity' in vals:
            for line in self.filtered(lambda l: l.purchase_line_id):
                line.purchase_line_id.order_id.set_value_inv_picking()

            for line in self.filtered(lambda l: l.sale_line_id):
                line.sale_line_id.order_id.set_value_inv_picking()   

        return res
    
