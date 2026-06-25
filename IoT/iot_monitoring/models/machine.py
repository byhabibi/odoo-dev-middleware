from odoo import models, fields, api
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class IoTMachine(models.Model):
    _name = 'iot.machine'
    _description = 'IoT Machine'

    def action_open_requests(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Operator Request",
            "res_model": "mes.request",
            "view_mode": "tree,form",
            "target": "current",
            "domain": [
                ("machine_id", "=", self.id),
                ("request_state", "=", "waiting"),
            ],
        }

    name = fields.Char(required=True)
    area_id = fields.Many2one('iot.area', string='Area')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    sensor_data_ids = fields.One2many('iot.sensor.data', 'machine_id')
    code = fields.Char(string='Machine Code')
    plc_offset = fields.Integer(default=0, store=True)

    # Core
    current_workorder_id = fields.Many2one('mrp.workorder')
    counter = fields.Integer(default=0, store=True)
    latest_timestamp = fields.Datetime(store=True)

    # Information Card 
    # total_machine = len(workcenter_id)

    # Product Plan
    product_qty = fields.Integer(compute='_compute_production_status', store = False)

    # Achievement Rate
    achievement_rate = fields.Float(string='Achievement Rate (%)', compute='_compute_achievement_rate', store=True)

    @api.depends('counter', 'product_qty')
    def _compute_achievement_rate(self):
        for rec in self:
            if rec.product_qty :
                rec.achievement_rate = (rec.counter / rec.product_qty * 100)
            else :
                rec.achievement_rate = 0

    # Computed Status Condition Plan vs Actual
    plan_status = fields.Selection([
        ('ok','OK'),
        ('low','Low'),
    ], compute = '_compute_plan_status', store=False)

    # Shift & MP
    shift_status = fields.Char(compute='_compute_production_status', store=False)
    mp_name = fields.Char(compute='_compute_production_status',  store=False)

    # UI computed
    production_status = fields.Char(
        compute='_compute_production_status',
        
        store=False
    )
    current_product = fields.Char(
        compute='_compute_production_status',
        store=False
    )

    # Counter terakhir sebelum ganti WO
    latest_counter = fields.Integer(
        compute='_compute_latest_counter',
        store=False
    )

    # Request dari MES
    request_count = fields.Integer(
        compute="_compute_request_count",
        string="Request"
    )

    @api.depends()
    def _compute_request_count(self):
        Request = self.env["mes.request"]

        for machine in self:
            machine.request_count = Request.search_count([
                ("machine_id", "=", machine.id),
                ("request_state", "=", "waiting")
            ])

    @api.depends('counter', 'product_qty')
    def _compute_plan_status(self):
        for machine in self:
            if machine.counter >= machine.product_qty and machine.product_qty > 0:
                machine.plan_status = 'ok'
            else:
                machine.plan_status = 'low'

    @api.depends('counter')
    def _compute_latest_counter(self):
        for machine in self:
            machine.latest_counter = machine.counter

    def _get_active_workorder(self):
        self.ensure_one()
        if not self.workcenter_id:
            return False
        return self.env['mrp.workorder'].search([
            ('workcenter_id', '=', self.workcenter_id.id),
            ('state', '=', 'progress'),
        ], order='date_start desc', limit=1)

    @api.depends()
    def _compute_production_status(self):
        for machine in self:
            wo = machine._get_active_workorder()

            if wo and wo.state == 'progress':

                machine.production_status = 'progress'
                machine.current_product = wo.product_id.name or '-'
                machine.product_qty = wo.production_id.product_qty or 0

                # SHIFT
                if 'shift_id' in wo.production_id._fields:
                    shift = wo.production_id['shift_id']
                    machine.shift_status = shift.name if shift else '-'
                else:
                    machine.shift_status = '-'

                # MP
                if 'operator_id' in wo.production_id._fields:
                    op = wo.production_id['operator_id']
                    machine.mp_name = op.name if op else '-'
                else:
                    machine.mp_name = '-'

            else:
                machine.production_status = 'stop'
                machine.current_product = '-'
                machine.product_qty = 0
                machine.shift_status = '-'
                machine.mp_name = '-'

    def _sync_workorder(self):
        for machine in self:
            wo = machine._get_active_workorder()
            current_wo_id = machine.current_workorder_id.id if machine.current_workorder_id else False
            new_wo_id = wo.id if wo else False

            if new_wo_id != current_wo_id:
                # Ambil nilai PLC terakhir dari sensor log
                last_sensor = self.env['iot.sensor.data'].search([
                    ('machine_id', '=', machine.id)
                ], limit=1, order='timestamp desc')
                
                last_plc_value = last_sensor.counter if last_sensor else 0

                machine.write({
                    'current_workorder_id': new_wo_id,
                    'counter': 0,
                    'plc_offset': last_plc_value,  # ← nilai PLC absolut terakhir
                    'latest_timestamp': fields.Datetime.now(),
                })

    def action_open_workorders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Work Orders - ' + self.name,
            'res_model': 'mrp.workorder',
            'view_mode': 'kanban,list,form',
            'domain': [
                ('workcenter_id', '=', self.workcenter_id.id),
                ('state', 'in', ['ready', 'progress']),
            ],
            'target': 'new',
        }

    def action_open_monitoring(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Monitoring - ' + self.name,
            'res_model': 'iot.production.summary',
            'view_mode': 'graph',
            'domain': [('machine_id', '=', self.id)],
            'context': {'default_machine_id': self.id},
            'target': 'current',
        }
    
    @api.model
    def _cron_sync_all_workorders(self):
        machines = self.search([])
        for machine in machines:
            wo = machine._get_active_workorder()
            current_wo_id = machine.current_workorder_id.id if machine.current_workorder_id else False
            new_wo_id = wo.id if wo else False

            if new_wo_id != current_wo_id:
                # Ambil nilai PLC terakhir dari sensor log
                last_sensor = self.env['iot.sensor.data'].search([
                    ('machine_id', '=', machine.id)
                ], limit=1, order='timestamp desc')
                
                last_plc_value = last_sensor.counter if last_sensor else 0

                machine.write({
                    'current_workorder_id': new_wo_id,
                    'counter': 0,
                    'plc_offset': last_plc_value,  # ← nilai PLC absolut terakhir
                    'latest_timestamp': fields.Datetime.now(),
                })

    @api.model
    def create(self, vals):
        if not vals.get('code') and vals.get('name'):
            vals['code'] = vals['name'].replace(" ", "").upper()
        return super().create(vals)

    def write(self, vals):
        if 'name' in vals and 'code' not in vals:
            vals['code'] = vals['name'].replace(" ", "").upper()
        return super().write(vals)
    
    last_hour_counter = fields.Integer(
        string='Last Hour Counter'
    )

    actual_sph = fields.Integer(
        string='Actual SPH'
    )

    sph_target = fields.Integer(
        related = 'workcenter_id.sph_machine',
        string = 'SPH Target'
    )
  
    @api.model
    def cron_generate_sph(self):

        for machine in self.search([]):

            machine.actual_sph = (
                machine.counter -
                machine.last_hour_counter
            )

            machine.last_hour_counter = machine.counter

    @api.depends('product_qty')
    def _compute_sph_target(self):
        for rec in self:

            shift_hours = 8

            if rec.product_qty:
                rec.sph_target = int(
                    rec.product_qty / shift_hours
                )
            else:
                rec.sph_target = 0