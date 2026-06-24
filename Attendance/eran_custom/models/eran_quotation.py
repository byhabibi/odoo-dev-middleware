from datetime import date, datetime, timedelta
from reportlab.pdfgen import canvas
import io
import logging
_logger = logging.getLogger(__name__)

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class EranQuotation(models.Model):
    _name = 'eran.quotation'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _order = 'date_order desc, id desc'
    _description = 'Quotation'

    STATE_SELECTION = [
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('done', 'Done'),
        ('closed', 'Closed')
    ]

    name = fields.Char("Name", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', "Customer", domain="[('type', '!=', 'private'), ('company_id', 'in', (False, company_id))]", tracking=True)
    date_order = fields.Datetime('Quotation Date', tracking=True)
    expiration_date = fields.Datetime('Expiration Date', tracking=True)
    

    # APPROVAL 
    approval_line_ids = fields.One2many('eran.quotation.approval.line', 'quotation_id', string="Approval Line", )
    approval_quotation_id = fields.Many2one('dsn.approval.sale', string="Approval Sale", compute="_compute_approval_quotation_id")
    approval_rule = fields.Selection(related="approval_quotation_id.approval_rule", string="Approval Rule")
    approval_type = fields.Selection(related="approval_quotation_id.approval_type", string="Approval Type")
    models = fields.Selection(related="approval_quotation_id.models", string="Model")
    assigned_to_ids = fields.Many2many(comodel_name="res.users",string="Approver",)
    user_in_assigned_to = fields.Boolean(string="User Is Assigned", compute="_computed_user_in_assigned_to")

    # pricelist_id = fields.Many2one('product.pricelist')
    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Pricelist",
        compute='_compute_pricelist_id',
        store=True, readonly=False, precompute=True, check_company=True, required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="If you change the pricelist, only newly added lines will be affected.", tracking=True)
    payment_term_id = fields.Many2one('account.payment.term', tracking=True)
    currency_id = fields.Many2one(
        related='pricelist_id.currency_id',
        depends=["pricelist_id"],
        store=True, precompute=True, ondelete="restrict")

    # Other info
    user_id = fields.Many2one('res.users', 'Salesperson', domain=lambda self: "[('groups_id', '=', {}), ('share', '=', False), ('company_ids', '=', company_id)]".format(
            self.env.ref("sales_team.group_sale_salesman").id
        ), tracking=True)
    team_id = fields.Many2one('crm.team', 'Sales Team', compute='_compute_team_id', store=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", tracking=True)
    require_signature = fields.Boolean(string="Online Signature", compute='_compute_require_signature', store=True, readonly=False, precompute=True,
        help="Request a online signature and/or payment to the customer in order to confirm orders automatically.", tracking=True)
    client_order_ref = fields.Char(string="Customer Reference", copy=False, tracking=True)
    tag_ids = fields.Many2many(
        comodel_name='crm.tag',
        relation='eran_quotation_tag_rel', column1='quotation', column2='tag_id',
        string="Tags", tracking=True)
    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string="Fiscal Position",
        domain="[('company_id', '=', company_id)]", tracking=True)
    commitment_date = fields.Datetime('Delivery Date', tracking=True)
    origin = fields.Char('Source document', tracking=True)
    campaign_id = fields.Many2one('utm.campaign', 'Campaign', tracking=True)
    medium_id = fields.Many2one('utm.medium', 'Medium', tracking=True)
    source_id = fields.Many2one('utm.source', 'Source', tracking=True)
    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string="Fiscal Position",
        compute='_compute_fiscal_position_id',
        store=True, readonly=False, precompute=True, check_company=True,
        help="Fiscal positions are used to adapt taxes and accounts for particular customers or sales orders/invoices."
            "The default value comes from the customer.",
        domain="[('company_id', '=', company_id)]", tracking=True)
    
    partner_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        string="Delivery Address",
        compute='_compute_partner_shipping_id',
        store=True, readonly=False, required=True, precompute=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", tracking=True)
    sale_rfq_id = fields.Many2one('eran.sale.rfq', 'RFQ', tracking=True)

    # Customer Signature
    signature = fields.Image(
        string="Signature",
        copy=False, attachment=True, max_width=1024, max_height=1024, tracking=True)
    signed_by = fields.Char(
        string="Signed By", copy=False, tracking=True)
    signed_on = fields.Datetime(
        string="Signed On", copy=False, tracking=True)
    
    note = fields.Html(
        string="Terms and conditions", tracking=True)
    is_loi_created = fields.Boolean('Loi Created', default=False, copy=False)
    

    # Quotation Line
    quotation_line = fields.One2many('eran.quotation.line', 'quotation_id', 'Quotation Line', copy=True)

    # Breakdown COGS
    breakdown_cogs_file = fields.Binary(string='File')
    breakdown_cogs_filename = fields.Char('Filename')

    parent_id = fields.Many2one('eran.quotation', 'Parent', tracking=True)
    child_line = fields.One2many('eran.quotation', 'parent_id', 'Child', tracking=True)
    child_line_count = fields.Integer('History', compute='_child_line_count', tracking=True)

    tax_totals = fields.Binary(compute='_compute_tax_totals', exportable=False)
    amount_untaxed = fields.Monetary(string="Untaxed Amount", store=True, compute='_compute_amounts', tracking=5)
    amount_tax = fields.Monetary(string="Taxes", store=True, compute='_compute_amounts')
    amount_total = fields.Monetary(string="Total", store=True, compute='_compute_amounts', tracking=4)

    state = fields.Selection(STATE_SELECTION, string='State', default='draft', tracking=True)
    breakdown_cogs_file_line = fields.One2many('eran.breakdown.cogs.line', 'quotation_id', string='Breakdown COGS')
    approve_uid = fields.Many2one('res.users', string='Approved by', readonly=True)
    approve_date = fields.Date('Approve date', readonly="True")

    loi_ids = fields.One2many('eran.quotation.loi', 'quotation_id', string='Loi')
    count_loi = fields.Integer('LOI', compute='_count_loi')


    def btn_draft(self):
        self.state = 'draft'

    @api.model
    def cron_remind_3_day_expire_notif(self):
        datetime_today = datetime.combine(date.today(), datetime.min.time())
        days_3_later = datetime_today + timedelta(days=3)
        days_4_later = datetime_today + timedelta(days=4)
        quotation = self.env['eran.quotation'].search([('state','=','done'),('expiration_date','>=',days_3_later),('expiration_date','<',days_4_later)])
        for quot in quotation:
            quot.activity_schedule(act_type_xmlid='eran_custom.reminder_quotation_expiration',user_id=quot.user_id.id, date_deadline=quot.expiration_date)

    def action_closed(self):
        self.write({
            'state': 'closed'
        })

    def update_expired_quotations(self):
        datetime_today = datetime.combine(date.today(), datetime.min.time())
        quotation_ids = self.env['eran.quotation'].search([('expiration_date', '<', datetime_today)])
        for quotation in quotation_ids:
            if not quotation.loi_ids:
                quotation.action_closed()

    def _count_loi(self):
        for rec in self:
            quotation_ids = self.child_line
            quotation_loi_ids = self.env['eran.quotation.loi'].search([('quotation_id', 'in', quotation_ids.ids)])
            rec.count_loi = len(quotation_loi_ids) if quotation_loi_ids else 0


    def action_view_loi(self):
        quotation_ids = self.child_line
        quotation_loi_ids = self.env['eran.quotation.loi'].search([('quotation_id', 'in', quotation_ids.ids)])
        action_vals = {
            'name': 'LOI',
            'domain': [('id', 'in', quotation_loi_ids.ids)],
            'view_mode': 'tree,form',
            'res_model': 'eran.quotation.loi',
            'type': 'ir.actions.act_window',
            'context': {}
        }
        return action_vals

    def _get_note_default(self):
        note_default = """
                        <p>Keterangan :</p>

                        <ul>
                        <li>Harga belum termasuk PPN 11%</li>
                        <li>Delivery 3 - 4 minggu dari PO</li>
                        <li>Pembayaran 30 hari setelah barang diterima</li>
                        <li>Validity harga 2 minggu</li>
                        </ul>
                        """
        return note_default

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res["note"] = self._get_note_default()
        return res

    def _child_line_count(self):
        for rec in self:
            rec.child_line_count = len(rec.child_line)

    @api.depends('company_id')
    def _compute_require_signature(self):
        for order in self:
            order.require_signature = order.company_id.portal_confirmation_sign

    @api.depends('partner_id', 'user_id')
    def _compute_team_id(self):
        cached_teams = {}
        for order in self:
            default_team_id = self.env.context.get('default_team_id', False) or order.team_id.id or order.partner_id.team_id.id
            user_id = order.user_id.id
            company_id = order.company_id.id
            key = (default_team_id, user_id, company_id)
            if key not in cached_teams:
                cached_teams[key] = self.env['crm.team'].with_context(
                    default_team_id=default_team_id
                )._get_default_team_id(
                    user_id=user_id, domain=[('company_id', 'in', [company_id, False])])
            order.team_id = cached_teams[key]


    @api.depends('partner_id')
    def _compute_pricelist_id(self):
        for order in self:
            if not order.partner_id:
                order.pricelist_id = False
                continue
            order = order.with_company(order.company_id)
            order.pricelist_id = order.partner_id.property_product_pricelist


    @api.depends('partner_id')
    def _compute_partner_shipping_id(self):
        for order in self:
            order.partner_shipping_id = order.partner_id.address_get(['delivery'])['delivery'] if order.partner_id else False

    @api.depends('partner_shipping_id', 'partner_id', 'company_id')
    def _compute_fiscal_position_id(self):
        """
        Trigger the change of fiscal position when the shipping address is modified.
        """
        cache = {}
        for order in self:
            if not order.partner_id:
                order.fiscal_position_id = False
                continue
            key = (order.company_id.id, order.partner_id.id, order.partner_shipping_id.id)
            if key not in cache:
                cache[key] = self.env['account.fiscal.position'].with_company(
                    order.company_id
                )._get_fiscal_position(order.partner_id, order.partner_shipping_id)
            order.fiscal_position_id = cache[key]


    @api.depends('quotation_line.tax_id', 'quotation_line.price_unit', 'amount_total', 'amount_untaxed')
    def _compute_tax_totals(self):
        for quotation in self:
            quotation_lines = quotation.quotation_line.filtered(lambda x: not x.display_type)
            quotation.tax_totals = self.env['account.tax']._prepare_tax_totals(
                [x._convert_to_tax_base_line_dict() for x in quotation_lines],
                quotation.currency_id,
            )

    @api.depends('quotation_line.price_subtotal', 'quotation_line.price_tax', 'quotation_line.price_total')
    def _compute_amounts(self):
        """Compute the total amounts of the SO."""
        for order in self:
            quotation_lines = order.quotation_line.filtered(lambda x: not x.display_type)
            order.amount_untaxed = sum(quotation_lines.mapped('price_subtotal'))
            order.amount_total = sum(quotation_lines.mapped('price_total'))
            order.amount_tax = sum(quotation_lines.mapped('price_tax'))

    @api.model
    def create(self, vals):
        sequences_setting = self.env['dsn.sales.sequence.setting'].search([
            ('type', '=', 'quotation'), ('company_id', '=', self.env.company.id)], limit=1)
        
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Quotation in Sales Sequences Settings")
        
        new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
        vals['name'] = new_name
        
        return super(EranQuotation, self).create(vals)
    
    def btn_create_loi(self):
        _logger.info('btn_create_loi')
        context = {'parent_id':self.id,
                    'default_partner_id': self.partner_id.id,
                    'default_pricelist_id': self.partner_id.property_product_pricelist.id,
                    'default_quotation_loi_line': [(0, 0, {'product_id':line.product_id.id, 'price': line.req_new_price if line.req_new_price > 0 else line.price_unit}) for line in self.quotation_line]
        }
        action_vals = {
            'name': "Letter Of Interest",
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'eran.quotation.loi.wiz',
            'view_id': self.env.ref('eran_custom.eran_quotation_loi_wizard').id,
            'target': 'new',
            'context':context
        }
        return action_vals

    def btn_create_revision(self):
        _logger.info('btn_create_revision')
        self.action_closed()
        for child in self.child_line:
            child.action_closed()
        data = super(EranQuotation, self).copy(default={'parent_id':self.id})
        data.write({'name': self.name + '-REV' + str(self.child_line_count + 1)})
        return data
    
    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        """ While duplicating quotation, generate name"""
        sequences_setting = self.env['dsn.sales.sequence.setting'].search([
            ('type', '=', 'quotation'), ('company_id', '=', self.env.company.id)], limit=1)
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Quotation in Sales Sequences Settings")
        default = dict(default or {}, 
                       name='New')
        return super().copy(default=default)

    def action_view_history(self):
        action_vals = {
            'name': 'Quotation',
            'domain': [('parent_id', '=', self.id)],
            'view_mode': 'tree,form',
            'res_model': 'eran.quotation',
            'type': 'ir.actions.act_window',
            'context': {}
        }
        return action_vals
    
    def _compute_approval_quotation_id(self):
        for rec in self:
            rec.approval_quotation_id = self.env['dsn.approval.sale'].search([('models', '=', 'quotation')], limit=1).id

    def _computed_user_in_assigned_to(self):
        if self.assigned_to_ids and self.state == 'waiting_approval':
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
            for appr_line in self.approval_quotation_id:
                if appr_line.approval_type == 'position-base-approval':
                    for job in appr_line.job_ids:
                        for approver in self.env.user.sudo().employee_id.approver_ids:
                            if job.job_id.id == approver.job_id.id:
                                records.append(approver.user_id.id)
                                self.env['eran.quotation.approval.line'].create({
                                    'quotation_id': self.id,
                                    'user_id': approver.user_id.id,
                                })
                else:
                    for user in appr_line.user_ids:
                        records.append(user.user_id.id)
                        self.env['eran.quotation.approval.line'].create({
                                'quotation_id': self.id,
                                'user_id': user.user_id.id,
                            })
        
        if not self.env.user.sudo().employee_id.approver_ids or len(records) == 0:
            raise ValidationError(_("Can't find approver for current user!"))

        self.assigned_to_ids = [(6, 0, records)]

        # send notification 
        if self.approval_rule == 'only-one-approved':
            # send notification to the first approver
            for rec in records:
                self.send_mail_activity('eran_custom.reminder_quotation_approval', rec)
        else:
            # send notification to all approver
            self.send_mail_activity('eran_custom.reminder_quotation_approval', records[0])

        # set state
        self.write({'state':'waiting_approval'})

    def send_mail_activity(self, act_type_xmlid, user_id):
        self.activity_schedule(
            act_type_xmlid=act_type_xmlid,
            user_id=user_id, 
            summary="Reminder Quotation Approval",
            note="You have items in the Quotation document that you need to approve ✅ Check if an action is needed. 👍")
                           
    def btn_approved(self):
        # set approval
        approval_quotation = self.env['eran.quotation.approval.line']
        # set is approved
        record = approval_quotation.search([('quotation_id', '=', self.id), ('user_id', '=', self.env.user.id),('is_approved', '=', False)], limit=1)
        record.write({'is_approved': True, 'date_approved': datetime.now()})
        
        res_model_id = self.env['ir.model'].sudo().search([('model', '=', 'eran.quotation')], limit=1).id

        # set state
        if self.approval_rule == 'only-one-approved':
            # self.active_approver = self.assigned_to_ids
            if any(self.approval_line_ids.mapped('is_approved')):
                self.write({
                    'state':'done', 
                    'approve_uid':self.env.user.id, 
                    'approve_date': fields.Date.today()
                })
                # set all mail activity to be done
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).action_done()
        # set state
        else:
            is_approved_counted = len(approval_quotation.search([('is_approved', '=', True), ('quotation_id.models', '=', 'quotation'), ('quotation_id', '=', self.id)]).ids)
            approval_quotation_user = [rec.user_id for rec in approval_quotation.search([], order='id asc')]
            current_user_id = approval_quotation_user[is_approved_counted - 1] if is_approved_counted else approval_quotation_user[0]

            if all(self.approval_line_ids.mapped('is_approved')):
                self.write({
                    'state':'done', 
                    'approve_uid':self.env.user.id, 
                    'approve_date': fields.Date.today()
                })
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
            else:
                # assign to the next approver
                user_id = approval_quotation_user[is_approved_counted]

                # set mail activity to be done one by one
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                
                # send notification to the next approver
                self.send_mail_activity('eran_custom.reminder_quotation_approval', user_id.id)

    
    def btn_set_to_draft(self):
        # ulink mail activity
        res_model_id = self.env['ir.model'].sudo().search([('model', '=', 'eran.quotation')], limit=1).id
        self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).unlink()
        # reset assigned_to_ids
        self.assigned_to_ids = [(6, 0, [])]
        # reset approval line
        self.env['eran.quotation.approval.line'].search([('quotation_id', '=', self.id)]).unlink()
        # set state
        self.write({'state':'draft'})


    def action_quotation_send(self):
        """ Opens a wizard to compose an email, with relevant mail template loaded by default """
        self.ensure_one()
        lang = self.env.context.get('lang')
        mail_template = self.env.ref('eran_custom.eran_mail_template_quotation', raise_if_not_found=False)
        if mail_template and mail_template.lang:
            lang = mail_template._render_lang(self.ids)[self.id]
        ctx = {
            'default_model': 'eran.quotation',
            'default_res_id': self.id,
            'default_use_template': bool(mail_template),
            'default_template_id': mail_template.id if mail_template else None,
            # 'default_use_template': False,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'default_email_layout_xmlid': 'mail.mail_notification_layout_with_responsible_signature',
            'proforma': self.env.context.get('proforma', False),
            'force_email': True,
            'cogs_file':self.breakdown_cogs_file_line.ids
            # 'model_description': self.with_context(lang=lang).type_name,
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

class EranQuotationApprovalLine(models.Model):
    _name = 'eran.quotation.approval.line'
    _description = "Eran Quotation Approval Line"

    quotation_id = fields.Many2one('eran.quotation', string="Quotation")
    is_approved = fields.Boolean(string="Is Approved")
    date_approved = fields.Datetime(string="Date Approved")
    user_id = fields.Many2one('res.users', string="User")    
    signature = fields.Binary(related='user_id.employee_id.signature', string="Signature")

class EranQuotationLine(models.Model):
    _name = 'eran.quotation.line'
    _description = 'Eran Quotation Line'


    quotation_id = fields.Many2one('eran.quotation', "Quotation Reference",
        required=True, ondelete='cascade', index=True, copy=False)
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        change_default=True, ondelete='restrict', check_company=True, index='btree_not_null',
        domain="[('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    product_name = fields.Char('Product Name', related="product_id.name")
    product_code = fields.Char('Product Code', related="product_id.default_code")
    product_template_id = fields.Many2one(
        string="Product Template",
        related='product_id.product_tmpl_id',
        domain=[('sale_ok', '=', True)])
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', depends=['product_id'])
    name = fields.Text(
        string="Description",
        compute='_compute_name',
        store=True, readonly=False, required=True, precompute=True)
    product_uom_qty = fields.Float(
        string="Quantity",
        digits='Product Unit of Measure', default=1.0,
        store=True)
    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string="Unit of Measure",
        domain="[('category_id', '=', product_uom_category_id)]")
    price_unit = fields.Float(
        string="Unit Price",
        digits='Product Price', compute="_compute_price_unit", store=True, readonly=False)
    tax_id = fields.Many2many(
        comodel_name='account.tax',
        string="Taxes",
        context={'active_test': False})
    company_id = fields.Many2one(
        related='quotation_id.company_id',
        store=True, index=True, precompute=True)
    currency_id = fields.Many2one(
        related='quotation_id.currency_id',
        depends=['quotation_id.currency_id'],
        store=True, precompute=True)
    order_partner_id = fields.Many2one(
        related='quotation_id.partner_id',
        string="Customer",
        store=True, index=True, precompute=True)
    salesman_id = fields.Many2one(
        related='quotation_id.user_id',
        string="Salesperson",
        store=True, precompute=True)
    display_type = fields.Selection(
        selection=[
            ('line_section', "Section"),
            ('line_note', "Note"),
        ],
        default=False)
    discount = fields.Float(
        string="Discount (%)",
        compute='_compute_discount',
        digits='Discount',
        store=True, readonly=False, precompute=True)
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute='_compute_amount',
        store=True, precompute=True)
    price_tax = fields.Float(
        string="Total Tax",
        compute='_compute_amount',
        store=True, precompute=True)
    price_total = fields.Monetary(
        string="Total",
        compute='_compute_amount',
        store=True, precompute=True)
    bom_cost = fields.Monetary('Bom Cost', compute="_compute_bom_cost")
    req_new_price = fields.Monetary('Req New Price')
    sale_rfq_line_id = fields.Many2one('eran.sale.rfq.line', string="RFQ Line")

    quotation_date = fields.Datetime('Quotation Date', related='quotation_id.date_order')
    quotation_expiration_date = fields.Datetime('Expiration Date', related='quotation_id.expiration_date')
    partner_id = fields.Many2one(string='Customer', related='quotation_id.partner_id')

    no_part = fields.Char('No Part')

    def write(self, vals):
        res = super(EranQuotationLine, self).write(vals)
        self.sale_rfq_line_id._compute_qty_quotation()
        self.sale_rfq_line_id.mapped('order_id').change_status()
        return res

    @api.depends('product_id')
    def _compute_price_unit(self):
        """
        Get price default from pricelit. with considered conditions are:
        1. min qty
        2. date
        3. product
        """

        for rec in self:
            if rec.product_id:
                # jika create date bernilai false diasumsikan quotation belum terbentuk, maka pakai datetime now
                create_date = rec.quotation_id.create_date or fields.datetime.today()

                item = rec.quotation_id.pricelist_id.item_ids.filtered(lambda r: 
                    r.product_tmpl_id.id == rec.product_id.product_tmpl_id.id and 
                    r.min_quantity <= rec.product_uom_qty and
                    (r.date_start and r.date_end)
                )

                item = item.filtered(lambda r: r.date_start <= create_date <= r.date_end)

                if len(item) > 0:
                    if len(item) == 1:
                        rec.price_unit = item.fixed_price
                    else:
                        rec.price_unit = item[0].fixed_price
                else:
                    rec.price_unit = 0

            else:        
                rec.price_unit = 0


    @api.depends('product_id')
    def _compute_bom_cost(self):
        for record in self:
            """
            Mengambil bom_cost dari report bom 'report.mrp.report_bom_structure'
            """
            record.bom_cost = 0
            bom_id = False
            if record.product_id.bom_ids:
                bom_id = record.product_id.bom_ids[0].id
                report_data = self.env['report.mrp.report_bom_structure']._get_report_data(bom_id)
                record.bom_cost = report_data['lines']['bom_cost']

    def _convert_to_tax_base_line_dict(self):
        """ Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.quotation_id.partner_id,
            currency=self.quotation_id.currency_id,
            product=self.product_id,
            taxes=self.tax_id,
            price_unit=self.price_unit,
            quantity=self.product_uom_qty,
            discount=self.discount,
            price_subtotal=self.price_subtotal,
        )

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        for line in self:
            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
            totals = list(tax_results['totals'].values())[0]
            amount_untaxed = totals['amount_untaxed']
            amount_tax = totals['amount_tax']

            line.update({
                'price_subtotal': amount_untaxed,
                'price_tax': amount_tax,
                'price_total': amount_untaxed + amount_tax,
            })
            if self.env.context.get('import_file', False) and not self.env.user.user_has_groups('account.group_account_manager'):
                line.tax_id.invalidate_recordset(['invoice_repartition_line_ids'])

    
    @api.depends('product_id', 'product_uom', 'product_uom_qty')
    def _compute_discount(self):
        for line in self:
            if not line.product_id or line.display_type:
                line.discount = 0.0

            if not (
                line.quotation_id.pricelist_id
                and line.quotation_id.pricelist_id.discount_policy == 'without_discount'
            ):
                continue

            line.discount = 0.0

            if not line.pricelist_item_id:
                continue

            line = line.with_company(line.company_id)
            pricelist_price = line._get_pricelist_price()
            base_price = line._get_pricelist_price_before_discount()

            if base_price != 0:  # Avoid division by zero
                discount = (base_price - pricelist_price) / base_price * 100
                if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
                    line.discount = discount
    


    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if not line.product_id:
                continue

            name = line.with_context(lang=line.order_partner_id.lang)._get_sale_order_line_multiline_description_sale()
            line.name = name

    def _get_sale_order_line_multiline_description_sale(self):
        """ Compute a default multiline description for this sales order line.

        In most cases the product description is enough but sometimes we need to append information that only
        exists on the sale order line itself.
        e.g:
        - custom attributes and attributes that don't create variants, both introduced by the "product configurator"
        - in event_sale we need to know specifically the sales order line as well as the product to generate the name:
          the product is not sufficient because we also need to know the event_id and the event_ticket_id (both which belong to the sale order line).
        """
        self.ensure_one()
        return self.product_id.get_product_multiline_description_sale()
    
    def _get_pricelist_price_before_discount_(self):
        """Compute the price used as base for the pricelist price computation.

        :return: the product sales price in the order currency (without taxes)
        :rtype: float
        """
        self.ensure_one()
        self.product_id.ensure_one()

        pricelist_rule = self.pricelist_item_id
        order_date = self.quotation_id.date_order or fields.Date.today()
        product = self.product_id.with_context(**self._get_product_price_context())
        qty = self.product_uom_qty or 1.0
        uom = self.product_uom

        if pricelist_rule:
            pricelist_item = pricelist_rule
            if pricelist_item.pricelist_id.discount_policy == 'without_discount':
                # Find the lowest pricelist rule whose pricelist is configured
                # to show the discount to the customer.
                while pricelist_item.base == 'pricelist' and pricelist_item.base_pricelist_id.discount_policy == 'without_discount':
                    rule_id = pricelist_item.base_pricelist_id._get_product_rule(
                        product, qty, uom=uom, date=order_date)
                    pricelist_item = self.env['product.pricelist.item'].browse(rule_id)

            pricelist_rule = pricelist_item

        price = pricelist_rule._compute_base_price(
            product,
            qty,
            uom,
            order_date,
            target_currency=self.currency_id,
        )

        return price
    
    def _get_pricelist_price_(self):
        """Compute the price given by the pricelist for the given line information.

        :return: the product sales price in the order currency (without taxes)
        :rtype: float
        """
        self.ensure_one()
        self.product_id.ensure_one()

        pricelist_rule = self.pricelist_item_id
        order_date = self.quotation_id.date_order or fields.Date.today()
        product = self.product_id.with_context(**self._get_product_price_context())
        qty = self.product_uom_qty or 1.0
        uom = self.product_uom or self.product_id.uom_id

        price = pricelist_rule._compute_price(
            product, qty, uom, order_date, currency=self.currency_id)

        return price
    
    @api.depends('product_id', 'product_uom', 'product_uom_qty')
    def _compute_discount_(self):
        for line in self:
            if not line.product_id:
                line.discount = 0.0

            if not (
                line.quotation_id.pricelist_id
                and line.quotation_id.pricelist_id.discount_policy == 'without_discount'
            ):
                continue

            line.discount = 0.0

            if not line.pricelist_item_id:
                # No pricelist rule was found for the product
                # therefore, the pricelist didn't apply any discount/change
                # to the existing sales price.
                continue

            line = line.with_company(line.company_id)
            pricelist_price = line._get_pricelist_price()
            base_price = line._get_pricelist_price_before_discount()

            if base_price != 0:  # Avoid division by zero
                discount = (base_price - pricelist_price) / base_price * 100
                if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
                    # only show negative discounts if price is negative
                    # otherwise it's a surcharge which shouldn't be shown to the customer
                    line.discount = discount

class EranBreakdownCogsLine(models.Model):
    _name = "eran.breakdown.cogs.line"

    quotation_id = fields.Many2one('eran.quotation', ondelete='cascade')
    name = fields.Char(string='Nama Attachment')
    attachment = fields.Binary(string='Upload Attachment')

class EranQuotationLoi(models.Model):
    _name = "eran.quotation.loi"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Letter of Interest'
    
    name = fields.Char()
    partner_id = fields.Many2one('res.partner', 'Customer')
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist')
    quotation_loi_line = fields.One2many('eran.quotation.loi.line', 'quotation_loi_id' ,'Line')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('done', 'Done'),
    ], string="State", default='draft', tracking=True, copy=False, )
    quotation_id = fields.Many2one('eran.quotation', string='Quotation')

    # APPROVAL 
    approval_line_ids = fields.One2many('eran.loi.approval.line', 'loi_id', string="Approval Line", )
    approval_loi_id = fields.Many2one('dsn.approval.sale', string="Approval Sale", compute="_compute_approval_loi_id")
    approval_rule = fields.Selection(related="approval_loi_id.approval_rule", string="Approval Rule")
    approval_type = fields.Selection(related="approval_loi_id.approval_type", string="Approval Type")
    models = fields.Selection(related="approval_loi_id.models", string="Model")
    assigned_to_ids = fields.Many2many(comodel_name="res.users",string="Approver",)
    user_in_assigned_to = fields.Boolean(string="User Is Assigned", compute="_computed_user_in_assigned_to")

    @api.depends('name')
    def _compute_approval_loi_id(self):
        for rec in self:
            rec.approval_loi_id = self.env['dsn.approval.sale'].search([('models', '=', 'loi')], limit=1).id

    def _computed_user_in_assigned_to(self):
        if self.assigned_to_ids and self.state == 'waiting_approval':
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

    def send_mail_activity(self, act_type_xmlid, user_id):
        self.activity_schedule(
            act_type_xmlid=act_type_xmlid,
            user_id=user_id, 
            summary="Reminder LOI Approval",
            note="You have items in the LOI document that you need to approve ✅ Check if an action is needed. 👍")
        
    def btn_waiting_approval(self):
        # set approver
        records = []
        if self.env.user.sudo().employee_id.approver_ids:
            for appr_line in self.approval_loi_id:
                if appr_line.approval_type == 'position-base-approval':
                    for job in appr_line.job_ids:
                        for approver in self.env.user.sudo().employee_id.approver_ids:
                            if job.job_id.id == approver.job_id.id:
                                records.append(approver.user_id.id)
                                self.env['eran.loi.approval.line'].create({
                                    'loi_id': self.id,
                                    'user_id': approver.user_id.id,
                                })
                else:
                    for user in appr_line.user_ids:
                        records.append(user.user_id.id)
                        self.env['eran.loi.approval.line'].create({
                                'loi_id': self.id,
                                'user_id': user.user_id.id,
                            })
        
        if not self.env.user.sudo().employee_id.approver_ids or len(records) == 0:
            raise ValidationError(_("Can't find approver for current user!"))

        self.assigned_to_ids = [(6, 0, records)]

        # send notification 
        if self.approval_rule == 'only-one-approved':
            # send notification to the first approver
            for rec in records:
                self.send_mail_activity('eran_custom.reminder_loi_approval', rec)
        else:
            # send notification to all approver
            self.send_mail_activity('eran_custom.reminder_loi_approval', records[0])

        # set state
        self.write({'state':'waiting_approval'})
    
    def btn_approved(self):
        # set approval
        approval_loi = self.env['eran.loi.approval.line']
        # set is approved
        record = approval_loi.search([('loi_id', '=', self.id), ('user_id', '=', self.env.user.id),('is_approved', '=', False)], limit=1)
        record.write({'is_approved': True, 'date_approved': datetime.now()})
        
        res_model_id = self.env['ir.model'].sudo().search([('model', '=', 'eran.quotation.loi')], limit=1).id

        # set state
        if self.approval_rule == 'only-one-approved':
            # self.active_approver = self.assigned_to_ids
            if any(self.approval_line_ids.mapped('is_approved')):
                # store pricelist
                for line in self.quotation_loi_line:
                    vals = {
                        'product_tmpl_id':line.product_id.product_tmpl_id.id,
                        'min_quantity':line.min_qty,
                        'fixed_price':line.price,
                        'date_start':line.start_date,
                        'date_end':line.end_date,
                        'pricelist_id':self.pricelist_id.id
                    }
                    self.env['product.pricelist.item'].create(vals)

                self.write({'state':'done'})
                # set all mail activity to be done
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).action_done()
        # set state
        else:
            is_approved_counted = len(approval_loi.search([('is_approved', '=', True), ('loi_id.models', '=', 'loi'), ('loi_id', '=', self.id)]).ids)
            approval_loi_user = [rec.user_id for rec in approval_loi.search([], order='id asc')]
            current_user_id = approval_loi_user[is_approved_counted - 1] if is_approved_counted else approval_loi_user[0]

            if all(self.approval_line_ids.mapped('is_approved')):
                # store pricelist
                for line in self.quotation_loi_line:
                    vals = {
                        'product_tmpl_id':line.product_id.product_tmpl_id.id,
                        'min_quantity':line.min_qty,
                        'fixed_price':line.price,
                        'date_start':line.start_date,
                        'date_end':line.end_date,
                        'pricelist_id':self.pricelist_id.id
                    }
                    self.env['product.pricelist.item'].create(vals)

                self.write({'state':'done'})
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
            else:
                # assign to the next approver
                user_id = approval_loi_user[is_approved_counted]

                # set mail activity to be done one by one
                self.env["mail.activity"].sudo().search([('res_id', '=', self.id),('res_model_id', '=', res_model_id),('user_id', '=', current_user_id.id)]).action_done()
                
                # send notification to the next approver
                self.send_mail_activity('eran_custom.reminder_loi_approval', user_id.id)
    
    def btn_set_to_draft(self):
        # ulink mail activity
        res_model_id = self.env['ir.model'].sudo().search([('model', '=', 'eran.quotation.loi')], limit=1).id
        self.env["mail.activity"].sudo().search([('res_id', '=', self.id), ('res_model_id', '=', res_model_id)]).unlink()
        # reset assigned_to_ids
        self.assigned_to_ids = [(6, 0, [])]
        # reset approval line
        self.env['eran.loi.approval.line'].search([('loi_id', '=', self.id)]).unlink()
        # set state
        self.write({'state':'draft'})

class EranQuotationLoiLine(models.Model):
    _name = "eran.quotation.loi.line"

    quotation_loi_id = fields.Many2one('eran.quotation.loi', 'Quotation Loi')
    product_id = fields.Many2one('product.product', 'Product')
    min_qty = fields.Float('Min. Quantity')
    price = fields.Float('Price')
    start_date = fields.Datetime('Start date')
    end_date = fields.Datetime('End date')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

class EranLoiApprovalLine(models.Model):
    _name = 'eran.loi.approval.line'
    _description = "Eran LOI Approval Line"

    loi_id = fields.Many2one('eran.quotation.loi', string="LOI")
    is_approved = fields.Boolean(string="Is Approved")
    date_approved = fields.Datetime(string="Date Approved")
    user_id = fields.Many2one('res.users', string="User")    
    signature = fields.Binary(related='user_id.employee_id.signature', string="Signature")