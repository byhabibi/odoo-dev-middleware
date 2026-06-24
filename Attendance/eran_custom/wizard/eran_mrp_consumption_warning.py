# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class MrpConsumptionWarning(models.TransientModel):
    _inherit = 'mrp.consumption.warning'
    _description = "Wizard in case of consumption in warning/strict and more component has been used for a MO (related to the bom)"


    def action_confirm(self):
        ctx = dict(self.env.context)
        ctx.pop('default_mrp_production_ids', None)
        action_from_do_finish = False
        if self.env.context.get('from_workorder'):
            if self.env.context.get('active_model') == 'mrp.workorder':
                action_from_do_finish = self.env['mrp.workorder'].browse(self.env.context.get('active_id')).do_finish()
        action_from_mark_done = self.mrp_production_ids.with_context(ctx, skip_consumption=True).button_mark_done()
        for mrp in self.mrp_production_ids:
            mrp.write({
                'state_approval':'done', 
                'need_approval': False
            })
        return action_from_do_finish or action_from_mark_done
