from odoo import api, fields, models, _
    
class EranReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'
    
    return_type = fields.Selection(string='Return Type', selection=[('claim', 'Claim'), ('complaint', 'Complaint')])
    
    def _prepare_picking_default_values(self):
        vals = {
            'move_ids': [],
            'picking_type_id': self.picking_id.picking_type_id.return_picking_type_id.id or self.picking_id.picking_type_id.id,
            'state': 'draft',
            'return_type': self.return_type,
            'origin': _("Return of %s") % self.picking_id.name,
            'reference_return_id': self.picking_id.id,
        }
        # TestPickShip.test_mto_moves_return, TestPickShip.test_mto_moves_return_extra,
        # TestPickShip.test_pick_pack_ship_return, TestPickShip.test_pick_ship_return, TestPickShip.test_return_lot
        if self.picking_id.location_dest_id:
            vals['location_id'] = self.picking_id.location_dest_id.id
        if self.location_id:
            vals['location_dest_id'] = self.location_id.id
        return vals
    

    def _prepare_move_default_values(self, return_line, new_picking):
        vals = super(EranReturnPicking, self)._prepare_move_default_values(return_line, new_picking)
        vals['product_uom_qty'] = return_line.quantity
        return vals