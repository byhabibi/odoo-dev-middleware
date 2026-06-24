# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import Warning,UserError
from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)

class stock_invoice_onshipping(models.TransientModel):
    _inherit = "stock.invoice.onshipping"

    def create_invoice(self):
        res = super(stock_invoice_onshipping, self).create_invoice()
        picking_obj = self.env['stock.picking'].browse(self._context.get('active_ids'))
        picking_obj.write({'invoice_id': res[0]})
        return res
