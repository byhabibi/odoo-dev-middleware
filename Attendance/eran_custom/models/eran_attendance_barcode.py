from odoo import models, fields, api
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def name_get(self):
        _logger.warning("=== NAME_GET WORKORDER ===")

        result = []

        for rec in self:

            mo = rec.production_id.name or "-"
            wo = rec.name or "-"
            product = rec.production_id.product_id.display_name or "-"
            wc = rec.workcenter_id.name or "-"

            name = f"{mo} | {wo} | {product} | {wc}"

            result.append((rec.id, name))

        return result

class BarcodeScanLog(models.Model):
    _name = "barcode.scan.log"
    _description = "Barcode Scan Log"
    _order = "scan_datetime desc"

    employee_id = fields.Many2one(
        "hr.employee",
        required=True
    )

    barcode = fields.Char(
        related="employee_id.barcode",
        store=True
    )

    scan_datetime = fields.Datetime(
        required=True
    )


class MesScanApproval(models.Model):
    _name = "mes.scan.approval"
    _description = "MES Scan Approval"
    _order = "scan_time desc"

    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
    )

    barcode = fields.Char(
        related="employee_id.barcode",
        store=True,
    )

    check_in = fields.Datetime()

    scan_time = fields.Datetime(
        default=fields.Datetime.now
    )

    shift_id = fields.Many2one(
        "eran.master.shift"
    )

    state = fields.Selection([
        ("draft", "Waiting"),
        ("ready", "Ready"),
        ("running", "Running"),
        ("done", "Done"),
    ], default="ready")

    note = fields.Text()

    line_ids = fields.One2many(
        "mes.scan.approval.line",
        "approval_id",
        string="Today's Work Orders",
    )


class MesScanApprovalLine(models.Model):
    _name = "mes.scan.approval.line"
    _description = "MES Scan Approval Line"
    _order = "id"

    #Ini relasi nih bang

    approval_id = fields.Many2one(
        "mes.scan.approval",
        required=True,
        ondelete="cascade",
    )

    workorder_id = fields.Many2one(
        "mrp.workorder",
        required=True,
    )

    # Ini related to my love story :(

    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=True,
    )

    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,
    )

    leader_id = fields.Many2one(
        related="workorder_id.leader_id",
        store=True,
    )

    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=True,
    )

    # Status Hubungan 

    wo_state = fields.Selection(
        related="workorder_id.state",
        store=True,
        string="WO Status",
    )

    mes_state = fields.Selection([
        ("waiting", "Waiting"),
        ("running", "Running"),
        ("done", "Done"),
    ], default="waiting")

    operator_id = fields.Many2one(
        "hr.employee"
    )

    shift_id = fields.Many2one(
        "eran.master.shift"
    )

    # Waktu 

    scan_time = fields.Datetime()

    start_time = fields.Datetime()

    stop_time = fields.Datetime()

    duration = fields.Float()

    # Button

    def action_start(self):

        self.ensure_one()

        vals = {
            "mes_state": "running",
            "operator_id": self.approval_id.employee_id.id,
            "shift_id": self.approval_id.shift_id.id,
            "scan_time": self.approval_id.scan_time,
        }

        if not self.start_time:
            vals["start_time"] = fields.Datetime.now()

        self.write(vals)

        return True
    
    def action_stop(self):

        self.ensure_one()

        self.write({
            "mes_state": "done",
            "stop_time": fields.Datetime.now(),
        })

        return True






