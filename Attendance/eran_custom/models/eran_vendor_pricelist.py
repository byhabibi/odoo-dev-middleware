
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models, _
import logging
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'
    _description = "Vendor Pricelist"

    rounding_value = fields.Integer(string='Rounding Value', default = 0)
    