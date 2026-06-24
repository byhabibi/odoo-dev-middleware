from odoo import _, fields, models, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import mimetypes
import base64
import itertools
import logging
_logger = logging.getLogger(__name__)


class DSNForecastOrder(models.Model):
    _inherit = "dsn.forecast.order"


    type = fields.Selection(selection_add=[('fix_order', 'Fix Order')])
    department_to = fields.Many2one('hr.department', string='To')
    department_from = fields.Many2one('hr.department', string='From')
    deadline = fields.Char(string='Deadline')
    is_created_demand = fields.Boolean(string='Created Demand ?')


    def replace_name(self):
        for this in self:
            if this.type == 'forecast_order':
                sequences_setting = self.env['dsn.sales.sequence.setting'].search([('type', '=', 'forecast_order'), ('company_id', '=', self.env.company.id)], limit=1)
        
                if not sequences_setting or not sequences_setting.sequence_id:
                    raise UserError("You must set sequence Sale Order in Sales Sequences Settings")
                
                name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
                this.name = name

            if this.type == 'fix_order':
                sequences_setting = self.env['dsn.sales.sequence.setting'].search([('type', '=', 'fix_order'), ('company_id', '=', self.env.company.id)], limit=1)
        
                if not sequences_setting or not sequences_setting.sequence_id:
                    raise UserError("You must set sequence Sale Order in Sales Sequences Settings")
                
                name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
                this.name = name

    def get_month_year_list(self, start_date, end_date):

        months = []
        while start_date <= end_date:
            month_year = start_date.strftime("%b-%y")
            months.append(month_year)
            start_date = start_date + timedelta(days=31)
            start_date = start_date + timedelta(days=-(start_date.day - 1)) 
        return months
    
    def get_forecast_date(self):        
        if self.forecast_line_ids:
            forecast_order_line_first = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date asc', limit=1)
            forecast_order_line_last = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date desc', limit=1)
            return self.get_month_year_list(forecast_order_line_first.forecast_date, forecast_order_line_last.forecast_date)
        else:
            return []
        
    def get_category_group(self):
        res_qty = {}
        res_amount = {}

        forecast_order_line_first = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date asc', limit=1)
        category_ids = self.forecast_line_ids.mapped('product_id.category_group_id')
        datas = []
        for categ_id in category_ids:
            forecast_order_line = self.env['dsn.forecast.order.line'].search([
                ('forecast_id', '=', self.id), ('product_id.category_group_id', '=', categ_id.id), ('forecast_date', '=', forecast_order_line_first.forecast_date)])

            value = {'ceteg_id': forecast_order_line[0].product_id.category_group_id, 'amount': sum(forecast_order_line.mapped('total'))}
            datas.append(value)
    
        sorted_a = sorted(datas, key=lambda x: x['amount'], reverse=True)
        ceteg_ids = [item['ceteg_id'] for item in sorted_a]

        category_group_ids = ceteg_ids
        forecast_order_line_last = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date desc', limit=1)
        month_year_list = self.get_month_year_list(forecast_order_line_first.forecast_date, forecast_order_line_last.forecast_date)

        total_vals_list_qty = [0] * len(month_year_list)
        total_vals_list_amount = [0] * len(month_year_list)
        for categ in category_group_ids:
            vals2_qty = 0
            vals2_amount = 0
            res_qty[categ.name] = []
            res_amount[categ.name] = []
            for month_year in month_year_list:
                vals_qty = 0
                vals_amount = 0
                for line in self.forecast_line_ids.filtered(lambda l:l.product_id.category_group_id.id == categ.id):
                    if line.forecast_date.strftime("%b-%y") == month_year:
                        vals_qty += line.quantity
                        vals_amount += line.total

                res_qty[categ.name].append(vals_qty)
                res_amount[categ.name].append(vals_amount)
                vals2_qty += vals_qty
                vals2_amount += vals_amount
                total_vals_list_qty[month_year_list.index(month_year)] += vals_qty
                total_vals_list_amount[month_year_list.index(month_year)] += vals_amount

        res_qty['Total'] = total_vals_list_qty    
        res_amount['Total'] = total_vals_list_amount
        return res_qty, res_amount

    # def get_category_group_total(self):
    #     res = {}
    #     category_group_ids = self.forecast_line_ids.mapped('product_id.category_group_id')
    #     forecast_order_line_first = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date asc', limit=1)
    #     forecast_order_line_last = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date desc', limit=1)
    #     month_year_list = self.get_month_year_list(forecast_order_line_first.forecast_date, forecast_order_line_last.forecast_date)

    #     total_vals_list = [0] * len(month_year_list)
    #     for categ in category_group_ids:
    #         vals2 = 0
    #         res[categ.name] = []
    #         for month_year in month_year_list:
    #             vals = 0
    #             for line in self.forecast_line_ids.filtered(lambda l:l.product_id.category_group_id.id == categ.id):
    #                 if line.forecast_date.strftime("%b-%y") == month_year:
    #                     vals += line.total
    #             res[categ.name].append(vals)
    #             vals2 += vals
    #             total_vals_list[month_year_list.index(month_year)] += vals
            
    #     res['Total'] = total_vals_list    
    #     return res

    def get_customer_group(self):
        res_qty = {}
        res_amount = {}

        forecast_order_line_first = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date asc', limit=1)
        customer_ids = self.forecast_line_ids.mapped('partner_id')
        datas = []
        for cust in customer_ids:
            forecast_order_line = self.env['dsn.forecast.order.line'].search([
                ('forecast_id', '=', self.id), ('partner_id', '=', cust.id), ('forecast_date', '=', forecast_order_line_first.forecast_date)])
            if forecast_order_line:
                value = {'partner_id': forecast_order_line[0].partner_id, 'amount': sum(forecast_order_line.mapped('total'))}
            else:
                value = {'partner_id': cust, 'amount': 0}
            datas.append(value)
    
        sorted_a = sorted(datas, key=lambda x: x['amount'], reverse=True)
        partner_ids = [item['partner_id'] for item in sorted_a]

        customer_group_ids = partner_ids        
        forecast_order_line_last = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date desc', limit=1)
        month_year_list = self.get_month_year_list(forecast_order_line_first.forecast_date, forecast_order_line_last.forecast_date)

        total_vals_list_qty = [0] * len(month_year_list)
        total_vals_list_amount = [0] * len(month_year_list)
        for cust in customer_group_ids:
            vals2_qty = 0
            vals2_amount = 0
            res_qty[cust.name] = []
            res_amount[cust.name] = []
            for month_year in month_year_list:
                vals_qty = 0
                vals_amount = 0
                for line in self.forecast_line_ids.filtered(lambda l:l.partner_id.id == cust.id):
                    if line.forecast_date.strftime("%b-%y") == month_year:
                        vals_qty += line.quantity
                        vals_amount += line.total

                res_qty[cust.name].append(vals_qty)
                res_amount[cust.name].append(vals_amount)
                vals2_qty += vals_qty
                vals2_amount += vals_amount
                total_vals_list_qty[month_year_list.index(month_year)] += vals_qty
                total_vals_list_amount[month_year_list.index(month_year)] += vals_amount

        res_qty['Total'] = total_vals_list_qty    
        res_amount['Total'] = total_vals_list_amount
        return res_qty, res_amount

    def get_category_sort_group(self):
        data_categories = self.get_category_group()
        data1, data2 = data_categories

        if 'OTHERS' in data1:
            others1 = data1.pop('OTHERS')
            total1 = data1.pop('Total')
            data1['OTHERS'] = others1 
            data1['Total'] = total1

        if 'OTHERS' in data2:
            others2 = data2.pop('OTHERS')
            total2 = data2.pop('Total')
            data2['OTHERS'] = others2 
            data2['Total'] = total2

        data_categories = (data1, data2)
        return data_categories
    
    # def get_customer_group_total(self):
    #     res = {}
    #     customer_group_ids = self.forecast_line_ids.mapped('partner_id')
    #     forecast_order_line_first = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date asc', limit=1)
    #     forecast_order_line_last = self.env['dsn.forecast.order.line'].search([('forecast_id', '=', self.id)], order='forecast_date desc', limit=1)
    #     month_year_list = self.get_month_year_list(forecast_order_line_first.forecast_date, forecast_order_line_last.forecast_date)

    #     total_vals_list = [0] * len(month_year_list)
    #     for cust in customer_group_ids:
    #         vals2 = 0
    #         res[cust.name] = []
    #         for month_year in month_year_list:
    #             vals = 0
    #             for line in self.forecast_line_ids.filtered(lambda l:l.partner_id.id == cust.id):
    #                 if line.forecast_date.strftime("%b-%y") == month_year:
    #                     vals += line.total
    #             res[cust.name].append(vals)
    #             vals2 += vals
    #             total_vals_list[month_year_list.index(month_year)] += vals
            
    #     res['Total'] = total_vals_list    
    #     return res


    # def button_to_confirm(self):
    #     self.get_category_group_qty()

        


class DSNForecastOrderLine(models.Model):
    _inherit = "dsn.forecast.order.line"

    type = fields.Selection(selection=[('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], related='forecast_id.type', store=True)
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('done', 'Done')], related='forecast_id.state', store=True)
    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)
    product_name = fields.Char('Product Name', related="product_id.name")
    product_code = fields.Char('Product Code', related="product_id.default_code")
    is_created_demand = fields.Boolean(string='Created Demand ?', related="forecast_id.is_created_demand")
    
    @api.onchange('product_id', 'partner_id')
    def _onchange_product_id(self):
        for rec in self:
            rec.price = 1.0
            if rec.product_id:
                if rec.product_id.lst_price > 0:
                    rec.price = rec.product_id.lst_price

            if rec.partner_id and rec.product_id:
                # ioafoieho8wggr
                if rec.partner_id.property_product_pricelist:
                    date = rec.create_date or fields.Datetime.now()
                    price_list = rec.partner_id.property_product_pricelist.item_ids.filtered(lambda x:x.product_tmpl_id == rec.product_id.product_tmpl_id and x.date_start <= date and x.date_end >= date)
                    price_list = price_list.sorted(lambda o: o.create_date, reverse=True)
                    if price_list:
                        rec.price = price_list[0].fixed_price

    @api.model
    def create(self, vals):
        res = super(DSNForecastOrderLine, self).create(vals)
        res.chechk_price()
        return res
    
    def chechk_price(self):
        for line in self:
            if line.price == 1.0:
                line._onchange_product_id()
          


class DSNDemandPlanning(models.Model):
    _inherit = "dsn.demand.planning"


    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True)
    mrp_non_material_ids = fields.One2many('eran.mrp.non.material', 'demand_id', string='MRP Non Material')
    mrp_non_material_count = fields.Integer(compute='_compute_mrp_non_materal_count')
    overhead_ids = fields.One2many('eran.work.center.overhead', 'demand_id')
    deadline_date = fields.Date(tracking=True)
    demand_order_detail_count = fields.Integer(compute='_compute_demand_order_count')
    forecast_start_date = fields.Date(string='Forecast Start Date')
    forecast_end_date = fields.Date(string='Forecast End Date')
    demand_forecast_ids = fields.One2many('eran.demand.order.forecast', 'demand_id')
    demand_order_forecast_count = fields.Integer(compute='_compute_mrp_non_materal_count')
    percen_forecast = fields.Float(string = 'Percentage Forecast', default = 98.20)
    forecast_ids = fields.Many2many('dsn.forecast.order', string='Forecast', copy=False)

    def action_print_report_cla(self):
        for this in self:
            if len(self.search([('type', '=', 'forecast_order'), ('start_date', '>=', this.start_date), ('end_date', '<=', this.end_date)])):
                return self.env.ref('eran_custom.eran_action_report_cover_letter_attachment').report_action(self)
            else:
                raise ValidationError(_("Error Print Report CLA: Demand Order for type 'forecast order' and for the period was not found!"))
    def set_material_forecast(self, product, record, bom_line):
        for this in self:
            bom_sfg = self.env['mrp.bom'].sudo().search([
                ('company_id', '=', this.company_id.id),
                ('active', '=', True),
                ('product_tmpl_id', '=', product.product_tmpl_id.id)], order='id desc',limit=1)
            if bom_sfg:
                continue

            else:

                qty_demand = record.demand_qty * bom_line.product_qty
                qty_demand = self._get_calculate_qty(product.uom_po_id, bom_line.product_uom_id, qty_demand)
                value = {
                    'bom_id': record.bom_id.id,
                    'uom_id': product.uom_po_id.id,
                    'company_id': this.company_id.id,
                    'demand_id': this.id,
                    'product_id': product.id,
                    'demand_qty': qty_demand,
                    'forecast_date': record.forecast_date,
                    'type': this.type,
                    'product_type': 'material',
                    'ref': record.ref,
                    'parent_id': record.id,
                }
                self.env['eran.demand.order.forecast'].create(value)

    def set_mrp_forecast(self):
        for this in self:
            for line in this.demand_forecast_ids:
                # if line.bom_type == 'subcontract':
                #     qty_demand = line.demand_qty
                #     qty_demand = self._get_calculate_qty(line.product_id.uom_po_id, line.product_id.uom_id, qty_demand)

                #     value = {
                #         'bom_id': line.bom_id.id,
                #         'uom_id': line.product_id.uom_po_id.id,
                #         'company_id': line.company_id.id,
                #         'demand_id': this.id,
                #         'product_id': line.product_id.id,
                #         'demand_qty': qty_demand,
                #         'forecast_date': line.forecast_date,
                #         'type': this.type,
                #         'product_type': 'material',
                #         'ref': line.ref,
                #         'parent_id': line.id,
                #     }
                #     self.env['eran.demand.order.forecast'].create(value)
                if line.bom_id:
                    for bom_line in line.bom_id.bom_line_ids:
                        product = bom_line.product_id
                        record = line
                        this.set_material_forecast(product, record, bom_line)

    def set_sfg_forecast(self, product, record, bom_line):
        for this in self:
            bom_sfg = self.env['mrp.bom'].sudo().search([
                ('company_id', '=', this.company_id.id),
                ('active', '=', True),
                ('product_tmpl_id', '=', product.product_tmpl_id.id)], order='id desc',limit=1)
            if bom_sfg:
                qty_demand = record.demand_qty * bom_line.product_qty
                
                value = {
                    'uom_id': product.uom_id.id,
                    'company_id': this.company_id.id,
                    'demand_id': this.id,
                    'product_id': product.id,
                    'bom_id': bom_sfg.id or False,
                    'demand_qty': qty_demand,
                    'forecast_date': record.forecast_date,
                    'type': this.type,
                    'product_type': 'sfg',
                    'ref': record.ref,
                    'parent_id': record.id,
                    
                }
                records = self.env['eran.demand.order.forecast'].create(value)
                for bom_line in bom_sfg.bom_line_ids:
                    product = bom_line.product_id
                    record = records
                    this.set_sfg_forecast(product, record, bom_line)

    def set_fg_forecast(self):
        for this in self:
            forecast_list = []
            for line in this.line_ids:
                for fcs in line.forecast_ids:
                    forecast_list.append(fcs.id)

            product_forecast_list = self.env['dsn.forecast.order.line'].sudo().search([
                ('company_id', '=', this.company_id.id),
                ('forecast_id.state', '=', 'confirm'),
                ('forecast_id.type', '=', this.type),
                ('forecast_id', 'in', forecast_list),
                # ('is_demand_order', '=', False),
                ('forecast_date', '>=', this.forecast_start_date),
                ('forecast_date', '<=', this.forecast_end_date)])
            datas = []
            for line in product_forecast_list:
                bom = self.env['mrp.bom'].sudo().search([
                    ('company_id', '=', this.company_id.id),
                    ('active', '=', True),
                    ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)], order='id desc', limit=1)

                value = {
                    'company_id': this.company_id.id,
                    'product_id': line.product_id.id,
                    'uom_id': line.uom_id.id,
                    'bom_id': bom.id or False,
                    'demand_qty': line.quantity,
                    'ref': line.forecast_id.name,
                    'forecast_date': line.forecast_date,
                    'type': this.type,
                    'product_type': 'fg'
                }
                datas.append((0,0, value))

            this.demand_forecast_ids = [(5,)]
            this.demand_forecast_ids = datas

            for line_frcst in this.demand_forecast_ids:
                if line_frcst.bom_id:
                    for bom_line in line_frcst.bom_id.bom_line_ids:
                        product = bom_line.product_id
                        record = line_frcst
                        this.set_sfg_forecast(product, record, bom_line)

    def set_demand_forecast(self):
        for this in self:
            if not this.forecast_start_date:
                raise UserError("You must set forecast range.")

            if not this.forecast_end_date:
                raise UserError("You must set forecast range.")

            this.set_fg_forecast()
            this.set_mrp_forecast()

    def view_demand_order_forecast(self):
        view_tree = self.env.ref('eran_custom.eran_view_eran_demand_order_forecast_tree').id
        action = {
            'name': 'Demand Forecast',
            'domain': [('id', 'in', self.demand_forecast_ids.ids)],
            'view_mode': 'tree',
            'res_model': 'eran.demand.order.forecast',
            'views': [(view_tree, 'tree')],
            'type': 'ir.actions.act_window',
            'context': {'create':0, 'copy':0, 'delete':0, 
                'search_default_forecast_date': 1, 'search_default_product_type_order': 1}
        }
        return action

    def replace_name(self):
        for this in self:
            sequences_setting = this.env['dsn.mrp.production.sequence.setting'].search([
            ('type', '=', 'demand_order'), ('company_id', '=', self.env.company.id)], limit=1)
        
            if not sequences_setting or not sequences_setting.sequence_id:
                raise UserError("You must set sequence Demand Order in Manufacturing Sequences Settings")
            
            new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
            
            this.name = new_name

    def _compute_demand_order_count(self):
        for this in self:
            this.demand_order_detail_count = len(this.line_ids.filtered(lambda x:x.production_qty != 0 and x.bom_type == 'normal'))

    def view_deman_order_detail(self):
        view_tree = self.env.ref('mrp_forecast_order.dsn_view_demand_order_detail_tree').id
        action = {
            'name': 'Demand Order Detail',
            'domain': [('id', 'in', self.line_ids.filtered(lambda x:x.production_qty != 0).ids), ('bom_type', '=', 'normal')],
            'view_mode': 'tree',
            'res_model': 'dsn.demand.planning.line',
            'views': [(view_tree, 'tree')],
            'type': 'ir.actions.act_window',
            'context': {'create':0, 'copy':0, 'delete':0}
        }
        return action

    def _compute_mrp_non_materal_count(self):
        for this in self:
            this.mrp_non_material_count = len(this.mrp_non_material_ids)
            this.demand_order_forecast_count = len(this.demand_forecast_ids)

    def view_mrp_non_material(self):
        view_tree = self.env.ref('eran_custom.eran_view_mrp_non_material_tree').id
        action = {
            'name': 'MRP Non Material',
            'domain': [('id', 'in', self.mrp_non_material_ids.ids)],
            'view_mode': 'tree',
            'res_model': 'eran.mrp.non.material',
            'views': [(view_tree, 'tree')],
            'type': 'ir.actions.act_window',
            'context': {'create':0, 'copy':0, 'delete':0}
        }

        return action

    def set_mrp_non_material(self):
        for this in self:
            if  this.overhead_ids:
                raise ValidationError(_("MRP Non Material already exist for demand %s.", this.name))

            datas = []
            for line in self.line_ids:
                if line.production_qty == 0:
                    continue
                if line.bom_id:
                    for operation in line.bom_id.operation_ids:
                        if operation.workcenter_id:
                            for overhead in operation.workcenter_id.overhead_ids:
                                if line.production_qty >= overhead.min_capacity and line.production_qty  <= overhead.max_capacity:
                                    value = {
                                        'product_id' : overhead.product_id.id,
                                        'uom_id': overhead.uom_id.id,
                                        'demand_workcenter_id': operation.workcenter_id.id,
                                        'qty': overhead.qty,
                                        'bom_id': line.bom_id.id
                                    }
                                    datas.append((0,0, value))
            if datas:
                this.overhead_ids = [(5,)]
                this.overhead_ids = datas

            if not datas:
                raise ValidationError(_("MRP Non Material not found in all Bill of Material Workcenter for document %s.", this.name))

            if this.overhead_ids:
                products = this.overhead_ids.mapped('product_id').ids

                for prod in products:
                    overhead_line = this.overhead_ids.filtered(lambda x:x.product_id.id == prod)
                    value = {
                        # 'bom_id': record.bom_id.id,
                        'uom_id': overhead_line[0].uom_id.id,
                        'company_id': this.company_id.id,
                        'demand_id': this.id,
                        'product_id': overhead_line[0].product_id.id,
                        'stock_on_hand': overhead_line[0].product_id.free_qty,
                        'demand_qty': sum(overhead_line.mapped('qty')),
                        'deadline_date': this.line_ids[0].deadline_date,
                    }
                    self.env['eran.mrp.non.material'].create(value)

    def get_forecast_data(self):
        for this in self:
            product_forecast_list = self.env['dsn.forecast.order.line'].sudo().search([
                ('company_id', '=', this.company_id.id),
                ('forecast_id.state', '=', 'confirm'),
                ('forecast_id.type', '=', this.type),
                ('is_demand_order', '=', False),
                ('is_created_demand', '!=', True),
                ('forecast_date', '>=', this.start_date),
                ('forecast_date', '<=', this.end_date)]).mapped('product_id')  
            datas = []
            level = 1
            fc = []
            for product in product_forecast_list:
                forecast_line_list = self.env['dsn.forecast.order.line'].sudo().search([
                    ('company_id', '=', this.company_id.id),
                    ('forecast_id.type', '=', this.type),
                    ('forecast_id.state', '=', 'confirm'),
                    ('forecast_date', '>=', this.start_date),
                    ('forecast_date', '<=', this.end_date),
                    ('is_demand_order', '=', False),
                    ('is_created_demand', '!=', True),
                    ('product_id', '=', product.id)])
                bom = self.env['mrp.bom'].sudo().search([
                    ('company_id', '=', this.company_id.id),
                    ('active', '=', True),
                    ('product_tmpl_id', '=', product.product_tmpl_id.id)], order='id desc', limit=1)

                value = {
                    'company_id': this.company_id.id,
                    'level': str(level),
                    'product_id': product.id,
                    'uom_id': product.uom_id.id,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'stock_on_hand': product.free_qty,
                    'bom_id': bom.id or False,
                    'demand_qty': sum(forecast_line_list.mapped('quantity')),
                    'forecast_ids': forecast_line_list.mapped('forecast_id').ids,
                    'note': 'Forecast :' + ' ' + str(sum(forecast_line_list.mapped('quantity'))) 
                }
                level += 1
                datas.append((0,0, value))
                
                for line in forecast_line_list.mapped('forecast_id').ids:
                    if line not in fc:
                        fc.append(line)

            this.line_ids = [(5,)]
            this.line_ids = datas
            this.forecast_ids = fc

    def search_data(self):
        for this in self:
            this.get_forecast_data()
            for line in this.line_ids:
                line.deadline_date = this.deadline_date
            # this.get_sale_demand()

    def reset_to_draft(self):
        res = super(DSNDemandPlanning, self).reset_to_draft()
        for line in self.forecast_ids:
            line.is_created_demand = False
        return res

            
    def action_report_mrp_xlsx(self):
        if self.type != 'forecast_order':
            if len(self.search([('type', '=', 'forecast_order'), ('start_date', '>=', self.start_date), ('end_date', '<=', self.end_date)])):
                return self.env.ref('eran_custom.eran_action_report_mrp_fix_order').report_action(self)
            else:
                raise ValidationError(_("Error Print Report MRP: Demand Order for type 'forecast order' and for the period was not found!"))
        else:
            return self.env.ref('eran_custom.eran_action_report_mrp').report_action(self)

    def action_confirm(self):
        for this in self:
            level = 1
            for line_unlink in this.line_ids:
                if not line_unlink.bom_id:
                    line_unlink.unlink()
            for line in this.line_ids:
                # if not line.bom_id:
                    # raise ValidationError(_("Bill of Material in demand detail cannot be empty."))
                if not line.deadline_date:
                    raise ValidationError(_("Daedline date in demand detail cannot be empty."))
                
                for forecast in line.forecast_ids:
                    for line_forecast in forecast.forecast_line_ids.filtered(lambda x:x.product_id == line.product_id\
                        and x.forecast_date >= this.start_date and x.forecast_date <= this.end_date):
                        line_forecast.write({'is_demand_order': True})

                    not_demand_order = forecast.forecast_line_ids.filtered(lambda x:x.is_demand_order == False)
                    if not not_demand_order:
                        forecast.write({'state': 'done'}) 
                
                for bom_line in line.bom_id.bom_line_ids:
                    line_level = str(line.level) + '.' + str(level)
                    product = bom_line.product_id
                    record = line
                    this.set_sfg(product, record, bom_line, line_level)

                level += 1
            
            this.write({'state': 'in_progress'})

            for fc in this.forecast_ids:
                fc.is_created_demand = True


class DSNDemandPlanningLine(models.Model):
    _inherit = "dsn.demand.planning.line"


    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True, related='demand_id.type', store=True)
    fulfilled_qty = fields.Float(string='Fulfilled Qty', tracking=True, compute='_compute_fullfilled_qty')
    production_qty = fields.Float(string='Production Qty', compute='_compute_production_qty', store=True)
    default_code = fields.Char(string='Internal Reference', related='product_id.default_code')
    part_name = fields.Char(string='Part Name', related='product_id.name')
    bom_type = fields.Selection(related='bom_id.type', tracking=True, store=True)
    mps_bu_ids = fields.One2many('dsn.mps.bu', 'demand_line_id')


    def _compute_fullfilled_qty(self):
        for this in self:
            mo_done = [0]
            for mps in this.mps_ids:
                for mo in mps.mo_ids:
                    if mo.state == 'done':
                        mo_done.append(mo.qty_producing)
            this.fulfilled_qty = sum(mo_done)

    @api.depends('demand_line_id','demand_qty','stock_on_hand','buffer_stock')
    def _compute_production_qty(self):
        for this in self:
            if not this.demand_line_id:
                production_qty = this.demand_qty - this.stock_on_hand + this.buffer_stock
            if this.demand_line_id:
                bom_qty_line = this.demand_line_id.bom_id.bom_line_ids.filtered(lambda x: x.product_id == this.product_id).product_qty
                demand_real = this.demand_line_id.production_qty * bom_qty_line
                production_qty = demand_real - this.stock_on_hand + this.buffer_stock
            if production_qty < 0:
                production_qty = 0
            this.production_qty = production_qty

    def generate_multi_mps(self):
        # if not self.deadline_date:
        #      raise ValidationError(_("Daedline date cannot be empty."))
        for this in self:
            if not this.demand_line_id:
                production_qty = this.demand_qty - this.stock_on_hand + this.buffer_stock
            if this.demand_line_id:
                bom_qty_line = this.demand_line_id.bom_id.bom_line_ids.filtered(lambda x: x.product_id == this.product_id).product_qty
                demand_real = this.demand_line_id.production_qty * bom_qty_line
                production_qty = demand_real - this.stock_on_hand + this.buffer_stock
            if production_qty < 0:
                production_qty = 0

            if production_qty == sum(this.mps_ids.mapped('production_qty')):
                raise ValidationError(_("Production quantity has been met by the quanity of mps for product %s.", this.product_id.display_name))
            if this.bom_type == 'subcontract':
                raise ValidationError(_("Cannot create MPS because BoM is of subcon type for product %s.", this.product_id.display_name))
                
        action = self.env['ir.actions.actions']._for_xml_id('mrp_forecast_order.dsn_action_mps_wizard')
        return action


class DSNMPS(models.Model):
    _inherit = "dsn.mps"
    _order = 'name desc, level desc'


    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True, related='demand_id.type', store=True)
    operator_id = fields.Many2one('hr.employee', string='Operator')
    leader_id = fields.Many2one('hr.employee', string='Leader')
    shift_id = fields.Many2one('eran.master.shift', string='Shift')
    default_code = fields.Char(string='Internal Reference', related='product_id.default_code')
    part_name = fields.Char(string='Part Name', related='product_id.name')
    level = fields.Char()

    def replace_name(self):
        for this in self:
            sequences_setting = this.env['dsn.mrp.production.sequence.setting'].search([
            ('type', '=', 'mps'), ('company_id', '=', self.env.company.id)], limit=1)
        
            if not sequences_setting or not sequences_setting.sequence_id:
                raise UserError("You must set sequence MPS in Manufacturing Sequences Settings")
            
            name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
            this.name = name


    def generate_multi_mo(self):
        for this in self:
            if this.mo_ids:
                raise ValidationError(_('MPS %s has created a manufacturing order', this.name))
            
            manufacturing = self.env['mrp.production'].sudo().create({
                'company_id': this.company_id.id,
                'dsn_mps_id': this.id,
                'product_id': this.product_id.id,
                'product_qty': this.production_qty,
                'product_uom_id': this.uom_id.id,
                'date_planned_start': this.scheduled_date,
                'origin': this.name,
                'bom_id': this.bom_id.id,
                'shift_id': this.shift_id.id or False,
                'operator_id': this.operator_id.id or False,
                'leader_id': this.leader_id.id or False
            })
            manufacturing._onchange_product_id()
            manufacturing._compute_move_raw_ids()
            manufacturing._compute_workorder_ids()

class DSNMPSBU(models.Model):
    _name = "dsn.mps.bu"
    _description = 'DSN MPS BU'
    order = 'level desc'


    demand_line_id = fields.Many2one('dsn.demand.planning.line', tracking=True)
    demand_id = fields.Many2one('dsn.demand.planning', tracking=True)
    product_id = fields.Many2one('product.product', string='Product', tracking=True)
    bom_id = fields.Many2one('mrp.bom', string='Bill of Material', tracking=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', tracking=True)
    production_qty = fields.Float(string='MPS Qty', tracking=True)
    scheduled_date = fields.Date(tracking=True)
    company_id = fields.Many2one('res.company', 'Company', copy=False, readonly=True, help="Comapny", related='demand_id.company_id', tracking=True)
    mo_ids = fields.Many2many('mrp.production', string='Manufacturing Orders')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('progress', 'In Progress'),
        ('to_close', 'To Close'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')], string='State',
       copy=False, index=True, readonly=True,
        store=True, tracking=True,
        help=" * Draft: The MO is not confirmed yet.\n"
             " * Confirmed: The MO is confirmed, the stock rules and the reordering of the components are trigerred.\n"
             " * In Progress: The production has started (on the MO or on the WO).\n"
             " * To Close: The production is done, the MO has to be closed.\n"
             " * Done: The MO is closed, the stock moves are posted. \n"
             " * Cancelled: The MO has been cancelled, can't be confirmed anymore.")
    balance = fields.Float(string='Balance', store=True)
    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True, related='demand_id.type', store=True)
    level = fields.Char()
    operator_id = fields.Many2one('hr.employee', string='Operator')
    leader_id = fields.Many2one('hr.employee', string='Leader')
    shift_id = fields.Many2one('eran.master.shift', string='Shift')


class DSNMRP(models.Model):
    _inherit = 'dsn.mrp'


    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True, related='demand_id.type', store=True)
    quantity_pr = fields.Float(string='Qty PR', compute='compute_quantity_purchase')
    quantity_po = fields.Float(string='Qty PO', compute='compute_quantity_purchase')
    quantity_to_buy = fields.Float(string='Quantity to Buy', compute='compute_quantity_to_buy', store=True)
    default_code = fields.Char(string='Internal Reference', related='product_id.default_code')
    part_name = fields.Char(string='Part Name', related='product_id.name')
    categ_group_id = fields.Many2one('eran.category.group', string="Group Category", related='product_id.category_group_id')

    @api.depends('quantity_po', 'stock_on_hand', 'demand_qty', 'mrp_buffer_stock', 'quantity_pr', 'quantity_po')
    def compute_quantity_to_buy(self):
        for this in self:
            quantity_to_buy = this.demand_qty - this.stock_on_hand + this.mrp_buffer_stock - this.quantity_pr - this.quantity_po
            if quantity_to_buy < 0:
                quantity_to_buy = 0
            this.quantity_to_buy = quantity_to_buy


    def compute_quantity_purchase(self):
        for this in self:
            quantity_pr_line = self.env['purchase.request.line'].sudo().search([
                ('product_id', '=', this.product_id.id),
                ('company_id', '=', this.company_id.id),
                ('request_id.state', '=', 'approved')])
            this.quantity_pr = sum(quantity_pr_line.mapped('product_qty')) - sum(quantity_pr_line.mapped('purchased_qty'))
            if this.quantity_pr < 0:
                this.quantity_pr = 0

            quantity_po_line = self.env['purchase.order.line'].sudo().search([
                ('product_id', '=', this.product_id.id),
                ('company_id', '=', this.company_id.id),
                ('order_id.state', '=', 'purchase')
            ])
            this.quantity_po =  sum(quantity_po_line.mapped('product_qty')) - sum(quantity_po_line.mapped('qty_received'))
            if this.quantity_po < 0:
                this.quantity_po = 0

            this.compute_quantity_to_buy()

    def replace_name(self):
        for this in self:
            sequences_setting = this.env['dsn.mrp.production.sequence.setting'].search([
            ('type', '=', 'mrp'), ('company_id', '=', self.env.company.id)], limit=1)
        
            if not sequences_setting or not sequences_setting.sequence_id:
                raise UserError("You must set sequence MRP in Manufacturing Sequences Settings")
            
            name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
            this.name = name

    def merge_create_pr(self):
        type_list = []
        for this in self:
            if not this.type:
                raise ValidationError(_("Type not detected."))
            if this.type not in type_list:
                type_list.append(this.type)
            
        if len(type_list) != 1:
            raise ValidationError(_("Must be of the same type."))

        res = super(DSNMRP, self).merge_create_pr()
        return res
    
    def view_pr(self):
        for this in self:
            view_tree = self.env.ref('eran_custom.eran_purchase_request_line_tree').id
            action = {
                'name': 'Purchase Request Lines',
                'domain': [('product_id', '=', this.product_id.id), ('company_id', '=', this.company_id.id), 
                    ('request_id.state', '=', 'approved'), ('outstanding_pr', '!=', 0)],
                'view_mode': 'tree',
                'res_model': 'purchase.request.line',
                'views': [(view_tree, 'tree')],
                'type': 'ir.actions.act_window',
                'context': {'create':0, 'copy':0, 'delete':0}
            }
            return action

    def view_po(self):
        for this in self:
            view_tree = self.env.ref('eran_custom.eran_purchase_order_line_tree').id
            action = {
                'name': 'Purchase Order Lines',
                'domain': [('product_id', '=', this.product_id.id), 
                    ('company_id', '=', this.company_id.id), 
                    ('order_id.state', '=', 'purchase'), ('outstanding_po', '!=', 0)],
                'view_mode': 'tree',
                'res_model': 'purchase.order.line',
                'views': [(view_tree, 'tree')],
                'type': 'ir.actions.act_window',
                'context': {'create':0, 'copy':0, 'delete':0}
            }
            return action
        
    def _compute_cost_mrp(self):
        
        price_list = 0
        date = datetime.now()
        pr_line_ids = self.env['purchase.request.line'].sudo().search([('mrp_id', '=', self.id)])
        for pr_line_id in pr_line_ids:
            date = pr_line_id.create_date
            
        vendor_pricelist_ids = self.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', self.product_id.product_tmpl_id.id), ('date_start', '<=', date), ('date_end', '>=',date), ('state', '=', 'done')])
        vendor_pricelist_id = self.env['product.supplierinfo'].sudo().search([('id', '=', max([x.id for x in vendor_pricelist_ids]) if vendor_pricelist_ids else 0)])
        
        for vendor_pricelist in vendor_pricelist_id:
            price_list = vendor_pricelist.price
            
        pr_mrp = sum([x.product_qty for x in pr_line_ids])
        res = pr_mrp * price_list
        
        return res


class DSNMRPWizard(models.TransientModel):
    _inherit = 'dsn.mrp.wizard'


    def get_type(self):
        context = self._context
        active_ids = context.get('active_ids')
        type = False
        for line in active_ids:
            mrp = self.env['dsn.mrp'].browse(line)
            type = mrp.type
        return type

    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], default=get_type)


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
            }
            line_ids.append((0,0, value))
            for mrp in line.mrp_ids:
                origin_list.append(mrp.name)

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

                for line_wizard in self.line_ids:
                    for mrp in line_wizard.mrp_ids:
                        mrp.write({'purchase_request_line_id': pr_line.id})


class DSNMRPLineWizard(models.TransientModel):
    _inherit = 'dsn.mrp.line.wizard'


    allocation_percentage_mrp = fields.Float(related='product_id.allocation_percentage_mrp', string='Allocation Percentage MRP(%)')


class EranMRPNonMaterial(models.Model):
    _name = 'eran.mrp.non.material'
    _description = 'Eran MRP Non Maerial'


    name = fields.Char()
    demand_id = fields.Many2one('dsn.demand.planning', ondelete='cascade', tracking=True)
    product_id = fields.Many2one('product.product', string='Product')
    uom_id = fields.Many2one('uom.uom', string='Purchase UoM')
    bom_id = fields.Many2one('mrp.bom', string='Bill of Material Ref.', tracking=True)
    mrp_buffer_stock = fields.Float(string='Buffer Stock', tracking=True, compute='compute_buffer_stock')
    stock_on_hand = fields.Float(string='Initial Available', tracking=True)
    demand_qty = fields.Float(string='Demand Qty', tracking=True)
    deadline_date = fields.Date(tracking=True)
    quantity_to_buy = fields.Float(string='Quantity to Buy', compute='compute_quantity_purchase')
    company_id = fields.Many2one('res.company', 'Company', copy=False, readonly=True, help="Comapny", default=lambda self: self.env.user.company_id, tracking=True)
    purchase_request_line_ids = fields.One2many('purchase.request.line', 'mrp_non_material_id', string='Purchase Request Line')
    purchase_request_ids = fields.Many2many('purchase.request', string='Purchase Request')
    quantity_pr = fields.Float(string='Qty PR', compute='compute_quantity_purchase')
    quantity_po = fields.Float(string='Qty PO', compute='compute_quantity_purchase')
    received_qty = fields.Float(string='Qty Received', compute='compute_balance')
    balance = fields.Float(string='Balance', compute='compute_balance', store=True)
    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True, related='demand_id.type', store=True)
    default_code = fields.Char(string='Internal Reference', related='product_id.default_code')
    part_name = fields.Char(string='Part Name', related='product_id.name')


    def compute_buffer_stock(self):
        for this in self:
            buffer_stock = self.env['stock.warehouse.orderpoint'].sudo().search([
                    ('product_id', '=', this.product_id.id),
                    ('company_id', '=', this.company_id.id)])
            this.mrp_buffer_stock = sum(buffer_stock.mapped('product_min_qty'))

    def compute_balance(self):
        for this in self:
            received_lines = []
            purchase_line = self.env['purchase.request.line'].sudo().search([
                ('product_id', '=', this.product_id.id),
                ('company_id', '=', this.company_id.id),
                ('mrp_non_material_id', '=', this.id)
            ])
            for pr_line in purchase_line:
                for pr in pr_line.purchase_lines:
                    received_lines.append(pr.qty_received)

            balance = this.demand_qty - sum(received_lines)
            if balance < 0:
                balance = 0
            this.balance = balance
            this.received_qty = sum(received_lines)

    def compute_quantity_purchase(self):
        for this in self:
            quantity_pr_line = self.env['purchase.request.line'].sudo().search([
                ('product_id', '=', this.product_id.id),
                ('company_id', '=', this.company_id.id),
                ('request_id.state', '=', 'approved')])
            this.quantity_pr = sum(quantity_pr_line.mapped('product_qty')) - sum(quantity_pr_line.mapped('purchased_qty'))
            if this.quantity_pr < 0:
                this.quantity_pr = 0

            quantity_po_line = self.env['purchase.order.line'].sudo().search([
                ('product_id', '=', this.product_id.id),
                ('company_id', '=', this.company_id.id),
                ('order_id.state', '=', 'purchase')
            ])
            this.quantity_po =  sum(quantity_po_line.mapped('product_qty')) - sum(quantity_po_line.mapped('qty_received'))
            if this.quantity_po < 0:
                this.quantity_po = 0

            quantity_to_buy = this.demand_qty - this.stock_on_hand + this.mrp_buffer_stock - this.quantity_pr - this.quantity_po
            if quantity_to_buy < 0:
                quantity_to_buy = 0
            this.quantity_to_buy = quantity_to_buy

    def replace_name(self):
        for this in self:
            sequences_setting = this.env['dsn.mrp.production.sequence.setting'].search([
            ('type', '=', 'mrp_non_material'), ('company_id', '=', self.env.company.id)], limit=1)
        
            if not sequences_setting or not sequences_setting.sequence_id:
                raise UserError("You must set sequence MRP Non Material in Manufacturing Sequences Settings")
            
            name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
            this.name = name

    @api.model
    def create(self, vals):
        res = super(EranMRPNonMaterial, self).create(vals)
        res.replace_name()
        return res
    
    def view_buffer_stock(self):
        for this in self:
            view_tree = self.env.ref('stock.view_warehouse_orderpoint_tree_editable').id
            action = {
                'name': 'Replenishment',
                'domain': [('product_id', '=', this.product_id.id), ('company_id', '=', this.company_id.id)],
                'view_mode': 'tree',
                'res_model': 'stock.warehouse.orderpoint',
                'views': [(view_tree, 'tree')],
                'type': 'ir.actions.act_window',
                'context': {'edit': 0, 'create':0, 'copy':0, 'delete':0}
            }
            return action
        
    def view_pr(self):
        for this in self:
            view_tree = self.env.ref('eran_custom.eran_purchase_request_line_tree').id
            action = {
                'name': 'Purchase Request Lines',
                'domain': [('product_id', '=', this.product_id.id), ('company_id', '=', this.company_id.id),
                    ('request_id.state', '=', 'approved'), ('outstanding_pr', '!=', 0)],
                'view_mode': 'tree',
                'res_model': 'purchase.request.line',
                'views': [(view_tree, 'tree')],
                'type': 'ir.actions.act_window',
                'context': {'create':0, 'copy':0, 'delete':0}
            }
            return action
        
    def view_po(self):
        for this in self:
            view_tree = self.env.ref('eran_custom.eran_purchase_order_line_tree').id
            action = {
                'name': 'Purchase Order Lines',
                'domain': [('product_id', '=', this.product_id.id), 
                    ('company_id', '=', this.company_id.id), 
                    ('order_id.state', '=', 'purchase'), ('outstanding_po', '!=', 0)],
                'view_mode': 'tree',
                'res_model': 'purchase.order.line',
                'views': [(view_tree, 'tree')],
                'type': 'ir.actions.act_window',
                'context': {'create':0, 'copy':0, 'delete':0}
            }
            return action
        
    def create_buffer_stock(self):
        for this in self:
            view_form = self.env.ref('mrp_forecast_order.dsn_view_warehouse_orderpoint_form').id
            route = self.env.ref('purchase_stock.route_warehouse0_buy').id
            action = {
                'name': 'Replenishment',
                'domain': [],
                'view_mode': 'form',
                'res_model': 'stock.warehouse.orderpoint',
                'views': [(view_form, 'form')],
                'type': 'ir.actions.act_window',
                'context': {
                    'default_product_id': this.product_id.id,
                    'default_active': True,
                    'default_route_id': route,
                }
            }

            return action
        
    def create_pr(self):
         for this in self:
            if this.quantity_to_buy == 0:
                raise ValidationError(_("Quantity to buy has been met by the quanity of Purchase Request."))
            
            if this.purchase_request_ids:
                raise ValidationError(_("Purchase request has already been made, so you can't make a purchase request again."))

            picking_type = self.env['stock.picking.type'].sudo().search([
                ('company_id', '=', this.company_id.id),
                ('code', '=', 'incoming')], limit=1)

            line_ids = [(0,0,{
                'product_id': this.product_id.id,
                'product_qty': this.quantity_to_buy - this.quantity_pr,
                'product_uom_id': this.uom_id.id,
                'mrp_non_material_id': this.id,
            })]

            pr = self.env['purchase.request'].sudo().create({
                'requested_by': self.env.user.id,
                'company_id': this.company_id.id,
                'date_start': fields.date.today(),
                'picking_type_id': picking_type.id or False,
                'line_ids': line_ids,
                'origin': this.name})

            for pr_line in pr.line_ids:
                pr_line.name = str(pr.name) + ' ' + str(pr_line.product_id.display_name)

    def merge_create_pr(self):
        type_list = []
        for this in self:
            if this.quantity_to_buy == 0:
                raise ValidationError(_('%s, quantity already fulfilled.', this.name))
            
            if this.purchase_request_ids:
                raise ValidationError(_('%s, purchase request already made.', this.name))

            if not this.type:
                raise ValidationError(_("Type not detected."))
            if this.type not in type_list:
                type_list.append(this.type)
            
        if len(type_list) != 1:
            raise ValidationError(_("Must be of the same type."))

        action = self.env['ir.actions.actions']._for_xml_id('eran_custom.eran_action_mrp_non_material_wizard')
        return action

class EranDemandOrderForecast(models.Model):
    _name = "eran.demand.order.forecast"
    _description = "Eran Demand Order Forecast"

    name = fields.Char()
    demand_id = fields.Many2one('dsn.demand.planning', ondelete='cascade', tracking=True)
    product_id = fields.Many2one('product.product', string='Product')
    uom_id = fields.Many2one('uom.uom', string='UoM')
    bom_id = fields.Many2one('mrp.bom', string='Bill of Material Ref.', tracking=True)
    demand_qty = fields.Float(string='Demand Qty', tracking=True)
    forecast_date = fields.Date(tracking=True)
    company_id = fields.Many2one('res.company', 'Company', copy=False, readonly=True, help="Comapny", default=lambda self: self.env.user.company_id, tracking=True)
    type = fields.Selection([('forecast_order', 'Forecast Order'), ('fix_order', 'Fix Order')], tracking=True, related='demand_id.type', store=True)
    default_code = fields.Char(string='Internal Reference', related='product_id.default_code')
    part_name = fields.Char(string='Part Name', related='product_id.name')
    product_type = fields.Selection([('fg', 'FG'), ('sfg', 'SFG'), ('material', 'Material')])
    ref = fields.Char()
    parent_id = fields.Many2one('eran.demand.order.forecast', string='Parent')
    bom_type = fields.Selection(related='bom_id.type', tracking=True)


    def replace_name(self):
        for this in self:
            sequences_setting = this.env['dsn.mrp.production.sequence.setting'].search([
            ('type', '=', 'demand_forecast'), ('company_id', '=', self.env.company.id)], limit=1)
        
            if not sequences_setting or not sequences_setting.sequence_id:
                raise UserError("You must set sequence Demand Forecast in Manufacturing Sequences Settings")
            
            name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
            this.name = name

    @api.model
    def create(self, vals):
        res = super(EranDemandOrderForecast, self).create(vals)
        res.replace_name()
        return res
    

class DSNMPSWizard(models.TransientModel):
    _inherit = 'dsn.mps.wizard'

    def _get_default_demand_lines(self):
        context = self._context
        model = context.get('active_model')
        return self.env[model].browse(context.get('active_ids')).ids


    demand_line_id = fields.Many2one('dsn.demand.planning.line', string='Demand Order Detail', default=False)
    demand_line_ids = fields.Many2many('dsn.demand.planning.line', string='Demand Order Detail', default=_get_default_demand_lines)


    def import_mps(self):
        mps_bu = self.env['dsn.mps.bu'].search([]).unlink()
        self.ensure_one()
        if not self.file:
            raise ValidationError(_('Please upload your file'))
        content_type = mimetypes.guess_type(self.file_name)
        self.file = base64.decodebytes(self.file)
        self.file_type = content_type[0]

        options = {
            'headers': True, 'advanced': True, 'keep_matches': False, 'encoding': 'utf-8', 'separator': ',', 'quoting': '"', 
            'date_format': '', 'datetime_format': '', 'float_thousand_separator': ',', 'float_decimal_separator': '.', 
            'fields': [], 'use_queue': False
        }
        format_header = ['ID','Demand Order','Product','BoM','MPS Qty','Scheduled Date','Shift','Leader','Operator']
        file_header = list(itertools.islice(self._read_file(options), 0, None))[1][0]
        if format_header != file_header:
            raise ValidationError(_("Error MPS Import: Invalid file template"))
        
        datas = itertools.islice(self._read_file(options), 1, None)
        for data in datas:
            index_of_interest = None
            for i, sublist in enumerate(data):
                if sublist == ['ID','Demand Order','Product','BoM','MPS Qty','Scheduled Date','Shift','Leader','Operator']:
                    index_of_interest = i
                    break

            desired_data = data[index_of_interest + 1:]
            no = 0
            row = 2
            mps_bu_ids = []
            demand_list = []
            for line in desired_data:
                demand_order = line[1]
                record_demand_order = self.env['dsn.demand.planning'].search([('name', '=', demand_order)], limit=1)
                if not record_demand_order:
                     raise ValidationError(_('Demand order %s in row %s is not found, make sure the input is correct, or check for spaces.', demand_order, row))  

                product = line[2]
                default_code = product.split('[')[1].split(']')[0]
            
                record_product = self.env['product.product'].search([('default_code', '=', default_code)], limit=1)
                if not record_product:
                    raise ValidationError(_('Product %s in row %s is not found, make sure the input is correct, or check for spaces.', product, row))

                record_bom = self.env['mrp.bom'].search([('product_tmpl_id', '=', record_product.product_tmpl_id.id)],limit=1)
                if not record_bom:
                    raise ValidationError(_('BoM %s in row %s is not found, make sure the input is correct, or check for spaces.', record_product.product_tmpl_id.display_name, row))
                                
                mps_qty = line[4]

                if '/' in line[5]:
                    scheduled_date = datetime.strptime(line[5], "%d/%m/%Y").date()
                else:
                    date_object = datetime.strptime(line[5], "%Y-%m-%d")
                    scheduled_date = date_object.strftime("%d/%m/%Y")
                    scheduled_date = datetime.strptime(scheduled_date, "%d/%m/%Y").date()


                shift = line[6]
                record_shift = self.env['eran.master.shift'].search([('name', '=', shift)], limit=1)

                leader = line[7]
                record_leader = self.env['hr.employee'] 
                if leader != '':
                    record_leader = self.env['hr.employee'].sudo().search([('name', 'ilike', leader)], limit=1)

                operator = line[8]
                record_operator = self.env['hr.employee']
                if operator != '':
                    record_operator = self.env['hr.employee'].sudo().search([('name', 'ilike', operator)], limit=1)

                demand_line_id = self.env['dsn.demand.planning.line'].search([('id', '=', int(line[0]))])
                if not demand_line_id:
                    raise ValidationError(_('Data with ID %s Demand Order : %s,  Product : %s, BoM : %s not found',  int(line[0]), record_demand_order.display_name, record_product.display_name, record_bom.display_name))
                    
                if scheduled_date > demand_line_id.deadline_date:
                    raise ValidationError(_('Schedule date %s cannot be greater than to deadline date %s, for row %s', scheduled_date, demand_line_id.deadline_date, row))

                value = {
                    'product_id': demand_line_id.product_id.id,
                    'demand_line_id': demand_line_id.id,
                    'demand_id': demand_line_id.demand_id.id,
                    'bom_id': demand_line_id.bom_id.id,
                    'uom_id': demand_line_id.product_id.uom_id.id,
                    'production_qty': mps_qty,
                    'scheduled_date': scheduled_date,
                    'level': demand_line_id.level,
                    'shift_id': record_shift.id or False,
                    'leader_id': record_leader.id or False,
                    'operator_id': record_operator.id or False,
                }
                mps = self.env['dsn.mps.bu'].create(value)
                mps_bu_ids.append(mps.id)
                demand_list.append(demand_line_id.demand_id.id)
                # demand_line_id._constrains_mps_qty()

                no += 1

        mps_x_list = []
        mps_bu = self.env['dsn.mps.bu'].search([('id', 'in', mps_bu_ids)], order='level asc')
        demand_line_id_list = []
        check_demand_line_double = []
        for mps_r in mps_bu:
            value = {
                'product_id': mps_r.product_id.id,
                'demand_line_id': mps_r.demand_line_id.id,
                'demand_id': mps_r.demand_id.id,
                'bom_id': mps_r.bom_id.id,
                'uom_id': mps_r.uom_id.id,
                'production_qty': mps_r.production_qty,
                'scheduled_date': mps_r.scheduled_date,
                'shift_id': mps_r.shift_id.id or False,
                'leader_id': mps_r.leader_id.id or False,
                'operator_id': mps_r.operator_id.id or False,
                'level': mps_r.level,
            }

            mps_x = self.env['dsn.mps'].create(value)
            mps_x.demand_line_id._constrains_mps_qty()
            mps_x_list.append(mps_x.id)


        
        mps_bu = self.env['dsn.mps.bu'].search([]).unlink()
        view_tree = self.env.ref('mrp_forecast_order.dsn_view_mps_tree').id
        action = {
            'name': 'MPS',
            'domain': [('id', 'in', mps_x_list)],
            'view_mode': 'tree',
            'res_model': 'dsn.mps',
            'views': [(view_tree, 'tree')],
            'type': 'ir.actions.act_window',
            'context': {'edit': 0, 'create':0, 'copy':0, 'delete':0, 'search_default_demand_order': 1}
        }

        return action


class PartnerXlsx(models.AbstractModel):
    _inherit = 'report.mrp_forecast_order.template_import_mps_report_xlsx'


    def generate_xlsx_report(self, workbook, data, objects):
        sheet = workbook.add_worksheet('Template MPS')

        text_title_style = workbook.add_format({'font_name': 'Calibri', 'font_size': 11, 'bold': True,'text_wrap': True,
            'align': 'center', 'font_color': '#028096'})
        text_header_style1 = workbook.add_format({'font_name': 'Calibri', 'font_size': 11, 'text_wrap': True, 'align': 'left',
            'border':False})
        num_style = workbook.add_format({'num_format': '#,##0.00', 'font_name': 'Calibri', 'font_size': 11, 'align': 'left'})
        text_thead_style = workbook.add_format({'font_name': 'Calibri', 'font_size': 11, 'text_wrap': True, 'align': 'center',
            'bg_color': '#E1E1E1', 'border':True})
        
        sheet.set_column('A:A', 5)
        sheet.set_column('B:B', 23)
        sheet.set_column('C:C', 55)
        sheet.set_column('D:D', 55)
        sheet.set_column('E:E', 10)
        sheet.set_column('F:F', 15)
        sheet.set_column('G:G', 5)
        sheet.set_column('H:H', 15)
        sheet.set_column('I:J', 15)


        sheet.write_row(0, 0, ['ID'], text_thead_style)
        sheet.write_row(0, 1, ['Demand Order'], text_thead_style)
        sheet.write_row(0, 2, ['Product'], text_thead_style)
        sheet.write_row(0, 3, ['BoM'], text_thead_style)
        sheet.write_row(0, 4, ['MPS Qty'], text_thead_style)
        sheet.write_row(0, 5, ['Scheduled Date'], text_thead_style)
        sheet.write_row(0, 6, ['Shift'], text_thead_style)
        sheet.write_row(0, 7, ['Leader'], text_thead_style)
        sheet.write_row(0, 8, ['Operator'], text_thead_style)

        row = 1
        schedule_date = [str(fields.date.today().strftime('%d/%m/%Y'))]
        for line in objects.demand_line_ids:
            sheet.write_column(row, 0, [line.id], text_header_style1)
            sheet.write_column(row, 1, [line.demand_id.display_name], text_header_style1)
            sheet.write_column(row, 2, [line.product_id.display_name], text_header_style1)
            sheet.write_column(row, 3, [line.bom_id.display_name], text_header_style1)
            sheet.write_column(row, 4, [line.production_qty], num_style)
            sheet.write_column(row, 5, schedule_date, text_header_style1)
            sheet.write_column(row, 6, ['1'], text_header_style1)
            sheet.write_column(row, 7, ['Admin'], text_header_style1)
            sheet.write_column(row, 8, ['Admin'], text_header_style1)

            row += 1
            

class EranDemandOrder(models.Model):
    _inherit = 'eran.demand.order.forecast'
    
    categ_group_id = fields.Many2one('eran.category.group', string="Group Category", related='product_id.category_group_id')