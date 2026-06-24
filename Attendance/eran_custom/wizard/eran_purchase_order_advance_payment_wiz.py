import time
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class PurchaseOrderAdvancePayment(models.TransientModel):
    _inherit = 'purchase.order.advance.payment'


    @api.model
    def _default_deposit_account_id(self):
        product_id = self.env['ir.config_parameter'].sudo().get_param('purchase_down_payment.po_deposit_default_product_id')
        product =  self.env['product.product'].browse(int(product_id)).exists()
        return product._get_product_accounts()['expense']
    

    deposit_account_id = fields.Many2one(
        comodel_name='account.account',
        string="Expense Account",
        domain=[('deprecated', '=', False)],
        help="Account used for deposits",
        default=_default_deposit_account_id)
    



    def create_advance_bill(self):
        """Function for creating purchase down payment bill"""
        purchase_order = self.env['purchase.order'].browse(
            self._context.get('active_ids', []))

        if self.advance_payment_method == 'delivered':
            if self.deduct_down_payments:
                purchase_order._deduct_payment(final=self.deduct_down_payments)
            else:
                purchase_order.action_create_invoice()
        else:
            if not self.product_id:
                # vals = self._prepare_down_payment_product_values()
                # self.product_id = self.env['product.product'].create(vals)
                # self.env['ir.config_parameter'].sudo().set_param(
                #     'purchase_down_payment.po_deposit_default_product_id',
                #     self.product_id.id)
                raise ValidationError(_('The product in down payment cannot be empty.'))
            
            self.product_id.property_account_expense_id = self.deposit_account_id.id

            purchase_line_obj = self.env['purchase.order.line']
            for order in purchase_order:
                amount, name = self._get_advance_details(order)
                if self.product_id.invoice_policy != 'order':
                    raise UserError(
                        _('The product used to invoice a down payment should have an invoice policy set to "Ordered quantities". Please update your deposit product to be able to create a deposit invoice.'))
                if self.product_id.type != 'service':
                    raise UserError(
                        _("The product used to invoice a down payment should be of type 'Service'. Please use another product or update this product."))
                taxes = self.product_id.supplier_taxes_id.filtered(
                    lambda
                        r: not order.company_id or r.company_id == order.company_id)
                tax_ids = order.fiscal_position_id.map_tax(taxes).ids

                po_line_values = self._prepare_po_line(order,
                                                       tax_ids, amount)
                po_line = purchase_line_obj.create(po_line_values)
                self._create_bill(order, po_line, amount)
                if self._context.get('open_invoices', False):
                    return purchase_order.action_view_invoice()
            return {'type': 'ir.actions.act_window_close'}

        if self._context.get('open_invoices', False):
            return purchase_order.action_view_invoice()
        return {'type': 'ir.actions.act_window_close'}