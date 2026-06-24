from odoo import api, fields, models, _
from odoo.tools.misc import formatLang
class EranGlobalDiscountWiz(models.Model):
    _name = 'eran.global.discount.wiz'
    _description = 'Global Discount Wizard'

    untaxed_amount = fields.Float(string="Untaxed Amount", readonly=True,)

    purchase_id = fields.Many2one('purchase.order', string="Purchase ID")
    sale_id = fields.Many2one('sale.order', string="Sale ID")

    order_type = fields.Char("Order Type")
    discount_type = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('percentage', 'Percentage'),
    ], string='Discount Type', default="fixed")
    
    fixed_amount = fields.Float(string="Fixed Amount")
    discount = fields.Float(string="Discount(%)")
    discount_amount = fields.Float(string="Discount Amt.", )

    @api.onchange('discount')
    def _onchange_discount_amount(self):
        self.discount_amount = self.discount * self.untaxed_amount / 100

    def btn_confirm(self):
        orders = self.purchase_id.order_line if self.order_type == 'purchase' else self.sale_id.order_line
        for rec in orders:
            if self.discount_type == 'fixed':
                if self.untaxed_amount:
                    rec.write({
                        "discount": self.fixed_amount / self.untaxed_amount * 100
                    })
            else:
                rec.write({
                    "discount": self.discount
                })

        # delete note and add new note
        if self.order_type == 'purchase':
            self.env['purchase.order.line'].search([('display_type', '=', 'line_note'), ('order_id', '=', self.purchase_id.id)]).unlink()
            self.env['purchase.order.line'].create({
                'sequence': max(self.env['purchase.order.line'].search([('order_id', '=', self.purchase_id.id)]).mapped('sequence')) + 1,
                'discount_line': True,
                'order_id': self.purchase_id.id,
                'display_type': 'line_note',
                'product_qty': 0,
                'name': "Discount sebesar " + formatLang(self.env, self.discount * self.untaxed_amount / 100 if self.untaxed_amount \
                                   else 0, currency_obj=self.purchase_id.currency_id) if self.discount_type == 'percentage' else \
                                    "Discount sebesar " +  formatLang(self.env, self.fixed_amount, currency_obj=self.purchase_id.currency_id),
            })
        else:
            self.env['sale.order.line'].search([('display_type', '=', 'line_note'), ('order_id', '=', self.sale_id.id)]).unlink()
            self.env['sale.order.line'].create({
                'sequence': max(self.env['sale.order.line'].search([('order_id', '=', self.sale_id.id)]).mapped('sequence')) + 1,
                'discount_line': True,
                'order_id': self.sale_id.id,
                'display_type': 'line_note',
                'product_uom_qty': 0,
                'name': "Discount sebesar " + formatLang(self.env, self.discount * self.untaxed_amount / 100, currency_obj=self.sale_id.currency_id) \
                    if self.discount_type == 'percentage' else "Discount sebesar " +  formatLang(self.env, self.fixed_amount, currency_obj=self.sale_id.currency_id),
            })
            
        
