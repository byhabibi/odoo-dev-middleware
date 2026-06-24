from odoo import api, fields, models, _

class LabelSTOWiz(models.TransientModel):
    _name = 'eran.label.sto.wiz'
    _description = 'Label STO'
    
    product_id = fields.Many2many('product.product', string='Product')
    location_id = fields.Many2many('stock.location', string="Location", domain="[('usage', '=', 'internal')]")
    product_category_id = fields.Many2many('product.category', string='Category')
    count_date = fields.Datetime(string="Count Date")
    counter_id = fields.Many2one('hr.employee', string="Counter")
    

    def action_print_label_sto(self):
        
        self.ensure_one()
        data = {'ids': self.env['stock.quant'].sudo().search([])}
        res = self.read()
        res = res and res[0] or {}
        data.update({'form': res})

        return self.env.ref('eran_custom.eran_action_report_stock_opname').report_action(self, data=data)
    