from odoo import models
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class ReportMRPFixOrderXlsx(models.AbstractModel):
    _name = 'report.eran_custom.eran_report_fix_order'
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
        
        ''' Find Forecast Order '''
        start_date = obj.start_date
        end_date = obj.end_date
        
        mrp_fix_order_ids = obj.env['dsn.mrp'].search([('demand_id', '=', obj.id)])
        demand_list_ids = obj.search([('type', '=', 'forecast_order'), ('start_date', '>=', start_date), ('end_date', '<=', end_date), ('id', '!=', obj.id)])
        demand_ids = obj.search([('id', '=', max([x.id for x in demand_list_ids]))])
        
        
        for record in demand_ids:
            mrp_ids = record.env['dsn.mrp'].search([('demand_id', '=', record.id)])
            forecast_ids = record.env['eran.demand.order.forecast'].search([('demand_id', '=', record.id)])
            
            
            forecast_month_list = []
            for frco in forecast_ids:
                forecast_month_list.append(frco.forecast_date)
                
            rm_duplicate = list(set(forecast_month_list))
            rm_duplicate.sort()
            res_list_mnt = []
            for temp in rm_duplicate:
                res_list_mnt.append(temp.strftime("%b-%y"))
            
            
            mrp_month_list = []
            temp_label_mnt = []
            month_forecast = record.end_date.month - record.start_date.month
            if month_forecast != 0:
                mrp_month_list.append(str(start_date.strftime("%b-%y")) + " - " + str(end_date.strftime("%b-%y")))
                temp_label_mnt.append(str(start_date.strftime("%b %Y")) + " - " + str(end_date.strftime("%b %Y")))
            else:
                mrp_month_list.append(str(start_date.strftime("%b-%y")))
                temp_label_mnt.append(str(start_date.strftime("%b %Y")))
            
            '''Create Header'''
            label = ['MATERIAL REQUIREMENT PLANNING-2']
            label_mnt = list(set(temp_label_mnt))
            sheet.write_row(0, 0, label, workbook.add_format({'font_size': 15, 'bold': True,}))
            sheet.write_row(1, 0, label_mnt, workbook.add_format({'font_size': 15, 'bold': True,}))
            
            header = ['Material Description', 'Valuation Class', 'UoM', 'Purch. Price', 'Stock']
            header2 = ['PR MRP-1', 'Cost PR MRP-1', 'PR MRP-2', 'Cost PR MRP-2', 'PR MRP Total', 'Purchase Cost MRP']
            dinamis_header = mrp_month_list + res_list_mnt
            headers = header + dinamis_header + header2
            sheet.write_row(2, 0, headers, text_header_style)
            
            '''Product Order from forecast and MRP'''
            product_order= []
            
            for prd_mrp in mrp_ids:
                product_order.append(prd_mrp.product_id.id)
                
            for prd_4cast in forecast_ids:
                product_order.append(prd_4cast.product_id.id)
                
            product_ids = record.env['product.product'].sudo().search([('id', 'in', list(set(product_order)))])
            valuation_class = [x.category_group_id.id for x in product_ids]
            
            '''Create Columns'''
            row = 2
            for val_class in set(valuation_class):
                subtotal_stock = []
                subtotal_demand_order = []
                subtotal_total_pr1 = []
                subtotal_cost_mrp1 = []
                subtotal_total_pr2 = []
                subtotal_cost_mrp2 = []
                subtotal_mrp_total = []
                subtotal_purc_cost_mrp = []
                for datas in product_ids.sorted(key=lambda x:x.category_group_id.name).filtered(lambda x: x.category_group_id.id == val_class):
                    row += 1
                    col = 5
                            
                    
                    # price_list = 0
                    # vendor_pricelist_ids = datas.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', datas.product_tmpl_id.id), ('state', '=', 'done')])
                    # vendor_pricelist = datas.env['product.supplierinfo'].sudo().search([('id', '=', max([x.id for x in vendor_pricelist_ids]) if vendor_pricelist_ids else 0)])
                    # for vendor_price in vendor_pricelist:
                    #     price_list = vendor_price.price
                        
                    
                    '''initial available all MRP'''
                    # initial_available = 0
                    # init_prd_mrp = [x.id for x in mrp_ids if x.product_id.id == datas.id]
                    # init_prd_frc = [x.id for x in demand_ids if x.product_id.id == datas.id]
                    # init_mrp_ids = datas.env['dsn.mrp'].search([('id', '=', max[init_prd_mrp + init_prd_frc])])
                    # for initial_stk in init_mrp_ids:
                    #     initial_available = initial_stk.stock_on_hand
                    
                    '''initial available MRP forecast'''
                    initial_available = 0
                    mrp_demand_order = 0
                    purc_price_list = 0
                    pr_mrp1 = 0
                    cost_pr_mrp1 = 0
                    for col_mrp in mrp_ids:
                        if col_mrp.product_id.id == datas.id:
                            # date = datetime.now()
                            initial_available = col_mrp.stock_on_hand
                            mrp_demand_order = col_mrp.demand_qty
                            
                            # pr_line_ids = col_mrp.env['purchase.request.line'].sudo().search([('mrp_id', '=', col_mrp.id)])
                            # for line_req in pr_line_ids:
                            date = col_mrp.purchase_request_line_id.create_date
                                
                            
                            price_list = 0
                            vendor_pricelist_ids = datas.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', datas.product_tmpl_id.id), ('date_start', '<=', date), ('date_end', '>=',date), ('state', '=', 'done')])
                            vendor_pricelist = datas.env['product.supplierinfo'].sudo().search([('id', '=', max([x.id for x in vendor_pricelist_ids]) if vendor_pricelist_ids else 0)])
                            for vendor_price in vendor_pricelist:
                                price_list = vendor_price.price
                            
                            purc_price_list = price_list
                            # pr_mrp1 = sum([x.product_qty for x in pr_line_ids])
                            pr_mrp1 = col_mrp.purchase_request_line_id.product_qty
                            cost_pr_mrp1 = pr_mrp1 * price_list
                    
                    pr_mrp2 = 0
                    cost_pr_mrp2 = 0
                    for self_mrp in mrp_fix_order_ids:
                        if self_mrp.product_id.id == datas.id:
                            # pr_line2_ids = self_mrp.env['purchase.request.line'].sudo().search([('mrp_id', '=', self_mrp.id)])
                            # pr_mrp2 = sum([x.product_qty for x in pr_line2_ids])
                            pr_mrp2 = self_mrp.purchase_request_line_id.product_qty
                            cost_pr_mrp2 = pr_mrp2 * purc_price_list
                            
                            
                    pr_mrp_total = pr_mrp1 + pr_mrp2
                    purch_cost_mrp = pr_mrp_total * purc_price_list
                    
                    '''SUBTOTAL'''
                    subtotal_stock.append(initial_available)
                    subtotal_demand_order.append(mrp_demand_order)
                    subtotal_total_pr1.append(pr_mrp1)
                    subtotal_cost_mrp1.append(cost_pr_mrp1)
                    subtotal_total_pr2.append(pr_mrp2)
                    subtotal_cost_mrp2.append(cost_pr_mrp2)
                    subtotal_mrp_total.append(pr_mrp_total)
                    subtotal_purc_cost_mrp.append(purch_cost_mrp)
                    
                    sheet.write(row, 0, datas.name, text_body_style)
                    sheet.write(row, 1, datas.category_group_id.name, text_body_style)
                    sheet.write(row, 2, datas.uom_id.name, text_body_style)
                    sheet.write(row, 3, int(purc_price_list), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                    sheet.write(row, 4, initial_available, text_body_style)
                    sheet.write(row, 5, mrp_demand_order, text_body_style)
                    for mnt in res_list_mnt:
                        col += 1
                        qty_4cast = sum([x.demand_qty for x in forecast_ids if x.product_id.id == datas.id and x.forecast_date.strftime("%b-%y") == mnt])
                        sheet.write(row, col, qty_4cast, text_body_style)
                    sheet.write(row, col+1, pr_mrp1, text_body_style)
                    sheet.write(row, col+2, int(cost_pr_mrp1), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                    sheet.write(row, col+3, pr_mrp2, text_body_style)
                    sheet.write(row, col+4, int(cost_pr_mrp2), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                    sheet.write(row, col+5, pr_mrp_total, text_body_style)
                    sheet.write(row, col+6, int(purch_cost_mrp), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'border': 1}))
                    
                row += 1
                cols = 5
                sheet.write(row, 0, 'SUBTOTAL', subtotal_style)
                sheet.write(row, 1, ' ', subtotal_style)
                sheet.write(row, 2, ' ', subtotal_style)
                sheet.write(row, 3, ' ', subtotal_style)
                sheet.write(row, 4, sum(subtotal_stock), subtotal_style)
                sheet.write(row, 5, sum(subtotal_demand_order), subtotal_style)
                for mnts in res_list_mnt:
                    cols += 1
                    forecast_qty_sub = sum([x.demand_qty for x in forecast_ids if str(x.forecast_date.strftime("%b-%y"))==mnts and x.product_id.category_group_id.id == val_class])
                    sheet.write(row, cols, forecast_qty_sub, subtotal_style)
                sheet.write(row, cols+1, sum(subtotal_total_pr1), subtotal_style)
                sheet.write(row, cols+2, sum(subtotal_cost_mrp1), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right'}))
                sheet.write(row, cols+3, sum(subtotal_total_pr2), subtotal_style)
                sheet.write(row, cols+4, sum(subtotal_cost_mrp2), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right'}))
                sheet.write(row, cols+5, sum(subtotal_mrp_total), subtotal_style)
                sheet.write(row, cols+6, sum(subtotal_purc_cost_mrp), workbook.add_format({'num_format': 'Rp #,##0.00', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right'}))