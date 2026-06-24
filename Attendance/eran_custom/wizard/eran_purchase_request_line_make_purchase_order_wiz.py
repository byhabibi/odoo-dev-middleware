# -*- coding: utf-8 -*-
import logging

from datetime import datetime
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)


class PurchaseRequestLineMakePurchaseOrder(models.TransientModel):
    _inherit = "purchase.request.line.make.purchase.order"
    _description = "Inheritance Purchase Request Line Make Purchase Order"

    categ_id = fields.Many2one(
        comodel_name='product.category',
        string="Purchase Category",
        )
    purchase_type = fields.Selection([
        ('project', 'Project'),
        ('reguler', 'Reguler'),
        ('import', 'Import'),
        ('raw_material', 'Raw Material'),
        ('non_operational', 'Non Operational'),
        ('component', 'Component'),
        ('sparepart_tools', 'Sparepart & Tools'),
        ('purchase_part', 'Purchase Part'),
        ('subcont', 'Subcont'),
        ('factory_supply_consumable', 'Factory Supply & Consumables'),
        ('dieshop', 'Dieshop '),
        ('metrans', 'Metrans'),
        ('shipment', 'Shipment'),
        ('others', 'Others')
    ], string='Purchase Type')

    @api.model
    def _prepare_purchase_order(self, picking_type, group_id, company, origin):
        data =  super(PurchaseRequestLineMakePurchaseOrder, self)._prepare_purchase_order(picking_type, group_id, company, origin)
        if self.purchase_type:
            data['purchase_type'] = self.purchase_type
        if self.categ_id:
            data['categ_id'] = self.categ_id.id
        if self.item_ids:
            pr_list = self.item_ids.mapped('request_id.name')
            notes_txt = ','.join(list(map(str, pr_list)))
            data['notes'] = notes_txt
        return data

    @api.model
    def _prepare_purchase_order_line(self, po, item):
        if not item.product_id:
            raise UserError(_("Please select a product for all lines"))
        product = item.product_id

        # Keep the standard product UOM for purchase order so we should
        # convert the product quantity to this UOM
        qty = item.product_uom_id._compute_quantity(
            item.product_qty, product.uom_po_id or product.uom_id
        )
        # Suggest the supplier min qty as it's done in Odoo core
        min_qty = item.line_id._get_supplier_min_qty(product, po.partner_id)
        qty = max(qty, min_qty)
        date_required = item.line_id.date_required
        return {
            "order_id": po.id,
            "product_id": product.id,
            "purchase_request_id": item.request_id.id,
            "product_uom": product.uom_po_id.id or product.uom_id.id,
            "price_unit": 0.0,
            "product_qty": qty,
            "qty_edit": qty,
            "analytic_distribution": item.line_id.analytic_distribution,
            "purchase_request_lines": [(4, item.line_id.id)],
            "date_planned": datetime(
                date_required.year, date_required.month, date_required.day
            ),
            "move_dest_ids": [(4, x.id) for x in item.line_id.move_dest_ids],
            "name": item.name
        }
        
    @api.model
    def _prepare_item(self, line):
        vals =  super(PurchaseRequestLineMakePurchaseOrder, self)._prepare_item(line)
        pr_product_qty = line.product_qty
        po_ids = line.request_id.mapped("line_ids.purchase_lines.order_id")
        po_product_qty = 0

        for po in po_ids:
            if po.state != 'cancel':
                for po_line in po.order_line.filtered(lambda pol: line.id in pol.purchase_request_lines.ids):
                    # if line.product_id == po_line.product_id:
                    po_product_qty += po_line.product_qty
        
        vals.update({'product_qty': pr_product_qty - po_product_qty})
        return vals

    @api.model
    def _get_order_line_search_domain(self, order, item):
        vals = self._prepare_purchase_order_line(order, item)
        name = item.name
        order_line_data = [
            ("order_id", "=", order.id),
            ("name", "=", name),
            ("product_id", "=", item.product_id.id),
            ("product_uom", "=", vals["product_uom"]),
            ("analytic_distribution", "=?", item.line_id.analytic_distribution),
        ]
        if self.sync_data_planned:
            date_required = item.line_id.date_required
            order_line_data += [
                (
                    "date_planned",
                    "=",
                    datetime(
                        date_required.year, date_required.month, date_required.day
                    ),
                )
            ]
        if not item.product_id:
            order_line_data.append(("name", "=", item.name))
        return order_line_data
    
    def make_purchase_order(self):
        _logger.info('make_purchase_ordermake_purchase_ordermake_purchase_order===============')
        for item in self.item_ids:
            # val = 1
            # temp = []
            # round_vals = []
            # round_ids = item.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', item.product_id.product_tmpl_id.id), ('partner_id.id', '=', self.supplier_id.id), ('state', '=', 'done')])
            # for ids in round_ids:
            #     if ids.rounding_value != 0 and item.product_qty < ids.rounding_value:
            #         raise ValidationError(_("The %s purchase quantity cannot be Less than the Rounding Value [%s]." %(item.product_id.name, int(ids.rounding_value))))
            #     round_vals.append(ids.rounding_value)
                
            #     while val <= item.product_qty:
            #         if (val % ids.rounding_value) == 0:
            #             temp.append(val)
            #         val += 1
            # if len(temp)!=0:
            #     if item.product_qty in temp:
            #         pass
            #     else:
            #         raise ValidationError(_("The quantity of PR %s must be a multiple of either %s." %(item.product_id.name, round_vals)))  
            
            if item.product_qty > item.balancing_qty:
                raise ValidationError(_("Quantity to Purchase can't more than Balancing Qty."))
            
            if self.categ_id and item.categ_id.id != self.categ_id.id:
                raise ValidationError(_("You can't PO items outside [{}] category. Proceed by removing the red-marked ones.".format(self.categ_id.display_name)))
            
        # return super(PurchaseRequestLineMakePurchaseOrder, self).make_purchase_order()
        
        # add condition in function    
        res = []
        purchase_obj = self.env["purchase.order"]
        po_line_obj = self.env["purchase.order.line"]
        pr_line_obj = self.env["purchase.request.line"]
        purchase = False

        for item in self.item_ids:
            line = item.line_id
            if item.product_qty <= 0.0:
                raise UserError(_("Enter a positive quantity."))
            if self.purchase_order_id:
                purchase = self.purchase_order_id
            if not purchase:
                po_data = self._prepare_purchase_order(
                    line.request_id.picking_type_id,
                    line.request_id.group_id,
                    line.company_id,
                    line.origin,
                )
                purchase = purchase_obj.create(po_data)

            # Look for any other PO line in the selected PO with same
            # product and UoM to sum quantities instead of creating a new
            # po line
            domain = self._get_order_line_search_domain(purchase, item)
            _logger.info('domain')
            _logger.info(domain)
            available_po_lines = po_line_obj.search(domain)
            new_pr_line = True
            # If Unit of Measure is not set, update from wizard.
            if not line.product_uom_id:
                line.product_uom_id = item.product_uom_id
            # Allocation UoM has to be the same as PR line UoM
            alloc_uom = line.product_uom_id
            wizard_uom = item.product_uom_id
            if available_po_lines and not item.keep_description:
                _logger.info('111111111111111111111111')
                new_pr_line = False
                po_line = available_po_lines[0]
                po_line.purchase_request_lines = [(4, line.id)]
                po_line.move_dest_ids |= line.move_dest_ids
                po_line_product_uom_qty = po_line.product_uom._compute_quantity(
                    po_line.product_uom_qty, alloc_uom
                )
                wizard_product_uom_qty = wizard_uom._compute_quantity(
                    item.product_qty, alloc_uom
                )
                all_qty = min(po_line_product_uom_qty, wizard_product_uom_qty)
                self.create_allocation(po_line, line, all_qty, alloc_uom)
            else:
                _logger.info('222222222222222222222222222')
                po_line_data = self._prepare_purchase_order_line(purchase, item)
                if item.keep_description:
                    po_line_data["name"] = item.name
                po_line = po_line_obj.create(po_line_data)
                po_line_product_uom_qty = po_line.product_uom._compute_quantity(
                    po_line.product_uom_qty, alloc_uom
                )
                wizard_product_uom_qty = wizard_uom._compute_quantity(
                    item.product_qty, alloc_uom
                )
                all_qty = min(po_line_product_uom_qty, wizard_product_uom_qty)
                self.create_allocation(po_line, line, all_qty, alloc_uom)
            # TODO: Check propagate_uom compatibility:
            new_qty = pr_line_obj._calc_new_qty(
                line, po_line=po_line, new_pr_line=new_pr_line
            )
            po_line.product_qty = new_qty
            # The quantity update triggers a compute method that alters the
            # unit price (which is what we want, to honor graduate pricing)
            # but also the scheduled date which is what we don't want.
            date_required = item.line_id.date_required
            po_line.date_planned = datetime(
                date_required.year, date_required.month, date_required.day
            )
            res.append(purchase.id)
            po_line.onchange_qty_edit()

        return {
            "domain": [("id", "in", res)],
            "name": _("RFQ"),
            "view_mode": "tree,form",
            "res_model": "purchase.order",
            "view_id": False,
            "context": False,
            "type": "ir.actions.act_window",
        }
    

class PurchaseRequestLineMakePurchaseOrderItem(models.TransientModel):
    _inherit = 'purchase.request.line.make.purchase.order.item'

    balancing_qty = fields.Float('Balancing Qty', compute='_compute_balancing_qty')
    categ_id = fields.Many2one('product.category', related='product_id.categ_id')

    @api.depends('product_id', 'product_qty')
    def _compute_balancing_qty(self):
        # cek di purchase request line
        for line in self:
            pr_product_qty = line.line_id.product_qty
            
            po_ids = line.request_id.mapped("line_ids.purchase_lines.order_id")
            po_product_qty = 0
            for po in po_ids:
                if po.state != 'cancel':
                    for po_line in po.order_line.filtered(lambda pol: line.line_id.id in pol.purchase_request_lines.ids):
                        # if line.product_id == po_line.product_id:
                        po_product_qty += po_line.product_qty

            line.balancing_qty = pr_product_qty  - po_product_qty      

    