from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

class SaleRequestQuotation(models.Model):
    _name = "eran.sale.rfq"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _description = 'Sale Request for Quotation'
    _order = 'date_order desc'

    STATE_SELECTION = [
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done')
    ]

    name = fields.Char("Name", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', "Customer", domain="[('type', '!=', 'private'), ('company_id', 'in', (False, company_id))]", tracking=True)
    date_order = fields.Datetime('Quotation Date', tracking=True)
    expiration_date = fields.Datetime('Expiration Date', tracking=True)
    
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
    quotations_ids = fields.Many2many('eran.quotation', string="Quotations", copy=False, tracking=True)
    count_quotations = fields.Integer(string="Quotations", compute='_compute_quotations_ids')
    
    partner_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        string="Delivery Address",
        compute='_compute_partner_shipping_id',
        store=True, readonly=False, required=True, precompute=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", tracking=True)

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
    
    tax_totals = fields.Binary(compute='_compute_tax_totals', exportable=False)
    amount_untaxed = fields.Monetary(string="Untaxed Amount", store=True, compute='_compute_amounts', tracking=5)
    amount_tax = fields.Monetary(string="Taxes", store=True, compute='_compute_amounts')
    amount_total = fields.Monetary(string="Total", store=True, compute='_compute_amounts', tracking=4)

    state = fields.Selection(STATE_SELECTION, string='State', default='draft', tracking=True)

    # Order lines
    order_line = fields.One2many('eran.sale.rfq.line', 'order_id', string='Order Lines', copy=True)

    @api.model
    def create(self, vals):
        sequences_setting = self.env['dsn.sales.sequence.setting'].search([
            ('type', '=', 'sale_rfq'), ('company_id', '=', self.env.company.id)], limit=1)
        
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Sale RFQ in Sales Sequences Settings")
        
        new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
        vals['name'] = new_name
        
        return super(SaleRequestQuotation, self).create(vals)

    def btn_draft(self):
        self.state = 'draft'

    def action_confirm(self):
        self.write({
            'state': 'confirm'
        })

    def action_generate_quotation(self):
        for record in self:
            value = {
                'partner_id': record.partner_id.id,
                'partner_shipping_id': record.partner_shipping_id.id,
                'user_id': record.user_id.id,
                'team_id': record.team_id.id,
                'sale_rfq_id': record.id,
                'date_order': record.date_order,
                'expiration_date': record.expiration_date,
                'company_id': record.company_id.id,
                'fiscal_position_id': record.fiscal_position_id.id,
                'commitment_date': record.commitment_date,
                'origin': record.origin,
                'campaign_id': record.campaign_id.id,
                'medium_id': record.medium_id.id,
                'source_id': record.source_id.id,
                'client_order_ref': record.client_order_ref,
                'note': record.note,
                'quotation_line': [(0, 0, {
                    'product_id': line.product_id.id,
                    'sale_rfq_line_id': line.id,
                    'product_uom_qty': line.product_uom_qty - line.qty_quotation,
                    'product_uom': line.product_uom.id,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'tax_id': [(6, 0, line.tax_id.ids)],
                }) for line in record.order_line if (line.product_uom_qty - line.qty_quotation) > 0]
            }
            quotation = self.env['eran.quotation'].create(value)
            record.quotations_ids = [(4, quotation.id)]

            for line in record.order_line:
                q_line = quotation.quotation_line.filtered(lambda x: x.product_id.id == line.product_id.id)
                if q_line:
                    line.quotation_line_ids = [(4, q.id) for q in q_line]
            
            record.change_status()

    def _compute_quotations_ids(self):
        for record in self:
            record.count_quotations = len(record.quotations_ids)

    def action_view_quotations(self):
        action_vals = {
            'name': 'Quotation',
            'domain': [('sale_rfq_id', '=', self.id)],
            'view_mode': 'tree,form',
            'res_model': 'eran.quotation',
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
    
    def change_status(self):
        for record in self:
            if all(line.product_uom_qty == line.qty_quotation for line in record.order_line):
                record.state = 'done'
            elif all(line.qty_quotation == 0 for line in record.order_line):
                record.state = 'draft'
            else:
                record.state = 'in_progress'


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


    @api.depends('order_line.tax_id', 'order_line.price_unit', 'amount_total', 'amount_untaxed')
    def _compute_tax_totals(self):
        for quotation in self:
            order_lines = quotation.order_line.filtered(lambda x: not x.display_type)
            quotation.tax_totals = self.env['account.tax']._prepare_tax_totals(
                [x._convert_to_tax_base_line_dict() for x in order_lines],
                quotation.currency_id,
            )

    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.price_total')
    def _compute_amounts(self):
        """Compute the total amounts of the SO."""
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            order.amount_untaxed = sum(order_lines.mapped('price_subtotal'))
            order.amount_total = sum(order_lines.mapped('price_total'))
            order.amount_tax = sum(order_lines.mapped('price_tax'))
    
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


class EranSaleRfqLine(models.Model):
    _name = 'eran.sale.rfq.line'
    _description = 'Sale Order Line'

    order_id = fields.Many2one('eran.sale.rfq', "Request for Quotation",
        required=True, ondelete='cascade', index=True, copy=False)
    quotation_line_ids = fields.Many2many('eran.quotation.line', string="Quotation Lines", copy=False)

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
        related='order_id.company_id',
        store=True, index=True, precompute=True)
    currency_id = fields.Many2one(
        related='order_id.currency_id',
        depends=['order_id.currency_id'],
        store=True, precompute=True)
    order_partner_id = fields.Many2one(
        related='order_id.partner_id',
        string="Customer",
        store=True, index=True, precompute=True)
    salesman_id = fields.Many2one(
        related='order_id.user_id',
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
    # req_new_price = fields.Monetary('Req New Price')

    qty_quotation = fields.Float('Qty Quotation', compute='_compute_qty_quotation')

    rfq_date = fields.Datetime('Request Date', related='order_id.date_order')
    rfq_expiration_date = fields.Datetime('Expiration Date', related='order_id.expiration_date')
    partner_id = fields.Many2one(string='Customer', related='order_id.partner_id')
    no_part = fields.Char('No Part')
    
    projection_sales = fields.Selection(
        string='Projection Sales',
        selection=[('add', 'Add'), ('replace', 'Replace')]
    )
    

    @api.depends('quotation_line_ids')
    def _compute_qty_quotation(self):
        for rec in self:
            rec.qty_quotation = sum(rec.quotation_line_ids.mapped('product_uom_qty'))
            rec.order_id.change_status()

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
                create_date = rec.order_id.create_date or fields.datetime.today()

                item = rec.order_id.pricelist_id.item_ids.filtered(lambda r: 
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
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
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
                line.order_id.pricelist_id
                and line.order_id.pricelist_id.discount_policy == 'without_discount'
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
        order_date = self.order_id.date_order or fields.Date.today()
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
        order_date = self.order_id.date_order or fields.Date.today()
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
                line.order_id.pricelist_id
                and line.order_id.pricelist_id.discount_policy == 'without_discount'
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