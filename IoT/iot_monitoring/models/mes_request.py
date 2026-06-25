from odoo import models, fields

class OperatorRequest(models.Model):
    _name = "mes.request"
    _description = "MES Operator Request"
    _order = "request_time desc"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        required=True
    )

    machine_id = fields.Many2one(
        "iot.machine",
        string="Machine",
        required=True
    )

    workcenter_id = fields.Many2one(
        "mrp.workcenter",
        string="Work Center"
    )

    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order"
    )

    workorder_id = fields.Many2one(
        "mrp.workorder",
        string="Work Order"
    )

    attendance_id = fields.Many2one(
        "hr.attendance",
        string="Attendance"
    )

    check_in = fields.Datetime()

    request_time = fields.Datetime(
        default=fields.Datetime.now
    )

    request_state = fields.Selection([
        ("waiting", "Waiting Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ], default="waiting")

    wo_state = fields.Char(
        string="WO Status"
    )