from odoo import api, fields, models, _
import statistics
import logging
_logger = logging.getLogger(__name__)

class EranCostVendorPricelist(models.Model):
    _name = 'eran.cost.vendor.pricelist'
    _description = 'Eran Cost Vendor Pricelist'

    name = fields.Char('Name', default='New')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    # partner_id = fields.Many2one('res.partner', string='Partner')
    pricelist_line_ids = fields.One2many('eran.cost.vendor.pricelist.line', 'pricelist_id', string='Pricelist Line')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirm'),
    ], string='State', default='draft')

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code('eran.cost.vendor.pricelist')
        res = super(EranCostVendorPricelist, self).create(vals)
        return res

    def action_confirm(self):
        self.state = 'confirm'

    def action_reset(self):
        self.state = 'reset'

    def action_compute(self):
        # purchases = self.env['purchase.order'].search([('partner_id','=',self.partner_id.id),('state','in',['done','purchase']),('date_approve','>=',self.start_date),('date_approve','<=',self.end_date)])
        purchases = self.env['purchase.order'].search([('state','in',['done','purchase']),('date_approve','>=',self.start_date),('date_approve','<=',self.end_date)])
        purchase_lines = purchases.mapped("order_line")
        products = purchases.mapped("order_line.product_id")
        line_list = [(5,0)]
        for product in products:
            # product_price_unit_list = purchase_lines.filtered(lambda line: line.product_id.id == product.id).mapped("price_unit")
            # avg_price = statistics.mean(product_price_unit_list)

            product_price_unit_list = purchase_lines.filtered(lambda line: line.product_id.id == product.id)
            avg_price = 0
            product_price_unit_list_datas = []
            for line in product_price_unit_list:
                if float(line.price_unit) not in product_price_unit_list_datas:
                    product_price_unit_list_datas.append(float(line.price_unit))
            if len(product_price_unit_list_datas) > 0:
                avg_price = sum(product_price_unit_list_datas) / len(product_price_unit_list_datas)
            line_list.append((0,0, {
                'product_id': product.id,
                'name': product.name,
                'avg_price': avg_price,
                'currency_id': self.env.company.currency_id.id,
            }))
        self.pricelist_line_ids = line_list

class EranCostVendorPricelistLine(models.Model):
    _name = 'eran.cost.vendor.pricelist.line'
    _description = 'Eran Cost Vendor Pricelist Line'

    pricelist_id = fields.Many2one('eran.cost.vendor.pricelist', string='Pricelist', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')
    name = fields.Char('Description')
    avg_price = fields.Monetary('Average Price')
    currency_id = fields.Many2one('res.currency', string='Currency')