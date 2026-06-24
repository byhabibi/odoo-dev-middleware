from odoo import api, fields, models, _
from odoo.tools import float_compare
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class EranProductTemplate(models.Model):
    _inherit = 'product.template'

    additional_qty = fields.Float(string="Alternative UoM", default=1.0, digits=(10, 5))
    additional_uom_id = fields.Many2one('uom.uom', string="UoM")
    allocation_percentage_mrp = fields.Float(string="Allocation Percentage MRP", default=100)
    is_global_discount = fields.Boolean(string="Is Global Discount ?") 
    product_location_ids = fields.Many2many('stock.location', string='Product Location')
    category_group_id = fields.Many2one('eran.category.group', string='Category Group')
    additional_qty_2 = fields.Float(string="Alternative UoM 2", default=1.0, digits=(10, 5))
    additional_uom_id_2 = fields.Many2one('uom.uom', string="UoM 2")
    short_string = fields.Boolean(string="Short String")
    
    
    @api.constrains('allocation_percentage_mrp')
    def _constrains_allocation_percentage_mrp(self):
        for this in self:
            if this.allocation_percentage_mrp > 100:
                raise ValidationError(_('Maximum percentage 100'))

class EranProductProduct(models.Model):
    _inherit = 'product.product'

    product_location_ids = fields.Many2many('stock.location', related='product_tmpl_id.product_location_ids')

    def _select_seller(self, partner_id=False, quantity=0.0, date=None, uom_id=False, params=False):
        self.ensure_one()
        if date is None:
            date = fields.Date.context_today(self)
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        res = self.env['product.supplierinfo']
        sellers = self._prepare_sellers(params)
        sellers = sellers.filtered(lambda s: not s.company_id or s.company_id.id == self.env.company.id)
        for seller in sellers:
            # Set quantity in UoM of seller
            quantity_uom_seller = quantity
            if quantity_uom_seller and uom_id and uom_id != seller.product_uom:
                quantity_uom_seller = uom_id._compute_quantity(quantity_uom_seller, seller.product_uom)

            if seller.date_start and seller.date_start > date:
                continue
            if seller.date_end and seller.date_end < date:
                continue
            if partner_id and seller.partner_id not in [partner_id, partner_id.parent_id]:
                continue
            if quantity is not None and float_compare(quantity_uom_seller, seller.min_qty, precision_digits=precision) == -1:
                continue
            if seller.product_id and seller.product_id != self:
                continue
            # if not res or res.partner_id == seller.partner_id:
            if not res and seller.state == 'done' or res.partner_id == seller.partner_id:
                res |= seller
        return res.sorted('price')[:1]

class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'
    
    @api.model
    def create(self,values):
        sequences_setting = self.env['dsn.inventory.sequence.setting'].search([
            ('type', '=', 'landed_cost'), ('company_id', '=', self.env.company.id)], limit=1)
        
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Landed Cost in Inventory Sequences Settings")
        
        new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())

        if 'name' in values:
            if values['name'] == 'New':
                values['sequence_number'] = 0
                values['parent_revision_name'] = new_name
                values['name'] = new_name
        else:
            values['sequence_number'] = 0
            values['parent_revision_name'] = new_name
            values['name'] = new_name
        
        res = super(StockLandedCost, self).create(values)
        return res
    
    sequence_number = fields.Integer(string='Sequence Number')
    parent_revision_name = fields.Char('Parent Revision Name')
    
class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)
    
    @api.model
    def create(self,values):
        sequences_setting = self.env['dsn.inventory.sequence.setting'].search([
            ('type', '=', 'scrap'), ('company_id', '=', self.env.company.id)], limit=1)
        
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Scrap in Inventory Sequences Settings")
        
        new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())

        if 'name' in values:
            if values['name'] == 'New':
                values['sequence_number'] = 0
                values['parent_revision_name'] = new_name
                values['name'] = new_name
        else:
            values['sequence_number'] = 0
            values['parent_revision_name'] = new_name
            values['name'] = new_name
        
        res = super(StockScrap, self).create(values)
        return res
    
    sequence_number = fields.Integer(string='Sequence Number')
    parent_revision_name = fields.Char('Parent Revision Name')
    unit_cost = fields.Monetary('Unit Value', compute='_compute_cost_value', store=True)
    value = fields.Monetary('Total Value', compute='_compute_cost_value', store=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    @api.depends('move_id.stock_valuation_layer_ids')
    def _compute_cost_value(self):
        for scrap in self:
            valuation_layers = scrap.move_id.stock_valuation_layer_ids.filtered(lambda v: v.value != 0)
            if valuation_layers:
                total_value = sum(valuation_layers.mapped('value'))
                total_qty = sum(valuation_layers.mapped('quantity'))
                scrap.value = total_value
                scrap.unit_cost = total_value / total_qty if total_qty else 0
            else:
                scrap.value = 0.0
                scrap.unit_cost = 0.0

class EranUom(models.Model):
    _inherit = 'uom.uom'

    is_rounded = fields.Boolean(string="Is it rounded up?")