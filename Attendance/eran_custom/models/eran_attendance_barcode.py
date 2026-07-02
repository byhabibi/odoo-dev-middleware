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

    workorder_ids = fields.Many2one(
        "mrp.workorder"
    )

    # =========================
    # PRODUKSI
    # =========================

    qty_target = fields.Float()

    qty_actual = fields.Float(default=0)

    sph = fields.Integer()


    # ========================
    # WORK ORDER
    # ========================

    workorder_info = fields.Html(
        string="Today's Assignment",
        compute="_compute_workorder_info",
        sanitize=False,
    )

    @api.depends("check_in", "employee_id")
    def _compute_workorder_info(self):

        for rec in self:

            if not rec.check_in:
                rec.workorder_info = ""
                continue

            mappings = self.env["eran.mrp.workcenter.employee"].search([
                ("employee_id", "=", rec.employee_id.id)
            ])

            workcenters = mappings.mapped("workcenter_id")

            today = rec.check_in.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

            tomorrow = today + timedelta(days=1)

            workorders = self.env["mrp.workorder"].search([
                ("workcenter_id", "in", workcenters.ids),
                ("state", "in", ["waiting", "ready", "progress"]),
                ("production_id.date_planned_start", ">=", today),
                ("production_id.date_planned_start", "<", tomorrow),
            ])

            cards = []

            for wo in workorders:

                leader = wo.leader_id.name if wo.leader_id else "-"

                cards.append(f"""
                <div style="
                    border:1px solid #dcdcdc;
                    border-radius:8px;
                    padding:12px;
                    margin-bottom:12px;
                    background:#fafafa;
                ">

                    <h4 style="margin:0;color:#0b72b9;">
                        📍 {wo.workcenter_id.name}
                    </h4>

                    <p>
                        <b>Leader :</b> {leader}
                    </p>

                    <p>
                        <b>Manufacturing Order</b><br/>
                        {wo.production_id.name}
                    </p>

                    <p>
                        <b>Work Order</b><br/>
                        {wo.name}
                    </p>

                    <p>
                        <b>Product</b><br/>
                        {wo.product_id.display_name}
                    </p>

                    <p>
                        <b>Status</b><br/>
                        {wo.state.upper()}
                    </p>

                </div>
                """)

            rec.workorder_info = "".join(cards)

    available_workorder_ids = fields.Many2many(
        "mrp.workorder",
        string="Today's Work Orders"
    )


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



