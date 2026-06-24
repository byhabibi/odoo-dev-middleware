from odoo import api, fields, models, _

class EranStockPickingRefund(models.TransientModel):
    _name = 'eran.stock.picking.refund'
    _description = 'Replacement Shipment'
    
    picking_id = fields.Many2one('stock.picking')
    
    def create_refund_product(self):
        vals = self.env['stock.picking'].create({
            'state': 'draft',
            'partner_id': self.picking_id.partner_id.id,
            'picking_type_id': 2,
            'location_id': 8,
            'location_dest_id': 5,  
            'origin': _("Replacement Shipment of %s") % self.picking_id.name,
            'move_ids_without_package':[(0, 0, {
                'state': 'draft',
                'location_id': 8,
                'location_dest_id': 5,
                'product_id':line.product_id.id,
                'name': line.name,
                'product_uom_qty':line.product_uom_qty,
                'product_uom':line.product_uom,
            }) for line in self.picking_id.move_ids_without_package]
        })
        
        return {
                'type': 'ir.actions.act_window',
                'view_id': self.env.ref('stock.view_picking_form').id,
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'res_id': vals.id,
                }