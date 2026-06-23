from odoo import models, fields

class IoTProductionSummary(models.Model):
    _name = 'iot.production.summary'
    _description = 'Production Summary Plan vs Actual'
    _auto = False

    machine_id = fields.Many2one('iot.machine', string='Mesin')
    product_name = fields.Char(string='Product')
    type = fields.Char(string='Type')
    qty = fields.Float(string='Qty (pcs)')
    sequence = fields.Integer()

    def init(self):
        self.env.cr.execute("""
            DROP VIEW IF EXISTS iot_production_summary;
            CREATE VIEW iot_production_summary AS (
                            
                -- 🟠 ACTUAL
                SELECT
                    ROW_NUMBER() OVER () as id,
                    m.id as machine_id,
                    pt.name->>'en_US' as product_name,
                    '1. Plan' as type,
                    mo.product_qty as qty
                FROM iot_machine m
                JOIN mrp_workorder wo ON m.current_workorder_id = wo.id
                JOIN mrp_production mo ON wo.production_id = mo.id
                JOIN product_product pp ON wo.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                WHERE wo.state IN ('progress', 'ready')

                UNION ALL

                -- 🔵 PLAN
                SELECT
                    ROW_NUMBER() OVER () + 100000 as id,
                    m.id as machine_id,
                    pt.name->>'en_US' as product_name,
                    '2. Actual' as type,
                    m.counter as qty
                FROM iot_machine m
                JOIN mrp_workorder wo ON m.current_workorder_id = wo.id
                JOIN product_product pp ON wo.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                WHERE wo.state IN ('progress', 'ready')
            )
        """)