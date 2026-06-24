from odoo import api, fields, models, _
import logging
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = "mrp.production"


    qty_plan = fields.Float('Qty Daily Pattern')
    qty_keppin = fields.Float('Qty Keppin', compute='_compute_qty_keppin', store=True)

    # APPROVAL 
    approval_line_ids = fields.One2many('eran.mrp.approval.line', 'mrp_id', string="Approval Line")
    approval_mrp_id = fields.Many2one('dsn.approval.mrp', string="Approval Mrp", compute="_compute_approval_mrp_id")
    approval_rule = fields.Selection(related="approval_mrp_id.approval_rule", string="Approval Rule")
    approval_type = fields.Selection(related="approval_mrp_id.approval_type", string="Approval Type")
    models = fields.Selection(related="approval_mrp_id.models", string="Model")
    assigned_to_ids = fields.Many2many(comodel_name="res.users",string="Approver",)
    user_in_assigned_to = fields.Boolean(string="User Is Assigned", compute="_computed_user_in_assigned_to")
    state_approval = fields.Selection([
        ('confirmed', 'Waiting'),
        ('to_approve', 'To Approve'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string="State", default='confirmed', tracking=True, copy=False)
    need_approval = fields.Boolean(string='Need Approval?', compute="_compute_need_approval", store=True)
    category_group_id = fields.Many2one('eran.category.group', string='Category Group', related='product_id.product_tmpl_id.category_group_id', store=True)
    mrp_workcenter_group_id = fields.Many2one('mrp.workcenter', string="Workcenter Group", compute="_compute_mrp_workcenter_group_id", store=True)
    operator_id2 = fields.Many2one("hr.employee",
        string="Operator 2",
        help="Master data employee employee module",
        domain="")
        
    # APPROVAL REQUEST MATERIAL
    # approval_req_mat_line_ids = fields.One2many('eran.mrp.req.mat.approval.line', 'mrp_id', string="Approval Line")
    # approval_mrp_req_mat_id = fields.Many2one('dsn.approval.mrp', string="Approval Mrp", compute="_compute_approval_mrp_id_req_material")
    # approval_req_mat_rule = fields.Selection(related="approval_mrp_req_mat_id.approval_rule", string="Approval Rule")
    # approval_req_mat_type = fields.Selection(related="approval_mrp_req_mat_id.approval_type", string="Approval Type")
    # models = fields.Selection(related="approval_mrp_req_mat_id.models", string="Model")

    # need_approval_req_mat = fields.Boolean(string='Need Approval Request Material', compute='_compute_need_approval_req_mat')
    # state_request_material = fields.Selection({
    #     ('draft', 'Draft'),
    #     ('requested', 'Requested'),
    #     ('approved', 'Approved')
    # }, string='State Request Material')
    


    # def btn_req_approval_material(self):
    #     self.write({
    #         'state_request_material': 'requested'
    #     })

    # def btn_approve_req_material(self):
    #     self.write({
    #         'state_request_material': 'approved'
    #     })


    @api.depends('qty_plan', 'product_qty')
    def _compute_qty_keppin(self):
        for rec in self:
            res = 0
            res = rec.product_qty - rec.qty_plan
            rec.qty_keppin = res

    
    def auto_create_request_material(self):
        if self.backorder_sequence == 0:
            pick_type = self.env['stock.picking.type'].search([('name', '=', 'Request Materials')], limit=1)
            source_location_id = self.picking_type_id.source_location_material.id
            requester_id = self.operator_id.id

            line_ids = []
            for move_line in self.move_raw_ids:
                value = {
                    'name': move_line.product_id.name,
                    'product_id': move_line.product_id.id,
                    'quantity_done': move_line.product_uom_qty,
                    'product_uom_qty': move_line.product_uom_qty,
                    'location_id': source_location_id,
                    'location_dest_id': self.location_src_id.id,
                }
                line_ids.append((0,0, value))
            
            m_id = self.env['stock.picking'].create({
                'name': self.env['ir.sequence'].next_by_code('eran.material.request'),
                'scheduled_date': datetime.now(),
                'requester': requester_id,
                'location_id': source_location_id,
                'location_dest_id': self.location_src_id.id,
                'picking_type_id': pick_type.id,
                'manufacture_production_id': self.id,
                'origin': self.name,
                # 'note': self.reason,
                'shift': self.shift_id.id,
                'move_ids_without_package': line_ids
            })
            
            m_id.action_confirm()
            for move in m_id.move_ids_without_package:
                move.production_id = False

    def action_confirm(self):
        for rec in self:
            rec.qty_plan = rec.product_qty
            if rec.picking_type_id.auto_create_request_material:
                rec.auto_create_request_material()
            res = super(MrpProduction, self).action_confirm()
            return res


    @api.depends('name')    
    def _compute_approval_mrp_id(self):
        for rec in self:
            rec.approval_mrp_id = self.env['dsn.approval.mrp'].search([('models', '=', 'mrp_production')], limit=1).id

    # @api.depends('name')    
    # def _compute_approval_mrp_id_req_material(self):
    #     for rec in self:
    #         rec.approval_mrp_id_req_mat = self.env['dsn.approval.mrp'].search([('models', '=', 'mrp_production'),('reference', '=', 'Manufacture Order Request Material Approval')], limit=1).id


    @api.depends('workorder_ids', 'workorder_ids.workcenter_id')
    def _compute_mrp_workcenter_group_id(self):
        for rec in self:
            workcenter_id = []
            for wo in  rec.workorder_ids:
                workcenter_id.append(wo.workcenter_id.id)
            
            if workcenter_id:
                rec.mrp_workcenter_group_id = workcenter_id[-1]


    def _computed_user_in_assigned_to(self):
        if self.assigned_to_ids and self.state_approval == 'to_approve':
            if self.approval_rule == 'only-one-approved':
                self.user_in_assigned_to = True if self.env.user.id in self.assigned_to_ids.ids else False
            else:
                for appr in self.approval_line_ids:
                    if appr.is_approved:
                        continue
                    else:
                        self.user_in_assigned_to = True if self.env.user.id == appr.user_id.id else False
                        break
        else:
            self.user_in_assigned_to = False

    
    def btn_waiting_approval(self):
        # set approver
        records = []
        if self.env.user.sudo().employee_id.approver_ids:
            for appr_line in self.approval_mrp_id:
                if appr_line.approval_type == 'position-base-approval':
                    for job in appr_line.job_ids:
                        for approver in self.env.user.sudo().employee_id.approver_ids:
                            if job.job_id.id == approver.job_id.id:
                                records.append(approver.user_id.id)
                                self.env['eran.mrp.approval.line'].create({
                                    'mrp_id': self.id,
                                    'user_id': approver.user_id.id,
                                })
                else:
                    for user in appr_line.user_ids:
                        records.append(user.user_id.id)
                        self.env['eran.mrp.approval.line'].create({
                                'mrp_id': self.id,
                                'user_id': user.user_id.id,
                            })
                        
        if not self.env.user.sudo().employee_id.approver_ids or len(records) == 0:
            raise ValidationError(_("Can't find approver for current user!"))

        self.assigned_to_ids = [(6, 0, records)]

        # send notification 
        if self.approval_rule == 'only-one-approved':
            # send notification to the first approver
            for rec in records:
                self.send_mail_activity('eran_custom.reminder_mrp_approval', rec)
        else:
            # send notification to all approver
            self.send_mail_activity('eran_custom.reminder_mrp_approval', records[0])

        # set state
        self.write({'state_approval':'to_approve'})



    def btn_approved(self):
        # set approval
        approval_mrp = self.env['eran.mrp.approval.line']
        # set is approved
        record = approval_mrp.search([('mrp_id', '=', self.id), ('user_id', '=', self.env.user.id),('is_approved', '=', False)], limit=1)
        record.write({'is_approved': True, 'date_approved': datetime.now()})
        
        res_model_id = self.env['ir.model'].search([('model', '=', 'mrp.production')], limit=1).id

        # set state
        consumption_issues = self._get_consumption_issues()
        if self.approval_rule == 'only-one-approved':
            # self.active_approver = self.assigned_to_ids
            if any(self.approval_line_ids.mapped('is_approved')):
                # self.write({
                #     'state_approval':'done', 
                #     'need_approval': False
                # })
                # set all mail activity to be done
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).action_done()
                # validate
                _logger.info('button_mark_dones')
                self.button_mark_done()
                return self._action_generate_consumption_wizard(consumption_issues)
        # set state
        else:
            is_approved_counted = len(approval_mrp.search([('is_approved', '=', True), ('mrp_id.models', '=', 'mrp_production'), ('mrp_id', '=', self.id)]).ids)
            approval_mrp_user = [rec.user_id for rec in approval_mrp.search([], order='id asc')]
            current_user_id = approval_mrp_user[is_approved_counted - 1] if is_approved_counted else approval_mrp_user[0]

            if all(self.approval_line_ids.mapped('is_approved')):
                # self.write({
                #     'state_approval':'done', 
                #     'need_approval': False
                # })
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                # validate
                self.button_mark_done()
                return self._action_generate_consumption_wizard(consumption_issues)
            else:
                # assign to the next approver
                user_id = approval_mrp_user[is_approved_counted]

                # set mail activity to be done one by one
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                
                # send notification to the next approver
                self.send_mail_activity('eran_custom.reminder_mrp_approval', user_id.id)


    def send_mail_activity(self, act_type_xmlid, user_id):
        self.activity_schedule(
            act_type_xmlid=act_type_xmlid,
            user_id=user_id, 
            summary="Reminder Mrp Approval",
            note="You have items in the Mrp document that you need to approve ✅ Check if an action is needed. 👍")
        
    @api.depends('qty_producing')
    def _compute_need_approval(self):
        """
        type: compute quantity done
        description: cek apakah ketika qty done melebihi qty demand maka butuh approval?
        return: void
        """
        for rec in self:
            if rec.qty_producing > rec.product_uom_qty:
                rec.need_approval = True
            else:
                rec.need_approval = False

    # @api.depends('backorder_sequence')
    # def _compute_need_approval_req_mat(self):
    #     for rec in self:
    #         if rec.backorder_sequence > 0:
    #             rec.need_approval_req_mat = True
    #         else:
    #             rec.need_approval_req_mat = False


    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):
        for rec in self:
            if rec.product_uom_qty < rec.qty_producing:
                return {
                    'warning': {
                        'title': 'Warning!',
                        'message': 'Quantity Producing and Quantity Done differ. Would you like to proceed?'}
                }
            
    def get_qty_done(self):
        for rec in self:
            stock_move_ids = self.env['stock.move'].search([
                ('move_orig_ids.production_id', 'in', rec.ids),
                ('is_subcontract', '=', True)
            ])
            _logger.info(stock_move_ids)
            for sm in stock_move_ids:
                if sm.state != 'done':
                    sm.quantity_done = rec.good_total


    def subcontracting_record_component(self):
        res = super(MrpProduction, self).subcontracting_record_component()
        self.get_qty_done()
        
        return res
    
class EranMrpApprovalLine(models.Model):
    _name = 'eran.mrp.approval.line'
    _description = "Eran MRP Approval Line"

    mrp_id = fields.Many2one('mrp.production', string="Manufacture Order")
    is_approved = fields.Boolean(string="Is Approved")
    date_approved = fields.Datetime(string="Date Approved")
    user_id = fields.Many2one('res.users', string="User")    
    signature = fields.Binary(related='user_id.employee_id.signature', string="Signature")


# class EranMrpReqMatApprovalLine(models.Model):
#     _name = 'eran.mrp.req.mat.approval.line'
#     _description = "Eran MRP Request Material Approval Line"

#     mrp_id = fields.Many2one('mrp.production', string="Manufacture Order")
#     is_approved = fields.Boolean(string="Is Approved")
#     date_approved = fields.Datetime(string="Date Approved")
#     user_id = fields.Many2one('res.users', string="User")    
#     signature = fields.Binary(related='user_id.employee_id.signature', string="Signature")

class StockMove(models.Model):
    _inherit = 'stock.move'

    component_type = fields.Selection([('component', 'Component'), ('tooling', 'Tooling')], string='Type', related='bom_line_id.component_type')