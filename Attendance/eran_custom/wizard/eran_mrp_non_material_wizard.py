from odoo import models, fields, api, _
from datetime import datetime
from odoo.exceptions import UserError, ValidationError
import mimetypes
import base64
import itertools
import logging
_logger = logging.getLogger(__name__)


class EranMRPNonMaterialWizard(models.TransientModel):
    _name = 'eran.mrp.non.material.wizard'
    _description = 'DSN MRP Non Material Wizard'


    def get_line(self):
        context = self._context
        active_ids = context.get('active_ids')
        datas = []
        for line in active_ids:
            mrp = self.env['eran.mrp.non.material'].browse(line)
            value = {
                'mrp_non_material_id': mrp.id,
                'product_id': mrp.product_id.id,
                'product_qty': mrp.quantity_to_buy - mrp.quantity_pr,
                'uom_id': mrp.uom_id.id,
            }
            datas.append((0,0, value))

        return datas
    
    def get_type(self):
        context = self._context
        active_ids = context.get('active_ids')
        type = False
        for line in active_ids:
            mrp = self.env['eran.mrp.non.material'].browse(line)
            type = mrp.type
        return type

    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], default=get_type)
    line_ids = fields.One2many('eran.mrp.non.material.line.wizard', 'wizard_id', default=get_line)


    def create_purchase_request(self):
        line_ids = []
        origin_list = []
        for line in self.line_ids:
            product_qty = line.product_qty
            if self.type == 'forecast_order':
                product_qty = line.product_qty*(line.allocation_percentage_mrp/100)
            value = {
                'product_id': line.product_id.id,
                'product_qty': product_qty,
                'product_uom_id': line.uom_id.id,
                'mrp_non_material_id': line.mrp_non_material_id.id,
            }
            line_ids.append((0,0, value))
            origin_list.append(line.mrp_non_material_id.name)

        if self.line_ids:
            picking_type = self.env['stock.picking.type'].sudo().search([
                ('company_id', '=', self.env.company.id),
                ('code', '=', 'incoming')], limit=1)
            
            pr = self.env['purchase.request'].sudo().create({
                'requested_by': self.env.user.id,
                'company_id': self.env.company.id,
                'date_start': fields.date.today(),
                'picking_type_id': picking_type.id or False,
                'line_ids': line_ids,
                'origin': ', '.join(origin_list)})

            for pr_line in pr.line_ids:
                pr_line.name = str(pr.name) + ' ' + str(pr_line.product_id.display_name)


class EranMRPLineWizard(models.TransientModel):
    _name = 'eran.mrp.non.material.line.wizard'
    _description = 'DSN MRP Non Material Line Wizard'


    wizard_id = fields.Many2one('eran.mrp.non.material.wizard', ondelete='cascade')
    mrp_non_material_id = fields.Many2one('eran.mrp.non.material', string='MRP Non Material')
    product_id = fields.Many2one('product.product', string='Product')
    product_qty = fields.Float('Quantity')
    uom_id = fields.Many2one('uom.uom', string='UoM')
    allocation_percentage_mrp = fields.Float(related='product_id.allocation_percentage_mrp', string='Allocation Percentage MRP(%)')