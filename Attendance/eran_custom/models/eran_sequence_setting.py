from odoo import fields, api, models, _
from odoo.exceptions import UserError, ValidationError

class DSNSettingSalesSequence(models.Model):
    _inherit = 'dsn.sales.sequence.setting'

    type = fields.Selection([
        ('sale_rfq', 'Sale RFQ'),
        ('quotation', 'Quotation'),
        ('sale_order', 'Sale Order'),
        ('loi', 'LOI'),
        ('forecast_order', 'Forecast Order'),
        ('fix_order', 'Fix Order'),
    ], tracking=True)

class DSNSettingMrpSequence(models.Model):
    _inherit = 'dsn.mrp.production.sequence.setting'

    type = fields.Selection([
        ('manufactur_order', 'Manufacturing Order'),
        ('demand_order', 'Demand Order'),
        ('mps', 'MPS'),
        ('mrp', 'MRP'),
        ('demand_forecast', 'Demand Forecast'),
        ('mrp_non_material', 'MRP Non Material'),
    ], tracking=True)
    
class DSNSettingInventorySequence(models.Model):
    _inherit = 'dsn.inventory.sequence.setting'

    name_operations = fields.Char(string='Operations Name', help="Used to create a name for the transfer operations type.")
    type_operations = fields.Selection([
        ('incoming', 'Receipt'),
        ('outgoing', 'Delivery'),
        ('internal', 'Internal Transfer'),
        ('mrp_operation', 'Manufacturing'),
    ], tracking=True)
    type = fields.Selection([
        ('order_sheet_customer', 'Order Sheet Customer'),
        ('order_sheet_vendor', 'Order Sheet Vendor'),
        ('landed_cost', 'Landed Cost'),
        ('stock_opname', 'Stock Opname'),
        ('scrap', 'Scrap'),
        ('transfer', 'Transfer'),
        ('batch_normal', 'Batch Normal'),
        ('batch_subcont', 'Batch Subcont'),
    ], tracking=True)
    
    def create_operations_types_transfer(self, ref_sequence=None):
        values = {
            'name': self.name_operations,
            'code': self.type_operations,
            'sequence_code': self.code,
            'sequence_id': ref_sequence
        }
        self.env['stock.picking.type'].create(values)
    
    def create_sequence(self):
        name = None
        suffix = '/' + str(self.code) + '/' + '%(month)s' + '/' + '%(y)s'
        if self.type != 'transfer':
            name = str(self.type)
        else:
            name = str(self.type) + ' - ' + self.code
            
        values = {
            'name' : name,
            'code' : str(self.type) + ' - ' + self.code,
            'suffix' : suffix,
            'number_next' : 1,
            'number_increment' : 1,
            'use_date_range' : True,
            'padding' : 5,
            'company_id' : self.company_id.id
        }
        sequence = self.env['ir.sequence'].create(values)
        self.write({'sequence_id': sequence.id, 'state': 'confirm'})
        if self.type == 'transfer':
            self.create_operations_types_transfer(sequence.id)
            
    def update_sequence_code(self):
        if self.sequence_id:
            suffix = '/' + str(self.code) + '/' + '%(month)s' + '/' + '%(y)s'
            val = {
                'code' : str(self.type) + ' - ' + self.code,
                'suffix' : suffix
                }
            
            self.sequence_id.update(val)
            
            if self.type =='Transfer':
                operation_type = self.env['stock.picking.type'].sudo().search([('sequence_id', '=', self.sequence_id.id)], limit=1)
                if operation_type:
                    val = {'sequence_code': self.code}
                    operation_type.update(val)
                    
    
    @api.constrains('type','company_id')
    def _constrains_double_data(self):
        if self.type != 'transfer':
            datas = self.search([('type', '=', self.type),('company_id', '=', self.company_id.id)])
            if len(datas) > 1:
                raise UserError(_('Data %s with %s Already Exist!', self.type, self.company_id.display_name))
    
