# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import api, fields, models
from odoo.tools import float_round
import logging
_logger = logging.getLogger(__name__)


class MrpCostStructure(models.AbstractModel):
    _inherit = 'report.mrp_account_enterprise.mrp_cost_structure'

    def get_lines(self, productions):
        ProductProduct = self.env['product.product']
        StockMove = self.env['stock.move']
        res = []
        currency_table = self.env['res.currency']._get_query_currency_table({'multi_company': True, 'date': {'date_to': fields.Date.today()}})
        for product in productions.mapped('product_id'):
            mos = productions.filtered(lambda m: m.product_id == product)
            # variables to calc cost share (i.e. between products/byproducts) since MOs can have varying distributions
            total_cost_by_mo = defaultdict(float)
            component_cost_by_mo = defaultdict(float)
            operation_cost_by_mo = defaultdict(float)

            # Get operations details + cost
            operations = []
            total_cost_operations = 0.0
            Workorders = self.env['mrp.workorder'].search([('production_id', 'in', mos.ids)])
            if Workorders:
                query_str = """SELECT
                                    wo.production_id,
                                    wo.id,
                                    op.id,
                                    wo.name,
                                    wc.name,
                                    wo.duration,
                                    CASE WHEN wo.costs_hour = 0.0 THEN wc.costs_hour ELSE wo.costs_hour END AS costs_hour,
                                    currency_table.rate
                                FROM mrp_workcenter_productivity t
                                LEFT JOIN mrp_workorder wo ON (wo.id = t.workorder_id)
                                LEFT JOIN mrp_workcenter wc ON (wc.id = t.workcenter_id)
                                LEFT JOIN mrp_routing_workcenter op ON (wo.operation_id = op.id)
                                LEFT JOIN {currency_table} ON currency_table.company_id = t.company_id
                                WHERE t.workorder_id IS NOT NULL AND t.workorder_id IN %s
                                GROUP BY wo.production_id, wo.id, op.id, wo.name, wc.costs_hour, wc.name, t.user_id, currency_table.rate
                                ORDER BY wo.name, wc.name
                            """.format(currency_table=currency_table,)
                self.env.cr.execute(query_str, (tuple(Workorders.ids), ))
                for mo_id, dummy_wo_id, op_id, wo_name, wc_name, duration, cost_hour, currency_rate in self.env.cr.fetchall():
                    cost = duration / 60.0 * cost_hour * currency_rate
                    total_cost_by_mo[mo_id] += cost
                    operation_cost_by_mo[mo_id] += cost
                    total_cost_operations += cost
                    operations.append([wc_name, op_id, wo_name, duration / 60.0, cost_hour * currency_rate])

            # Get the cost of raw material effectively used
            raw_material_moves = {}
            total_cost_components = 0.0
            query_str = """SELECT
                                sm.product_id,
                                mo.id,
                                abs(SUM(svl.quantity)),
                                abs(SUM(svl.value)),
                                currency_table.rate
                             FROM stock_move AS sm
                       INNER JOIN stock_valuation_layer AS svl ON svl.stock_move_id = sm.id
                       LEFT JOIN mrp_production AS mo on sm.raw_material_production_id = mo.id
                       LEFT JOIN {currency_table} ON currency_table.company_id = mo.company_id
                            WHERE sm.raw_material_production_id in %s AND sm.state != 'cancel' AND sm.product_qty != 0 AND scrapped != 't'
                         GROUP BY sm.product_id, mo.id, currency_table.rate""".format(currency_table=currency_table,)
            self.env.cr.execute(query_str, (tuple(mos.ids), ))
            for product_id, mo_id, qty, cost, currency_rate in self.env.cr.fetchall():
                cost *= currency_rate
                if product_id in raw_material_moves:
                    product_moves = raw_material_moves[product_id]
                    product_moves['cost'] += cost
                    product_moves['qty'] += qty
                else:
                    raw_material_moves[product_id] = {
                    'qty': qty,
                    'cost': cost,
                    'product_id': ProductProduct.browse(product_id),
                }
                total_cost_by_mo[mo_id] += cost
                component_cost_by_mo[mo_id] += cost
                total_cost_components += cost
            raw_material_moves = list(raw_material_moves.values())
            # Get the cost of scrapped materials
            scraps = StockMove.search([('production_id', 'in', mos.ids), ('scrapped', '=', True), ('state', '=', 'done')])

            _logger.info(scraps)

            # Get the byproducts and their total + avg per uom cost share amounts
            total_cost_by_product = defaultdict(float)
            qty_by_byproduct = defaultdict(float)
            qty_by_byproduct_w_costshare = defaultdict(float)
            component_cost_by_product = defaultdict(float)
            operation_cost_by_product = defaultdict(float)
            # tracking consistent uom usage across each byproduct when not using byproduct's product uom is too much of a pain
            # => calculate byproduct qtys/cost in same uom + cost shares (they are MO dependent)
            byproduct_moves = mos.move_byproduct_ids.filtered(lambda m: m.state != 'cancel')
            for move in byproduct_moves:
                qty_by_byproduct[move.product_id] += move.product_qty
                # byproducts w/o cost share shouldn't be included in cost breakdown
                if move.cost_share != 0:
                    qty_by_byproduct_w_costshare[move.product_id] += move.product_qty
                    cost_share = move.cost_share / 100
                    total_cost_by_product[move.product_id] += total_cost_by_mo[move.production_id.id] * cost_share
                    component_cost_by_product[move.product_id] += component_cost_by_mo[move.production_id.id] * cost_share
                    operation_cost_by_product[move.product_id] += operation_cost_by_mo[move.production_id.id] * cost_share

            # Get product qty and its relative total + avg per uom cost share amount
            uom = product.uom_id
            mo_qty = 0
            is_ng = False
            total_cost_fg = 0
            unit_cost_fg = 0
            total_cost_ng = 0
            unit_cost_ng = 0
            qty_ng = 0
            qty_good = 0
            for m in mos:
                cost_share = float_round(1 - sum(m.move_finished_ids.mapped('cost_share')) / 100, precision_rounding=0.0001)
                total_cost_by_product[product] += total_cost_by_mo[m.id] * cost_share
                component_cost_by_product[product] += component_cost_by_mo[m.id] * cost_share
                operation_cost_by_product[product] += operation_cost_by_mo[m.id] * cost_share
                qty = sum(m.move_finished_ids.filtered(lambda mo: mo.state == 'done' and mo.product_id == product and mo.location_id.usage in ("inventory", "production")).mapped('product_uom_qty'))


                if m.product_uom_id.id == uom.id:
                    mo_qty += qty
                else:
                    mo_qty += m.product_uom_id._compute_quantity(qty, uom)


                if m.ng_total > 0 and len( m.move_finished_ids.filtered(lambda x:x.state == 'done')) > 1:
                    is_ng = True
                    move_fg =  m.move_finished_ids[0]
                    stock_valuation_layer = self.env['stock.valuation.layer'].sudo().search([('stock_move_id', '=', move_fg.id)])
                    if stock_valuation_layer:
                        unit_cost_fg = stock_valuation_layer.unit_cost
                        total_cost_fg = stock_valuation_layer.value

                    move_ng =  m.move_finished_ids[1]
                    stock_valuation_layer = self.env['stock.valuation.layer'].sudo().search([('stock_move_id', '=', move_ng.id)])
                    if stock_valuation_layer:
                        unit_cost_ng = stock_valuation_layer.unit_cost
                        total_cost_ng = stock_valuation_layer.value  

                    qty_ng = m.ng_total
                    qty_good = m.good_total  

            res.append({
                'product': product,
                'mo_qty': mo_qty,
                'mo_uom': uom,
                'operations': operations,
                'currency': self.env.company.currency_id,
                'raw_material_moves': raw_material_moves,
                'total_cost_components': total_cost_components,
                'total_cost_operations': total_cost_operations,
                'total_cost': total_cost_components + total_cost_operations,
                'scraps': scraps,
                'is_ng': is_ng,
                'mocount': len(mos),
                'unit_cost_fg': unit_cost_fg,
                'total_cost_fg': total_cost_fg,
                'unit_cost_ng': unit_cost_ng,
                'total_cost_ng': total_cost_ng,
                'qty_ng': qty_ng,
                'qty_good': qty_good,
                'byproduct_moves': byproduct_moves,
                'component_cost_by_product': component_cost_by_product,
                'operation_cost_by_product': operation_cost_by_product,
                'qty_by_byproduct': qty_by_byproduct,
                'qty_by_byproduct_w_costshare': qty_by_byproduct_w_costshare,
                'total_cost_by_product': total_cost_by_product
            })
        return res

# code baru
class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    product_category_id = fields.Many2one(
        'product.category', 
        string='Product Category',
        compute='_compute_category_group',
        store=True
    )

    category_group_id = fields.Many2one(
        'eran.category.group', 
        string='Category Group',
        compute='_compute_category_group',
        store=True
    )

    @api.depends('product_id')
    def _compute_category_group(self):
        for rec in self:
            product = rec.product_id
            if product:
                rec.product_category_id = product.categ_id
                rec.category_group_id = product.product_tmpl_id.category_group_id if product.product_tmpl_id else False
            else:
                rec.product_category_id = False
                rec.category_group_id = False
