from odoo import models, fields


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

    # =========================
    # OPERATOR
    # =========================

    employee_id = fields.Many2one(
        "hr.employee",
        required=True
    )

    barcode = fields.Char(
        related="employee_id.barcode",
        store=True
    )

    shift_id = fields.Many2one(
        "eran.master.shift",
        string="Shift"
    )

    workcenter_id = fields.Many2one(
        "mrp.workcenter",
        string="Work Center"
    )

    # =========================
    # SCAN
    # =========================

    check_in = fields.Datetime()

    scan_time = fields.Datetime()

    # =========================
    # MES
    # =========================

    production_id = fields.Many2one(
        "mrp.production"
    )

    workorder_id = fields.Many2one(
        "mrp.workorder"
    )

    # =========================
    # PRODUKSI
    # =========================

    qty_target = fields.Float()

    qty_actual = fields.Float(default=0)

    sph = fields.Integer()

    # =========================
    # STATUS
    # =========================

    state = fields.Selection([
        ("draft", "Waiting"),
        ("ready", "Ready"),
        ("running", "Running"),
        ("done", "Done"),
    ], default="draft")

    start_time = fields.Datetime()

    stop_time = fields.Datetime()

    duration = fields.Float()

    note = fields.Text()

    def action_approve(self):
        self.write({
            "state": "ready"
        })
        return True

    def action_reject(self):
        self.write({
            "state": "draft"
        })
        return True



