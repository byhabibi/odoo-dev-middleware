import logging
from datetime import datetime
_logger = logging.getLogger(__name__)

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

#  ================================\approval\========================================>
class MansApprovaHr(models.Model):
    _name = "mans.approval.hr"
    _description = "Mans Approval hr"
    _rec_name = 'reference'

    reference = fields.Char("Reference")
    models = fields.Selection(
        [('attendance_overtime', 'Attendance Overtime'),
        ], string="Model", default="attendance_overtime")
    approval_type = fields.Selection([('position-base-approval', 'Position Base Approval'), ('individual-base-approval', 'Individual Base Approval')], default="position-base-approval")
    approval_rule = fields.Selection([('only-one-approved', 'Only One Approved'), ('all-approved', 'All Approved')], default="only-one-approved")

    user_ids = fields.One2many('mans.hr.approval.user.line', 'approval_hr_id', string='Approver')
    job_ids = fields.One2many('mans.hr.approval.job.line', 'approval_hr_id', string='Job Position')

    @api.constrains('user_ids')
    def _constrains_user_ids(self):
        for this in self:
            if this.approval_type == 'individual-base-approval' and len(this.user_ids) == 0:
                raise ValidationError(_("Don't leave the user ids line blank if you set individual base approval!"))
    
    @api.constrains('job_ids')
    def _constrains_job_ids(self):
        for this in self:
            if this.approval_type == 'position-base-approval' and len(this.job_ids) == 0:
                raise ValidationError(_("Don't leave the job ids line blank if you set position base approval!"))

    @api.constrains('models')
    def _constrains_double_data(self):
        for this in self:
            datas = self.search([('models', '=', this.models)])
            if len(datas) > 1:
                raise ValidationError(_('Approval for %s document already exist!', this.models))
            
    @api.constrains('reference')
    def _constrains_double_data(self):
        for this in self:
            datas = self.search([('reference', '=', this.reference)])
            if len(datas) > 1:
                raise ValidationError(_('Approval for reference %s already exist!', this.reference))
        
#  ================================\user ids\========================================>
class MansHrApprovalUserLine(models.Model):
    _name = "mans.hr.approval.user.line"
    _description = "Mans HR Attendance Overtime Approval User Line"

    sequence = fields.Integer(string='Sequence')
    user_id = fields.Many2one('res.users', string="User")
    approval_hr_id = fields.Many2one('mans.approval.hr', string="Approver HR")

#  ================================\job ids\========================================>
class MansHrApprovalJobLine(models.Model):
    _name = "mans.hr.approval.job.line"
    _description = "Mans HR Attendance Overtime Approval Job Line"

    sequence = fields.Integer(string='Sequence')
    job_id = fields.Many2one('hr.job', string="Job Position")
    approval_hr_id = fields.Many2one('mans.approval.hr', string="Approver HR")