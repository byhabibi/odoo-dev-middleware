from odoo import models, fields, api, _

class EranProductionPerformanceReport(models.Model):
    _name = 'eran.production.performance.report'
    _auto = False
    _description = 'Production Performance Report'
    _order = 'schedule_date desc' # ✅ BARIS INI DITAMBAH


    manufacture = fields.Char(string="No MO")
    schedule_date = fields.Datetime(string='Schedule Date')
    date_done = fields.Datetime(string='Effective Date')
    product_id = fields.Many2one('product.product', string='Product')
    operator_id = fields.Many2one('hr.employee', string='Operator')
    product_qty = fields.Float('Qty Produksi')
    qty_plan = fields.Float('Qty Plan')
    qty_keppin = fields.Float('Qty Keppin')
    mrp_workcenter_group_id = fields.Many2one('mrp.workcenter', string="Workcenter Group")
    short_string = fields.Boolean(string="Short string")
    category_group_id = fields.Many2one('eran.category.group', string='Category Group')

    def init(self):
        self._cr.execute("""
        DROP VIEW IF EXISTS eran_production_performance_report;
        CREATE OR REPLACE VIEW eran_production_performance_report AS (
            SELECT
                row_number() over (ORDER BY mp.procurement_group_id) AS id,
                pc.name as manufacture,
                MIN(mp.date_planned_start) as schedule_date,
                MAX(mp.date_finished) as date_done,
                mp.product_id as product_id,
                mp.mrp_workcenter_group_id as mrp_workcenter_group_id,
                pt.short_string as short_string,
                pt.category_group_id AS category_group_id,
                MIN(mp.operator_id) as operator_id,
                SUM(mp.product_qty) as product_qty,
                MIN(mp.qty_plan) as qty_plan,
                (SUM(mp.product_qty) - MIN(mp.qty_plan)) as qty_keppin
            FROM 
                mrp_production as mp
                INNER JOIN procurement_group pc ON mp.procurement_group_id = pc.id
                INNER JOIN product_product pp ON mp.product_id = pp.id
                INNER JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE
                mp.state = 'done'
            GROUP BY 
                mp.procurement_group_id, pc.name, mp.product_id, 
                pt.category_group_id, mp.mrp_workcenter_group_id, pt.short_string
        )
        """)
   
    
    # def init(self):
    #     # self._cr.execute("""
    #     #                 DROP VIEW IF EXISTS eran_production_performance_report;
    #     #                 CREATE OR REPLACE VIEW eran_production_performance_report AS (
    #     #                 SELECT
    #     #                     row_number() over (ORDER BY mp.id) AS id,
    #     #                     mp.id as manufacture_id,
    #     #                     mp.date_planned_start as schedule_date,
    #     #                     mp.date_finished as date_done,
    #     #                     mp.product_id as product_id,
    #     #                     mp.operator_id as operator_id,
    #     #                     mp.product_qty as product_qty,
    #     #                     mp.qty_plan as qty_plan,
    #     #                     mp.qty_keppin as qty_keppin
    #     #                 FROM 
    #     #                     mrp_production as mp
    #     #                 WHERE
    #     #                     mp.state = 'done'
    #     #                 )
    #     #                 """)

    #     self._cr.execute("""
    #                     DROP VIEW IF EXISTS eran_production_performance_report;
    #                     CREATE OR REPLACE VIEW eran_production_performance_report AS (
    #                     SELECT
    #                         row_number() over (ORDER BY mp.procurement_group_id) AS id,
    #                         pc.name as manufacture,
    #                         (select mp2.date_planned_start from mrp_production as mp2 
    #                         where mp2.procurement_group_id = mp.procurement_group_id 
    #                         order by mp2.id asc limit 1) as schedule_date,
    #                         (select mp2.date_finished from mrp_production as mp2 
    #                         where mp2.procurement_group_id = mp.procurement_group_id 
    #                         order by mp2.id desc limit 1) as date_done,
    #                         mp.product_id as product_id,
    #                         mp.mrp_workcenter_group_id as mrp_workcenter_group_id,
    #                         pt.short_string as short_string,
    #                         pt.category_group_id AS category_group_id,
    #                         (select mp2.operator_id from mrp_production as mp2 
	#                         where mp2.procurement_group_id = mp.procurement_group_id order by mp2.id asc limit 1) as operator_id,
    #                         sum(mp.product_qty) as product_qty,
    #                         (select mp2.qty_plan from mrp_production as mp2 
    #                         where mp2.procurement_group_id = mp.procurement_group_id order by mp2.id asc limit 1) as qty_plan,
    #                         (sum(mp.product_qty) - (select mp2.qty_plan from mrp_production as mp2 
    #                         where mp2.procurement_group_id = mp.procurement_group_id order by mp2.id asc limit 1))  as qty_keppin
    #                     FROM 
    #                         mrp_production as mp
    #                         inner join procurement_group pc
    #                         on mp.procurement_group_id = pc.id
    #                         inner join product_product pp
    #                         on mp.product_id = pp.id
    #                         inner join product_template pt
    #                         on pp.product_tmpl_id = pt.id
    #                     WHERE
    #                         mp.state = 'done'
    #                     group by mp.procurement_group_id, pc.name, mp.product_id, pt.category_group_id, mp.operator_id, mp.mrp_workcenter_group_id, pt.short_string
    #                     )
    #                     """)