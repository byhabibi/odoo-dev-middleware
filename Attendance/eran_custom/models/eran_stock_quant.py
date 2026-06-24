from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import datetime
import logging
_logger = logging.getLogger(__name__)
from odoo.tools import config, float_compare



class StockQuant(models.Model):
    _inherit = "stock.quant"

    cost_product = fields.Float(related='product_id.product_tmpl_id.standard_price', string="Cost", store=False)

    def _domain_location_id(self):
        if not self._is_inventory_mode():
            return
        return [('usage', 'in', ['internal', 'transit', 'production'])]
    

    location_id = fields.Many2one(
        'stock.location', 'Location',
        domain=lambda self: self._domain_location_id(),
        auto_join=True, ondelete='restrict', required=True, index=True, check_company=True)

    @api.model
    def action_view_inventory(self):
        """ Similar to _get_quants_action except specific for inventory adjustments (i.e. inventory counts). """
        self = self._set_view_context()
        self._quant_tasks()

        ctx = dict(self.env.context or {})
        ctx['no_at_date'] = True
        if self.user_has_groups('stock.group_stock_user') and not self.user_has_groups('stock.group_stock_manager'):
            ctx['search_default_my_count'] = True
        action = {
            'name': _('Inventory Adjustments'),
            'view_mode': 'list',
            'view_id': self.env.ref('stock.view_stock_quant_tree_inventory_editable').id,
            'res_model': 'stock.quant',
            'type': 'ir.actions.act_window',
            'context': ctx,
            'domain': [('location_id.usage', 'in', ['internal', 'transit', 'production'])],
            'help': """
                <p class="o_view_nocontent_smiling_face">
                    {}
                </p><p>
                    {} <span class="fa fa-long-arrow-right"/> {}</p>
                """.format(_('Your stock is currently empty'),
                           _('Press the CREATE button to define quantity for each product in your stock or import them from a spreadsheet throughout Favorites'),
                           _('Import')),
        }
        return action

    @api.constrains("product_id", "quantity")
    def check_negative_qty(self):
        # To provide an option to skip the check when necessary.
        # e.g. mrp_subcontracting_skip_no_negative - passes the context
        # for subcontracting receipts.
        if self.env.context.get("skip_negative_qty_check"):
            return
        p = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        check_negative_qty = (
            config["test_enable"] and self.env.context.get("test_stock_no_negative")
        ) or not config["test_enable"]
        if not check_negative_qty:
            return

        for quant in self:
            disallowed_by_product = (
                not quant.product_id.allow_negative_stock
                and not quant.product_id.categ_id.allow_negative_stock
            )
            disallowed_by_location = not quant.location_id.allow_negative_stock
            if (
                float_compare(quant.quantity, 0, precision_digits=p) == -1
                and quant.product_id.type == "product"
                and quant.location_id.usage in ["internal", "transit"]
                and disallowed_by_product
                and disallowed_by_location
            ):
                msg_add = ""
                if quant.lot_id:
                    msg_add = _(" lot {}").format(quant.lot_id.name_get()[0][1])
                if not quant.location_id.is_subcontracting_location:
                    raise ValidationError(
                        _(
                            "You cannot validate this stock operation because the "
                            "stock level of the product '{name}'{name_lot} would "
                            "become negative "
                            "({q_quantity}) on the stock location '{complete_name}' "
                            "and negative stock is "
                            "not allowed for this product and/or location."
                        ).format(
                            name=quant.product_id.display_name,
                            name_lot=msg_add,
                            q_quantity=quant.quantity,
                            complete_name=quant.location_id.complete_name,
                        )
                    )
