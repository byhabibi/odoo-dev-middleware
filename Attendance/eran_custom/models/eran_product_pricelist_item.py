from odoo import api, fields, models, _

class EranProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"
    _order = "id asc"