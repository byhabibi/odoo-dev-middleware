# -*- coding: utf-8 -*-
import logging

from datetime import datetime
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)


class EranMaterialRequestWiz(models.TransientModel):
    _name = "eran.material.request.wiz"
    _description = 'Material Request Additional'

    name = fields.Char("MR Number", default="New")
    request_date = fields.Datetime(string="Request Date", default=lambda self: fields.Datetime.now())
    requester_id = fields.Many2one("hr.employee",
        string="Requester",
        help="Operator MO",
        domain="")
    
    source_location_id = fields.Many2one("stock.location", 
        string="Source Location",
        help="Components Locations MO")
    
    reason = fields.Text("Reason")
    material_request_line_ids = fields.One2many('eran.material.request.line.wiz', 
                                                "material_request_id", 
                                                string="Material Request Line")
    production_id = fields.Many2one("mrp.production",
        string="Production",
        help="MRP Production",
        domain="")
    
    move_raw_ids = fields.One2many(related="production_id.move_raw_ids", string='Move Raw')
    bom_qty = fields.Float(related="production_id.bom_id.product_qty")
    
    balance_check = fields.Boolean(string="Balance", help="Check Qty Material Request from transfer and mo", compute="_check_balance_material_request", store=True)

    def _check_balance_material_request(self):
        for rec in self:
            picking_ids = rec.env['stock.picking'].search([('manufacture_production_id', '=', rec.production_id.id), ('state', '!=', 'cancel')])
            material_request_qty = sum([line.product_uom_qty for line in picking_ids.move_ids_without_package])
            components_qty = sum([line.product_uom_qty for line in rec.move_raw_ids])
            material_wiz_request_qty = sum([line.quantity for line in rec.material_request_line_ids])
            
            rec.balance_check = True if (material_request_qty + material_wiz_request_qty) > components_qty else False

    @api.onchange('name')
    def _onchange_material_request_line_ids(self):
        for rec in self:
            for move in rec.move_raw_ids:
                if move.component_type != 'tooling':
                    factor = move.product_uom.factor if move.product_uom.factor != 0 and move.product_id.uom_id.id !=  move.product_uom.id else 1
                    self.env['eran.material.request.line.wiz'].create(
                        {
                            'material_request_id': rec.id,
                            'product_id': move.product_id.id,
                            'quantity': move.product_uom_qty * rec.bom_qty,
                            'uom_id': move.product_uom.id,
                            'product_qty': (move.product_uom_qty * rec.bom_qty) / factor,

                        }
                    )
            rec._check_balance_material_request()
           

    def action_confirm(self):
        pick_type = self.env['stock.picking.type'].search([('is_request_material', '!=', False)], limit=1)

        line_ids = []
        for move_line in self.material_request_line_ids:
            qty = move_line.uom_id._compute_quantity(move_line.quantity, move_line.product_id.uom_id)
            value = {
                'name': move_line.product_id.name,
                # 'picking_id': m_id.id,
                'product_id': move_line.product_id.id,
                'quantity_done': qty,
                'product_uom_qty': qty,
                'location_id': self.source_location_id.id,
                'location_dest_id': self.production_id.location_src_id.id,
            }
            line_ids.append((0,0, value))
        
        m_id = self.env['stock.picking'].create({
            'name': self.env['ir.sequence'].next_by_code('eran.material.request'),
            'scheduled_date': datetime.now(),
            'requester': self.requester_id.id,
            'location_id': self.source_location_id.id,
            'location_dest_id': self.production_id.location_src_id.id,
            'picking_type_id': pick_type.id,
            'manufacture_production_id': self.production_id.id,
            'origin': self.production_id.name,
            'note': self.reason,
            'shift': self.production_id.shift_id.id,
            'move_ids_without_package': line_ids
        })
        
        m_id.action_confirm()
        for move in m_id.move_ids_without_package:
            move.production_id = False
            

    def action_discard(self):
        return

class EranMaterialRequestLineWiz(models.TransientModel):
    _name = "eran.material.request.line.wiz"
    _description = "Material Reuqest Additional Line"

    material_request_id = fields.Many2one("eran.material.request.wiz", string="Material Request")
    product_id = fields.Many2one("product.product", string="Product")
    quantity = fields.Float(string="Qty")
    uom_id = fields.Many2one('uom.uom', string="UoM")

    product_qty = fields.Float(string="Qty", help="From qty for product UoM")
    product_uom_id = fields.Many2one('uom.uom', string="UoM", related='product_id.uom_id', store=True)

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        for rec in self:
            factor = rec.product_id.uom_id.factor if rec.product_id.uom_id.factor != 0 else 1
            rec.quantity = rec.product_qty * factor
    
    @api.onchange('quantity')
    def _onchange_quantity(self):
        for rec in self:
            move_ids = rec.env['stock.move'].search([('picking_id.manufacture_production_id', '=', rec.material_request_id.production_id.id), ('picking_id.state', '!=', 'cancel')])
            material_request_qty = sum([move.product_uom_qty for move in move_ids])
            components_qty = sum([line.product_uom_qty for line in rec.material_request_id.move_raw_ids if line.product_id.id == rec.product_id.id])
            
            if (material_request_qty + rec.quantity) > components_qty:
                return {
                    'warning': {
                        'title': 'Warning!',
                        'message': 'The quantity of material requested is more than the compenent material. Do you still want to continue?'}
                }


