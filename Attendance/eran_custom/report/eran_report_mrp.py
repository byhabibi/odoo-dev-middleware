from odoo import models, fields, api, _
from datetime import datetime
from odoo.tools import config
from markupsafe import Markup
import logging
_logger = logging.getLogger(__name__)
# from odoo import models, _

class ReportMRPForecastXlsx(models.AbstractModel):
    _name = 'report.eran_custom.eran_report_mrp'
    _inherit = 'report.report_xlsx.abstract'
    
    
    def generate_xlsx_report(self, workbook, data, obj):
        sheet = workbook.add_worksheet('Sheet 1')
        text_header_style = workbook.add_format({'font_size': 11, 'bold': True, 'align': 'center', 'border': 1})
        text_body_style = workbook.add_format({'num_format': '#,##0.00', 'font_size': 11, 'border': 1})
        subtotal_style = workbook.add_format({'num_format': '#,##0.00', 'font_size': 11, 'bold': True, 'border': 1})
        
        
        sheet.set_column('A:A', 20)
        sheet.set_column('B:B', 20)
        sheet.set_column('C:C', 20)
        sheet.set_column('D:D', 20)
        sheet.set_column('E:E', 20)
        sheet.set_column('F:F', 20)
        sheet.set_column('G:G', 20)
        sheet.set_column('H:H', 10)
        sheet.set_column('I:I', 20)
        sheet.set_column('J:J', 20)
        sheet.set_column('K:K', 20)
        sheet.set_column('L:L', 10)
        sheet.set_column('M:M', 20)
        sheet.set_column('N:N', 20)
        sheet.set_column('O:O', 20)
        sheet.set_column('P:P', 20)
        sheet.set_column('Q:Q', 20)
        sheet.set_column('R:R', 20)
        sheet.set_column('S:S', 20)
        sheet.set_column('T:T', 20)
        sheet.set_column('U:U', 20)
        sheet.set_column('V:V', 20)
        sheet.set_column('W:W', 20)
        sheet.set_column('X:X', 20)
        sheet.set_column('Y:Y', 20)
        sheet.set_column('Z:Z', 20)
        
        header = ['Material Description', 'Valuation Class', 'UoM', 'Purch. Price', 'Stock']
        header2 = ['PR MRP-1', 'Cost PR MRP-1', 'PR MRP-2', 'Cost PR MRP-2', 'PR MRP Total', 'Purchase Cost MRP']
        
        # MRP
        start_date = obj.start_date
        end_date = obj.end_date
        month = end_date.month - start_date.month
        mrp_month_list = []
        temp_label_mnt = []
        if month != 0:
            mrp_month_list.append(str(start_date.strftime("%b-%y")) + " - " + str(end_date.strftime("%b-%y")))
            temp_label_mnt.append(str(start_date.strftime("%b %Y")) + " - " + str(end_date.strftime("%b %Y")))
        else:
            mrp_month_list.append(str(start_date.strftime("%b-%y")))
            temp_label_mnt.append(str(start_date.strftime("%b %Y")))
        
        mrp_ids = obj.env['dsn.mrp'].search([('demand_id', '=', obj.id)])
        

        
        # Forecast
        list_forecast_month = []
        forecast_ids = obj.env['eran.demand.order.forecast'].search([('demand_id', '=', obj.id)])
        for forecast in forecast_ids:
            list_forecast_month.append(forecast.forecast_date)
        
        rm_duplicate_mnt = list(set(list_forecast_month))
        rm_duplicate_mnt.sort()
        temp_month_forecast = []
        for temp in rm_duplicate_mnt:
            temp_month_forecast.append(temp.strftime("%b-%y"))
        
        # create header
        label = ['MATERIAL REQUIREMENT PLANNING-1']
        label_mnt = temp_label_mnt
        sheet.write_row(0, 0, label, workbook.add_format({'font_size': 15, 'bold': True,}))
        sheet.write_row(1, 0, label_mnt, workbook.add_format({'font_size': 15, 'bold': True,}))
        
        dinamyc_header = mrp_month_list + temp_month_forecast
        headers = header + dinamyc_header + header2
        sheet.write_row(2, 0, headers, text_header_style)
        
        product_demand_order = list(set([x.product_id.id for x in forecast_ids] + [x.product_id.id for x in mrp_ids]))
        product_ids = obj.env['product.product'].search([('id', 'in', product_demand_order)])

        valuation_class = [x.category_group_id.id for x in product_ids]
        row = 2
        for val in set(valuation_class):
            subtotal_stock = []
            subtotal_demand_order = []
            subtotal_total_pr1 = []
            subtotal_cost_mrp1 = []
            subtotal_total_pr2 = []
            subtotal_cost_mrp2 = []
            subtotal_mrp_total = []
            subtotal_purc_cost_mrp = []
            
            for datas in product_ids.sorted(key=lambda x:x.category_group_id.name).filtered(lambda x:x.category_group_id.id==val):
                col = 5
                row += 1
                
                # price_list = 0
                # vendor_pricelist_ids = datas.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', datas.product_tmpl_id.id), ('state', '=', 'done')])
                # vendor_pricelist = datas.env['product.supplierinfo'].sudo().search([('id', '=', max([x.id for x in vendor_pricelist_ids]) if vendor_pricelist_ids else 0)])
                # for vendor_price in vendor_pricelist:
                #     price_list = vendor_price.price
                    
                initial_available = 0
                demand_order = 0
                price_list = 0
                purc_price_list = 0
                total_pr1 = 0
                cost_mrp1 = 0
                total_pr2 = 0
                cost_mrp2 = 0
                for mrp in mrp_ids:
                    if mrp.product_id.id == datas.id:
                        # date = datetime.now()
                        # pr_line_ids = mrp.env['purchase.request.line'].sudo().search([('mrp_id', '=', mrp.id)])
                        # for line_req in pr_line_ids:
                        date = mrp.purchase_request_line_id.create_date
                        
                        _logger.info("dskaufdsfkjdsbfjsdbfjsdb")
                        _logger.info(date)
                            
                        vendor_pricelist_ids = datas.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', datas.product_tmpl_id.id), ('date_start', '<=', date), ('date_end', '>=',date), ('state', '=', 'done')])
                        vendor_pricelist = datas.env['product.supplierinfo'].sudo().search([('id', '=', max([x.id for x in vendor_pricelist_ids]) if vendor_pricelist_ids else 0)])
                        for vendor_price in vendor_pricelist:
                            price_list = vendor_price.price
                            
                        purc_price_list = price_list 
                        # total_pr1 = sum([x.product_qty for x in pr_line_ids])
                        total_pr1 = mrp.purchase_request_line_id.product_qty
                        cost_mrp1 = price_list * total_pr1
                        initial_available = mrp.stock_on_hand
                        demand_order = mrp.demand_qty
                        
                
                mrp_total = total_pr1 + total_pr2
                purc_cost_mrp =mrp_total * purc_price_list
                
                # subtotal per categories
                subtotal_stock.append(initial_available)
                subtotal_demand_order.append(demand_order)
                subtotal_total_pr1.append(total_pr1)
                subtotal_cost_mrp1.append(cost_mrp1)
                subtotal_total_pr2.append(total_pr2)
                subtotal_cost_mrp2.append(cost_mrp2)
                subtotal_mrp_total.append(mrp_total)
                subtotal_purc_cost_mrp.append(purc_cost_mrp)
                
                # Cols line
                sheet.write(row, 0, datas.name, text_body_style)
                sheet.write(row, 1, datas.category_group_id.name, text_body_style)
                sheet.write(row, 2, datas.uom_id.name, text_body_style)
                sheet.write(row, 3, purc_price_list, workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                sheet.write(row, 4, initial_available, text_body_style)
                sheet.write(row, 5, demand_order, text_body_style)
                for mnt in temp_month_forecast:
                    col += 1
                    forecast_qty = sum([x.demand_qty for x in forecast_ids if x.product_id==datas and str(x.forecast_date.strftime("%b-%y"))==mnt])
                    sheet.write(row, col, forecast_qty, text_body_style)
                sheet.write(row, col+1, total_pr1, text_body_style)
                sheet.write(row, col+2, int(cost_mrp1), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                sheet.write(row, col+3, total_pr2, text_body_style)
                sheet.write(row, col+4, int(cost_mrp2), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                sheet.write(row, col+5, mrp_total, text_body_style)
                sheet.write(row, col+6, int(purc_cost_mrp), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                
            # Subtotal Cols
            row += 1
            cols = 5   
            sheet.write(row, 0, 'SUBTOTAL', subtotal_style)
            sheet.write(row, 1, ' ', subtotal_style)
            sheet.write(row, 2, ' ', subtotal_style)
            sheet.write(row, 3, ' ', subtotal_style)
            sheet.write(row, 4, sum(subtotal_stock), subtotal_style)
            sheet.write(row, 5, sum(subtotal_demand_order), subtotal_style)
            for mnts in temp_month_forecast:
                cols+=1
                # fore_fill = forecast_ids.filtered(lambda x: str(x.forecast_date.strftime("%b-%y"))== mnts and x.product_id.category_group_id.id == val)
                forecast_qty_sub = sum([x.demand_qty for x in forecast_ids if str(x.forecast_date.strftime("%b-%y"))==mnts and x.product_id.category_group_id.id == val])
                sheet.write(row, cols, forecast_qty_sub, subtotal_style)
            sheet.write(row, cols+1, sum(subtotal_total_pr1), subtotal_style)
            sheet.write(row, cols+2,  sum(subtotal_cost_mrp1), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right'}))
            sheet.write(row, cols+3, sum(subtotal_total_pr2), subtotal_style)
            sheet.write(row, cols+4,  sum(subtotal_cost_mrp2),  workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right'}))
            sheet.write(row, cols+5, sum(subtotal_mrp_total), subtotal_style)
            sheet.write(row, cols+6,  sum(subtotal_purc_cost_mrp),  workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right'}))
            
# code baru
class CustomAccountReport(models.Model):
    _inherit = 'account.report'

    def _init_options_buttons(self, options, previous_options=None):
        super()._init_options_buttons(options, previous_options)
        
        options['buttons'].append({
            'name': _('PDF Filter'),
            'sequence': 15,
            'class': 'btn-secondary',
            'action': 'export_file',
            'action_param': 'export_to_pdf_filter',
            'file_export_type': _('PDF')
        })
        return options
    
    def export_to_pdf_filter(self, options):
        self.ensure_one()
        if not config['test_enable']:
            self = self.with_context(commit_assetsbundle=True)

        base_url = self.env['ir.config_parameter'].sudo().get_param('report.url') or self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        rcontext = {
            'mode': 'print',
            'base_url': base_url,
            'company': self.env.company,
        }

        print_mode_self = self.with_context(print_mode=True)
        options['no_child'] = True
        all_lines = self._get_lines(options)
        filtered_lines = [
            line for line in all_lines
            if line.get('level') == 1 and not line.get('name', '').strip().startswith("Total ")
        ]
        body_html = print_mode_self.with_context(no_child=True).get_html(options, filtered_lines)
        body = self.env['ir.ui.view']._render_template(
            "account_reports.print_template",
            values=dict(rcontext, body_html=body_html),
        )
        footer = self.env['ir.actions.report']._render_template("web.internal_layout", values=rcontext)
        footer = self.env['ir.actions.report']._render_template("web.minimal_layout", values=dict(rcontext, subst=True, body=Markup(footer.decode())))

        landscape = False
        if len(options['columns']) * len(options['column_groups']) > 5:
            landscape = True

        file_content = self.env['ir.actions.report']._run_wkhtmltopdf(
            [body],
            footer=footer.decode(),
            landscape=landscape,
            specific_paperformat_args={
                'data-report-margin-top': 10,
                'data-report-header-spacing': 10
            }
        )

        return {
            'file_name': self.get_default_report_filename('pdf'),
            'file_content': file_content,
            'file_type': 'pdf',
        }