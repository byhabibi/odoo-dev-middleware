from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)
import datetime


class EranOrderSheet(models.Model):
  _name = 'eran.order.sheet'
  _order = 'id desc'

  name = fields.Char("Reference", required=True, copy=False, readonly=True, default=lambda self: _('New'))
  partner_id = fields.Many2one('res.partner', string="Contact")
  type_order = fields.Selection([
  ('sale','Sales'),
  ('purchase', 'Purchase')], string="Type Order")
  is_manual = fields.Boolean(string="Is Manual ?")
  sale_ids = fields.Many2many('sale.order', string="No. Order")
  purchase_ids = fields.Many2many('purchase.order', string="No. Order")
  no_order_sheet = fields.Char('No. Order Sheet')
  partner_ref = fields.Char(string="Partner Ref")
  remark = fields.Char(string="Remark")
  schedule_date = fields.Datetime(string="Schedule Date", default=datetime.datetime.now())
  sheet_line_ids = fields.One2many('eran.order.sheet.line', 'order_sheet_id', string='Order Sheet Line', copy=False)
  state = fields.Selection([
  ('draft','Draft'),
  ('done', 'Done'),
  ('return', 'Return'),
  ('cancel','Cancel')], string="State", default="draft")
  order_sheet_count = fields.Integer('History', compute='_order_sheet_count')
  order_qty_line = fields.Boolean('Qty Line', compute='_order_qty_line_count')
  # order_qty_sheet = fields.Float('Qty', compute='_get_qty_order_sheets', store=True)
  truck_number = fields.Char('No Truck')
  delivery_preparation = fields.Char(string="Delivery Preparation")
  company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
  picking_id = fields.Many2one('stock.picking', related='sheet_line_ids.picking_id')
  prepared_by_uid = fields.Many2one('res.users', string='Prepared By')
  checked_by_uid = fields.Many2one('res.users', string='Checked By')
  approved_by_uid = fields.Many2one('res.users', string='Approved By')
  revision_order_sheet_id = fields.Many2one('eran.order.sheet', string='Revision Order Sheet (Source)', help="Order Sheet dimana revisi berasal.")
  revision_order_sheet_ids = fields.One2many('eran.order.sheet', 'revision_order_sheet_id', string='Revision Order Sheet', help="Order Sheet revisi")
  revision_picking_id = fields.Many2one('stock.picking', string='Revision Picking (Source)', help="Transfer dimana revisi berasal.")

  qty_return_line = fields.Boolean('Qty Return Line', compute='_return_qty_line_count')

  @api.depends('sheet_line_ids.qty_return')
  def _return_qty_line_count(self):
      for data in self:
          _logger.info("_return_qty_line_count")
          result = []

          for line in data.sheet_line_ids:
              if line.product_id:
                  if line.qty_return > 0:
                      result.append(True)
                  else:
                      result.append(False)

          data.qty_return_line = any(result)
  
  @api.returns('self', lambda value: value.id)
  def copy(self, default=None):
    res = super(EranOrderSheet, self).copy(default)
    res.order_sheet_onchange()
    return res

  @api.depends('sheet_line_ids.qty_receipt')
  def _order_qty_line_count(self):
    for data in self:
      _logger.info("_order_qty_line_count")
      df = []
      for order in data.sheet_line_ids:
        if order.product_id:
          ks = [('id', '=', 0)]
          if order.sale_line_id:
            ks = [('state', '!=', 'cancel'),('order_sheet_id', '!=', False),('sale_line_id', '=', order.sale_line_id.id),('id', '!=', order._origin.id)]
          elif order.purchase_line_id:
            ks = [('state', '!=', 'cancel'),('order_sheet_id', '!=', False),('purchase_line_id', '=', order.purchase_line_id.id),('id', '!=', order._origin.id)]
          osl = self.env['eran.order.sheet.line'].search(ks)
          _logger.info(order.qty_order - (sum(osl.mapped('qty_receipt')) + order.qty_receipt))
          if order.qty_order <= (sum(osl.mapped('qty_receipt')) + order.qty_receipt):
            _logger.info("kesini")
            df.append(True)
          else:
            df.append(False)
      if False in df:
        data.order_qty_line = False
      else:
        data.order_qty_line = True

  @api.depends('state')
  def _order_sheet_count(self):
      for order in self:
        ks = [('id', '=', 0)]
        if len(order.sale_ids)==1:
          ks = [('sale_ids', '=', order.sale_ids.id)]
        elif len(order.purchase_ids)==1:
          ks = [('purchase_ids', '=', order.purchase_ids.id)]
        osl = self.search(ks)
        order.order_sheet_count = len(osl.mapped('id'))

  def action_view_history(self):
    ks = []
    name = 'Order Sheet'
    if len(self.sale_ids)==1:
      ks = [('sale_ids', '=', self.sale_ids.id)]
      ct = {'default_type_order': 'sale', 'default_is_manual': True}
      name = 'Order Sheet Customer'
    elif len(self.purchase_ids)==1:
      ks = [('purchase_ids', '=', self.purchase_ids.id)]
      ct = {'default_type_order': 'purchase', 'default_is_manual': True}
      name = 'Order Sheet Vendor'
    action_vals = {
        'name': name,
        'domain': ks,
        'view_mode': 'tree,form',
        'res_model': 'eran.order.sheet',
        'type': 'ir.actions.act_window',
        'context': ct
    }
    return action_vals

  @api.onchange('sale_ids', 'purchase_ids')
  def order_sheet_onchange(self):
    lines = [(5,0,0)]
    for data in self:
      if data.sale_ids:
        data.purchase_ids = False
        data.partner_id = data.sale_ids.partner_id.id
        for sale_line in data.sale_ids.order_line:
          _logger.info(sale_line.id)
          _logger.info(sale_line.product_id)
          _logger.info(sale_line)
          if sale_line.product_id and sale_line.product_id.is_global_discount != True:
            first_order_sheet_line = self.env['eran.order.sheet.line'].search([('sale_line_id', '=', sale_line._origin.id), ('state', 'not in', ['cancel','return'])], order='id asc', limit=1)
            all_order_sheet_line = self.env['eran.order.sheet.line'].search([('sale_line_id', '=', sale_line._origin.id), ('state', 'not in', ['cancel','return'])])
            total_qty_receipt = sum(all_order_sheet_line.mapped('qty_receipt'))
            total_qty_return = sum(all_order_sheet_line.mapped('qty_return'))
            qty_order = first_order_sheet_line.qty_order - total_qty_receipt + total_qty_return if first_order_sheet_line else sale_line.product_uom_qty
            val = {
                'sale_id': sale_line.order_id.id,
                'sale_line_id' : sale_line.id,
                'product_id' : sale_line.product_id.id,
                'uom_id' : sale_line.product_id.uom_id.id,
                'name' : sale_line.name,
                'qty_order' : qty_order,
            }
            lines.append((0, 0, val))
        data.sheet_line_ids = lines

      elif data.purchase_ids:
        data.sale_ids = False
        for purchase_line in data.purchase_ids.order_line:
          if purchase_line.product_id and purchase_line.product_id.is_global_discount != True:
            first_order_sheet_line = self.env['eran.order.sheet.line'].search([('purchase_line_id', '=', purchase_line._origin.id)], order='id asc', limit=1)
            all_order_sheet_line = self.env['eran.order.sheet.line'].search([('purchase_line_id', '=', purchase_line._origin.id), ('state', 'not in', ['cancel','return'])])
            total_qty_receipt = sum(all_order_sheet_line.mapped('qty_receipt'))
            total_qty_return = sum(all_order_sheet_line.mapped('qty_return'))
            qty_order = first_order_sheet_line.qty_order - total_qty_receipt + total_qty_return if first_order_sheet_line else purchase_line.product_uom_qty
            val = {
                'purchase_id': purchase_line.order_id.id,
                'purchase_line_id' : purchase_line.id,
                'product_id' : purchase_line.product_id.id,
                'uom_id' : purchase_line.product_id.uom_id.id,
                'name' : purchase_line.name,
                'qty_order' : qty_order,
            }
            lines.append((0, 0, val))
        data.sheet_line_ids = lines
        
  def create_transfer_os(self):
    dl_tf = self.env['stock.picking.type'].search([('name', '=', 'Delivery Orders')])
    rc_tf = self.env['stock.picking.type'].search([('name', '=', 'Receipts')])
    vals_list = []
    order_list = []
    date_today = datetime.date.today()

          
    for data in self:
      schedule_date = fields.Datetime.context_timestamp(self, data.schedule_date).date()

      if data.type_order == 'sale':
        for orders in data.sheet_line_ids:
          order_list.append(orders.sale_id.id)
      elif data.type_order == 'purchase':
        for orders in data.sheet_line_ids:
          order_list.append(orders.purchase_id.id)
      
      
      for data_line in data.sheet_line_ids:
        if data_line.qty_receipt!=0:
          vals_list.append(data_line.qty_receipt)

        if data_line.qty_receipt==0:
          data_line.unlink()

      if date_today > schedule_date:
        if not self.env.user.has_group('eran_custom.eran_order_sheet_bypass'):
          raise UserError(_('Cannot Generate Order Sheet because Schedule Date must be greater than today'))
          
      if len(vals_list) == 0:
        raise UserError(_('Cannot Generate Order Sheet because Receipt/Delivery is all zero'))
      
      if data.type_order == 'sale':
        for loop in set(order_list):
          lines = []
          for data_order in data.sheet_line_ids:
            if data_order.sale_id.id == loop:
              if data_order.qty_receipt != 0:
                value_line = {
                    'order_sheet_line_id': data_order.id,
                    'product_id': data_order.product_id.id,
                    'sale_line_id': data_order.sale_line_id.id,
                    'product_uom_qty': data_order.qty_receipt,
                    'price_unit': data_order.sale_line_id.price_unit,
                    'date': data.schedule_date,
                    'name':  data_order.product_id.name,
                    'product_uom':  data_order.product_id.uom_id.id,
                    'location_id': dl_tf.default_location_src_id.id,
                    'location_dest_id': data.partner_id.property_stock_customer.id,
                    'partner_id': data.partner_id.id,
                }
                lines.append((0, 0, value_line))
          value = {
              'order_sheet_id': data.id,
              'partner_id': data.partner_id.id,
              'scheduled_date': data.schedule_date,
              'picking_type_id': dl_tf.id,
              'origin': data.name,
              'location_id': dl_tf.default_location_src_id.id,
              'location_dest_id': data.partner_id.property_stock_customer.id,
              'move_ids_without_package': lines,
              'sale_order_id': loop,
          }
          if self.revision_picking_id:
            value['revision_picking_id'] = self.revision_picking_id.id
          intet_tf = self.env['stock.picking'].create(value)

          intet_tf.action_confirm()
      elif data.type_order == 'purchase':
        for loop in set(order_list):
          lines = []
          for data_order in data.sheet_line_ids:
            if data_order.purchase_id.id == loop:
              if data_order.qty_receipt != 0:
                value_line = {
                    'order_sheet_line_id': data_order.id,
                    'product_id': data_order.product_id.id,
                    'purchase_line_id': data_order.purchase_line_id.id,
                    'product_uom_qty': data_order.qty_receipt,
                    'price_unit': data_order.purchase_line_id.price_unit,
                    'date': data.schedule_date,
                    'name':  data_order.product_id.name,
                    'product_uom':  data_order.product_id.uom_id.id,
                    'location_id': data.partner_id.property_stock_supplier.id,
                    'location_dest_id': rc_tf.default_location_dest_id.id,
                    'partner_id': data.partner_id.id,
                    'description_picking': data_order.name
                }
                lines.append((0, 0, value_line))
          value = {
              'order_sheet_id': data.id,
              'partner_id': data.partner_id.id,
              'scheduled_date': data.schedule_date,
              'picking_type_id': rc_tf.id,
              'origin': data.name,
              'location_id': data.partner_id.property_stock_supplier.id,
              'location_dest_id': rc_tf.default_location_dest_id.id,
              'move_ids_without_package': lines,
          }
          if self.revision_picking_id:
            value['revision_picking_id'] = self.revision_picking_id.id
          intet_tf = self.env['stock.picking'].create(value)
          intet_tf.action_confirm()

      data.state = 'done'
      for data_lines in data.sheet_line_ids:
        data_lines._get_data_picking_id()

  def create_next_order_sheet(self):
    for data in self:
      name = 'Order Sheet'
      lines = []

      # schedule_date = fields.Datetime.context_timestamp(self, data.schedule_date).date()
      # date_today = datetime.date.today()

      # if date_today > schedule_date:
      #   raise UserError(_('Cannot Generate Order Sheet because Schedule Date must be greater than today'))

      for order in data.sheet_line_ids:
        if order.product_id:
          ks = [('id', '=', 0)]
          if order.sale_line_id:
            ks = [('state', '!=', 'cancel'),('order_sheet_id', '!=', False),('sale_line_id', '=', order.sale_line_id.id),('id', '!=', order.id)]
            name = 'Order Sheet Customer'
            oldest_ovs_domain = [('order_sheet_id', '!=', False),('sale_line_id', '=', order.sale_line_id.id),('id', '<', order.id), ('state', '!=', 'cancel')]
          elif order.purchase_line_id:
            ks = [('state', '!=', 'cancel'),('order_sheet_id', '!=', False),('purchase_line_id', '=', order.purchase_line_id.id),('id', '!=', order.id)]
            name = 'Order Sheet Vendor'
            oldest_ovs_domain = [('order_sheet_id', '!=', False),('purchase_line_id', '=', order.purchase_line_id.id),('id', '<', order.id), ('state', '!=', 'cancel')]
          osl = self.env['eran.order.sheet.line'].search(ks)
          old_osl = self.env['eran.order.sheet.line'].search(oldest_ovs_domain, limit=1, order='id asc')
          osl_qty_order = old_osl.qty_order if old_osl else order.qty_order
          # if osl_qty_order > (sum(osl.mapped('qty_receipt')) + order.qty_receipt):
          #  ............... code baru ...............
          total_received = sum(osl.mapped('qty_receipt')) + order.qty_receipt
          if osl_qty_order > total_received or order.qty_return > 0:
          #  .........................................
            _logger.info("trewerhretgetyh")
            val = {
                'purchase_id': order.purchase_id.id,
                'purchase_line_id' : order.purchase_line_id.id,
                'sale_id': order.sale_id.id,
                'sale_line_id' : order.sale_line_id.id,
                'product_id' : order.product_id.id,
                'uom_id' : order.product_id.uom_id.id,
                'name' : order.name,
                'qty_order' : osl_qty_order - (sum(osl.mapped('qty_receipt')) + order.qty_receipt),
            }
            #  ............... code baru ...............
            if order.qty_return > 0:
                total_return = sum(osl.mapped('qty_return')) + order.qty_return
                val['qty_order'] = max(0, osl_qty_order - total_received + total_return)
            #  .........................................
            lines.append((0, 0, val))

      intet_tf = self.create({
          'type_order': data.type_order,
          'is_manual': data.is_manual,
          'purchase_ids': data.purchase_ids,
          'sale_ids': data.sale_ids,
          'partner_id': data.partner_id.id,
          'partner_ref': data.partner_ref,
          'schedule_date': data.schedule_date,
          'remark': data.remark,
          'sheet_line_ids': lines,
      })
      action_vals = {
          'name': name,
          'res_id': intet_tf.id,
          'view_mode': 'form',
          'res_model': 'eran.order.sheet',
          'type': 'ir.actions.act_window',
          'context': {}
      }
      data.state = 'done'
      
      for data_lines in data.sheet_line_ids:
        data_lines._get_data_picking_id()
      return action_vals
            
  @api.model
  def create(self, vals):
    if vals['type_order'] == 'purchase':
      sequences_setting = self.env['dsn.inventory.sequence.setting'].search([('type', '=', 'order_sheet_vendor'), ('company_id', '=', self.env.company.id)], limit=1)
      if not sequences_setting or not sequences_setting.sequence_id:
        raise UserError("You must set sequence Order Sheet Vendor in Inventory Sequences Settings")
      name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
      vals['name'] = name
    else:
      sequences_setting = self.env['dsn.inventory.sequence.setting'].search([('type', '=', 'order_sheet_customer'), ('company_id', '=', self.env.company.id)], limit=1)
      if not sequences_setting or not sequences_setting.sequence_id:
        raise UserError("You must set sequence Order Sheet Customer in Inventory Sequences Settings")
      name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
      vals['name'] = name
    return super(EranOrderSheet, self).create(vals)

  def cancel_order_sheet(self):
    osl = self.env['stock.picking'].search([('order_sheet_id', '=', self.id)])
    for data in osl:
      if data.state == 'done':
        raise UserError(_('Cannot cancel transfer %s because already Done') % (data.name))
      elif data.state == 'cancel':
        raise UserError(_('Cannot cancel transfer %s because already Cancel') % (data.name))
      data.state = 'cancel'
    self.state = 'cancel'
    
    if self.type_order == 'purchase':
      for po_line in self.sheet_line_ids:
        po_line.purchase_line_id._compute_order_sheet_line_qty()
        po_line.purchase_id._compute_all_create_osv()
    elif self.type_order == 'sale':
      for so_id in self.sheet_line_ids:
        so_id.sale_line_id._compute_order_sheet_line_qty()
        so_id.sale_id._compute_all_create_order_sheet()

  def unlink(self):
    if self.state == 'cancel':
      raise UserError(_('Cannot delete Order Sheet %s because already Cancel') % (self.name))
    osl = self.env['stock.picking'].search([('order_sheet_id', '=', self.id)])
    for data in osl:
      if data.state == 'done':
        raise UserError(_('Cannot delete transfer %s because already Done') % (data.name))
      elif data.state == 'cancel':
        raise UserError(_('Cannot delete transfer %s because already Cancel') % (data.name))
    res = super(EranOrderSheet, self).unlink()
    return res
  
  # @api.depends('sheet_line_ids', 'state')
  # def _get_qty_order_sheets(self):
  #   for rec in self:
  #     res = 0
  #     if rec.state != 'cancel':
  #       for line in rec.sheet_line_ids:
  #         res += line.qty_receipt
        
  #     rec.order_qty_sheet = res
  
  # Connected and related to the function 'onchange_receipt_qty' in 'order_sheet_line'
  # which will trigger the function in purchase order or sale order to run.
  @api.onchange('sheet_line_ids')
  def _onchange_qty_receipt(self):
    for rec in self:
      if rec.type_order == 'sale':
        order_list = [x.sale_id for x in rec.sheet_line_ids]
        for orders in set(order_list):
          orders._compute_all_create_order_sheet()
      elif rec.type_order == 'purchase':
        order_list = [x.purchase_id for x in rec.sheet_line_ids]
        for orders in set(order_list):
          orders._compute_all_create_osv()
        
  def btn_print_order_sheet_vendor(self):
    docids = self.ids
    report_name = 'eran_custom.eran_report_order_sheet_vendor'
    action = self.env.ref(report_name).report_action(docids)
    return action

  def btn_print_order_sheet_customer(self):
    docids = self.ids
    report_name = 'eran_custom.eran_action_report_order_sheet_customer'
    action = self.env.ref(report_name).report_action(docids)
    return action
    
        
        

class EranOrderSheetLine(models.Model):
  _name = 'eran.order.sheet.line'

  order_sheet_id = fields.Many2one('eran.order.sheet', string="Order Sheet", required=True, ondelete='cascade', index=True, copy=False)
  sale_line_id = fields.Many2one('sale.order.line', string="Order Line")
  purchase_line_id = fields.Many2one('purchase.order.line', string="Order Line")
  product_id = fields.Many2one('product.product', string="Product")
  name = fields.Char(string="Description")
  qty_order = fields.Float(string="Order")
  # qty_balancing = fields.Float(string="Balancing")
  qty_receipt = fields.Float(string="Receipt", default=0, copy=False)
  uom_id = fields.Many2one('uom.uom', string="UoM")
  state = fields.Selection(string="State", related="order_sheet_id.state", store=True)
  
  sale_id = fields.Many2one('sale.order', string="Reference")
  purchase_id = fields.Many2one('purchase.order', string="Reference")
  picking_id = fields.Many2one('stock.picking', string="Transfer Ref", compute = "_get_data_picking_id", store=True)
  po_ref = fields.Char(string="PO Customer", related='sale_id.po_ref', store=True)
  partner_id = fields.Many2one(related='order_sheet_id.partner_id', store=True)
  schedule_date = fields.Datetime(related='order_sheet_id.schedule_date', store=True)
  no_order_sheet = fields.Char(related='order_sheet_id.no_order_sheet', store=True)
  os_name = fields.Char(related="order_sheet_id.name", string="Order Sheet", store=True)
  category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)
  product_name = fields.Char('Product Name', related="product_id.name", store=True)
  product_code = fields.Char('Product Code', related="product_id.default_code", store=True)
  effective_date = fields.Datetime('Effective Date', related="picking_id.date_done", store=True)
  ready_to_invoice_date = fields.Datetime('Ready to Invoice Date', related="picking_id.ready_to_invoice_date", store=True)
  dn_back_date = fields.Datetime('DN Back Date', related="picking_id.dn_back_date", store=True)
  dn_out_date = fields.Datetime('DN Back Date', related="picking_id.dn_out_date", store=True)
  quantity_done = fields.Float('Quantity Delivery', compute="_get_data_quantity_dones", store=True)
  alternative_uom_qty_receipt = fields.Float('Alternative UoM Qty Receipt', compute="_get_alternative_qty_uom", inverse="_inverse_alternative_qty_uom", store=True)
  alternative_uom_id_receipt = fields.Many2one(related="product_id.additional_uom_id", string='Alternative Uom Receipt', store=True)
  sale_price_unit = fields.Float('Unit Price', related="sale_line_id.price_unit", store=True)
  sale_amount = fields.Monetary('Amount', compute="_get_sale_amount", store=True)
  invoice_id = fields.Many2one('account.move', string='Invoice No', related='picking_id.invoice_id', store=True)
  currency_id = fields.Many2one('res.currency', string='Currency')

  amount_plan = fields.Float('Plan Amount', compute="_get_amount_plan", store=True)
  quantity_after_returns = fields.Float('Quantity After Return', compute="_get_data_quantity_dones", store=True)
  delivery_amount = fields.Float('Delivery Amount AT', compute="_get_amount_plan", store=True)
  transfer_state = fields.Selection(string="Status Transfer", related="picking_id.state", store=True)
  schedule_date = fields.Datetime(related='picking_id.scheduled_date', store=True)
  qty_return = fields.Float('Qty Return')

  # @api.depends('state')
  # def _compute_balancing_qty(self):
  #     for order in self:
  #       ks = [('id', '=', 0)]
  #       if order.sale_line_id:
  #         ks = [('sale_line_id', '=', order.sale_line_id.id),('state', '=', 'done')]
  #       elif order.purchase_line_id:
  #         ks = [('purchase_line_id', '=', order.purchase_line_id.id),('state', '=', 'done')]
  #       osl = self.search(ks)
  #       order.qty_balancing = sum(osl.mapped('qty_receipt'))
  
  @api.onchange('qty_receipt')
  def onchange_receipt_qty(self):
      for order in self:
        if order.product_id:
          ks = [('id', '=', 0)]
          if order.sale_line_id:
            ks = [('state', '!=', 'cancel'),('order_sheet_id', '!=', False),('sale_line_id', '=', order.sale_line_id.id),('id', '!=', self._origin.id)]
          elif order.purchase_line_id:
            ks = [('state', '!=', 'cancel'),('order_sheet_id', '!=', False),('purchase_line_id', '=', order.purchase_line_id.id),('id', '!=', self._origin.id)]
          osl = self.search(ks)
          qty_sisa = order.qty_order - sum(osl.mapped('qty_receipt'))
          if order.qty_order < order.qty_receipt:
            order.qty_receipt = 0
            raise UserError(_('Cannot Transfer because Qty Order Sheet %s greater than %s Qty Transfer') % (order.name, int(qty_sisa)))
          
          # qty_os_line = sum(osl.mapped('qty_receipt')) + order.qty_receipt
          if order.sale_line_id:
            order.sale_line_id._compute_order_sheet_line_qty()
          elif order.purchase_line_id:
             order.purchase_line_id._compute_order_sheet_line_qty()
          
          # order.qty_balancing = order.qty_order - (sum(osl.mapped('qty_receipt')) + order.qty_receipt)
          
  # def _get_data_quantity_done(self):
  #   for rec in self:
  #     move_id = rec.env['stock.move'].sudo().search([('order_sheet_line_id', '=', rec.id)], limit=1)
  #     if move_id:
  #       rec.quantity_done = move_id.quantity_done
  #     else:
  #       rec.quantity_done = False

  @api.depends('picking_id.move_ids_without_package.quantity_done', 'picking_id.move_ids_without_package.qty_return')
  def _get_data_quantity_dones(self):
      for line in self:
          if line.picking_id:
              move_lines = line.picking_id.move_ids_without_package.filtered(
                  lambda m: m.product_id == line.product_id and m.state != 'cancel'
              )
              res = sum(move_lines.mapped('qty_return'))
              line.quantity_done = sum(move_lines.mapped('quantity_done'))
              line.quantity_after_returns = line.quantity_done - res
          else:
              line.quantity_done = 0.0
              line.quantity_after_returns = 0.0

  @api.depends('qty_receipt', 'sale_price_unit', 'quantity_after_returns')
  def _get_amount_plan(self):
    for rec in self:
      rec._get_data_picking_id()
      rec._get_data_quantity_dones()
      rec._get_sale_amount()

      amount = rec.sale_price_unit * rec.qty_receipt
      delivery_amount = rec.sale_price_unit * rec.quantity_after_returns

      rec.delivery_amount = delivery_amount
      rec.amount_plan = amount


  def _get_data_picking_id(self):
    for rec in self:
      move_id = rec.env['stock.move'].sudo().search([('order_sheet_line_id', '=', rec.id)], limit=1)
      if move_id:
        rec.picking_id = move_id.picking_id.id
      else:
        rec.picking_id = False

  @api.depends('sale_price_unit', 'qty_receipt')
  def _get_sale_amount(self):
    for rec in self:
      amount = rec.sale_price_unit * rec.qty_receipt
      rec.sale_amount = amount
        
  # def unlink(self):
  #   for rec in self:
  #     if rec.state == 'done':
  #       raise UserError(_('Cannot delete Order Sheet %s because already Done') % (rec.name))
  #     if rec.picking_id:
  #       raise UserError(_('Cannot delete Order Sheet %s because already create Transfer') % (rec.name))
  #   return super(EranOrderSheetLine, self).unlink()
  
  @api.depends('qty_receipt')
  def _get_alternative_qty_uom(self):
      for rec in self:
          if rec.product_id.additional_qty > 0:
            rec.alternative_uom_qty_receipt = rec.qty_receipt * rec.product_id.additional_qty if rec.product_id.additional_qty else 0
          else:
            rec.alternative_uom_qty_receipt = rec.qty_receipt
  
  @api.onchange('alternative_uom_qty_receipt')
  def _inverse_alternative_qty_uom(self):
      for rec in self:
          is_rounded = rec.product_id.uom_id.is_rounded
          if rec.product_id.additional_qty > 0:
              rec.qty_receipt = rec.alternative_uom_qty_receipt / rec.product_id.additional_qty if is_rounded != True else round(rec.alternative_uom_qty_receipt / rec.product_id.additional_qty)
          else:
              rec.qty_receipt = rec.alternative_uom_qty_receipt