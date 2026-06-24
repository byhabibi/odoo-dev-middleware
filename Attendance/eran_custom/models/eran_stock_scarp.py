from odoo import _, api, fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    product_category_group_id = fields.Many2one(string='Product Category Group', related='product_id.category_group_id', store=True)
    effective_date = fields.Date(string='Effective Date', default=fields.Date.context_today, required=True)