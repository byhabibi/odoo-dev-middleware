from odoo import api, fields, models, _

class EranMasterShift(models.Model):
    _name = 'eran.master.shift'
    _description = 'Master Shift'
    
    name = fields.Char(string="Shift", required=True)
    start_time = fields.Float(string="Start Time", required=True)
    end_time = fields.Float(string="End Time", required=True)
    start_checkin = fields.Float(string="Start Checkin", required=True)
    end_checkin = fields.Float(string="End Checkin", required=True)
    start_checkout = fields.Float(string="Start Checkout", required=True)
    end_checkout = fields.Float(string="End Checkout", required=True)

class MrpWorkcenterProductivityLoss(models.Model):
    _inherit = 'mrp.workcenter.productivity.loss'

    active = fields.Boolean('Active', default=True)
    