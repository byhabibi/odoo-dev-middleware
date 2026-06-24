# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from datetime import datetime, timedelta
import pytz
from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, api, _, Command
from odoo.tools import populate
from odoo.tools.misc import OrderedSet, format_date, groupby as tools_groupby

from odoo.tools import float_compare, float_round, float_is_zero, format_datetime
import logging
_logger = logging.getLogger(__name__)


class EranNgMrpProduction(models.Model):
    _name = 'eran.ng.mrp.production'

    quantity = fields.Float(string="Quantity", readonly=False)

    production_id = fields.Many2one("mrp.production",
        string="Production",
        help="MRP Production",
        domain="")
    
    no_good_id = fields.Many2one("eran.no.good",
        string="NG Type",
        help="Master data No Good quality module",
        domain="")
    
    workcenter_id = fields.Many2one("mrp.workcenter",
        string="Work Center",
        help="Work Center",
        domain="")

    workcenter_ids = fields.Many2many(
        comodel_name="mrp.workcenter",
        string="Work Order",
        compute="_compute_workorders",
        recursive=True,
    )
    
    schedule_date = fields.Datetime(string="Schedule Date", related='production_id.date_planned_start', store=True)
    product_id = fields.Many2one("product.product", string="Product", help="Product", related='production_id.product_id', store=True)
    shift_id = fields.Many2one("eran.master.shift", string="Shift", help="Shift", related='production_id.shift_id', store=True)
    operator_id = fields.Many2one("hr.employee", string="Operator", help="Operator", related='production_id.operator_id', store=True)
    category_group_id = fields.Many2one(related="product_id.category_group_id", store=True)

    @api.depends('production_id', 'workcenter_id', 'production_id.workorder_ids')
    def _compute_workorders(self):
        for rec in self:
            res = [(6, 0, rec.production_id.workorder_ids.mapped('workcenter_id').ids)]
            rec.workcenter_ids = res

class MroProduction(models.Model):
    _inherit = 'mrp.production'

    ng_ids = fields.One2many('eran.ng.mrp.production', 'production_id', string="Product", copy=False)
    
    operator_id = fields.Many2one("hr.employee",
        string="Operator",
        help="Master data employee employee module",
        domain="")
    
    operator_id2 = fields.Many2one("hr.employee",
        string="Operator 2",
        help="Master data employee employee module",
        domain="")

    leader_id = fields.Many2one("hr.employee",
        string="Leader",
        domain="")
    
    shift_id = fields.Many2one("eran.master.shift",
        string="Shift",
        help="Master data shift employee module",
        domain="")
    ng_total = fields.Float("NG Total", compute="_compute_ng_total")
    
    stock_picking_ids = fields.One2many("stock.picking", 'manufacture_production_id', string="Stock Picking", copy=False)
    material_request_count = fields.Integer("Material Request", compute="_compute_material_request_count")
    good_total = fields.Float(string='Good total', compute=False, copy=False)
    ng_location_id = fields.Many2one('stock.location', string='NG Location', related='picking_type_id.ng_location_id')
    start_time = fields.Datetime(string='Start Time', copy=False)
    end_time = fields.Datetime(string='End Time', copy=False)
    quantity_plan = fields.Float(string='Quantity', copy=False)
    eran_is_finished = fields.Integer(string="Production Cycle Finished", compute='_compute_eran_is_finished', default=0, store=True)


    def overall_equipment_effectiveness(self):
        y = self.env['mrp.workcenter.productivity'].search([])
        for x in y:
            x.compute_time()

    @api.onchange('good_total', 'ng_ids')
    def _onchange_good_total(self):
        self.qty_producing = self.good_total + sum(self.ng_ids.mapped('quantity'))
        self.workorder_ids._get_ng_ids()
        for check in self.check_ids:
            check.write({'order_qty': self.good_total})

    @api.onchange('quantity_plan')
    def _onchange_quantity_plan(self):
        for record in self:
            record.product_qty = record.quantity_plan

    @api.constrains('good_total')
    def _constarins_good_total(self):
        for this in self:
            for check in this.check_ids:
                check.write({'order_qty': self.good_total})

    @api.constrains('start_time', 'end_time')
    def _constrains_date_time(self):
        for this in self:
            if this.start_time and this.end_time:
                for line in this.workorder_ids:
                    line.write({'start_time': this.start_time, 'end_time': this.end_time})
                    line.write({'date_planned_start': this.start_time, 'date_planned_finished': this.end_time})
                    line._compute_eran_duration()

    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id')
    def _compute_workorder_ids(self):
        for production in self:
            if production.state != 'draft':
                continue
            workorders_list = [Command.link(wo.id) for wo in production.workorder_ids.filtered(lambda wo: not wo.operation_id)]
            if not production.bom_id and not production._origin.product_id:
                production.workorder_ids = workorders_list
            if production.product_id != production._origin.product_id:
                production.workorder_ids = [Command.clear()]
            if production.bom_id and production.product_id and production.product_qty > 0:
                # keep manual entries
                workorders_values = []
                product_qty = production.product_uom_id._compute_quantity(production.product_qty, production.bom_id.product_uom_id)
                exploded_boms, dummy = production.bom_id.explode(production.product_id, product_qty / production.bom_id.product_qty, picking_type=production.bom_id.picking_type_id)

                for bom, bom_data in exploded_boms:
                    # If the operations of the parent BoM and phantom BoM are the same, don't recreate work orders.
                    if not (bom.operation_ids and (not bom_data['parent_line'] or bom_data['parent_line'].bom_id.operation_ids != bom.operation_ids)):
                        continue
                    for operation in bom.operation_ids:
                        if operation._skip_operation_line(bom_data['product']):
                            continue
                        workorders_values += [{
                            'name': operation.name,
                            'production_id': production.id,
                            'workcenter_id': operation.workcenter_id.id,
                            'product_uom_id': production.product_uom_id.id,
                            'operation_id': operation.id,
                            'time_cycle': operation.time_cycle,
                            'default_capacity': operation.workcenter_id.default_capacity,
                            'state': 'pending',
                        }]
                workorders_dict = {wo.operation_id.id: wo for wo in production.workorder_ids.filtered(lambda wo: wo.operation_id)}
                for workorder_values in workorders_values:
                    if workorder_values['operation_id'] in workorders_dict:
                        # update existing entries
                        workorders_list += [Command.update(workorders_dict[workorder_values['operation_id']].id, workorder_values)]
                    else:
                        # add new entries
                        workorders_list += [Command.create(workorder_values)]
                production.workorder_ids = workorders_list
            else:
                production.workorder_ids = [Command.delete(wo.id) for wo in production.workorder_ids.filtered(lambda wo: wo.operation_id)]

    def action_confirm(self):
        for this in self:
            if this.picking_type_id:
                if not this.picking_type_id.ng_location_id and this.ng_total > 0:
                    raise ValidationError(_('Must set the NG location in the operation type %s', this.picking_type_id.display_name))
            
        res = super(MroProduction, self).action_confirm()

        for check in this.check_ids:
            if check.point_id.automatic_pass:
                check.do_pass()
        return res
    
    def _split_productions(self, amounts=False, cancel_remaining_qty=False, set_consumed_qty=False):
        """ Splits productions into productions smaller quantities to produce, i.e. creates
        its backorders.

        :param dict amounts: a dict with a production as key and a list value containing
        the amounts each production split should produce including the original production,
        e.g. {mrp.production(1,): [3, 2]} will result in mrp.production(1,) having a product_qty=3
        and a new backorder with product_qty=2.
        :param bool cancel_remaining_qty: whether to cancel remaining quantities or generate
        an additional backorder, e.g. having product_qty=5 if mrp.production(1,) product_qty was 10.
        :param bool set_consumed_qty: whether to set qty_done on move lines to the reserved quantity
        or the initial demand if no reservation, except for the remaining backorder.
        :return: mrp.production records in order of [orig_prod_1, backorder_prod_1,
        backorder_prod_2, orig_prod_2, backorder_prod_2, etc.]
        """
        def _default_amounts(production):
            return [production.qty_producing, production._get_quantity_to_backorder()]

        if not amounts:
            amounts = {}
        has_backorder_to_ignore = defaultdict(lambda: False)
        for production in self:
            mo_amounts = amounts.get(production)
            if not mo_amounts:
                amounts[production] = _default_amounts(production)
                continue
            total_amount = sum(mo_amounts)
            if total_amount < production.product_qty and not cancel_remaining_qty:
                amounts[production].append(production.product_qty - total_amount)
                has_backorder_to_ignore[production] = True
            elif total_amount > production.product_qty or production.state in ['done', 'cancel']:
                raise UserError(_("Unable to split with more than the quantity to produce."))

        backorder_vals_list = []
        initial_qty_by_production = {}

        # Create the backorders.
        for production in self:
            initial_qty_by_production[production] = production.product_qty
            if production.backorder_sequence == 0:  # Activate backorder naming
                production.backorder_sequence = 1
            production.name = self._get_name_backorder(production.name, production.backorder_sequence)
            (production.move_raw_ids | production.move_finished_ids).name = production.name
            (production.move_raw_ids | production.move_finished_ids).origin = production._get_origin()
            backorder_vals = production.copy_data(default=production._get_backorder_mo_vals())[0]
            backorder_qtys = amounts[production][1:]
            production.product_qty = amounts[production][0]

            next_seq = max(production.procurement_group_id.mrp_production_ids.mapped("backorder_sequence"), default=1)

            for qty_to_backorder in backorder_qtys:
                next_seq += 1
                backorder_vals_list.append(dict(
                    backorder_vals,
                    product_qty=qty_to_backorder,
                    name=production._get_name_backorder(production.name, next_seq),
                    backorder_sequence=next_seq,
                    eran_is_finished=0,
                ))

        backorders = self.env['mrp.production'].with_context(skip_confirm=True).create(backorder_vals_list)

        index = 0
        production_to_backorders = {}
        production_ids = OrderedSet()
        for production in self:
            number_of_backorder_created = len(amounts.get(production, _default_amounts(production))) - 1
            production_backorders = backorders[index:index + number_of_backorder_created]
            production_to_backorders[production] = production_backorders
            production_ids.update(production.ids)
            production_ids.update(production_backorders.ids)
            index += number_of_backorder_created

        # Split the `stock.move` among new backorders.
        new_moves_vals = []
        moves = []
        move_to_backorder_moves = {}
        for production in self:
            for move in production.move_raw_ids | production.move_finished_ids:
                if move.additional:
                    continue
                move_to_backorder_moves[move] = self.env['stock.move']
                unit_factor = move.product_uom_qty / initial_qty_by_production[production]
                initial_move_vals = move.copy_data(move._get_backorder_move_vals())[0]
                move.with_context(do_not_unreserve=True).product_uom_qty = production.product_qty * unit_factor

                for backorder in production_to_backorders[production]:
                    move_vals = dict(
                        initial_move_vals,
                        product_uom_qty=backorder.product_qty * unit_factor
                    )
                    if move.raw_material_production_id:
                        move_vals['raw_material_production_id'] = backorder.id
                    else:
                        move_vals['production_id'] = backorder.id
                    new_moves_vals.append(move_vals)
                    moves.append(move)

        backorder_moves = self.env['stock.move'].create(new_moves_vals)
        # Split `stock.move.line`s. 2 options for this:
        # - do_unreserve -> action_assign
        # - Split the reserved amounts manually
        # The first option would be easier to maintain since it's less code
        # However it could be slower (due to `stock.quant` update) and could
        # create inconsistencies in mass production if a new lot higher in a
        # FIFO strategy arrives between the reservation and the backorder creation
        for move, backorder_move in zip(moves, backorder_moves):
            move_to_backorder_moves[move] |= backorder_move

        move_lines_vals = []
        assigned_moves = set()
        partially_assigned_moves = set()
        move_lines_to_unlink = set()

        for initial_move, backorder_moves in move_to_backorder_moves.items():
            # Create `stock.move.line` for consumed but non-reserved components
            if initial_move.raw_material_production_id and not initial_move.move_line_ids and set_consumed_qty:
                ml_vals = initial_move._prepare_move_line_vals()
                backorder_move_to_ignore = backorder_moves[-1] if has_backorder_to_ignore[initial_move.raw_material_production_id] else self.env['stock.move']
                for move in list(initial_move + backorder_moves - backorder_move_to_ignore):
                    new_ml_vals = dict(
                        ml_vals,
                        qty_done=move.product_uom_qty,
                        move_id=move.id
                    )
                    move_lines_vals.append(new_ml_vals)

        for initial_move, backorder_moves in move_to_backorder_moves.items():
            ml_by_move = []
            product_uom = initial_move.product_id.uom_id
            for move_line in initial_move.move_line_ids:
                available_qty = move_line.product_uom_id._compute_quantity(move_line.reserved_uom_qty, product_uom)
                if float_compare(available_qty, 0, precision_rounding=move_line.product_uom_id.rounding) <= 0:
                    continue
                ml_by_move.append((available_qty, move_line, move_line.copy_data()[0]))

            initial_move.move_line_ids.with_context(bypass_reservation_update=True).write({'reserved_uom_qty': 0})
            moves = list(initial_move | backorder_moves)

            move = moves and moves.pop(0)
            move_qty_to_reserve = move.product_qty
            for quantity, move_line, ml_vals in ml_by_move:
                while float_compare(quantity, 0, precision_rounding=product_uom.rounding) > 0 and move:
                    # Do not create `stock.move.line` if there is no initial demand on `stock.move`
                    taken_qty = min(move_qty_to_reserve, quantity)
                    taken_qty_uom = product_uom._compute_quantity(taken_qty, move_line.product_uom_id)
                    if move == initial_move:
                        move_line.with_context(bypass_reservation_update=True).reserved_uom_qty = taken_qty_uom
                        if set_consumed_qty:
                            move_line.qty_done = taken_qty_uom
                    elif not float_is_zero(taken_qty_uom, precision_rounding=move_line.product_uom_id.rounding):
                        new_ml_vals = dict(
                            ml_vals,
                            reserved_uom_qty=taken_qty_uom,
                            move_id=move.id
                        )
                        if set_consumed_qty:
                            new_ml_vals['qty_done'] = taken_qty_uom
                        move_lines_vals.append(new_ml_vals)
                    quantity -= taken_qty
                    move_qty_to_reserve -= taken_qty

                    if float_compare(move_qty_to_reserve, 0, precision_rounding=move.product_uom.rounding) <= 0:
                        assigned_moves.add(move.id)
                        move = moves and moves.pop(0)
                        move_qty_to_reserve = move and move.product_qty or 0

                # Unreserve the quantity removed from initial `stock.move.line` and
                # not assigned to a move anymore. In case of a split smaller than initial
                # quantity and fully reserved
                if quantity:
                    self.env['stock.quant']._update_reserved_quantity(
                        move_line.product_id, move_line.location_id, -quantity,
                        lot_id=move_line.lot_id, package_id=move_line.package_id,
                        owner_id=move_line.owner_id, strict=True)

            if move and move_qty_to_reserve != move.product_qty:
                partially_assigned_moves.add(move.id)

            move_lines_to_unlink.update(initial_move.move_line_ids.filtered(
                lambda ml: not ml.reserved_uom_qty and not ml.qty_done).ids)

        self.env['stock.move'].browse(assigned_moves).write({'state': 'assigned'})
        self.env['stock.move'].browse(partially_assigned_moves).write({'state': 'partially_available'})
        # Avoid triggering a useless _recompute_state
        self.env['stock.move.line'].browse(move_lines_to_unlink).write({'move_id': False})
        self.env['stock.move.line'].browse(move_lines_to_unlink).unlink()
        self.env['stock.move.line'].create(move_lines_vals)

        workorders_to_cancel = self.env['mrp.workorder']
        for production in self:
            initial_qty = initial_qty_by_production[production]
            initial_workorder_remaining_qty = []
            bo = production_to_backorders[production]

            # Adapt duration
            for workorder in bo.workorder_ids:
                workorder.duration_expected = workorder._get_duration_expected()

            # Adapt quantities produced
            for workorder in production.workorder_ids:
                initial_workorder_remaining_qty.append(max(initial_qty - workorder.qty_reported_from_previous_wo - workorder.qty_produced, 0))
                workorder.qty_produced = min(workorder.qty_produced, workorder.qty_production)
            workorders_len = len(production.workorder_ids)
            for index, workorder in enumerate(bo.workorder_ids):
                remaining_qty = initial_workorder_remaining_qty[index % workorders_len]
                workorder.qty_reported_from_previous_wo = max(workorder.qty_production - remaining_qty, 0)
                if remaining_qty:
                    initial_workorder_remaining_qty[index % workorders_len] = max(remaining_qty - workorder.qty_produced, 0)
                else:
                    workorders_to_cancel += workorder
        workorders_to_cancel.action_cancel()
        backorders._action_confirm_mo_backorders()

        return self.env['mrp.production'].browse(production_ids)
    
    def _get_quantity_to_backorder(self):
        self.ensure_one()
        if self.picking_type_id.active == True:
            return max(self.product_qty - self.good_total, 0)
        else:
            return max(self.product_qty - self.qty_producing, 0)
      
    def button_mark_done(self):
        for this in self:
            if this.state not in ('done', 'cancel'):
                move_finished = this.finished_move_line_ids.filtered(lambda m: not m.production_id and m.qty_done == 0)
                if move_finished:
                    move_finished.unlink()

            if this.good_total <= 0 and this.picking_type_id.active == True:
                raise ValidationError(_('Good total cannot be null or minus'))
            if this.picking_type_id:
                if not this.picking_type_id.ng_location_id and this.ng_total > 0 and this.picking_type_id.active == True:
                    raise ValidationError(_('Must set the NG location in the operation type %s', this.picking_type_id.display_name))
                
            if not this.start_time and not this.end_time and this.picking_type_id.active == True:
                raise ValidationError(_('Productivity Periode cannot be empty in tab work order.'))
            
            if this.picking_type_id.active == True:
                for line in this.workorder_ids:
                    if line.start_time and line.end_time:
                        productivity_id = self.env.ref('mrp.block_reason7').id
                        record_productivity = line.time_ids.filtered(lambda x:x.loss_id.id == productivity_id)
                        if record_productivity:
                            record_productivity.unlink()

                        jam_start = line.start_time.hour+7
                        menit_start =  line.start_time.minute
                        start_jam_dalam_float = jam_start + (menit_start / 60)

                        jam_end = line.end_time.hour+7
                        menit_end =  line.end_time.minute
                        end_jam_dalam_float = jam_end + (menit_end / 60)
                        line.time_ids.create({
                            'workorder_id': line.id,
                            'workcenter_id': line.workcenter_id.id,
                            'user_id': self.env.user.id,
                            'start_date': line.start_time,
                            'end_date': line.end_time,
                            'loss_id': productivity_id,
                            'start_time': start_jam_dalam_float,
                            'end_time': end_jam_dalam_float,
                        })
        res = super(MroProduction, self).button_mark_done()

        for this in self:
            if this.ng_total > 0:
                stock_move_ng = self.env['stock.move'].sudo().search([
                    ('group_id', '=', this.move_finished_ids[0].group_id.id),
                    ('state', '=', 'cancel')], limit=1)
                
                if stock_move_ng:
                    total_cost_material = 0
                    qty_done = 0
                    for mv_raw in this.move_raw_ids:
                        total_cost_material += mv_raw.product_id.standard_price * mv_raw.quantity_done
                        qty_done += mv_raw.quantity_done

                    total_cost_machine = this._get_cost_machine()
                    total_cost_component = total_cost_material + total_cost_machine
                    price_unit = total_cost_component/(this.good_total+this.ng_total)
                    stock_move_ng.write({ 'state': 'draft'})
                    stock_move_ng.refresh()

                    stock_move_ng.write({
                        'quantity_done': this.ng_total,
                        'price_unit': price_unit,
                    })
                    stock_move_ng._action_assign()
                    stock_move_ng.move_line_ids.lot_id = this.lot_producing_id
                    stock_move_ng.write({'quantity_done': this.ng_total,'price_unit': price_unit})
                    stock_move_ng._action_confirm()
                    stock_move_ng.write({'quantity_done': this.ng_total,'price_unit': price_unit})
                    stock_move_ng._action_done()

                    scrap = self.env['stock.scrap'].create({
                        'product_id': stock_move_ng.product_id.id,
                        'product_uom_id': stock_move_ng.product_uom.id,
                        'production_id': this.id,
                        'scrap_qty': stock_move_ng.quantity_done,
                        'location_id': stock_move_ng.location_dest_id.id,
                        'scrap_location_id':this.ng_location_id.id,
                        'lot_id': this.lot_producing_id.id or False,
                    })
                    scrap.action_validate()

                    quantity_done = sum(this.move_finished_ids.filtered(lambda x: x.state == 'done').mapped('quantity_done'))
                    this.write({'product_qty': quantity_done})

            for line in this.workorder_ids:
                record_productivity = line.time_ids[-1]
                record_productivity.write({'loss_id': self.env.ref('mrp.block_reason7').id})

        return res
    
    def _get_cost_machine(self):
        total_cost_operations = 0
        diff_per_production = {}
        for production in self:
            diff_per_production[production] = 1
            if production.qty_produced != (production.ng_total + production.good_total):
                diff_per_production[production] = production.qty_produced/(production.ng_total + production.good_total)

        for workorder in self.workorder_ids:
            if workorder.state not in ('done', 'cancel'):
                workorder.duration_expected = workorder._get_duration_expected()
            if workorder.duration == 0.0:
                workorder.duration = workorder.duration_expected * diff_per_production[workorder.production_id]
                cost = workorder.duration / 60.0 * workorder.workcenter_id.costs_hour
                total_cost_operations += cost
            else:
                cost = workorder.duration / 60.0 * workorder.workcenter_id.costs_hour
                total_cost_operations += cost

        return total_cost_operations
    
    def _post_inventory(self, cancel_backorder=False):
        moves_to_do, moves_not_to_do = set(), set()
        for move in self.move_raw_ids:
            if move.state == 'done':
                moves_not_to_do.add(move.id)
            elif move.state != 'cancel':
                moves_to_do.add(move.id)
                if move.product_qty == 0.0 and move.quantity_done > 0:
                    move.product_uom_qty = move.quantity_done
        self.env['stock.move'].browse(moves_to_do)._action_done(cancel_backorder=cancel_backorder)
        moves_to_do = self.move_raw_ids.filtered(lambda x: x.state == 'done') - self.env['stock.move'].browse(moves_not_to_do)
        # Create a dict to avoid calling filtered inside for loops.
        moves_to_do_by_order = defaultdict(lambda: self.env['stock.move'], [
            (key, self.env['stock.move'].concat(*values))
            for key, values in tools_groupby(moves_to_do, key=lambda m: m.raw_material_production_id.id)
        ])
        for order in self:
            finish_moves = order.move_finished_ids.filtered(lambda m: m.product_id == order.product_id and m.state not in ('done', 'cancel'))
            if finish_moves:
                finish_moves = order.move_finished_ids.filtered(lambda m: m.product_id == order.product_id and m.state not in ('done', 'cancel'))[0]
            
            # the finish move can already be completed by the workorder.
            if finish_moves and not finish_moves.quantity_done:
                if order.ng_total > 0:
                    finish_moves._set_quantity_done(float_round(order.good_total, precision_rounding=order.product_uom_id.rounding, rounding_method='HALF-UP'))
                    total_cost_material = 0
                    qty_done = order.good_total
                    for mv_raw in order.move_raw_ids:
                        total_cost_material += mv_raw.product_id.standard_price * mv_raw.quantity_done

                    total_cost_machine = order._get_cost_machine()
                    total_cost_component = total_cost_material + total_cost_machine
                    price_unit = total_cost_component/qty_done
                    finish_moves.write({'price_unit': price_unit})
                else:
                    finish_moves._set_quantity_done(float_round(order.qty_producing - order.qty_produced, precision_rounding=order.product_uom_id.rounding, rounding_method='HALF-UP'))

                finish_moves.move_line_ids.lot_id = order.lot_producing_id
            order._cal_price(moves_to_do_by_order[order.id])
        moves_to_finish = self.move_finished_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
        moves_to_finish = moves_to_finish._action_done(cancel_backorder=cancel_backorder)
        self.action_assign()
        for order in self:
            consume_move_lines = moves_to_do_by_order[order.id].mapped('move_line_ids')
            order.move_finished_ids.move_line_ids.consume_line_ids = [(6, 0, consume_move_lines.ids)]
        return True

    @api.depends('ng_total', 'product_qty')
    def _compute_good_total(self):
        for rec in self:
            rec.good_total = rec.product_qty - rec.ng_total
            for line in rec.workorder_ids:
                line._get_ng_ids()

    def _compute_ng_total(self):
        self.ng_total = sum(ng.quantity for ng in self.ng_ids)

    def _compute_material_request_count(self):
        for rec in self:
            rec.material_request_count = len(rec.stock_picking_ids.ids)
        
    def action_request_material(self):
        if self.stock_picking_ids:
            if self.stock_picking_ids[-1].state not in ('done', 'cancel'):
                ValidationError(_('Previous material requests have not been processed.'))

        context = {
            'default_requester_id': self.operator_id.id,
            'default_source_location_id': self.picking_type_id.source_location_material.id,
            # 'default_move_raw_ids': [(6, 0, self.move_raw_ids.ids)],
            'default_production_id': self.id,

        }

        return {
            'name': "Material Request Additional",
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'eran.material.request.wiz',
            'view_id': self.env.ref('eran_custom.eran_material_request_view').id,
            'target': 'new',
            'context':context
        }
        
    def action_open_stock_picking(self):
        """Open stock picking tree view"""

        return {
            'name': _('Request Material'),
            'type': 'ir.actions.act_window',
            # 'view_type': 'list',
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            # 'view_id': self.env.ref('stock.vpicktree').id,
            'target': 'current',
            'domain': [('id', 'in', self.stock_picking_ids.ids)],
            'context': {'create': True, 'edit': True},
        }

    def action_start_all_workorders(self):
        """ Klik Start di Production, otomatis Start Work Order yang siap """
        # Ambil timezone user (default ke UTC jika tidak diatur)
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        now_utc = datetime.now() # Waktu sekarang dalam UTC untuk database
        for production in self:
            # Cari work order yang belum selesai dan belum berjalan
            production.eran_is_finished = 1
            workorders = production.workorder_ids.filtered(
                lambda wo: wo.state not in ('done', 'cancel') and not wo.is_user_working
            )
            if not production.shift_id or not production.leader_id or not production.operator_id and production.picking_type_id.active == True:
                raise ValidationError(_('Shift, Leader, and Operator must be filled in tab work order before start production.'))
            
            for wo in workorders:
                if wo.shift_id:
                    wo.button_start()
                    shift = wo.shift_id
                    
                    # 1. Tentukan tanggal hari ini di timezone user
                    now_user = datetime.now(user_tz)
                    
                    # 2. Buat jam Start & End dalam Local Time (WIB)
                    h_start = int(shift.start_time)
                    m_start = int((shift.start_time - h_start) * 60)
                    h_end = int(shift.end_time)
                    m_end = int((shift.end_time - h_end) * 60)

                    # Set jam lokal (WIB)
                    start_local = now_user.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
                    end_local = now_user.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

                    # 3. Logika Overnight (Pindah Hari)
                    if shift.end_time < shift.start_time:
                        end_local += timedelta(days=1)

                    # 4. KONVERSI DARI LOKAL KE UTC (Penting agar view benar)
                    # Fungsi astimezone(pytz.utc) akan mengurangi 7 jam secara otomatis untuk WIB
                    start_utc = now_user.astimezone(pytz.utc).replace(tzinfo=None)
                    end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)

                    # 5. Simpan ke Database
                    wo.write({
                        'date_planned_start': start_utc,
                        'date_planned_finished': end_utc
                    })

                    # --- 5. Update Data ---
                    wo.production_id.write({
                        'start_time': start_utc,
                        'end_time': end_utc
                    })

                    productivity = self.env['mrp.workcenter.productivity'].search([
                        ('workorder_id', '=', wo.id),
                        ('user_id', '=', self.env.user.id),
                        ('date_end', '=', False)
                    ], limit=1)

                    if productivity:
                        productivity.write({
                            'date_start': now_utc, # Klik sekarang (UTC)
                            'date_end': end_utc     # Akhir shift (UTC)
                        })

        return True

    def action_stop_all_workorders(self):
        """ Klik Stop di Production, otomatis Pause/Pending semua Work Order yang sedang berjalan """
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        for production in self:
            # Cari work order yang sedang berjalan (progress)
            workorders = production.workorder_ids
            for wo in workorders:
                wo.button_finish()
                if wo.shift_id:
                    # 1. Tentukan tanggal hari ini di timezone user
                    now_user = datetime.now(user_tz)
                    
                    # 4. KONVERSI DARI LOKAL KE UTC (Penting agar view benar)
                    # Fungsi astimezone(pytz.utc) akan mengurangi 7 jam secara otomatis untuk WIB
                    end_utc = now_user.astimezone(pytz.utc).replace(tzinfo=None)

                    # 5. Simpan ke Database
                    wo.write({
                        'date_planned_finished': end_utc
                    })

                    # --- 5. Update Data ---
                    wo.production_id.write({
                        'end_time': end_utc
                    })

                    productivity = self.env['mrp.workcenter.productivity'].search([
                        ('workorder_id', '=', wo.id),
                        ('user_id', '=', self.env.user.id),
                        ('date_end', '=', False)
                    ], limit=1)

                    if productivity:
                        productivity.write({
                            'date_end': end_utc     # Akhir shift (UTC)
                        })
            
            production.eran_is_finished = 2
            production.button_mark_done()
        return True    
    
    @api.depends('state')
    def _compute_eran_is_finished(self):
        for rec in self:
            if rec.state in ('done', 'cancel', 'to_close'):
                rec.eran_is_finished = 2
            elif rec.state in ('progress', 'ready') and ( not rec.start_time or not rec.end_time):
                rec.eran_is_finished = 1
            else:
                rec.eran_is_finished = 0

class EranWorkOrder(models.Model):
    _inherit = 'mrp.workorder'

    activity_ids = fields.Many2many('mrp.workcenter.productivity', string='Activity Type', compute='_get_activity_type_ids')
    problem_ng_ids = fields.Many2many('eran.no.good', string='Problem NG', compute='_get_problem_ng_ids')
    time_cycle = fields.Float(string="Time Cycle")
    default_capacity = fields.Float(string="Capacity", related='workcenter_id.default_capacity', store=True)
    ng_qty = fields.Float(string="NG Mesin Qty", compute="_get_ng_ids", store=True)
    start_time = fields.Datetime(string='Start Time')
    end_time = fields.Datetime(string='End Time')
    eran_duration = fields.Float('Productivity Duration', compute='_compute_eran_duration', store=True)
    # Related fields to expose production's shift, leader, operator, operator 2, quantity plan on the workorder
    shift_id = fields.Many2one('eran.master.shift', string='Shift', related='production_id.shift_id', store=False, readonly=True)
    leader_id = fields.Many2one('hr.employee', string='Leader', related='production_id.leader_id', store=False, readonly=True)
    operator_id = fields.Many2one('hr.employee', string='Operator', related='production_id.operator_id', store=False, readonly=True)
    operator_id2 = fields.Many2one('hr.employee', string='Operator 2', related='production_id.operator_id2', store=False, readonly=True)
    quantity_plan = fields.Float(string='Quantity Plan', related='production_id.quantity_plan', store=False, readonly=True)
    quantity_good = fields.Float(string='Quantity Good', related='production_id.good_total', store=False, readonly=True)
    workcenter_group_id = fields.Many2one('eran.work.center.group', related='workcenter_id.workcenter_group_id', store=True, string="Work Center Group", readonly=True)
    color_state = fields.Integer(string="Color State", compute="_compute_color_state", store=True)
    
    @api.depends('state')
    def _compute_color_state(self):
        # 1 red
        # 2 orange
        # 3 yellow
        # 4 light blue
        # 5 green
        # 6 magenta red
        # 7 navy blue
        # 8 silver
        # 9 purple
        # 10 light green
        # 11 light violet
        for rec in self:
            if rec.state == 'done':
                rec.color_state = 10 # light green
            elif rec.state == 'progress':
                rec.color_state = 7 # navy blue
            elif rec.state == 'ready':
                rec.color_state = 4 # light blue
            elif rec.state == 'pending':
                rec.color_state = 1 # red
            elif rec.state == 'waiting':
                rec.color_state = 3 # yellow
            else:
                rec.color_state = 0 # no color

    @api.depends('production_id')        
    def _get_ng_ids(self):
        for rec in self:
            qty_ng_mesin = sum([production.quantity for production in rec.production_id.ng_ids if production.workcenter_id.id==rec.workcenter_id.id])
            rec.ng_qty = qty_ng_mesin

    @api.depends('start_time', 'end_time')
    def _compute_eran_duration(self):
        for this in self:
            this.eran_duration = 0
            if this.end_time and this.start_time:
                selisih = this.end_time - this.start_time
                total_detik = selisih.total_seconds()
                # Menghitung jam dan menit
                selisih_jam = total_detik // 3600  # Mengambil jam penuh
                selisih_menit = (total_detik % 3600) // 60  # Mengambil menit penuh

                # Konversi ke format float
                selisih_float = selisih_jam + (selisih_menit / 60)
                this.eran_duration = selisih_float

                this.date_planned_start = this.start_time
                this.date_planned_finished = this.end_time
                this.duration_expected = this.eran_duration * 60

    def _get_problem_ng_ids(self):
        for rec in self:
            s_ng_ids = rec.env['eran.ng.mrp.production'].sudo().search([('production_id', '=', rec.production_id.id), ('workcenter_id', '=', rec.workcenter_id.id)])
            res = [(6, 0, s_ng_ids.no_good_id.mapped('id'))]
            rec.problem_ng_ids = res
            self._get_ng_ids()
    
    def _get_activity_type_ids(self):
        for rec in self:
            res = [(6, 0, rec.time_ids.mapped('id'))]
            rec.activity_ids = res

    @api.constrains('start_time', 'end_time')
    def _constrains_time(self):
        for this in self:
            if this.start_time and this.end_time:
                if this.start_time >= this.end_time:
                    raise ValidationError(_('Start time cannot be equal or greater than the end time'))

    @api.constrains('time_ids','time_ids.start_date','time_ids.end_date','time_ids.start_time','time_ids.end_time')
    def _constrains_date_time(self):
        for this in self:
            for line in this.time_ids:
                if line.start_time <= 0:
                    raise UserError("Start time cannot be empty.")
                if line.end_time <= 0:
                    raise UserError("End time cannot be empty.")
                if line.start_date >  line.end_date:
                    raise UserError("Start date cannot be greater than the end date.")
                
                if line.start_date ==  line.end_date and line.start_time >= line.end_time:
                    raise ValidationError(_('on the same date, the start time cannot be greater than or equal to the endtime.'))
                
            if this.start_time and this.end_time and this.time_ids:
                if this.eran_duration <= sum(this.time_ids.mapped('duration'))/60:
                    raise ValidationError(_('Productivity Duration cannot be greater than or equal to total duration time tracking.'))

            this.update_pending()

    def update_pending(self):
        self.button_pending()

    def button_start(self):
        res = super().button_start()
        for this in self:
            productivity_id = self.env.ref('mrp.block_reason7').id
            record_productivity = this.time_ids.filtered(lambda x:x.loss_id.id == productivity_id and x.start_date == False and x.end_date == False)
            if record_productivity:
                record_productivity.unlink()
        return res
    
    def name_get(self):
        res = []
        for wo in self:                  
            if len(wo.production_id.workorder_ids) == 1:
                name = wo.product_id.name or wo.name
                res.append((wo.id, name))
            else:
                name = wo.product_id.name or wo.name
                res.append((wo.id, name))
        return res
    
    def button_start(self):
        # 1. Jalankan fungsi standar
        # Ini akan membuat record di mrp.workcenter.productivity secara otomatis
        res = super().button_start()
        # Ambil timezone user (default ke UTC jika tidak diatur)
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        now_utc = datetime.now() # Waktu sekarang dalam UTC untuk database

        for record in self:
            if not record.production_id.shift_id or not record.production_id.leader_id or not record.production_id.operator_id:
                raise ValidationError(_('Shift, Leader, and Operator must be filled in tab work order before start production.'))
            
            if record.shift_id:
                shift = record.shift_id
                
                # 1. Tentukan tanggal hari ini di timezone user
                now_user = datetime.now(user_tz)
                
                # 2. Buat jam Start & End dalam Local Time (WIB)
                h_start = int(shift.start_time)
                m_start = int((shift.start_time - h_start) * 60)
                h_end = int(shift.end_time)
                m_end = int((shift.end_time - h_end) * 60)

                # Set jam lokal (WIB)
                start_local = now_user.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
                end_local = now_user.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

                # 3. Logika Overnight (Pindah Hari)
                if shift.end_time < shift.start_time:
                    end_local += timedelta(days=1)

                # 4. KONVERSI DARI LOKAL KE UTC (Penting agar view benar)
                # Fungsi astimezone(pytz.utc) akan mengurangi 7 jam secara otomatis untuk WIB
                start_utc = now_user.astimezone(pytz.utc).replace(tzinfo=None)
                end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)

                # 5. Simpan ke Database
                record.write({
                    'date_planned_start': start_utc,
                    'date_planned_finished': end_utc
                })

                # --- 5. Update Data ---
                record.production_id.write({
                    'start_time': start_utc,
                    'end_time': end_utc
                    
                })

                record.production_id.eran_is_finished = 1

                productivity = self.env['mrp.workcenter.productivity'].search([
                    ('workorder_id', '=', record.id),
                    ('user_id', '=', self.env.user.id),
                    ('date_end', '=', False)
                ], limit=1)

                if productivity:
                    productivity.write({
                        'date_start': now_utc, # Klik sekarang (UTC)
                        'date_end': end_utc     # Akhir shift (UTC)
                    })
        return res
    
    def button_finish(self):
        res = super().button_finish()
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        now_utc = datetime.now(user_tz) # Waktu sekarang dalam UTC untuk database
        end_local = now_utc.astimezone(pytz.utc).replace(tzinfo=None)
        if self.production_id and self.production_id.good_total <= 0:
            raise ValidationError(_('Good total cannot be null or minus'))
        for record in self:

            record.write({
                    'date_planned_finished': end_local
                })
            record.production_id.write({
                    'end_time': end_local
                })
            record.production_id.eran_is_finished = 2
            productivity = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', record.id),
                ('user_id', '=', self.env.user.id),
                ('date_end', '=', False)
            ], limit=1)

            if productivity:
                productivity.write({
                    'date_end': end_local     # Klik sekarang (UTC)
                })
            
        return res