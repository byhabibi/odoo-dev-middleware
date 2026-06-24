from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)
import json

class EranStockPicking(models.Model):
    _inherit = 'stock.picking'
    
    return_type = fields.Selection(string='Return Type', selection=[('claim', 'Claim'), ('complaint', 'Complaint')])
    picking_type = fields.Char(string="Picking type", related='picking_type_id.name', store=True)
    order_sheet_id = fields.Many2one("eran.order.sheet", string="Order Sheet", ondelete='cascade', index=True, copy=False)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id, readonly=True)

    requester = fields.Many2one('hr.employee', string="Requester")
    suplier = fields.Many2one('hr.employee', string="Suplier")
    request_date = fields.Datetime(string='Request Date', default=lambda self: fields.Datetime.now())
    shift = fields.Many2one('eran.master.shift', string="Shift")
    
    ready_to_invoice = fields.Boolean(string="Ready to Invoice", copy=False)
    dn_back = fields.Boolean(string="DN Back", copy=False)
    dn_out = fields.Boolean(string="DN Out", copy=False)
    plat_no = fields.Char(string="Plat No.")
    delivery_preparation_number = fields.Char(string="Delivery Preparation Number")
    driver = fields.Char(string="Driver")
    manufacture_production_id = fields.Many2one("mrp.production", string="Manufacture Production")
    dn_supplier = fields.Char(string="DN Supplier")

    sale_order_date = fields.Datetime(related="sale_id.date_order", string="SO Date")
    purchase_order_date = fields.Datetime(related="purchase_id.date_order", string="PO Date")
    so_number = fields.Char(related="sale_id.name", string="SO Number")
    po_number = fields.Char(related="purchase_id.name", string="PO Number")
    list_return_type = fields.Selection([('claim', 'Claim'), ('complaint', 'Complaint')], tracking=True)
    able_to_invoice = fields.Selection(related="picking_type_id.able_to_invoice")
    validated_by_id = fields.Many2one('res.users', string='Validated By')

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', compute="_compute_eran_purchase_id", store=True, help="This is used to display the PO number of the product subcontracting.")
    run_purchase_order_id_compute = fields.Boolean(compute='run_purchase_order_id')
    sale_order_id = fields.Many2one('sale.order', string="Sale Order")
    need_approval = fields.Boolean(string='Need Approval?', compute="_compute_need_approval", store=True)
    po_ref = fields.Char('PO Reference', related='sale_order_id.po_ref', store=True)
    no_order_sheet = fields.Char('No. Order Sheet', related='order_sheet_id.no_order_sheet', store=True)

    # APPROVAL 
    approval_line_ids = fields.One2many('eran.stock.approval.line', 'stock_id', string="Approval Line", )
    approval_stock_id = fields.Many2one('dsn.approval.stock', string="Approval Stock", compute="_compute_approval_stock_id")
    approval_rule = fields.Selection(related="approval_stock_id.approval_rule", string="Approval Rule")
    approval_type = fields.Selection(related="approval_stock_id.approval_type", string="Approval Type")
    models = fields.Selection(related="approval_stock_id.models", string="Model")
    assigned_to_ids = fields.Many2many(comodel_name="res.users",string="Approver",)
    user_in_assigned_to = fields.Boolean(string="User Is Assigned", compute="_computed_user_in_assigned_to")
    state_approval = fields.Selection([
        ('confirmed', 'Waiting'),
        ('to_approve', 'To Approve'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string="State", default='confirmed', tracking=True, copy=False, )

    purchase_ref_id = fields.Many2one('purchase.order', string='Purchase Order', compute="_compute_ref_purchase_id", store=True)
    eran_amount_total = fields.Monetary(string="Amount", compute="_compute_amount_purchase", store=True)
    reference_return_id = fields.Many2one('stock.picking', 'Reference Return', copy=False)
    return_ids = fields.One2many('stock.picking', 'reference_return_id', string='Returns')
    return_count = fields.Integer(compute='compute_return_count')
    is_return = fields.Boolean(compute='compute_return', store=True)
    transfer_reference = fields.Char('Transfer Reference')
    ready_to_invoice_date = fields.Datetime('Ready to Invoice Date', tracking=True)
    dn_back_date = fields.Datetime('DN Back Date', tracking=True)
    dn_out_date = fields.Datetime('DN Out Date', tracking=True)
    name = fields.Char(
        'Reference', default='/',
        copy=False, index='trigram', readonly=True, states={'draft': [('readonly', False)], 'waiting': [('readonly', False)], 'confirmed': [('readonly', False)], 'assigned': [('readonly', False)]})

    invoice_state = fields.Selection([('invoiced', 'Invoiced'), ('2binvoiced', 'To Be Invoiced'), ('partial_invoice', 'Partial Invoice'), ('nothing_to_invoice', 'Nothing To Invoice')], default="2binvoiced",
                                     string="Invoice Control")
    revision_picking_id = fields.Many2one('stock.picking', string='Revision Picking (Source)', help="Transfer dimana revisi berasal.")
    revision_picking_ids = fields.One2many('stock.picking', 'revision_picking_id', string='Revision Picking', help="Transfer revisi.")
    revision_picking_ids_count = fields.Integer('Revision Picking Count', compute="_compute_revision")
    hide_revision_button = fields.Boolean('Hide Revision Button', compute="_compute_button_revision")
    invoice_count = fields.Integer('Invoice Count', compute="_compute_invoice_count")
    act_delv_date = fields.Datetime(string="Actual Delivery Date", default=datetime.now())
    state_dn_out = fields.Char(string='State DN Out', default='draft', compute='_compute_state_dn_out')  # Sesuaikan tipe field jika perlu

    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = self.env['account.move'].search_count([('picking_ids', 'in', [record.id])])

    def view_account_move_ids(self):
        self.ensure_one()
        domain = [('picking_ids', 'in', [self.id])]
        account_ids = self.env['account.move'].search(domain)

        action = {
            'name': _('Invoices'),
            'domain': domain,
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
        }

        if len(account_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': account_ids.id,
            })
        else:
            view_tree = self.env.ref('account.view_move_tree')
            action.update({
                'view_mode': 'tree,form',
                'views': [(view_tree.id, 'tree'), (False, 'form')],
            })

        return action

    @api.depends('move_ids_without_package.qty_return')
    def _compute_button_revision(self):
        for picking in self:
            if all(move.qty_return == move.quantity_done and move.quantity_done > 0 for move in picking.move_ids_without_package) and picking.picking_type_code == 'outgoing':
                picking.hide_revision_button = False
            else:
                picking.hide_revision_button = True

    @api.depends('revision_picking_ids')
    def _compute_revision(self):
        for picking in self:
            picking.revision_picking_ids_count = len(self.revision_picking_ids)

    def create_revision_picking(self):
        # eran.order.sheet
        # vals = {
        #     'partner_id': self.partner_id,
        #     'sale_ids': [(6, 0, self.order_sheet_id.sale_ids.ids)],
        #     ''
        # }
        self.order_sheet_id.state = 'return'
        revision_order_sheet = self.order_sheet_id.copy({
            'revision_order_sheet_id': self.order_sheet_id.id,
            'revision_picking_id': self.id,
        })
        action = {
            'name': 'Revision Order Sheet',
            'view_mode': 'form',
            'res_model': 'eran.order.sheet',
            'res_id': revision_order_sheet.id,
            'type': 'ir.actions.act_window',
            'context': {'create':0, 'copy':0, 'delete':0}
        }
        return action
    
    def action_view_revision_picking_id(self):
        action = {
            'name': 'Revision Transfer',
            'view_mode': 'form',
            'res_model': 'stock.picking',
            'res_id': self.revision_picking_id.id,
            'type': 'ir.actions.act_window',
            'context': {'create':0, 'copy':0, 'delete':0}
        }
        return action
    
    def action_view_revision_picking_ids(self):
        action = {
            'name': 'Revision Transfer',
            'res_model': 'stock.picking',
            'type': 'ir.actions.act_window',
            'context': {'create':0, 'copy':0, 'delete':0}
        }
        if len(self.revision_picking_ids) > 1:
            action['view_mode'] = 'tree,form'
            action['domain'] = [('id','in', self.revision_picking_ids.ids)]
        elif len(self.revision_picking_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.revision_picking_ids.id
        else:
            return {'type': 'ir.actions.act_window_close'}
        return action

    def action_is_nothing_invoice(self):
        for rec in self:
            states = []
            for line in rec.move_ids_without_package:
                qty = line.quantity_done if line.quantity_done > 0 else line.product_uom_qty
                if line.qty_return >= qty:
                    states.append('full_return')
                else:
                    states.append('not_full_return')
            
            
            if 'not_full_return' not in states:
                rec.invoice_state = 'nothing_to_invoice'

            return True

    def run_purchase_order_id(self):
        for rec in self:
            rec._compute_eran_purchase_id()
            rec.run_purchase_order_id_compute = True
    
    def run_purchase_order_id_all(self):
        picking_ids = self.search([('state', 'in', ['waiting', 'confirmed', 'assigned'])])
        for picking in picking_ids:
            picking.run_purchase_order_id()

    def find_first_missing(self,data):        
        for i in range(len(data) - 1):
            if data[i+1] - data[i] > 1:
                return data[i] + 1
        return data[-1] + 1

    def replace_name(self, picking_type):
        if picking_type.sequence_id:
            if picking_type.sequence_id.use_date_range:
                for line_date in picking_type.sequence_id.date_range_ids:
                    today = fields.Date.today()
                    if line_date.date_from <= today <= line_date.date_to:
                        year_now = datetime.now().year
                        first_date_year = datetime(year_now, 1, 1)
                        last_date_year = datetime(year_now, 12, 31)
                        picking_ids = self.search([('picking_type_id', '=', picking_type.id), ('create_date', '>=', first_date_year), ('create_date', '<=', last_date_year)])
                        mapp = picking_ids.mapped('name')
                        datas = []
                        for m in mapp:
                            if m and m.split('/')[0].isdigit():
                                datas.append(int(m.split('/')[0]))
                        if mapp:
                            if datas:
                                num = self.find_first_missing(sorted(datas))
                                line_date.number_next_actual = num
                        
    @api.model_create_multi
    def create(self, vals_list):
        scheduled_dates = []
        for vals in vals_list:
            defaults = self.default_get(['name', 'picking_type_id'])
            picking_type = self.env['stock.picking.type'].browse(vals.get('picking_type_id', defaults.get('picking_type_id')))
            if vals.get('name', '/') == '/' and defaults.get('name', '/') == '/' and vals.get('picking_type_id', defaults.get('picking_type_id')):
                if picking_type.sequence_id:
                    _logger.info('etesttsetse')
                    self.replace_name(picking_type)
                    vals['name'] = picking_type.sequence_id.next_by_id()

            # make sure to write `schedule_date` *after* the `stock.move` creation in
            # order to get a determinist execution of `_set_scheduled_date`
            scheduled_dates.append(vals.pop('scheduled_date', False))

        pickings = super().create(vals_list)

        for picking, scheduled_date in zip(pickings, scheduled_dates):
            if scheduled_date:
                picking.with_context(mail_notrack=True).write({'scheduled_date': scheduled_date})
        pickings._autoconfirm_picking()

        for picking, vals in zip(pickings, vals_list):
            # set partner as follower
            if vals.get('partner_id'):
                if picking.location_id.usage == 'supplier' or picking.location_dest_id.usage == 'customer':
                    picking.message_subscribe([vals.get('partner_id')])
            if vals.get('picking_type_id'):
                for move in picking.move_ids:
                    if not move.description_picking:
                        move.description_picking = move.product_id.with_context(lang=move._get_lang())._get_description(move.picking_id.picking_type_id)
        return pickings

    @api.depends('picking_type_id')
    def compute_return(self):
        for this in self:
            picking_type_return = self.env['stock.picking.type'].search([
                ('id', '=', this.picking_type_id.id),
                ('name', 'ilike', 'return')])
            if picking_type_return:
                this.is_return = True
            else:
                this.is_return = False
    
    def _compute_amount_purchase(self):
        for rec in self:
            k = 0
            for line in rec.move_ids_without_package.filtered(lambda l: l.purchase_line_id):
                k = k + (line.product_uom_qty * line.purchase_line_id.price_unit)
            rec.eran_amount_total = k

    def compute_return_count(self):
        for this in self:
            this.return_count = len(this.return_ids)

    def action_to_return(self):
        view_id = self.env.ref('stock.view_picking_form').id
        view_tree_id = self.env.ref('stock.vpicktree').id
        action_vals = {
            'name': 'Returns',
            'domain': [('id', 'in', self.return_ids.ids)],
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'views': [[view_tree_id, 'list'],[view_id, 'form']],
            'type': 'ir.actions.act_window',
            'context': {'create': False}
        }
        return action_vals

    @api.depends('move_line_ids_without_package', 'backorder_id')
    def _compute_ref_purchase_id(self):
        for rec in self:
            k = 0
            for line in rec.move_ids_without_package.filtered(lambda l: l.purchase_line_id):
                k = line.purchase_line_id.order_id.id
            rec.purchase_ref_id = k
    
    def _compute_eran_purchase_id(self):
        for rec in self:
            # _logger.info('==========compute_purchase_id========')
            purchase_ids = rec._get_subcontracting_source_purchase()
            # _logger.info(purchase_ids)
            if purchase_ids:
                rec.purchase_order_id = purchase_ids[0]
            else:
                # _logger.info('1')
                if rec.origin:
                    # _logger.info('2')
                    origin = self.search([('name', '=', rec.origin)])
                    # _logger.info(origin)
                    purchase_ids2 = origin.move_ids.purchase_line_id.mapped('order_id')
                    if purchase_ids2:
                        # _logger.info(purchase_ids2)
                        rec.purchase_order_id = purchase_ids2[0]
                    else:
                        pass
                else:
                    pass
            
    @api.depends('name')    
    def _compute_approval_stock_id(self):
        for rec in self:
            rec.approval_stock_id = self.env['dsn.approval.stock'].search([('models', '=', 'stock_picking')], limit=1).id
    
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
            for appr_line in self.approval_stock_id:
                if appr_line.approval_type == 'position-base-approval':
                    for job in appr_line.job_ids:
                        for approver in self.env.user.sudo().employee_id.approver_ids:
                            if job.job_id.id == approver.job_id.id:
                                records.append(approver.user_id.id)
                                self.env['eran.stock.approval.line'].create({
                                    'stock_id': self.id,
                                    'user_id': approver.user_id.id,
                                })
                else:
                    for user in appr_line.user_ids:
                        records.append(user.user_id.id)
                        self.env['eran.stock.approval.line'].create({
                                'stock_id': self.id,
                                'user_id': user.user_id.id,
                            })
        
        if not self.env.user.sudo().employee_id.approver_ids or len(records) == 0:
            raise ValidationError(_("Can't find approver for current user!"))

        self.assigned_to_ids = [(6, 0, records)]

        # send notification 
        if self.approval_rule == 'only-one-approved':
            # send notification to the first approver
            for rec in records:
                self.send_mail_activity('eran_custom.reminder_stock_approval', rec)
        else:
            # send notification to all approver
            self.send_mail_activity('eran_custom.reminder_stock_approval', records[0])

        # set state
        self.write({'state_approval':'to_approve'})

    def btn_approved(self):
        # set approval
        approval_stock = self.env['eran.stock.approval.line']
        # set is approved
        record = approval_stock.search([('stock_id', '=', self.id), ('user_id', '=', self.env.user.id),('is_approved', '=', False)], limit=1)
        record.write({'is_approved': True, 'date_approved': datetime.now()})
        
        res_model_id = self.env['ir.model'].search([('model', '=', 'stock.picking')], limit=1).id

        # set state
        if self.approval_rule == 'only-one-approved':
            # self.active_approver = self.assigned_to_ids
            if any(self.approval_line_ids.mapped('is_approved')):
                self.write({
                    'state_approval':'done', 
                    'need_approval': False
                })
                # set all mail activity to be done
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).action_done()
                # validate
                self.button_validate()
        # set state
        else:
            is_approved_counted = len(approval_stock.search([('is_approved', '=', True), ('stock_id.models', '=', 'stock_picking'), ('stock_id', '=', self.id)]).ids)
            approval_stock_user = [rec.user_id for rec in approval_stock.search([], order='id asc')]
            current_user_id = approval_stock_user[is_approved_counted - 1] if is_approved_counted else approval_stock_user[0]

            if all(self.approval_line_ids.mapped('is_approved')):
                self.write({
                    'state_approval':'done', 
                    'need_approval': False
                })
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                # validate
                self.button_validate()
            else:
                # assign to the next approver
                user_id = approval_stock_user[is_approved_counted]

                # set mail activity to be done one by one
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                
                # send notification to the next approver
                self.send_mail_activity('eran_custom.reminder_stock_approval', user_id.id)

    def send_mail_activity(self, act_type_xmlid, user_id):
        self.activity_schedule(
            act_type_xmlid=act_type_xmlid,
            user_id=user_id, 
            summary="Reminder Stock Approval",
            note="You have items in the Stock document that you need to approve ✅ Check if an action is needed. 👍")
    
    def action_cancel(self):
        res = super(EranStockPicking, self).action_cancel()
        self.need_approval = False

        self.assigned_to_ids = [(6, 0, [])]
        for rec in self:
            self.env['eran.stock.approval.line'].search([('stock_id', '=', rec.id)]).unlink()
        # unlink mail activity
        res_model_id = self.env['ir.model'].search([('model', '=', 'stock.picking')], limit=1).id
        for rec in self:
            self.env["mail.activity"].sudo().search([('res_id', '=', rec.id), ('res_model_id', '=', res_model_id)]).unlink()
        return res

    @api.depends('move_ids_without_package.quantity_done')
    def _compute_need_approval(self):
        """
        type: compute quantity done
        description: cek apakah ketika qty done melebihi qty demand maka butuh approval?
        return: void
        """
        for rec in self:
            if rec.picking_type_id.need_approval_exceeding_demand and rec.state not in ('done','cancel'):
                if rec.move_ids_without_package.filtered(lambda x: x.product_uom_qty < x.quantity_done):
                    rec.need_approval = True

    def action_confirm(self):
        # custom to no merge stock move
        # merge=False
        self._check_company()
        self._compute_ref_purchase_id()
        self.mapped('package_level_ids').filtered(lambda pl: pl.state == 'draft' and not pl.move_ids)._generate_moves()
        self.move_ids.filtered(lambda move: move.state == 'draft')._action_confirm(merge=False)
        
        self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done'))._trigger_scheduler()
        
        for check in self.check_ids:
            if check.point_id.automatic_pass:
                check.do_pass()
        return True
    
    
    def _get_invoice_vals(self, key, inv_type, journal_id, move):
        res = super(EranStockPicking, self)._get_invoice_vals(key, inv_type, journal_id, move)
        sale = move.picking_id.sale_id
        res.update({
            'narration': sale.payment_term_id.description,
        })
        return res

    def open_btn_stock_invoice_onshipping(self):
        for record in self:
            if record.picking_type_id.able_to_invoice not in ['invoiceable', 'billable']:
                raise ValidationError(_('Operation type can\'t produce invoice.'))

            type = record.picking_type_id.code
            if type == 'incoming' and not record.state == 'done':
                raise UserError("Can only create bill from Done Receipt")
            elif type == 'outgoing' and not (record.ready_to_invoice and record.state == 'done'):
                raise UserError("Can't create invoice until delivery note is marked returned by clicking 'Ready To Invoice' button.")
        action = self.env['ir.actions.actions']._for_xml_id('invoice_from_picking.bi_action_stock_invoice')
        return action
        # return {
        #     'name': "Create Draft Invoices",
        #     'type': 'ir.actions.act_window',
        #     'view_type': 'form',
        #     'view_mode': 'form',
        #     'res_model': 'stock.invoice.onshipping',
        #     'view_id': self.env.ref('invoice_from_picking.view_stock_invoice_onshipping_form').id,
        #     'target': 'new',
        # } 

    def check_lines_qty(self):
        for rec in self:
            for line in rec.move_ids_without_package:
                if line.purchase_line_id:
                    if line.quantity_done > line.purchase_line_id.product_uom_qty:
                        raise ValidationError("Qty Done can't more than Purchase Order Line Qty %s." % line.product_id.name)

    def button_validate(self):
        for rec in self:
            rec.validated_by_id = self.env.user
            for move in rec.move_ids_without_package:
                move._onchange_check_good_qty()
                move._depends_order_sheet_line()
                if rec.is_return:
                    move._qty_return_order_sheet()
                    move._depends_order_sheet_line()
            
            rec._check_schedule_date()
            # rec.check_lines_qty()
            if rec.is_return and rec.reference_return_id:
                self.reference_return_id.action_is_nothing_invoice()
        res = super(EranStockPicking, self).button_validate()
        return res

    # ........ code baru ..........
    # def button_validate(self):
    #     self.validated_by_id = self.env.user
    #     for move in self.move_ids_without_package:
    #         move._onchange_check_good_qty()
    #     self._check_schedule_date()
    #     self.check_lines_qty()

    #     for rec in self:
    #         if rec.is_return and rec.reference_return_id:
    #             rec.reference_return_id.action_is_nothing_invoice()

    #     res = super(EranStockPicking, self).button_validate()

    #     for picking in self:
    #         for move in picking.move_ids_without_package:
    #             if (
    #                 move.order_sheet_line_id
    #                 and move.to_refund
    #                 and move.state != 'cancel'
    #             ):
    #                 move.order_sheet_line_id.qty_return = move.quantity_done

    #     return res
    # .............................

    def _check_schedule_date(self):
        for rec in self:
            if rec.picking_type_id.code == 'incoming':
                date_today = datetime.now()
                if rec.scheduled_date > date_today:
                    raise ValidationError(_("Scheduled date can't more than Date Done!"))

    # def action_button_ready2invoice(self):
    #     for rec in self:
    #         if rec.invoice_state != 'invoiced' and rec.ready_to_invoice != True:
    #             rec.write({
    #                 'ready_to_invoice': True,
    #                 'ready_to_invoice_date': datetime.now(),
    #             })

    def action_button_ready2invoice(self):
        for rec in self:
            if not rec.dn_back:
                raise UserError("You must do DN Back before Ready to Invoice!")
            if rec.invoice_state != 'invoiced' and not rec.ready_to_invoice:
                rec.write({
                    'ready_to_invoice': True,
                    'ready_to_invoice_date': datetime.now(),
                })

    def action_button_dn_back(self):
        for rec in self:
            if rec.invoice_state != 'invoiced' and rec.dn_back != True:
                rec.write({
                    'dn_back': True,
                    'dn_back_date': datetime.now(),
                })
    
    def action_button_dn_out(self):
        for rec in self:
            if rec.invoice_state != 'invoiced' and rec.dn_out != True:
                rec.write({
                    'dn_out': True,
                    'dn_out_date': fields.Datetime.now(),
                })
    
    def btn_refund(self):
        # ctx = dict(self.env.context)
        # ctx.update(
        #     {'default_picking_id':self.id}
        # )
        # return {'type': 'ir.actions.act_window',
        #        'name': _('Replacement Shipment'),
        #        'res_model': 'stock.return.picking',
        #        'target': 'new',
        #        'view_mode': 'form',
        #        'context':ctx,
        #        }
        action = self.env['ir.actions.actions']._for_xml_id('stock.act_stock_return_picking')
        context = self._context
        context = {'active_model': context.get('active_model'), 'active_ids': context.get('active_ids'), 'default_picking_id':self.id}
        action['context'] = context

        return action
    
    def _invoice_create_line(self, moves, journal_id, inv_type='out_invoice'):
        invoice_obj = self.env['account.move']
        move_obj = self.env['stock.move']
        invoices = {}
        is_extra_move, extra_move_tax = move_obj._get_moves_taxes(moves, inv_type)
        product_price_unit = {}
        invoice_id = False
        
        for move in moves:
            if (move.quantity_done if move.quantity_done > 0 else move.product_uom_qty) - (move.qty_invoiced + move.qty_return) > 0:
                company = move.company_id
                origin = move.picking_id.name
                partner, user_id, currency_id = move_obj._get_master_data(move, company)

                key = (partner, currency_id, company.id, user_id)
                invoice_vals = self._get_invoice_vals(key, inv_type, journal_id, move)
                if key not in invoices:
                    # Get account and payment terms
                    invoice_id = self._create_invoice_from_picking(move.picking_id, invoice_vals)
                    invoice_id.picking_ids = [(4, move.picking_id.id)]
                    invoices[key] = invoice_id.id
                else:
                    invoice = invoice_obj.browse(invoices[key])
                    invoice.picking_ids = [(4, move.picking_id.id)]
                    merge_vals = {}
                    if not invoice.ref or invoice_vals['ref'] not in invoice.ref.split(', '):
                        invoice_origin = filter(None, [invoice.ref, invoice_vals['ref']])
                        merge_vals['ref'] = ', '.join(invoice_origin)
                    if invoice_vals.get('name', False) and (
                            not invoice.name or invoice_vals['name'] not in invoice.name.split(', ')):
                        invoice_name = filter(None, [invoice.name, invoice_vals['name']])
                        merge_vals['name'] = ', '.join(invoice_name)
                    if merge_vals:
                        invoice.write(merge_vals)
                
                invoice_line_vals = move_obj._get_invoice_line_vals(move, partner, inv_type)
                invoice_line_vals['move_id'] = invoices[key]
                invoice_line_vals['ref'] = origin
                invoice_line_vals['sale_line_id'] = move.sale_line_id.id
                invoice_line_vals['purchase_line_id'] = move.purchase_line_id.id
                invoice_line_vals['stock_move_id'] = move.id
                invoice_line_vals['picking_id'] = move.picking_id.id
                
                if not is_extra_move[move.id]:
                    product_price_unit[invoice_line_vals['product_id']] = invoice_line_vals['price_unit']
                if is_extra_move[move.id] and (invoice_line_vals['product_id']) in product_price_unit:
                    invoice_line_vals['price_unit'] = product_price_unit[invoice_line_vals['product_id']]
                if is_extra_move[move.id]:
                    desc = (inv_type in ('out_invoice') and move.product_id.product_tmpl_id.description_sale) or \
                        (inv_type in ('purchase') and move.product_id.product_tmpl_id.description_purchase)
                    invoice_line_vals['name'] += ' ' + desc if desc else ''
                    if extra_move_tax[move.picking_id, move.product_id]:
                        invoice_line_vals['invoice_line_tax_id'] = extra_move_tax[move.picking_id, move.product_id]
                    # the default product taxes
                    elif (0, move.product_id) in extra_move_tax:
                        invoice_line_vals['invoice_line_tax_id'] = extra_move_tax[0, move.product_id]
                invice_line = invoice_id.update({
                    'invoice_line_ids':[(0, None,invoice_line_vals)]
                    })
                move_data = self.env['account.move'].browse(invoices[key])
                
                move.picking_id.write({'invoice_state': 'invoiced'})
        
        if not invoice_id:
            raise UserError(_('There is no invoiceable product!'))
        
        for inv_line in invoice_id.invoice_line_ids :
            for move in moves:
                
                if inv_line.sale_line_id.id == move.sale_line_id.id:
                    if move.sale_line_id:
                        move.sale_line_id.invoice_lines = [(4, inv_line.id)]
                
                if inv_line.purchase_line_id.id == move.purchase_line_id.id:
                    if move.purchase_line_id:
                        move.purchase_line_id.invoice_lines = [(4, inv_line.id)]
                
                
        if invoice_id:
            invoice_id._compute_amount()

        return invoices.values()

    @api.depends('dn_out', 'state')
    def _compute_state_dn_out(self):
        for rec in self:
            if rec.dn_out:
                rec.state_dn_out = 'done'
            elif rec.state == 'cancel':
                rec.state_dn_out = 'cancel'
            else:
                rec.state_dn_out = 'draft'
    
    @api.model
    def filter_on_barcode(self, barcode):
        # Cari picking berdasarkan barcode (biasanya berdasarkan field 'name')
        picking = self.search([('name', '=', barcode)], limit=1)
        
        if picking:
            # Cek jika status sudah 'done' atau 'cancel'
            if picking.dn_out == True:
                raise UserError(_("This picking is already done atau sudah DN Out."))
            if picking.state == 'cancel':
                raise UserError(_("Picking ini telah dibatalkan."))
                
        # Jika lolos validasi, panggil fungsi aslinya
        return super(EranStockPicking, self).filter_on_barcode(barcode)
    
    @api.model
    def _get_fields_stock_barcode(self):
        fields = super()._get_fields_stock_barcode()
        fields += ['dn_out', 'picking_type_code']
        return fields
    
    
class EranStockApprovalLine(models.Model):
    _name = 'eran.stock.approval.line'
    _description = "Eran Stock Approval Line"

    stock_id = fields.Many2one('stock.picking', string="Stock")
    is_approved = fields.Boolean(string="Is Approved")
    date_approved = fields.Datetime(string="Date Approved")
    user_id = fields.Many2one('res.users', string="User")    
    signature = fields.Binary(related='user_id.employee_id.signature', string="Signature")

class EranStocPickingType(models.Model):
    _inherit = 'stock.picking.type'
    
    able_to_invoice = fields.Selection(selection=[('invoiceable', 'Invoiceable'), ('billable', 'Billable')], string='Able to Invoice')
    source_location_material = fields.Many2one('stock.location', 'Source Location Material',)
    need_approval_exceeding_demand = fields.Boolean(string="Need Approval Exceeding Demand")
    ng_location_id = fields.Many2one('stock.location', string='NG Location')
    auto_create_request_material = fields.Boolean('Automatic Create Request Material')
    is_request_material = fields.Boolean('Is Request Material?')


class EranStockMove(models.Model):
    _inherit = 'stock.move'
    
    order_sheet_line_id = fields.Many2one('eran.order.sheet.line', 'Order Sheet Line Id')
    good_qty = fields.Float(string="Good Qty", compute='_get_quality_good_qty')
    date_done_picking = fields.Datetime(related="picking_id.date_done", string="Effective Date", store=True)
    product_category_id = fields.Many2one("product.category", related="product_id.product_tmpl_id.categ_id", string="Product Category", store=True)
    list_return_type = fields.Selection([('claim', 'Claim'), ('complaint', 'Complaint')], related="picking_id.list_return_type", store=True)

    price_so = fields.Float(string="Price", related="sale_line_id.price_unit", store=True)
    currency_id = fields.Many2one("res.currency", related="sale_line_id.currency_id", store=True)
    qty_so = fields.Float(string="Ordered Qty", related="sale_line_id.product_uom_qty", store=True)
    price_subtotal_so = fields.Monetary(string="Total Sales", related="sale_line_id.price_subtotal", store=True)
    date_so = fields.Datetime(string="Order Date", related="sale_line_id.order_id.date_order", store=True)
    date_os = fields.Datetime(string="Order Sheet Date", related="order_sheet_line_id.order_sheet_id.schedule_date", store=True)
    qty_os = fields.Float(string="Order Sheet Qty", related="order_sheet_line_id.qty_order", store=True)
    price_subtotal_os = fields.Float(string="Total Order Sheet", compute='_get_total_order_sheet_price', store=True)
    date_picking_id = fields.Datetime(string="Delivery Date", related="picking_id.date_done", store=True)
    price_subtotal_picking = fields.Float(string="Total Delivery", compute='_get_total_order_sheet_price', store=True)

    do_state = fields.Selection(related="picking_id.state", string="DO State")
    so_number = fields.Many2one(related="picking_id.sale_order_id")
    po_number = fields.Char(related="picking_id.po_number")
    sale_order_date = fields.Datetime(related="sale_line_id.date_order")
    purchase_order_date = fields.Datetime(related="picking_id.purchase_order_date")
    do_number = fields.Char(related="picking_id.name")
    scheduled_date = fields.Datetime(related="picking_id.scheduled_date")
    delivery_preparation_number = fields.Char(related="picking_id.delivery_preparation_number")
    invoice_state = fields.Selection(related="picking_id.invoice_state")
    picking_type_code = fields.Selection(related="picking_id.picking_type_code")
    price_po = fields.Float(related="purchase_line_id.price_unit", store=True)
    alternative_uom_id = fields.Many2one(related="product_id.additional_uom_id", string='Alternative Uom')
    alternative_uom_qty = fields.Float('Alternative UoM Qty', compute="_get_alternative_qty_uom", inverse="_inverse_alternative_qty_uom", store=True)
    alternative_qty_done = fields.Float('Alternative Done', compute="_get_alternative_qty_done", inverse="_inverse_alternative_qty_done", store=True)
    payment_state = fields.Selection(string="Payment Status", related="picking_id.invoice_id.payment_state")
    is_serial = fields.Boolean('Is serial', compute="_get_tracking_categories", store=True)
    is_lot = fields.Boolean('Is Lots', compute="_get_tracking_categories", store=True)
    contact_id = fields.Many2one(related="purchase_line_id.order_id.partner_id")
    id_pkp = fields.Boolean(related='contact_id.l10n_id_pkp', string='ID PKP')
    quantity_total_po = fields.Float(string="Amount", compute="_compute_quantity_total_po", store=True)
    quantity_total_so = fields.Float(string="Amount", compute="_compute_quantity_total_so")
    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)
    product_name = fields.Char('Product Name', related="product_id.name")
    product_code = fields.Char('Product Code', related="product_id.default_code")

    remaining_qty_inv = fields.Float(string='Remaining Qty Inv.')
    qty_return = fields.Float(string='Qty Return', compute='_get_qty_return')
    qty_invoiced = fields.Float(string='Qty Invoiced', compute='_get_qty_invoiced')
    qty_invoice_remind = fields.Float(string='Qty Invoice Created', compute='_compute_qty_invoice_remind')
    additional_qty = fields.Float(string="Alternative UoM", help="Alternative UoM for product", related='product_id.additional_qty')
    alternative_quantity_done = fields.Float(string="Alternative Done", compute="_depends_quantity_done", inverse="_onchange_alternative_quantity_done", store=True)
    price_unit = fields.Float('Unit Price', copy=True)

    # field tambahan
    effective_date = fields.Datetime('Effective Date', related="order_sheet_line_id.effective_date", store=True)
    sale_id = fields.Many2one('sale.order', related="order_sheet_line_id.sale_id", string="Reference", store=True)
    po_ref = fields.Char(string="PO Customer", related="order_sheet_line_id.po_ref", store=True)
    qty_receipt = fields.Float(string="Receipt", compute="_depends_order_sheet_line", store=True)
    sale_price_unit = fields.Float('Unit Price', related="order_sheet_line_id.sale_price_unit", store=True)
    sale_amount = fields.Monetary('Amount', compute="_depends_order_sheet_line", store=True)
    amount_plan = fields.Float('Plan Amount', compute="_depends_order_sheet_line", store=True)
    invoice_id = fields.Many2one('account.move', string='Invoice No', related="order_sheet_line_id.invoice_id", store=True)
    os_name = fields.Char( related="order_sheet_line_id.os_name", string="Order Sheet", store=True)
    transfer_state = fields.Selection(string="Status Transfer", related="order_sheet_line_id.transfer_state", store=True)
    quantity_after_returns = fields.Float('Quantity After Return', compute="_depends_order_sheet_line", store=True)
    delivery_amount = fields.Float('Delivery Amount AT', compute="_depends_order_sheet_line", store=True)
    dn_back_date = fields.Datetime('DN Back Date', related="picking_id.dn_back_date", store=True)
    dn_out_date = fields.Datetime('DN Out Date', related='picking_id.dn_out_date', store=True)
    ready_to_invoice_date = fields.Datetime('Ready to Invoice Date', related="order_sheet_line_id.ready_to_invoice_date", store=True)

    @api.depends('order_sheet_line_id', 'state', 'picking_id', 'picking_id.backorder_id')
    def _depends_order_sheet_line(self):
        for move in self:
            move.quantity_after_returns = move.quantity_done - move.qty_return
            move.qty_receipt = move.order_sheet_line_id.qty_receipt
            move.sale_amount = move.order_sheet_line_id.sale_amount
            move.amount_plan = move.order_sheet_line_id.amount_plan
            move.delivery_amount = move.quantity_after_returns * move.sale_price_unit

            if move.state == 'cancel':
                move.qty_receipt = 0
                move.delivery_amount = 0
                move.sale_amount = 0
                move.amount_plan = 0
                move.quantity_after_returns = move.order_sheet_line_id.quantity_after_returns
            
            if move.picking_id.backorder_id:
                move.qty_receipt = 0
                move.amount_plan = 0
            

    @api.onchange('alternative_quantity_done')
    def _onchange_alternative_quantity_done(self):
        for rec in self:
            is_rounded = rec.product_id.uom_id.is_rounded
            if rec.additional_qty > 0:
                rec.quantity_done = rec.alternative_quantity_done / rec.additional_qty if is_rounded != True else round(rec.alternative_quantity_done / rec.additional_qty)
            else:
                rec.quantity_done = rec.alternative_quantity_done

    
    @api.depends('quantity_done')
    def _depends_quantity_done(self):
        for rec in self:
            rec.alternative_quantity_done = rec.quantity_done * rec.product_id.additional_qty if  rec.additional_qty > 0 else rec.quantity_done

    def _create_quality_checks_for_mo(self):
        # Groupby move by production order. Use it in order to generate missing quality checks.
        mo_moves = defaultdict(lambda: self.env['stock.move'])
        check_vals_list = []

        for move in self:
            by_product_ids = move.production_id.move_byproduct_ids.mapped('id')
            if move.id not in by_product_ids:
                if move.production_id and not move.scrapped:
                    mo_moves[move.production_id] |= move

        # QC of product type
        for production, moves in mo_moves.items():
            quality_points_domain = self.env['quality.point']._get_domain(moves.product_id, production.picking_type_id, measure_on='product')
            quality_points_domain = self.env['quality.point']._get_domain_for_production(quality_points_domain)
            quality_points = self.env['quality.point'].sudo().search(quality_points_domain)

            # Since move lines are created too late for the manufactured product, we create the QC of move_line type directly here instead, excluding by-products
            domain_lot_type = self.env['quality.point']._get_domain(production.product_id, production.picking_type_id, measure_on='move_line')
            quality_points_lot_type = self.env['quality.point'].sudo().search(domain_lot_type)

            quality_points = quality_points | quality_points_lot_type
            if not quality_points:
                continue
            mo_check_vals_list = quality_points._get_checks_values(moves.product_id, production.company_id.id, existing_checks=production.sudo().check_ids)
            for check_value in mo_check_vals_list:
                check_value.update({
                    'production_id': production.id,
                })
            check_vals_list += mo_check_vals_list

        # QC of operation type
        for production, moves in mo_moves.items():
            domain_operation_type = self.env['quality.point']._get_domain(self.env['product.product'], production.picking_type_id, measure_on='operation')
            domain_operation_type = self.env['quality.point']._get_domain_for_production(domain_operation_type)
            quality_points_operation = self.env['quality.point'].sudo().search(domain_operation_type)

            for point in quality_points_operation:
                if point.check_execute_now():
                    check_vals_list.append({
                        'point_id': point.id,
                        'team_id': point.team_id.id,
                        'measure_on': 'operation',
                        'production_id': production.id,
                    })

        self.env['quality.check'].sudo().create(check_vals_list)

    @api.depends('quantity_done', 'purchase_line_id')
    def _compute_quantity_total_po(self):
        for rec in self:
            rec.quantity_total_po = rec.quantity_done * rec.purchase_line_id.price_unit

    def _compute_quantity_total_so(self):
        for rec in self:
            rec.quantity_total_so = rec.quantity_done * rec.sale_line_id.price_unit

    def _get_qty_return(self):
        for rec in self:
            res = sum(rec.returned_move_ids.filtered(lambda m: m.state != 'cancel').mapped('quantity_done'))
            rec.qty_return = res

            rec._depends_order_sheet_line()

    def _get_qty_invoiced(self):
        for rec in self:
            # if rec.sale_line_id:
            #     domain = [('parent_state','=', 'posted'), ('product_id', '=', rec.product_id.id), ('sale_line_id', '=', rec.sale_line_id.id)]
            # elif rec.purchase_line_id:
            #     domain = [('parent_state','=', 'posted'), ('product_id', '=', rec.product_id.id), ('purchase_line_id', '=', rec.purchase_line_id.id)]
            # else:
            #     domain = []
            domain = [('parent_state','!=', 'cancel'), ('product_id', '=', rec.product_id.id), ('stock_move_id', '=', rec.id)]

            res = sum(self.env['account.move.line'].search(domain).mapped('quantity')) if domain else 0
            rec.qty_invoiced = res

    def _compute_qty_invoice_remind(self):
        for rec in self:
            domain = [('parent_state','!=', 'cancel'), ('product_id', '=', rec.product_id.id), ('stock_move_id', '=', rec.id)]
            
            res = sum(self.env['account.move.line'].search(domain).mapped('quantity'))
            rec.qty_invoice_remind = res
    
    # def _compute_qty_invoice_remind(self):
    #     for rec in self:
    #         if rec.sale_line_id:
    #             domain = [('parent_state','!=', 'cancel'), ('product_id', '=', rec.product_id.id), ('sale_line_id', '=', rec.sale_line_id.id)]
    #         elif rec.purchase_line_id:
    #             domain = [('parent_state','!=', 'cancel'), ('product_id', '=', rec.product_id.id), ('purchase_line_id', '=', rec.purchase_line_id.id)]
    #         else:
    #             domain = []

    #         res = sum(self.env['account.move.line'].search(domain).mapped('quantity'))
    #         rec.qty_invoice_remind = res

    @api.depends('has_tracking', 'picking_type_id.use_create_lots', 'picking_type_id.use_existing_lots', 'state')
    def _compute_display_assign_serial(self):
        for move in self:
            move.display_assign_serial = (
                move.has_tracking in ['serial','lot'] and
                move.state in ('partially_available', 'assigned', 'confirmed') and
                move.picking_type_id.use_create_lots and
                not move.picking_type_id.use_existing_lots
                and not move.origin_returned_move_id.id
            )

    @api.depends('product_uom_qty')
    def _get_alternative_qty_uom(self):
        for rec in self:
            rec.alternative_uom_qty = rec.product_uom_qty * rec.product_id.additional_qty if rec.product_id.additional_qty else 0

    @api.onchange('alternative_uom_qty')
    def _inverse_alternative_qty_uom(self):
        for rec in self:
            rec.product_uom_qty = rec.alternative_uom_qty / rec.product_id.additional_qty if rec.product_id.additional_qty else 0

    @api.depends('quantity_done')
    def _get_alternative_qty_done(self):
        for rec in self:
            rec.alternative_qty_done = rec.quantity_done * rec.product_id.additional_qty if rec.product_id.additional_qty else 0
    
    @api.onchange('alternative_qty_done')
    def _inverse_alternative_qty_done(self):
        for rec in self:
            is_rounded = rec.product_id.uom_id.is_rounded
            if rec.additional_qty > 0:
                rec.quantity_done = rec.alternative_qty_done / rec.additional_qty if is_rounded != True else round(rec.alternative_qty_done / rec.additional_qty)
            else:
                rec.quantity_done = rec.alternative_qty_done

    @api.onchange('quantity_done')
    def _onchange_quantity_done(self):
        for rec in self:
            if rec.picking_type_id.name in ['Receipts','Delivery Orders']:
                if rec.order_sheet_line_id and rec.product_uom_qty < rec.quantity_done:
                    raise UserError(_("Qty DO can't more than qty Order Sheet %s") % rec.product_uom_qty)
                
            if rec.product_uom_qty < rec.quantity_done:
                return {
                    'warning': {
                        'title': 'Warning!',
                        'message': 'Quantity Demand and Quantity Done differ. Would you like to proceed?'}
                }
    
    @api.onchange('order_sheet_line_id.qty_order', 'quantity_done')
    def _get_total_order_sheet_price(self):
        for rec in self:
            rec.price_subtotal_os = rec.order_sheet_line_id.qty_order * rec.sale_line_id.price_unit
            rec.price_subtotal_picking = rec.quantity_done * rec.sale_line_id.price_unit

    def get_po_number(self):
        for rec in self:
            moves_subcontracted =  rec.picking_id.move_ids.move_dest_ids.raw_material_production_id.move_finished_ids.move_dest_ids.filtered(lambda m: m.is_subcontract)
            if moves_subcontracted:
                return moves_subcontracted.purchase_line_id.order_id.name
            else:
                return rec.picking_id.purchase_order_id.name

    # @api.onchange('good_qty', 'quantity_done')
    def _onchange_check_good_qty(self):
        for rec in self:
            if rec.product_id:
                if rec.good_qty > 0 and rec.quantity_done > rec.good_qty:
                    rec.quantity_done = 0
                    raise ValidationError("Qty Done can't more than Good Qty %s." % self.product_id.name)
                # else:
                #     pass

 
    def _qty_return_order_sheet(self):
        for rec in self:
            if rec.order_sheet_line_id:
                sheet_return = rec.order_sheet_line_id.qty_return
                rec.order_sheet_line_id.qty_return = sheet_return + rec.quantity_done
                rec.order_sheet_line_id._get_data_quantity_dones()
                rec.order_sheet_line_id._get_amount_plan()

    def _get_quality_good_qty(self):
        for order in self:
            check_qc = self.env['quality.check'].search([('picking_id', '=', order.picking_id.id),('product_id', '=', order.product_id.id)])
            order.good_qty = sum(check_qc.mapped('good_qty'))
            
    @api.depends('product_id')
    def _get_tracking_categories(self):
        for rec in self:
            if rec.product_id.tracking == 'serial':
                rec.is_serial = True
            else:
                rec.is_serial = False
                
            if rec.product_id.tracking == 'lot':
                rec.is_lot = True
            else:
                rec.is_lot = False

    @api.constrains('quantity_done', 'product_uom_qty', 'picking_type_id', 'order_sheet_line_id')
    def _check_quantity_done(self):
        for rec in self:
            """
            Ada bug saat mengassign value seperti 887.3 menjadi 887.300000001. Jadi field dibulatkan rec.quantity_done
            """
            if rec.order_sheet_line_id.id:
                if rec.picking_type_id.code == 'outgoing' and round(rec.quantity_done,2) > rec.product_uom_qty:
                    raise ValidationError("Qt`y DO can't more than qty Order Sheet %s." % rec.product_id.name)
                elif rec.picking_type_id.code == 'incoming' and round(rec.quantity_done,2) > rec.product_uom_qty:
                    raise ValidationError("Qty Receipt can't more than qty Order Sheet %s." % rec.product_id.name)
            else:
                pass
            
    def action_assign_serial_show_details(self):
        """ On `self.move_line_ids`, assign `lot_name` according to
        `self.next_serial` before returning `self.action_show_details`.
        """
        
        if self.next_serial_count > self.good_qty or self.quantity_done > self.good_qty:
            raise ValidationError("Qty Done can't more than Good Qty %s." % self.product_id.name)
        
        self.ensure_one()
        if not self.next_serial:
            raise UserError(_("You need to set a Serial Number before generating more."))
        self._generate_serial_numbers()
        return self.action_show_details()

    def _create_quality_checks(self):
        _logger.info("FSGREdfd")
        # Groupby move by picking. Use it in order to generate missing quality checks.
        pick_moves = defaultdict(lambda: self.env['stock.move'])
        for move in self:
            if move.picking_id:
                pick_moves[move.picking_id] |= move
        check_vals_list = self._create_operation_quality_checks(pick_moves)
        for picking, moves in pick_moves.items():
            # Quality checks by product
            quality_points_domain = self.env['quality.point']._get_domain(moves.product_id, picking.picking_type_id, measure_on='product')
            quality_points = self.env['quality.point'].sudo().search(quality_points_domain)

            if not quality_points:
                continue
            picking_check_vals_list = quality_points._get_checks_values(moves.product_id, picking.company_id.id, existing_checks=picking.sudo().check_ids)
            for check_value in picking_check_vals_list:
                for m_line in moves:
                    _logger.info("prddd")
                    _logger.info(check_value['product_id'])
                    if check_value['product_id'] == m_line.product_id.id:
                        _logger.info("loooopiiinggg")
                        check_value.update({
                            'picking_id': picking.id,
                            'order_sheet_id': picking.order_sheet_id.id,
                            'order_qty': m_line.product_uom_qty,
                        })
            check_vals_list += picking_check_vals_list
        self.env['quality.check'].sudo().create(check_vals_list)

    @api.model
    def create(self, vals):
        res = super(EranStockMove, self).create(vals)
        if res.picking_id:
            res.set_auto_move_line()
        return res

    # def _get_qty_invoiced(self):
    #     for rec in self:
    #         domain = [('parent_state','=', 'posted'), ('product_id', '=', rec.product_id.id), ('stock_move_id', '=', rec.id)]

    #         if rec.purchase_line_id:
    #             domain = [('parent_state','=', 'posted'), ('product_id', '=', rec.product_id.id), ('purchase_line_id', '=', rec.purchase_line_id.id), ('stock_move_id', '=', rec.id)]

    #         res = sum(self.env['account.move.line'].search(domain).mapped('quantity'))
    #         rec.qty_invoiced = res


    
    def _get_invoice_line_vals(self, move, partner, inv_type):
        name = False
        move_lies = []
        # for move in moves:
        if inv_type in ('out_invoice'):
            account_id = move.product_id.property_account_income_id.id
            if not account_id:
                account_id = move.product_id.categ_id.property_account_income_categ_id.id
            if move.sale_line_id:
                name = move.sale_line_id.name
        else:
            account_id = move.product_id.property_account_expense_id.id
            if not account_id:
                # account_id = move.product_id.categ_id.property_account_expense_categ_id.id
                account_id = move.product_id.categ_id.property_stock_account_input_categ_id.id

        # set UoS if it's a sale and the picking doesn't have one
        uos_id = move.product_uom.id
        quantity = move.product_uom_qty - (move.qty_invoiced + move.qty_return)

        discount = 0
        
        if move.sale_line_id:
            discount = move.sale_line_id.discount
        elif move.purchase_line_id:
            discount = move.purchase_line_id.discount

        if move.quantity_done > 0:
            quantity = move.quantity_done - (move.qty_invoiced + move.qty_return)

        taxes_ids = self._get_taxes(move)
        if self._get_price_unit_invoice(move, inv_type) != None:
            price = self._get_price_unit_invoice(move, inv_type)
            subtotal = quantity * self._get_price_unit_invoice(move, inv_type)
        else:
            price = 0.0
            subtotal = quantity

        return  {
                'name': name or move.name,
                'move_id': move.id,
                'account_id': account_id,
                'product_id': move.product_id.id,
                'quantity': quantity,
                'price_subtotal':subtotal ,
                'price_unit': price,
                'tax_ids': [(6, 0, taxes_ids)],
                'discount': discount,
                'product_uom_id': uos_id,
            }

    def set_auto_move_line(self):
        for line in self:
            if not line.move_line_ids:
                datas = [(0, 0, {
                    'picking_id': line.picking_id.id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom.id,
                    'qty_done': 0,
                    'location_id': line.location_id.id,
                    'location_dest_id': line.location_dest_id.id,
                    'company_id': line.company_id.id or self.env.company.id,
                    'lot_id': False,
                    'package_id': False,
                    'result_package_id': False,
                })]
                line.move_line_ids = datas
class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # alternative_qty_done = fields.Float('Alternative Done', compute="_get_alternative_qty_done", inverse="_inverse_alternative_qty_done", store=True)
    alternative_qty_done = fields.Float('Alternative Done')
    alt_qty_done_uom_id = fields.Many2one(related="product_additional_uom_id", domain="[]")
    qty_done_uom_id = fields.Many2one(related="product_uom_id", domain="[]")
    qty_per_lot = fields.Float(string="Quantity(Kg)")
    is_weight = fields.Boolean(string='Weight', compute='eran_compute_weight')
    product_uom_qty = fields.Float(related='move_id.product_uom_qty', string="Demand")
    good_qty = fields.Float(related='move_id.product_uom_qty', string="Good Qty")
    alt_qty_demand = fields.Float('Alt Qty Demand',compute="_compute_alt_qty")

    @api.depends('product_uom_qty', 'product_additional_qty')
    def _compute_alt_qty(self):
        for move_line in self:
            if move_line.product_additional_qty and move_line.product_uom_qty:
                move_line.alt_qty_demand = move_line.product_additional_qty * move_line.product_uom_qty
            else:
                move_line.alt_qty_demand = 0


    @api.onchange('qty_per_lot')
    def _onchange_qty_per_lot(self):
        if self.product_uom_id.uom_type == 'bigger':
            self.qty_done = self.qty_per_lot / self.product_uom_id.factor
        elif self.product_uom_id.uom_type == 'smaller':
            self.qty_done = self.qty_per_lot * self.product_uom_id.factor
        else:
            self.qty_done = self.qty_per_lot

    @api.depends('product_uom_id')
    def eran_compute_weight(self):
        for this in self:
            this.is_weight = False
            uom_category_weight = self.env.ref('uom.product_uom_categ_kgm')
            if this.product_uom_id:
                if this.product_uom_id.category_id.id == uom_category_weight.id:
                    this.is_weight = True

    # @api.depends('qty_done')
    # def _get_alternative_qty_done(self):
    #     for rec in self:
    #         rec.alternative_qty_done = round(rec.qty_done * rec.move_id.product_id.additional_qty) if rec.move_id.product_id.additional_qty else 0

    @api.onchange('alternative_qty_done')
    def _inverse_alternative_qty_done(self):
        for rec in self:
            rec.qty_done = round(rec.alternative_qty_done / rec.move_id.product_id.additional_qty) if rec.move_id.product_id.additional_qty else 0

class StockInvoiceOnshipping(models.TransientModel):
    _inherit = 'stock.invoice.onshipping'

    @api.model
    def _default_has_down_payment(self):
        purchase_list = []
        sale_list = []
        picking_obj = self.env['stock.picking'].browse(self._context.get('active_ids', []))
        # Ambil daftar order ID terkait move line
        for picking in picking_obj:
            for mv in picking.move_ids_without_package:
                if mv.sale_line_id:
                    sale_list.append(mv.sale_line_id.order_id.id)
                
                if mv.purchase_line_id:
                    purchase_list.append(mv.purchase_line_id.order_id.id)

        if sale_list:
            sale_order = self.env['sale.order'].browse(sale_list[-1])
            return sale_order.order_line.filtered(
                lambda sale_order_line: sale_order_line.is_downpayment and not sale_order_line.is_downpayment_created and not sale_order_line.display_type
            )

        if purchase_list:
            purchase_order = self.env['purchase.order'].browse(purchase_list[-1])
            return purchase_order.order_line.filtered(
                lambda purchase_order_line: purchase_order_line.is_downpayment and not purchase_order_line.is_downpayment_created and not purchase_order_line.display_type
            )

        return False

    deduct_down_payments = fields.Boolean('Deduct down payments', default=True)
    has_down_payments = fields.Boolean('Has down payments', default=_default_has_down_payment, readonly=True)

    def open_invoice(self):
        try:
            invoice_ids = self.create_invoice()
        except IndexError:
            raise UserError(_('No invoice created or invoice is already created !'))

        if not invoice_ids:
            raise UserError(_('No invoice created or invoice is already created !'))
        action = {}
        if self.journal_type == 'sale':
            inv_type = 'out_invoice'
        else:
            inv_type = 'in_invoice'
        data_obj = self.env['ir.model.data']
        if inv_type == "out_invoice":
            action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
        elif inv_type == "in_invoice":
            action = self.env.ref('account.action_move_in_invoice_type').sudo().read()[0]
        if action and invoice_ids:
            if type(invoice_ids).__name__ == 'list':
                # action['domain'] = "[('id','in', [" + ','.join(map(str, invoice_ids)) + "])]"
                action['domain'] = [('id','in', invoice_ids)]
            else:
                action['domain'] = [('id','in', invoice_ids.ids)]
                
            return action
        # return True

    def create_invoice(self):
        # Ambil picking dari active_ids di context
        picking_obj = self.env['stock.picking'].browse(self._context.get('active_ids', []))
        
        if not picking_obj:
            raise UserError("No pickings found. Please select at least one picking.")
        
        # Ambil picking pertama untuk menentukan tipe
        pick = picking_obj[0]
        type = pick.picking_type_id.code
        
        # Penanganan untuk tipe 'incoming'
        if type == 'incoming':
            inv_type = 'in_invoice'
            purchase_list = []

            for picking in picking_obj:
                if picking.invoice_state == 'invoiced':
                    raise UserError("Invoice has been created.")

                for mv in picking.move_ids_without_package:
                    if mv.purchase_line_id:
                        purchase_list.append(mv.purchase_line_id.order_id.id)

            if purchase_list:
                purchase_orders = self.env['purchase.order'].sudo().search([('id', 'in', purchase_list)])
                if self.group:
                    # Buat invoice secara grup
                    inv = purchase_orders._create_invoices(final=self.deduct_down_payments, picking=picking_obj)
                    return inv
                else:
                    # Buat invoice satu per satu
                    inv_x = self.env['account.move']
                    for po in purchase_orders:
                        inv_x += po._create_invoices(final=self.deduct_down_payments, picking=picking_obj)
                    return inv_x
            else:
                # fallback ke cara lama kalau tidak ada PO terkait
                res = picking_obj.with_context(
                    date_inv=self.invoice_date,
                    inv_type=inv_type
                ).action_invoice_create(
                    journal_id=self.journal_id.id,
                    group=self.group,
                    move_type=inv_type,
                )
                return res

        # Penanganan untuk tipe 'outgoing'
        else:
            inv_type = 'out_invoice'
            sale_list = []
            
            # Ambil daftar order ID terkait move line
            for picking in picking_obj:
                if picking.invoice_state == 'invoiced':
                    raise UserError("Invoice has been created.")

                for mv in picking.move_ids_without_package:
                    if mv.sale_line_id:
                        sale_list.append(mv.sale_line_id.order_id.id)
                                    
            if sale_list:
                # Cari sale orders berdasarkan sale_list
                sale_orders = self.env['sale.order'].sudo().search([('id', 'in', sale_list)])
                if self.group:
                    # Buat invoice secara grup
                    inv = sale_orders._create_invoices(final=self.deduct_down_payments, picking=picking_obj)
                    return inv
                else:
                    # Buat invoice satu per satu
                    inv_x = self.env['account.move']
                    for sale in sale_orders:
                        inv_x += sale._create_invoices(final=self.deduct_down_payments, picking=picking_obj)
                    return inv_x

            else:
                # Jika tidak ada sale orders, proses dengan cara standar
                res = picking_obj.with_context(date_inv=self.invoice_date, inv_type=inv_type).action_invoice_create(
                    journal_id=self.journal_id.id,
                    group=self.group,
                    move_type=inv_type,
                )
                return res

    # def update_is_downpayment_created(self, obj):
    #     for record in obj:
    #         for line in record.order_line:
    #             line.is_downpayment_created = True