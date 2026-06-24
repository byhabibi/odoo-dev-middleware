from odoo import models, fields, api, _

class EranProductionReport(models.Model):
    _name = 'eran.production.report'
    _auto = False
    _description = 'Production Report'
    
    manufacture_id = fields.Many2one('mrp.production', string="No MO")
    date = fields.Datetime(string='Date')
    product_id = fields.Many2one("product.product", string="Product")
    plan_qty = fields.Float(string='Plan')
    shift_id = fields.Many2one("eran.master.shift", string="Shift")
    
    operator_id = fields.Many2one("hr.employee", string="Operator")
    operator_id2 = fields.Many2one("hr.employee", string="Operator 2")
    leader_id = fields.Many2one("hr.employee", string="Leader")
    product_uom_id = fields.Many2one("uom.uom", string="Unit")
    quantity_ok = fields.Float(string='OK')
    quantity_ng = fields.Float(string='NG')
    qty_stroke = fields.Float(string="Qty Stroke")
    time_cycle = fields.Float(string="Time Cycle")
    
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    operation = fields.Char(string="Operation")
    mesin = fields.Many2one('mrp.workcenter', string='Mesin')
    line_stop_ids = fields.Many2many('mrp.workcenter.productivity', string='Problem Line Stop', related='workorder_id.activity_ids')
    problem_ng_ids = fields.Many2many('eran.no.good', string='Problem NG', related='workorder_id.problem_ng_ids')
    lot_id = fields.Many2one('stock.lot', string="Lot", related='workorder_id.finished_lot_id')
    # code baru
    category_group_id = fields.Many2one('eran.category.group', string='Category Group')
    workcenter_group_id = fields.Many2one('eran.work.center.group', related='mesin.workcenter_group_id', store=True, string="Work Center Group", readonly=True)
    
    def init(self):
        self._cr.execute("""
                        DROP VIEW IF EXISTS eran_production_report;
                        CREATE OR REPLACE VIEW eran_production_report AS (
                        SELECT
                            row_number() over (ORDER BY workorder.id) AS id,
                            production.id as manufacture_id,
                            workorder.id as workorder_id,
                            production.date_planned_start as date,
                            production.product_id as product_id,
                            pt.category_group_id as category_group_id,
                            workorder.name as operation,
                            workorder.workcenter_id as mesin,
                            workorder.time_cycle as time_cycle,
                            production.product_qty as plan_qty,
                            production.shift_id as shift_id,
                            production.operator_id as operator_id,
                            production.operator_id2 as operator_id2,
                            production.leader_id as leader_id,
                            production.product_uom_id as product_uom_id,
                            (production.product_qty - workorder.ng_qty) as quantity_ok,
                            workorder.ng_qty as quantity_ng,
                            workorder.default_capacity as qty_stroke,
                            workorder.workcenter_group_id as workcenter_group_id
                            
                        FROM 
                            mrp_workorder as workorder
                        LEFT JOIN
                            mrp_production as production on production.id = workorder.production_id
                        LEFT JOIN
                            product_product pp on production.product_id = pp.id
                        LEFT JOIN
                            product_template pt on pp.product_tmpl_id = pt.id 
                        WHERE
                            workorder.state = 'done'
                        )
                        """)
    
    
    # def _get_data_operations_ids(self):
    #     # workcenter_ids = self.env['mrp.workcenter'].sudo().search([('production_id.id', '=', self.manufacture_id.id)])
    #     # for ids in workcenter_ids:
    #     #     self.operation_ids = ids.mapped('id').ids
    #     for rec in self:
    #         rec.operation_ids = rec.manufacture_id.mapped('workorder_ids').ids