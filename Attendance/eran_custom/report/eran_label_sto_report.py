from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class EranLabelStoReport(models.AbstractModel):
    _name = 'report.eran_custom.eran_label_sto_report'
    _description = 'Eran Label Sto Report'
    
    # def _get_columns(self, counter, count_date):
    #     res =[]
    #     res.append([counter, count_date])
    #     return res
        
    @api.model
    def _get_report_values(self, docids, data=None):
        report_name = 'eran_custom.eran_label_sto_report'
        report = self.env['ir.actions.report']._get_report_from_name(report_name)
        
        domain = []
        
        product_id = data['form']['product_id']
        location_id = data['form']['location_id']
        category = data['form']['product_category_id']
        count_date = data['form']['count_date']
        counter = data['form']['counter_id']
        
        if product_id:
            domain += [('product_id.id', '=', product_id)]
            
        if location_id:
            domain += [('location_id.id', '=', location_id)]
        else:
            domain += [('location_id.usage', '=', 'internal')]
            
        if category:
            domain += [('product_id.categ_id.id', '=', category)]
            
        docs = self.env['stock.quant'].search(domain)
            
            
        if count_date:
            data_count_date = str(count_date)
        else:
            data_count_date = ''
        if counter:
            empl = self.env['hr.employee'].sudo().search([('id', '=', counter[0])], limit=1)
            data_counter = empl.name
        else:
            data_counter = ''
            
        data_counter = [data_counter]
        data_date_counter = [data_count_date]

        return {
            'docs': docs,
            'data_counter': data_counter,
            "data_date_counter": data_date_counter
        }
        