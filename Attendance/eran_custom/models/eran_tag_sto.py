from venv import logger
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class EranTagSto(models.Model):
    _name = 'eran.tag.sto'
    _description = 'Eran Tag Sto'

    name = fields.Char('No. Tag STO', default='New')
    location_id = fields.Many2one('stock.location', string='Location', required=True)
    count_date = fields.Datetime('Count Date')
    # product_category_id = fields.Many2one('product.category', string='Product Category')
    note = fields.Text('Note')
    product_line_ids = fields.One2many('eran.tag.sto.line', 'tag_sto_id', string='Product Line')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
    ], string='state', default='draft')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    internal_references = fields.Char('Internal Reference', compute='_compute_product_data', store=True)
    product_name = fields.Char(string='Product', compute='_compute_product_data', store=True)
    product_uom_id = fields.Many2one('uom.uom', string='Product UOM', compute='_compute_product_data', store=True)
    available_product_ids = fields.Many2many('product.product', compute="_compute_available_product_ids")

    @api.depends('location_id')
    def _compute_available_product_ids(self):
        list_product = []
        for product in self.env['product.product'].search([]):
            if product.product_location_ids:
                if self.location_id.id in product.product_location_ids.ids:
                    list_product.append(product.id)

        if list_product:
            self.available_product_ids = [(6,0,list_product)]
        else:
            self.available_product_ids = False

    @api.onchange('location_id')
    def _onchange_location_id(self):
        self.product_line_ids = [(6,0,[])]

    @api.depends('product_line_ids', 'product_line_ids.product_id')
    def _compute_product_data(self):
        for tag in self:
            if tag.product_line_ids:
                tag.internal_references = tag.product_line_ids[0].product_id.default_code
                tag.product_name = tag.product_line_ids[0].product_id.name
                tag.product_uom_id = tag.product_line_ids[0].product_id.uom_id.id

    def btn_confirm(self):
        for tag in self:
            if tag.state == 'draft':
                tag.state = 'confirmed'

    def btn_validate(self):
        self.state = 'done'

    def btn_reset(self):
        self.state = 'draft'

    def btn_print(self):
        report_name = 'eran_custom.eran_action_report_tag_sto'
        action = self.env.ref(report_name).report_action(self.ids)
        return action
    
    def find_first_missing(self,data):        
        for i in range(len(data) - 1):
            if data[i+1] - data[i] > 1:
                return data[i] + 1
        return data[-1] + 1

    @api.model
    def create(self, vals):
        
        seq = self.env['ir.sequence'].search([('code', '=', 'eran.tag.sto')], limit=1)
        if seq:
            if not seq.use_date_range:
                mapp = self.search([]).mapped('name')
                datas = []
                for m in mapp:
                    if m.split('/')[0].isdigit():
                        datas.append(int(m.split('/')[0]))
                if datas:
                    num = self.find_first_missing(sorted(datas))
                    seq.number_next_actual = num
            else:
                for line_date in seq.date_range_ids:
                    today = fields.Date.today()
                    if line_date.date_from <= today <= line_date.date_to:
                        year_now = datetime.now().year
                        first_date_year = datetime(year_now, 1, 1)
                        last_date_year = datetime(year_now, 12, 31)
                        mapp = self.search([('create_date', '>=', first_date_year), ('create_date', '<=', last_date_year)]).mapped('name')
                        datas = []
                        for m in mapp:
                            if m.split('/')[0].isdigit():
                                datas.append(int(m.split('/')[0]))
                        if datas:
                            num = self.find_first_missing(sorted(datas))
                            line_date.number_next_actual = num
        vals['name'] = self.env['ir.sequence'].next_by_code('eran.tag.sto')
        res = super(EranTagSto, self).create(vals)
        return res

class EranTagStoLine(models.Model):
    _name = 'eran.tag.sto.line'
    _description = 'Eran Tag Sto Line'

    tag_sto_id = fields.Many2one('eran.tag.sto', string='Tag Sto', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', domain="['|', ('id', 'in', available_product_ids),('product_location_ids', '=', False)]")
    available_product_ids = fields.Many2many('product.product', related="tag_sto_id.available_product_ids")
    
    @api.constrains('product_id')
    def access_check_product_id(self):
        for rec in self:
            if rec.product_id.product_location_ids and rec.tag_sto_id.location_id.id not in rec.product_id.product_location_ids.ids:
                raise ValidationError(_('Please select the product that suits the location'))

    # @api.depends('product_id')
    # def _compute_product_location_ids(self):
    #     for rec in self:
    #         if rec.product_id:
    #             rec.product_location_ids = [(6, 0, rec.product_id.product_tmpl_id.product_location_ids.ids)]
    #             if rec.tag_sto_id.location_id:
    #                 if rec.tag_sto_id.location_id.id not in rec.product_id.product_tmpl_id.product_location_ids.ids:
    #                     raise ValidationError(_('Aiiiiiih2'))
    #             else:
    #                 raise ValidationError(_('Aiiiiiih1'))
    #         else:
    #             rec.product_location_ids = False
        