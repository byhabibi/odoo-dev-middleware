from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv.expression import AND
import datetime
import logging
_logger = logging.getLogger(__name__)

class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    batch_type = fields.Selection([
        ('normal', 'Normal'),
        ('subcont', 'Subcont')
    ])
    picking_type_id = fields.Many2one(
        'stock.picking.type', 'Operation Type', check_company=True, copy=False,
        readonly=True, index=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env['stock.picking.type'].search([('name', '=', 'Resupply Subcontractor')], limit=1))
    no_mobil = fields.Char("No.Mobil")
    partner_id = fields.Many2one('res.partner', string='Vendor')
    picking_ids = fields.One2many(
        'stock.picking', 'batch_id', string='Transfers', readonly=True,
        domain="[('id', 'in', allowed_picking_ids)]", check_company=True,
        states={'draft': [('readonly', False)], 'in_progress': [('readonly', False)]},
        help='List of transfers associated to this batch')
    # eran_allowed_picking_ids = fields.One2many('stock.picking', compute='_compute_eran_allowed_picking_ids')
    request_date = fields.Datetime("Request Delivery Date")
    purchase_ids = fields.Many2many('purchase.order', string='Purchase Order')
    order_sheet_ids = fields.Many2many('eran.order.sheet', string='Order sheet')
    order_sheet_ids_domain = fields.Many2many('eran.order.sheet', string='Order sheet Domain', compute="_compute_osv_domain")
    product_ids = fields.Many2many('product.product', string='Product')
    product_ids_domain = fields.Many2many('product.product', string='Product Domain', compute="_compute_product_domain")

    def _replace_name(self):
        for record in self:
            if record.batch_type == 'normal':
                sequences_setting = self.env['dsn.inventory.sequence.setting'].search([
                    ('type', '=', 'batch_normal'), ('company_id', '=', self.env.company.id)], limit=1)
                
                if not sequences_setting or not sequences_setting.sequence_id:
                    raise UserError("You must set sequence Batch Normal in Inventory Sequences Settings")
                
                new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
                record.name = new_name
            else:
                sequences_setting = self.env['dsn.inventory.sequence.setting'].search([
                    ('type', '=', 'batch_subcont'), ('company_id', '=', self.env.company.id)], limit=1)

                if not sequences_setting or not sequences_setting.sequence_id:
                    raise UserError("You must set sequence Batch Subcont in Inventory Sequences Settings")

                new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
                record.name = new_name

    @api.model
    def create(self, vals):
        res = super(StockPickingBatch, self).create(vals)
        res._replace_name()
        return res

    # @api.depends('purchase_ids')
    # def _compute_osv_domain(self):
    #     for batch in self:
    #         order_sheets = []
            

    #         # Get purchase order ids
    #         purchase_ids = batch.purchase_ids.ids
    #         if purchase_ids:
    #             # Query order sheets directly from relation table
    #             self.env.cr.execute("""
    #                 SELECT DISTINCT eran_order_sheet_id 
    #                 FROM eran_order_sheet_purchase_order_rel
    #                 WHERE purchase_order_id IN %s
    #             """, (tuple(purchase_ids),))
    #             order_sheets = [r[0] for r in self.env.cr.fetchall()]
                
    #         batch.order_sheet_ids_domain = [(6, 0, order_sheets)]

    @api.depends('purchase_ids')
    def _compute_osv_domain(self):
        for batch in self:
            order_sheets = set()  # Gunakan set untuk menghindari duplikat ID
            
            # Kumpulkan picking IDs dari resupplies untuk menghindari or-ing recordset besar
            picking_ids = set()
            for purchase in batch.purchase_ids:
                # Pastikan purchase adalah singleton (meskipun dalam loop, ini aman)
                resupplies = purchase._get_subcontracting_resupplies()
                picking_ids.update(resupplies.ids)  # Kumpulkan IDs sebagai set
            
            # Buat recordset picking dari IDs yang dikumpul
            picking = self.env['stock.picking'].browse(picking_ids)
            
            # Filter picking yang state-nya bukan 'done' atau 'cancel'
            filtered_picking_ids = set()
            for p in picking:
                if p.state not in ['done', 'cancel']:
                    filtered_picking_ids.add(p.id)
            
            # Jika ada filtered picking, kumpulkan origins satu per satu
            if filtered_picking_ids:
                origins = set()
                for p_id in filtered_picking_ids:
                    p = self.env['stock.picking'].browse(p_id)  # Akses satu per satu untuk menghindari singleton error
                    if p.origin:
                        origins.add(p.origin)
                
                # Search picking_ROG berdasarkan origins
                picking_ROG = self.env['stock.picking'].search([('name', 'in', list(origins))])
                
                # Kumpulkan order_sheet IDs satu per satu untuk menghindari mapped pada recordset besar
                for rog in picking_ROG:
                    for move in rog.order_sheet_id:
                        if move.id:
                            order_sheets.add(move.id)
            
            # Set domain dengan list dari set (menghilangkan duplikat)
            batch.order_sheet_ids_domain = [(6, 0, list(order_sheets))]

    @api.depends('order_sheet_ids')
    def _compute_product_domain(self):
       for batch in self:
           products = []
           
           order_sheet_names = batch.order_sheet_ids.mapped('name')
           picking_ROG = self.env['stock.picking'].search([
                                ('origin', 'in', order_sheet_names),  # Perbaikan: gunakan 'in'
                           ])
           picking = self.env['stock.picking']
           for purchase in batch.purchase_ids:
               picking |= purchase._get_subcontracting_resupplies()
           # Filter: state not done/cancel, dan origin harus dalam order_sheet_names
           picking = picking.filtered(lambda p: p.state not in ['done','cancel'] and p.origin == picking_ROG.name)
           if picking:
               products = picking.mapped('move_ids_without_package.product_id').ids
           batch.product_ids_domain = [(6, 0, products)]
   
    
    @api.onchange('partner_id')
    def _onchange_clear_purchase(self):
        for rec in self:
            rec.purchase_ids = [(5,0,0)]

    @api.onchange('partner_id','purchase_ids')
    def _onchange_clear_order_sheet(self):
        for rec in self:
            rec.order_sheet_ids = [(5,0,0)]

    @api.onchange('partner_id','purchase_ids','order_sheet_ids')
    def _onchange_clear_product(self):
        for rec in self:
            rec.product_ids = [(5,0,0)]

    @api.onchange('product_ids')
    def _compute_partner_id(self):
        for rec in self:
            """ Mengambil picking berdasarkan vendor, po & product yg dipilih.

                Hati-hati saat mengubah field picking_ids. Field picking_ids bertipe one2many.
                Menghilangkan line dari field picking_ids bisa jadi bukan hanya menghilangkan
                hubungan one2many tetapi menghapus seluruh picking
            """
            # list_picking = self.env['stock.picking'].search([('partner_id', '=', rec.partner_id.id),('picking_type_id.name', '=', rec.picking_type_id.name),('state', 'in', ['draft','waiting','confirmed','assigned'])]).ids
            picking = self.env['stock.picking']
            val_remove_picking = []
            val_add_picking = []
            order_sheet_names = self.order_sheet_ids.mapped('name')
            picking_ROG = self.env['stock.picking'].search([
                                ('origin', 'in', order_sheet_names),  # Perbaikan: gunakan 'in'
                           ])
            for purchase in rec.purchase_ids:
                picking |= purchase._get_subcontracting_resupplies()
            picking = picking.filtered(lambda p: p.state not in ['done','cancel'] and any(product in p.mapped('move_ids_without_package.product_id').ids for product in rec.product_ids.ids))
            
            if picking:
                for origin_pick in rec.picking_ids.ids:
                    if origin_pick not in picking.ids:
                        val_remove_picking.append((3,origin_pick)) # Menghilangkan line dari one2many tanpa menghapus
                        # origin_pick.batch_id = False
                        self.env['stock.picking'].browse(origin_pick).batch_id = False
                # Modifikasi: Tambahkan kondisi if untuk memfilter berdasarkan origin
                picking_ROG_names = picking_ROG.mapped('name')  # Dapatkan list nama dari picking_ROG
                for pick in picking:
                    origin = pick.origin
                    if pick.origin in picking_ROG_names:  # Kondisi baru: Jika origin pick cocok dengan name di picking_ROG
                        val_add_picking.append((4,pick.id)) # Menghubungkan dengan one2many
            _logger.info("===============")
            _logger.info(rec._origin.picking_ids.ids)
            _logger.info(rec.picking_ids.ids)
            _logger.info(picking)
            _logger.info(val_remove_picking)
            _logger.info(val_add_picking)
            _logger.info("===============")
            # rec.write({'picking_ids':val_remove_picking})
            rec.write({'picking_ids': val_remove_picking + val_add_picking})



    def check_qty_po(self):
        # for move_line in self.move_line_ids:
        #     picking_id = move_line.picking_id
        #     finish_product_ids = move_line.finish_product_ids
        #     if picking_id:
        #         po_ids = picking_id._get_subcontracting_source_purchase()
        #         _logger.info(po_ids)
        #         for po_line in po_ids.order_line:
        #             if po_line.product_id.id in finish_product_ids.ids:
        #                 if move_line.qty_done > po_line.product_qty:
        #                     ValidationError(_('Quantity cannot be more than PO quantity'))
        for move_line in self.move_line_ids:
            if move_line.qty_done > move_line.reserved_uom_qty:
                ValidationError(_('Quantity cannot be more than PO quantity'))

    def action_done(self):
        self.check_qty_po()
        picking = self.env['stock.picking']
        values = []
        for detail_line in self.move_line_ids:
            if detail_line.qty_done == 0:
                picking |= self.picking_ids.filtered(lambda pick: pick.id == detail_line.picking_id.id)
        if picking:
            for pick in picking:
                values.append((3,pick.id))
            self.write({
                'picking_ids': values
            })

        return super(StockPickingBatch, self).action_done()

    @api.depends('company_id', 'picking_type_id', 'state')
    def _compute_allowed_picking_ids(self):
        allowed_picking_states = ['waiting', 'confirmed', 'assigned']

        for batch in self:
            # Search picking_ROG berdasarkan origins
            picking_ROG = self.env['stock.picking'].search([('order_sheet_id', 'in', list(batch.order_sheet_ids.ids))])
            domain_states = list(allowed_picking_states)
            # Allows to add draft pickings only if batch is in draft as well.
            if batch.state == 'draft':
                domain_states.append('draft')
            domain = [
                ('company_id', '=', batch.company_id.id),
                ('state', 'in', domain_states),
            ]
            if not batch.is_wave:
                domain = AND([domain, [('immediate_transfer', '=', False)]])
            if batch.picking_type_id:
                domain += [('picking_type_id', '=', batch.picking_type_id.id)]
                domain += [('origin', '=', picking_ROG.name)]
            batch.allowed_picking_ids = self.env['stock.picking'].search(domain)

    def action_create_move_lines(self):
        """Create stock.move.line records from stock.move data"""
        for batch in self:
            for move in batch.move_ids:
                existing_lines = self.env['stock.move.line'].search([
                    ('move_id', '=', move.id),
                    ('product_id', '=', move.product_id.id),
                    ('picking_id', '=', move.picking_id.id)
                ])
                if not existing_lines:
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'qty_done': 0,
                        'picking_id': move.picking_id.id,
                        'batch_id': batch.id,
                    })
        return True


class StockMoveLube(models.Model):
    _inherit = 'stock.move.line'


    product_additional_qty = fields.Float(string='Alternative UoM Qty', related='product_id.additional_qty')
    product_additional_uom_id = fields.Many2one('uom.uom', string='Additional UoM', related='product_id.additional_uom_id')
    product_additional_qty_2 = fields.Float(string='Alternative UoM Qty 2', related='product_id.additional_qty_2')
    product_additional_uom_id_2 = fields.Many2one('uom.uom', string='Additional UoM 2', related='product_id.additional_uom_id_2')
    finish_product_ids = fields.Many2many('product.product', string='Finish Product', compute='_compute_finish_product_ids')
    alternative_qty_done = fields.Float('Alternative Done', compute="_get_alternative_qty_done", inverse="_inverse_alternative_qty_done", store=True)


    @api.depends('product_id')
    def _compute_finish_product_ids(self):
        for rec in self:
            _logger.info('_compute_finish_product_ids_compute_finish_product_ids_compute_finish_product_ids')
            res = []
            product_tmpl_id = self.env['mrp.bom'].search([('bom_line_ids.product_id', '=', rec.product_id.id)]).mapped('product_tmpl_id')
            if product_tmpl_id:
                res = self.env['product.product'].search([('product_tmpl_id', 'in', product_tmpl_id.ids)])
            rec.finish_product_ids = res
        
    @api.depends('product_uom_qty', 'product_additional_qty')
    def _compute_alt_qty(self):
        for move_line in self:
            if move_line.picking_type_id.id == 11:
                if move_line.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty and move_line.product_uom_qty:
                    move_line.alt_qty_demand = move_line.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty * move_line.product_uom_qty
                else:
                    move_line.alt_qty_demand = 0
    
    @api.depends('qty_done')
    def _get_alternative_qty_done(self):
        for rec in self:
            if rec.picking_type_id.id == 11:
                rec.alternative_qty_done = rec.qty_done * rec.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty if rec.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty else 0
    
    @api.onchange('alternative_qty_done')
    def _inverse_alternative_qty_done(self):
        for rec in self:
            
            is_rounded = rec.product_id.uom_id.is_rounded
            if rec.picking_type_id.id == 11:
                if rec.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty > 0:
                    rec.qty_done = rec.alternative_qty_done / rec.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty if is_rounded != True else round(rec.alternative_qty_done / rec.move_id.bom_line_id.bom_id.product_tmpl_id.additional_qty)
                else:
                    rec.qty_done = rec.alternative_qty_done
