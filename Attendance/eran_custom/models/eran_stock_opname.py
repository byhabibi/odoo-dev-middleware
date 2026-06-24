from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError
import datetime
import logging
_logger = logging.getLogger(__name__)


class EranStockOpname(models.Model):
    _name = 'eran.stock.opname'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _order = 'no_tag desc'
    _description = 'Eran Stock Opname'

    no_tag = fields.Char(string="No. Tag", required=True, readonly=True, copy=False, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    tag_sto_id = fields.Many2one('eran.tag.sto', string='Tag STO')
    state = fields.Selection([
        ('draft','Draft'),
        ('confirm', 'Confirmed')], string="State", default="draft")
    sto_line_ids = fields.One2many('eran.stock.opname.line','stock_opname_id')
    stock_move_opname_line_ids = fields.One2many('eran.stock.move.opname.line','stock_opname_id')
    locations = fields.Many2one('stock.location', domain=[('usage', 'in', ('internal', 'transit', 'production'))], string="Location", copy=False)
    count_date = fields.Datetime(string="Count Date", copy=False)
    note = fields.Char(string="Note")
 
    counter_id = fields.Many2one('hr.employee', string="Counter", copy=False)
    checker = fields.Many2one('res.users', string="Checker", copy=False)
    data_entry = fields.Many2one('res.users', string="Data entry", copy=False)
    invoice_control = fields.Many2one('res.users', string="Inv Control", copy=False)

    internal_reference = fields.Char('Internal Reference', compute='_compute_products', store=True)
    product_names = fields.Char(string='Product', compute='_compute_products', store=True)
    product_uom = fields.Many2one('uom.uom', string='Product UOM', compute='_compute_products', store=True)
    counted_qty = fields.Float(string='Counted Qty', compute='_compute_products', store=True)

    @api.depends('stock_move_opname_line_ids', 'stock_move_opname_line_ids.product_id')
    def _compute_products(self):
        for tag in self:
            if tag.stock_move_opname_line_ids:
                tag.internal_reference = tag.stock_move_opname_line_ids[0].product_id.default_code
                tag.product_names = tag.stock_move_opname_line_ids[0].product_id.name
                tag.product_uom = tag.stock_move_opname_line_ids[0].product_id.uom_id.id
                tag.counted_qty = tag.stock_move_opname_line_ids[0].quantity_done

    @api.onchange('tag_sto_id')
    def _onchange_tag_sto_id(self):
        for sto in self:
            if sto.tag_sto_id:
                sto.locations = sto.tag_sto_id.location_id
                sto.count_date = sto.tag_sto_id.count_date
                sto.note = sto.tag_sto_id.note
                sto.stock_move_opname_line_ids = [(0,0, {
                    'product_id': line.product_id.id,
                }) for line in sto.tag_sto_id.product_line_ids]
            else:
                sto.locations = False
                sto.count_date = False
                sto.note = False
                sto.stock_move_opname_line_ids = [(5,0,0)]

    def name_get(self):
        result = []
        for tag in self:
            result.append((tag.id, "%s"%(tag.no_tag)))
        return result

    @api.model
    def create(self, vals):
        sequences_setting = self.env['dsn.inventory.sequence.setting'].search([
            ('type', '=', 'stock_opname'), ('company_id', '=', self.env.company.id)], limit=1)
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Stock Opname in Inventory Sequences Settings")

        name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
  
        if vals.get('no_tag', _('New')) == _('New'):
            vals['no_tag'] = name or _('New')
        if vals.get('tag_sto_id',False):
            new_tag_sto = self.env['eran.tag.sto'].browse(vals['tag_sto_id'])
            new_tag_sto.write({
                'state':'done'
            })
        res = super(EranStockOpname, self).create(vals)
        return res

    def write(self,vals):
        if vals.get('tag_sto_id',False):
            if self.tag_sto_id:
                self.tag_sto_id.state = 'confirmed'
            new_tag_sto = self.env['eran.tag.sto'].browse(vals['tag_sto_id'])
            new_tag_sto.write({
                'state':'done'
            })
        res = super(EranStockOpname, self).write(vals)
        return res

    def action_button_confirm(self):
        self.write({
            'state':'confirm',
            'count_date': fields.Datetime.now(),
        })
        for rec in self:
            if len(rec.stock_move_opname_line_ids)!=0:
                pass
            else:
                raise ValidationError(_('Please input detailed products.'))

            for line in rec.stock_move_opname_line_ids:
                stock_quant = line.env['stock.quant'].sudo().search([('product_id', '=', line.product_id.id), ('location_id', '=', self.locations.id), ('lot_id', '=', line.lot_id.id)])
     
                if line.product_id.id not in [x.product_id.id for x in stock_quant] and line.locations.id not in [x.location_id.id for x in stock_quant] and line.lot_id.id not in [x.lot_id.id for x in stock_quant]:
                    vals = self.env['stock.quant'].create({
                        'location_id': self.locations.id,
                        'product_id': line.product_id.id,
                        'lot_id': line.lot_id.id,
                        'inventory_quantity': line.quantity_done,
                        'inventory_date': self.count_date,
                        'inventory_quantity_set': True,
                        'user_id': self.create_uid.id
                })
                else:
                    for stq in stock_quant:
                        vals = stq.update({
                            'inventory_quantity': line.quantity_done
                            })
            return vals
  
    def action_button_cancel(self):
        self.write({
            'state':'cancel',
        })
  
    def action_button_reset_to_draft(self):
        self.write({
            'state':'draft',
        })
    
    @api.constrains('sto_line_ids')
    def _constrains_product_id(self):
        temp = []
        for rec in self.sto_line_ids:
            if rec.product_id:
                if rec.product_id.id not in temp:
                    temp.append(rec.product_id.id)
                else:
                    raise UserError(_('The %s product already exist!', rec.product_id.name))

class EranStockOpnameLine(models.Model):
    _name = 'eran.stock.opname.line'
    _description = 'Eran Stock Opname Line'
    
    product_id = fields.Many2one('product.product', string="Product")
    lot_id = fields.Many2one('stock.lot', string="Lot/Serial Number", copy=False)
    stock_opname_id = fields.Many2one('eran.stock.opname', string="No. Tag")
    stock_move_opname_line_ids = fields.One2many('eran.stock.move.opname.line','stock_opname_line_id')
    tracing = fields.Boolean(string="tracking", related='stock_opname_id.tracing', store=True)
    quantity_done = fields.Float(string="Counted", compute="_compute_quantity_done")
    quantity_done_kg = fields.Float(string='Counted(KG)', compute="_compute_quantity_done")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    product_uom = fields.Many2one(
        'uom.uom', 'Unit of Measure',
        related='product_id.uom_id', store=True,
        help="Default unit of measure used for all stock operations.")
    locations = fields.Many2one('stock.location', string="Location", related='stock_opname_id.locations')
    notes = fields.Char(string="Notes")
    tracing = fields.Selection([
        ('serial','By Unique Serial Number'),
        ('lot', 'By Lots'),
        ('none', 'No Tracking')], string="Tracking", related='product_id.tracking')
    
    @api.depends('stock_move_opname_line_ids')
    def _compute_quantity_done(self):
        for rec in self:
            res = 0
            res_kg = 0
            for line in rec.stock_move_opname_line_ids:
                res += line.quantity_done
                res_kg += line.quantity_done_kg

                
            rec.quantity_done = res
            rec.quantity_done_kg = res_kg
    
    def action_show_details(self):
        self.ensure_one()
        
        view = self.env.ref('eran_custom.eran_stock_opname_line_view_operations')
        return {
            'name': _('Detailed Operations'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'eran.stock.opname.line',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': self.id,
            'context': {},
        }
    
    
class EranStockMoveOpnameLine(models.Model):
    _name = 'eran.stock.move.opname.line'
    _description = 'Eran Stock Move Opname Line'
    _rec_name = 'no_tag'
    
    product_id = fields.Many2one('product.product', string="Product")
    stock_opname_line_id = fields.Many2one('eran.stock.opname.line', string="Stock Opname Line")
    stock_opname_id = fields.Many2one('eran.stock.opname', string="Stock Opname")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    locations = fields.Many2one('stock.location', string="Location", copy=False)
    lot_id = fields.Many2one('stock.lot', string="Lot/Serial Number", domain="[('product_id', '=', product_id)]", copy=False)
    quantity_done_kg = fields.Float(string='Counted(KG)')
    quantity_done = fields.Float(string="Counted")
    product_uom = fields.Many2one(
        'uom.uom', 'Unit of Measure',
        related='product_id.uom_id', store=True,
        help="Default unit of measure used for all stock operations.")
    tracing = fields.Selection([
        ('serial','By Unique Serial Number'),
        ('lot', 'By Lots'),
        ('none', 'No Tracking')], string="Tracking", related='product_id.tracking')
    is_weight = fields.Boolean(string='Weight', compute='compute_weight')
    count_date = fields.Datetime(string="Count Date", related='stock_opname_id.count_date', store=True)
    no_tag = fields.Char(string="No. Tag", related='stock_opname_id.no_tag', store=True,)
    tag_sto_id = fields.Many2one('eran.tag.sto',  related='stock_opname_id.tag_sto_id', store=True)
    state = fields.Selection([
        ('draft','Draft'),
        ('confirm', 'Confirmed')], related='stock_opname_id.state', store=True)
    value = fields.Monetary(
        string="Value",
        compute="_compute_value",
        currency_field="currency_id",
        store=True,
    )
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    categ_id = fields.Many2one('product.category', related='product_id.categ_id', store=True, readonly=True)
    category_group_id = fields.Many2one('eran.category.group', related='product_id.category_group_id', store=True, readonly=True)

    @api.depends('quantity_done', 'product_id.standard_price')
    def _compute_value(self):
        for line in self:
            line.value = line.quantity_done * line.product_id.standard_price

    
    @api.onchange('product_id', 'lot_id')
    def onchange_quantity_done(self):
        for rec in self:
            res = 0
            if rec.tracing == 'serial':
                res = 1
            else:
                pass
            rec.quantity_done = res

    @api.onchange('quantity_done_kg', 'product_uom')
    def _onchange_quantity_done(self):
        if self.product_uom:
            uom_kg = self.env.ref('uom.product_uom_kgm')
            uom_unit = self.product_uom
            quantity = self.quantity_done_kg
            self.quantity_done = self._get_calculate_qty(uom_unit, uom_kg, quantity)

    def _get_calculate_qty(self, uom_po, uom_id, quantity):
        if uom_po.id != uom_id.id:
            if uom_po.uom_type == 'bigger':
                qty_calculate =quantity * uom_po.factor
                return qty_calculate
            elif uom_po.uom_type == 'smaller':
                qty_calculate =quantity * uom_po.factor
                return qty_calculate
            elif uom_id.uom_type == 'bigger':
                qty_calculate =quantity / uom_id.factor
                return qty_calculate
            elif uom_id.uom_type == 'smaller':
                qty_calculate =quantity / uom_id.factor
                return qty_calculate
            else:
                qty_calculate =quantity
                return qty_calculate
        else:
            qty_calculate =quantity
            return qty_calculate

    @api.depends('product_uom')
    def compute_weight(self):
        for this in self:
            this.is_weight = False
            uom_category_weight = self.env.ref('uom.product_uom_categ_kgm')
            if this.product_uom:
                if this.product_uom.category_id.id == uom_category_weight.id:
                    this.is_weight = True