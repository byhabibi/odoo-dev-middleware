from odoo import api, fields, models, _
import logging
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class EranMrpProductWorkCenter(models.Model):
    _name = 'eran.mrp.product.bom'
    _description = 'Eran MRP Product BOM'

    name = fields.Char()
    product_template_id = fields.Many2one(
        string="Cost Name",
        comodel_name="product.template",
        copy=True,
        help="Product Template",
        index=True
    )
    workcenter_id = fields.Many2one('mrp.bom', string='BOM Id')
    cost = fields.Float(string="Cost", store=True, readonly=False, compute="_compute_cost")
    quantity = fields.Float(string="Quantity", store=True, readonly=False, compute="_compute_quantity_available")
    tooling_start_date = fields.Datetime('Start Date')
    tooling_end_date = fields.Datetime('End Date')
    bom_line_ids = fields.One2many('mrp.bom.line', 'product_tooling_id', string='BOM Line Id')


    @api.depends('product_template_id')
    def _compute_cost(self):
        for rec in self:
            rec.cost = rec.product_template_id.standard_price

    @api.depends('product_template_id')
    def _compute_quantity_available(self):
        for rec in self:
            rec.quantity = rec.product_template_id.qty_available

    def btn_confirm(self):
        for rec in self:
            if rec.bom_line_ids:
                rec.bom_line_ids.unlink()
            product_id = self.env['product.product'].search([('product_tmpl_id', '=', rec.product_template_id.id)])
            product_id.standard_price = rec.cost
            mrp_bom_ids = rec.workcenter_id
            mrp_bom_ids.write({
                'bom_line_ids': [(0, 0, {
                'product_id': product_id.id,
                'product_qty': rec.quantity,
                'product_uom_id': product_id.uom_id.id,
                'product_tooling_id': rec.id,
            })],
            })
            # _logger.info('product_id')
            # _logger.info(product_id)
            # mrp_bom_ids.bom_line_ids = [(0, 0, {
            #     'product_id': product_id.id,
            #     'product_qty': rec.quantity,
            #     'product_uom_id': product_id.uom_id.id,
            # })]

class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    product_tooling_id = fields.Many2one('eran.mrp.product.bom', string='Tooling')
    component_type = fields.Selection([('component', 'Component'), ('tooling', 'Tooling')], string='Type', compute='_get_component_type')

    def _get_component_type(self):
        for rec in self:
            rec.component_type = 'component' if not rec.product_tooling_id else 'tooling'


class MrpBom(models.Model):
    _inherit = 'mrp.bom' 
    _description = 'Manufacturing'

    product_ids = fields.One2many('eran.mrp.product.bom', 'workcenter_id', string="Product", copy=False)

    @api.model
    def check_bom_end_date(self):        
        next_week = datetime.now() + timedelta(days=7)
        
        for rec in self.search([]):
            for product in rec.product_ids:
                if next_week.strftime('%m/%d/%Y') == product.tooling_end_date.strftime('%m/%d/%Y') if product.tooling_end_date else False:
                    activity_type_id = self.env.ref("mail.mail_activity_data_todo").id
                    res_model_id = self.env['ir.model'].search([('model', '=', 'mrp.bom')], limit=1).id
                    manufacture_admin_group = self.env['res.groups'].search([('id', '=', self.env.ref('mrp.group_mrp_manager').id)])
                    
                    for user_id in [user.id for user in manufacture_admin_group.users]:
                        self.env["mail.activity"].sudo().create(
                            {
                                "activity_type_id": activity_type_id,
                                "note": _(
                                    "A manufacturing order that generated this. "
                                    "The expiry date on tooling %s for product %s will be end next week. "
                                    "Check if an action is needed."
                                )% (product.name, rec.product_tmpl_id.name),
                                "user_id": (
                                    user_id
                                ),
                                "res_id": rec.id,
                                "res_model_id": res_model_id,
                                'summary': 'Reminder BOM',
                            }
                        )

    @api.constrains('operation_ids', 'byproduct_ids', 'type')
    def _check_subcontracting_no_operation(self):
        if self.filtered_domain([('type', '=', 'subcontract'), '|', ('operation_ids', '!=', False), ('byproduct_ids', '!=', False)]):
            raise ValidationError(_('You can not set a Bill of Material with operations or by-product line as subcontracting.'))