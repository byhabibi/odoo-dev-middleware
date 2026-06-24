from collections import defaultdict
from datetime import date, datetime, timedelta

from odoo import api, fields, models, _
from odoo.tools import populate
from odoo.exceptions import ValidationError, UserError
import logging, json
_logger = logging.getLogger(__name__)

class QualityCheckWizard(models.TransientModel):
    _inherit = 'quality.check.wizard'

    order_sheet_id = fields.Many2one('eran.order.sheet', string="Order Sheet", related='current_check_id.order_sheet_id')
    order_qty = fields.Float(string="Order Qty", related='current_check_id.order_qty')
    good_qty = fields.Float(string="Good Qty", compute='_quality_ng_qty')
    not_good_qty = fields.Float(string="Not Good Qty", compute='_quality_ng_qty')
    quality_ng_ids = fields.One2many('quality.check.wizard.ng', 'quality_check_id', string='Quality Ng', copy=True)
    quality_attachment_ng_ids = fields.One2many('quality.attachment.wizard.ng', 'quality_check_id', string='Quality Attachment Ng', copy=True)

    @api.depends('quality_ng_ids.ng_qty')
    def _quality_ng_qty(self):
        for order in self:
            ng_qty = sum(order.quality_ng_ids.mapped('ng_qty'))
            order.not_good_qty = ng_qty
            order.good_qty = order.order_qty - ng_qty

    def do_pass(self):
        if self.test_type == 'picture' and not self.picture:
            raise UserError(_('You must provide a picture before validating'))
        lines = []
        lines_attach = []
        for line in self.quality_ng_ids:
            val = {
                'not_good_id' : line.not_good_id.id,
                'ng_qty' : line.ng_qty,
            }
            lines.append((0, 0, val))
        for line_attach in self.quality_attachment_ng_ids:
            val = {
                'image' : line_attach.image,
            }
            lines_attach.append((0, 0, val))
        self.current_check_id.quality_ng_ids = lines
        self.current_check_id.quality_attachment_ng_ids = lines_attach
        self.current_check_id.good_qty = self.good_qty
        self.current_check_id.not_good_qty = self.not_good_qty
        self.current_check_id.do_pass()
        self.current_check_id.validation_date = fields.Datetime.now()
        return self.action_generate_next_window()
    
    def create_lmk(self):
        for order in self:
            value = {
                'delivery_date': order.current_check_id.picking_id.scheduled_date,
                'lmk_date': fields.date.today(),
                'product_id': order.current_check_id.product_id.id,
                'order_sheet_id': order.current_check_id.order_sheet_id.id,
                'order_qty': order.order_qty,
                'picking_id': order.current_check_id.picking_id.id,
                'quality_check_id': order.current_check_id.id,
                'point_id': order.current_check_id.point_id.id,
                'team_id': order.current_check_id.team_id.id,
                'partner_id': order.current_check_id.partner_id.id,
            }
            lmk = self.env['eran.lembar.masalah.kualitas'].create(value)
            view_form = self.env.ref('eran_custom.eran_lembar_masalah_kualitas_view_form').id
            action_vals = {
                'name': 'LMK Form',
                'res_id': lmk.id,
                'view_mode': 'form',
                'res_model': 'eran.lembar.masalah.kualitas',
                'type': 'ir.actions.act_window',
                'views': [(view_form, 'form')],
                'context': {}
            }
            return action_vals

class QualityCheckWizardNg(models.TransientModel):
    _name = 'quality.check.wizard.ng'

    quality_check_id = fields.Many2one('quality.check.wizard', string="Quality Check", required=True, ondelete='cascade', index=True, copy=False)
    not_good_id = fields.Many2one('eran.no.good', string="Ng", required=True)
    ng_qty = fields.Float(string="Quantity", required=True)

class QualityAttachmentWizardNg(models.TransientModel):
    _name = 'quality.attachment.wizard.ng'

    quality_check_id = fields.Many2one('quality.check.wizard', string="Quality Check")
    image = fields.Image(string="Image",attachment=True)

class QualityCheck(models.Model):
    _inherit = "quality.check"

    def do_set_draft(self):
        self.quality_state = 'none'

    order_sheet_id = fields.Many2one('eran.order.sheet', string="Order Sheet")
    order_qty = fields.Float(string="Order Qty", readonly=True)
    good_qty = fields.Float(string="Good Qty", compute='_quality_ng_qty')
    not_good_qty = fields.Float(string="Not Good Qty", compute='_quality_ng_qty')
    quality_ng_ids = fields.One2many('quality.check.ng', 'quality_check_id', string='Quality Ng', copy=True)
    quality_attachment_ng_ids = fields.One2many('quality.attachment.ng', 'quality_check_id', string='Quality Attachment Ng', copy=True)
    validation_date = fields.Datetime(string="Validation Date", )
    lmk_ids = fields.One2many('eran.lembar.masalah.kualitas', 'quality_check_id', string='LMK', copy=False)
    lmk_count = fields.Float(string="LMK Count", compute='_lmk_count')
    batch_id = fields.Many2one('stock.picking.batch', string="Batch", compute='_get_bacth_id', store=True)

    def action_lmk_list(self):
        for order in self:
            view_tree = self.env.ref('eran_custom.eran_lembar_masalah_kualitas_view_tree').id
            view_form = self.env.ref('eran_custom.eran_lembar_masalah_kualitas_view_form').id
            action = {
                'name': 'LMK',
                'domain': [('quality_check_id', '=', order.id)],
                'view_mode': 'tree,form',
                'res_model': 'eran.lembar.masalah.kualitas',
                'views': [(view_tree, 'tree'),(view_form, 'form')],
                'type': 'ir.actions.act_window',
                'context': {}
            }
            return action

    @api.depends('picking_id')
    def _get_bacth_id(self):
        for order in self:
            if order.picking_id:
                order.batch_id = order.picking_id.batch_id.id

    def create_lmk(self):
        for order in self:
            value = {
                'delivery_date': order.picking_id.scheduled_date,
                'lmk_date': fields.date.today(),
                'product_id': order.product_id.id,
                'order_sheet_id': order.order_sheet_id.id,
                'order_qty': order.order_qty,
                'picking_id': order.picking_id.id,
                'point_id': order.point_id.id,
                'quality_check_id': order.id,
                'team_id': order.team_id.id,
                'partner_id': order.partner_id.id,
            }
            lmk = self.env['eran.lembar.masalah.kualitas'].create(value)
            view_form = self.env.ref('eran_custom.eran_lembar_masalah_kualitas_view_form').id
            action_vals = {
                'name': 'LMK Form',
                'res_id': lmk.id,
                'view_mode': 'form',
                'res_model': 'eran.lembar.masalah.kualitas',
                'type': 'ir.actions.act_window',
                'views': [(view_form, 'form')],
                'context': {}
            }
            return action_vals
    
    @api.depends('quality_ng_ids.ng_qty')
    def _quality_ng_qty(self):
        for order in self:
            ng_qty = sum(order.quality_ng_ids.mapped('ng_qty'))
            order.not_good_qty = ng_qty
            order.good_qty = order.order_qty - ng_qty

    def _lmk_count(self):
        for order in self:
            lmk_c = len(order.lmk_ids.mapped('id'))
            order.lmk_count = lmk_c


    def create_wrapper(self, records):
        list = []
        l = 0
        row = []
        for i in records:
            l += 1
            row.append(i)
            if l == 2:
                list.append(row)
                l = 0
                row = []
        return list
                


class QualityCheckNg(models.Model):
    _name = 'quality.check.ng'

    quality_check_id = fields.Many2one('quality.check', string="Quality Check")
    product_id = fields.Many2one('product.product', string="Product", related='quality_check_id.product_id', store=True)
    picking_id = fields.Many2one('stock.picking', string="Picking", related='quality_check_id.picking_id', store=True)
    partner_id = fields.Many2one('res.partner', string="Partner", related='quality_check_id.picking_id.partner_id', store=True)
    not_good_id = fields.Many2one('eran.no.good', string="Ng", required=True)
    ng_qty = fields.Float(string="Quantity", required=True)

    @api.onchange('ng_qty')
    def _onchange_(self):
        for line in self:
            if line.ng_qty:
                if line.ng_qty < 0:
                    raise ValidationError("Cannot input value less than 0")

class QualityAttachmentNg(models.Model):
    _name = 'quality.attachment.ng'

    quality_check_id = fields.Many2one('quality.check', string="Quality Check")
    image = fields.Image(string="Image",attachment=True)

class EranLembarMasalahKualitas(models.Model):
    _name = 'eran.lembar.masalah.kualitas'
    _description = "Lembar Masalah Kualitas"

    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']

    name = fields.Char(string="Name")
    picking_id = fields.Many2one('stock.picking', string="Picking")
    production_id = fields.Many2one('mrp.production', string="Production Order")
    partner_type = fields.Selection(string='Partner Type',
        selection=[
            ('customer', 'Customer'),
            ('vendor', 'Vendor')]
    )
    lmk_type = fields.Selection(string='LMK Type',
        selection=[
            ('claim', 'Claim'),
            ('complain', 'Complain'),
            ('tukar_guling', 'Tukar Guling')]
    )
    
    quality_check_id = fields.Many2one('quality.check', string="Control Check")
    point_id = fields.Many2one('quality.point', string="Control Point")
    team_id = fields.Many2one('quality.alert.team', string="Team")
    partner_id = fields.Many2one('res.partner', string="Partner")
    lmk_date = fields.Date(string="Create Date")
    delivery_date = fields.Date(string="Delivery Date")
    production_date = fields.Date(string="Production Date")
    product_id = fields.Many2one('product.product', string="Product")
    order_sheet_id = fields.Many2one('eran.order.sheet', string="Order Sheet")
    order_qty = fields.Float(string="Order Qty")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('done', 'Done'),
    ], string="State", default='draft', tracking=True, copy=False)
    # jenis_cacat = fields.Selection([
    #     ('Visual', 'Visual'),
    #     ('Dimensi', 'Dimensi'),
    #     ('Fungsi', 'Fungsi'),
    #     ('Material', 'Material')
    # ], string='Jenis Cacat Part')
    part_defect_type_ids = fields.Many2many('eran.part.defect.type', string='Jenis Cacat Part')
    # area_ditemukan = fields.Selection([
    #     ('Incoming', 'Incoming'),
    #     ('Produksi', 'Produksi'),
    #     ('Gudang', 'Gudang'),
    #     ('Customer', 'Customer')
    # ], string='Area Ditemukan Masalah')
    area_found_ids = fields.Many2many('eran.area.found', string='Area Ditemukan Masalah')
    tindakan_sementara = fields.Char(string="Tindakan Sementara")
    batas_waktu = fields.Char(string="Batas Waktu Jawaban")
    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)
    lmk_line_ids = fields.One2many('eran.lembar.masalah.kualitas.line', 'lmk_id', string='LMK Detail', copy=True)
    lmk_attachment_ids = fields.One2many('eran.lembar.masalah.kualitas.attachment', 'lmk_id', string='Attachment', copy=True)

    # APPROVAL 
    approval_line_ids = fields.One2many('eran.lmk.approval.line', 'lmk_id', string="Approval Line", )
    approval_qc_id = fields.Many2one('dsn.approval.qc', string="Approval QC", compute="_compute_approval_qc_id")
    approval_rule = fields.Selection(related="approval_qc_id.approval_rule", string="Approval Rule")
    approval_type = fields.Selection(related="approval_qc_id.approval_type", string="Approval Type")
    models = fields.Selection(related="approval_qc_id.models", string="Model")
    assigned_to_ids = fields.Many2many(comodel_name="res.users",string="Approver",)
    user_in_assigned_to = fields.Boolean(string="User Is Assigned", compute="_computed_user_in_assigned_to")

    approve_uid = fields.Many2one('res.users', string='Approved by', readonly=True)
    approve_date = fields.Date('Approve date', readonly="True")
    organizational_chart = fields.Text(string="Organizational Chart")
    is_pica_created = fields.Boolean(string='PICA Created', default=False)
    pica_ids = fields.One2many('eran.pica', 'lmk_id', string='PICA')
    pica_count = fields.Integer(string='Jumlah PICA', compute='_compute_pica_count')


    def set_organizational_chart(self, employee):
        chart = []
        current = employee
        visited = set()

        while current and current.parent_id and current.parent_id.user_id:
            parent_user_id = current.parent_id.user_id.id

            if parent_user_id in visited:
                break

            visited.add(parent_user_id)
            chart.append(parent_user_id)
            current = current.parent_id

        self.organizational_chart = json.dumps(chart)

    # APPROVAL

    def _compute_approval_qc_id(self):
        for rec in self:
            rec.approval_qc_id = self.env['dsn.approval.qc'].search([('models', '=', 'quality_check')], limit=1).id

    def _computed_user_in_assigned_to(self):
        if self.assigned_to_ids and self.state == 'waiting_approval':
            if self.approval_rule == 'only-one-approved':
                self.user_in_assigned_to = True if self.env.user.id in self.assigned_to_ids.ids else False
            else:
                for appr in self.approval_line_ids.sorted(key=lambda r: r.sequence).sorted(key=lambda r: r.sequence):
                    if appr.is_approved:
                        continue
                    else:
                        self.user_in_assigned_to = True if self.env.user.id == appr.user_id.id else False
                        break
        else:
            self.user_in_assigned_to = False

    def btn_waiting_approval(self):
        self.set_organizational_chart(self.env.user.employee_id)
        organizational_chart = json.loads(self.organizational_chart or "[]")

        # set approver
        records = []
        if self.env.user.sudo().employee_id.approver_ids:
            for appr_line in self.approval_qc_id:
                if appr_line.approval_type == 'position-base-approval':
                    for job in appr_line.job_ids:
                        for approver in self.env.user.sudo().employee_id.approver_ids:
                            if job.job_id.id == approver.job_id.id:
                                records.append(approver.user_id.id)
                                self.env['eran.lmk.approval.line'].create({
                                    'lmk_id': self.id,
                                    'user_id': approver.user_id.id,
                                })
                else:
                    for user in appr_line.user_ids:
                        records.append(user.user_id.id)
                        self.env['eran.lmk.approval.line'].create({
                                'lmk_id': self.id,
                                'user_id': user.user_id.id,
                            })
        
        if not self.env.user.sudo().employee_id.approver_ids or len(records) == 0:
            raise ValidationError(_("Can't find approver for current user!"))
        
        order_map = {v: i for i, v in enumerate(organizational_chart)}
        b_sorted = sorted(records, key=lambda x: order_map.get(x, float('inf')))
        b_sorted_sequenced = {k: i + 1 for i, k in enumerate(b_sorted)}


        for arpproval_line in self.env['eran.lmk.approval.line'].search([('lmk_id', '=', self.id)]):
            _logger.info("=========", b_sorted, b_sorted_sequenced, arpproval_line.user_id.id, b_sorted_sequenced[arpproval_line.user_id.id], "=======")
            arpproval_line.sequence = b_sorted_sequenced[arpproval_line.user_id.id]


        self.assigned_to_ids = [(6, 0, b_sorted)]

        # send notification 
        if self.approval_rule == 'only-one-approved':
            # send notification to the first approver
            for rec in b_sorted:
                self.send_mail_activity('eran_custom.reminder_qc_approval', rec)
        else:
            # send notification to all approver
            self.send_mail_activity('eran_custom.reminder_qc_approval', b_sorted[0])

        # set state
        self.write({'state':'waiting_approval'})

    def send_mail_activity(self, act_type_xmlid, user_id):
        self.activity_schedule(
            act_type_xmlid=act_type_xmlid,
            user_id=user_id, 
            summary="Reminder qc Approval",
            note="You have items in the qc document that you need to approve ✅ Check if an action is needed. 👍")
                           
    def btn_approved(self):
        # set approval
        approval_qc = self.env['eran.lmk.approval.line']
        # set is approved
        record = approval_qc.search([
            ('lmk_id', '=', self.id), 
            ('user_id', '=', self.env.user.id),
            ('is_approved', '=', False)], 
            order="sequence", limit=1)
        record.write({'is_approved': True, 'date_approved': datetime.now()})
        
        res_model_id = self.env['ir.model'].sudo().search([('model', '=', 'eran.lembar.masalah.kualitas')], limit=1).id

        # set state
        if self.approval_rule == 'only-one-approved':
            # self.active_approver = self.assigned_to_ids
            if any(self.approval_line_ids.sorted(key=lambda r: r.sequence).mapped('is_approved')):
                self.write({
                    'state':'done', 
                    'approve_uid':self.env.user.id, 
                    'approve_date': fields.Date.today()
                })
                # set all mail activity to be done
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).action_done()
        # set state
        else:
            is_approved_counted = len(approval_qc.search([('is_approved', '=', True), ('lmk_id.models', '=', 'quality_check'), ('lmk_id', '=', self.id)]).ids)
            approval_qc_user = [rec.user_id for rec in approval_qc.search([('lmk_id.models', '=', 'quality_check'), ('lmk_id', '=', self.id)], order='sequence asc')]
            current_user_id = approval_qc_user[is_approved_counted - 1] if is_approved_counted else approval_qc_user[0]

            if all(self.approval_line_ids.sorted(key=lambda r: r.sequence).mapped('is_approved')):
                self.write({
                    'state':'done', 
                    'approve_uid':self.env.user.id, 
                    'approve_date': fields.Date.today()
                })
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
            else:
                # assign to the next approver
                user_id = approval_qc_user[is_approved_counted]

                # set mail activity to be done one by one
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                
                # send notification to the next approver
                self.send_mail_activity('eran_custom.reminder_qc_approval', user_id.id)

    
    def btn_set_to_draft(self):
        # ulink mail activity
        res_model_id = self.env['ir.model'].sudo().search([('model', '=', 'eran.lembar.masalah.kualitas')], limit=1).id
        self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).unlink()
        # reset assigned_to_ids
        self.assigned_to_ids = [(6, 0, [])]
        # reset approval line
        self.env['eran.lmk.approval.line'].search([('lmk_id', '=', self.id)]).unlink()
        # set state
        self.write({'state':'draft'})
    # END APPROVAL

    def btn_create_pica(self):
        self.ensure_one()
        if not self.lmk_line_ids:
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': 'Tidak ada NG items untuk dibuat PICA',
                    'type': 'warning',
                }
            }
        
        created_picas = []
        for line in self.lmk_line_ids:
            pica_vals = {
                'lmk_id': self.id,
                'product_id': self.product_id.id if self.product_id else False,
                'pica_date': self.lmk_date,
                'pica_delivery_date': self.delivery_date,
                'partner_id': self.partner_id.id if self.partner_id else False,
                'partner_type': self.partner_type if self.partner_type else False,
                'not_good_id': line.not_good_id.id if line.not_good_id else False,
                'quantity_ng': line.quantity_ng or 0,
            }
            pica = self.env['eran.pica'].create(pica_vals)
            created_picas.append(pica.name)
        
        self.is_pica_created = True
        
        return {
            'effect': {
                'fadeout': 'slow',
                'message': f'Berhasil membuat {len(created_picas)} PICA: {", ".join(created_picas)}',
                'type': 'rainbow_man',
            }
        }
    
    @api.depends('pica_ids')
    def _compute_pica_count(self):
        for rec in self:
            rec.pica_count = len(rec.pica_ids)
    
    def action_open_pica(self):
        self.ensure_one()
        return {
            'name': 'PICA',
            'type': 'ir.actions.act_window',
            'res_model': 'eran.pica',
            'view_mode': 'tree',
            'domain': [('lmk_id', '=', self.id)],
            'context': {'default_lmk_id': self.id},
        }

    def replace_name(self):
        for this in self:
            this.name = self.env['ir.sequence'].next_by_code('eran.lmk.seq')

    @api.model
    def create(self, vals):
        res = super(EranLembarMasalahKualitas, self).create(vals)
        res.replace_name()
        return res

    def request_approval(self):
        return True
    
class EranLmkApprovalLine(models.Model):
    _name = 'eran.lmk.approval.line'
    _order = 'sequence'
    _description = "Eran Quality Check Approval Line"

    lmk_id = fields.Many2one('eran.lembar.masalah.kualitas', string="LMK")
    is_approved = fields.Boolean(string="Is Approved")
    date_approved = fields.Datetime(string="Date Approved")
    user_id = fields.Many2one('res.users', string="User")    
    signature = fields.Binary(related='user_id.employee_id.signature', string="Signature")
    sequence = fields.Integer('Sequence')

class EranLembarMasalahKualitasLine(models.Model):
    _name = 'eran.lembar.masalah.kualitas.line'

    lmk_id = fields.Many2one('eran.lembar.masalah.kualitas', string="LMK")
    quantity_sample = fields.Float(string="Quantity Sample")
    not_good_id = fields.Many2one('eran.no.good', string="Jenis Ng", required=True)
    quantity_ng = fields.Float(string="Quantity NG")
    lmk_date = fields.Date(string="Create Date", related='lmk_id.lmk_date', store=True)
    delivery_date = fields.Date(string="Delivery Date", related='lmk_id.delivery_date', store=True)
    product_id = fields.Many2one('product.product', string="Product", related='lmk_id.product_id', store=True)
    category_group = fields.Many2one('eran.category.group', string="Category Group", related="lmk_id.product_id.category_group_id", store=True)
    partner_type = fields.Selection(string='Partner Type', related="lmk_id.partner_type", store=True)
    lmk_type = fields.Selection(string='LMK Type', related="lmk_id.lmk_type", store=True)
    production_date = fields.Date(string="Production Date", related="lmk_id.production_date")
    order_sheet_id = fields.Many2one('eran.order.sheet', string="Order Sheet", related="lmk_id.order_sheet_id", store=True)
    order_qty = fields.Float(string="Order Qty", related="lmk_id.order_qty", store=True)
    partner_id = fields.Many2one('res.partner', string="Partner", related="lmk_id.partner_id", store=True)

class EranLembarMasalahKualitasAttachment(models.Model):
    _name = 'eran.lembar.masalah.kualitas.attachment'

    lmk_id = fields.Many2one('eran.lembar.masalah.kualitas', string="LMK")
    image = fields.Image(string="Image",attachment=True)


class QualityPoint(models.Model):
    _inherit = "quality.point"


    automatic_pass = fields.Boolean()


class EranPartDefectType(models.Model):
    _name = "eran.part.defect.type"

    name = fields.Char()

class EranAreaFound(models.Model):
    _name = "eran.area.found"

    name = fields.Char()

class EranReturnOrderLine(models.Model):
    _name = "eran.return.order.line"


    picking_id = fields.Many2one('stock.picking', string='Transfer')
    partner_id = fields.Many2one('res.partner', string='Contact')
    date_done_picking = fields.Date(string='Effective Date')
    product_id = fields.Many2one('product.product', string='Product')
    product_category_id = fields.Many2one('product.category', string='Product Category')
    list_return_type = fields.Selection([('claim', 'Claim'), ('complaint', 'Complaint')])
    quantity_done = fields.Float(string='Quantity Done')
    category_group_id = fields.Many2one('eran.category.group', string='Category Group')
    location_id = fields.Many2one('stock.location', string='From')
    location_dest_id = fields.Many2one('stock.location', string='To')
    product_uom = fields.Many2one('uom.uom', string='UoM')
    replanishment_type = fields.Selection([('not_available', 'NOT AVAILABLE'), ('available', 'AVAILABLE')])
    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)

    def action_eran_return_order_line(self):
        eran_return_order_line = self.env['eran.return.order.line'].sudo().search([('create_uid', '=', self.env.user.id)])
        if eran_return_order_line:
            eran_return_order_line.unlink()

        ids_list = []
        stock_picking = self.env['stock.picking'].sudo().search([
            ('reference_return_id', '=', False),
            ('picking_type_id.code', '!=', 'internal'),
            ('state', '=', 'done')])
        for picking in stock_picking:
            if not picking.return_ids:
                continue
            
            for ret in picking.return_ids:
                if not ret.return_ids:
                   for sm in ret.move_ids_without_package:
                       value = {
                           'picking_id': sm.picking_id.id,
                           'partner_id': sm.picking_id.partner_id.id,
                           'date_done_picking': sm.date_done_picking,
                           'product_id': sm.product_id.id,
                           'product_category_id': sm.product_id.categ_id.id,
                           'list_return_type': sm.list_return_type,
                           'location_id': sm.location_id.id,
                           'location_dest_id': sm.location_dest_id.id,
                           'product_uom': sm.product_uom.id,
                           'replanishment_type': 'not_available',
                           'quantity_done': sm.quantity_done}
                       
                       reference_return = self.env['eran.return.order.line'].create(value)
                       ids_list.append(reference_return.id)

                if ret.return_ids:
                    for ret2 in ret.return_ids:
                        for sm2 in ret2.move_ids_without_package:
                            available = 'available'
                            if sm2.picking_id.state in ('draft', 'cancel'):
                                available = 'not_available'
                            value2 = {
                                'picking_id': sm2.picking_id.reference_return_id.id,
                                'partner_id': sm2.picking_id.partner_id.id,
                                'date_done_picking': sm2.date_done_picking,
                                'product_id': sm2.product_id.id,
                                'product_category_id': sm2.product_id.categ_id.id,
                                'list_return_type': sm2.list_return_type,
                                'location_id': sm2.location_id.id,
                                'location_dest_id': sm2.location_dest_id.id,
                                'product_uom': sm2.product_uom.id,
                                'replanishment_type': available,
                                'quantity_done': sm2.quantity_done}
                    
                            reference_return2 = self.env['eran.return.order.line'].create(value2)
                            ids_list.append(reference_return2.id)

        view_tree_id = self.env.ref('eran_custom.return_order_line_view_tree').id
        graph_id = self.env.ref('eran_custom.view_return_order_line_graph').id
        pivot_id = self.env.ref('eran_custom.view_return_order_line_pivot').id
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Return Order Line'),
            'domain': [('id', 'in', ids_list)],
            'res_model': 'eran.return.order.line',
            'view_mode': 'tree,graph,pivot',
            'views': [[view_tree_id, 'list'],[graph_id, 'graph'], [pivot_id, 'pivot']],
            'context': {}
        }
        return action
    

class EranQualityClaimRate(models.Model):
    _name = "eran.quality.claim.rate"
    _description = "Dashboard Quality Claim Rate"

    date = fields.Date("Date")
    target = fields.Integer("Target")
    key_message = fields.Text("Message")

class EranQualityComplaint(models.Model):
    _name = "eran.quality.complaint"
    _description = "Dashboard Quality Complaint"

    date = fields.Date("Date")
    target = fields.Integer("Target")
    key_message = fields.Text("Message")
class EranQualityDisposal(models.Model):
    _name = "eran.quality.disposal"
    _description = "Dashboard Quality Disposal to Sales"

    date = fields.Date("Date")
    target = fields.Integer("Target")
    key_message = fields.Text("Message")