from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, time
import logging
_logger = logging.getLogger(__name__)


class EranMrpProductWorkCenter(models.Model):
    _name = 'eran.mrp.product.workcenter'
    _description = 'Eran MRP Product Workcenter'

    name = fields.Char()
    product_template_id = fields.Many2one(
        string="Cost Name",
        comodel_name="product.template",
        copy=True,
        help="Product Template",
        index=True,
        domain=[('type', '=', 'product')]
    )
    workcenter_id = fields.Many2one('mrp.workcenter', string='Workcenter Id')
    cost = fields.Float(string="Cost", store=True, readonly=False, compute="_compute_cost")
    quantity = fields.Float(string="Quantity", store=True, readonly=False, compute="_compute_quantity")
    total_cost = fields.Float(string="Total Cost", compute="_compute_total_cost")
    
    @api.depends('product_template_id')
    def _compute_cost(self):
        for rec in self:
            rec.cost = rec.product_template_id.standard_price

    @api.depends('product_template_id')
    def _compute_quantity(self):
        for rec in self:
            rec.quantity = rec.product_template_id.qty_available

    @api.depends('cost','quantity')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.cost * rec.quantity

class MrpWorkCenter(models.Model):
    _inherit = 'mrp.workcenter' 
    _description = 'Work Center Inherit'

    product_ids = fields.One2many('eran.mrp.product.workcenter', 'workcenter_id', string="Product", copy=False)
    workcenter_group_id = fields.Many2one('eran.work.center.group', string="Work Center Group")
    overhead_ids = fields.One2many('eran.work.center.overhead', 'workcenter_id')
    
    @api.onchange('product_ids')
    def _onchange_product_ids(self):
        for rec in self:
            rec.costs_hour = sum(rec.product_ids.mapped('total_cost'))

class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"
    _order = 'id asc'
    
    product_id = fields.Many2one('product.product', string='Product', related='workorder_id.production_id.product_id', store=True, readonly=True)
    workcenter_group_id = fields.Many2one('eran.work.center.group', related='workcenter_id.workcenter_group_id', string="Work Center Group", readonly=True)
    start_date = fields.Date(string='Start Date Productivity')
    end_date = fields.Date(string='End Date Productivity')
    start_time = fields.Float(string='Start Time(Hour)')
    end_time = fields.Float(string='End Time(Hour)')
    duration = fields.Float('Duration (Minute)', compute='_compute_duration', store=True)
    real_duration = fields.Float('Real Duration (Minute)', compute='_compute_real_duration', store=True)

    date_start = fields.Datetime('Start Date', default=fields.Datetime.now, required=True, compute='compute_time', store=True)
    date_end = fields.Datetime('End Date',  compute='compute_time', store=True)


    @api.depends('start_date', 'end_date', 'start_time', 'end_time')
    def compute_time(self):
        for this in self:
            this.date_start = this.date_start
            this.date_end = this.date_end
           
            if this.start_date and this.start_time:
                hours = int(this.start_time)
                minutes = int(round((this.start_time - hours) * 60, 2))

                this.date_start = datetime.combine(this.start_date, datetime.min.time()) + timedelta(hours=hours-7, minutes=minutes)

            if this.end_date and this.end_time:
                hours_ = int(this.end_time)
                minutes_ = int(round((this.end_time - hours_) * 60, 2))

                this.date_end = datetime.combine(this.end_date, datetime.min.time()) + timedelta(hours=hours_-7, minutes=minutes_)

    @api.depends('start_date', 'end_date', 'start_time', 'end_time', 'loss_id')
    def _compute_duration(self):
        for blocktime in self:
            blocktime.duration = 0
            if blocktime.start_date and blocktime.end_date and blocktime.start_time and blocktime.end_time:
                # Misalkan blocktime.start_date adalah objek datetime.date
                start_date = blocktime.start_date  # Ini adalah objek datetime.date, bukan string
                end_date = blocktime.end_date  # Ini juga objek datetime.date

                # Nilai start_time dan end_time dalam bentuk desimal (misalnya 10.0 dan 19.0)
                start_time = blocktime.start_time
                end_time = blocktime.end_time

                # Mengonversi start_time dan end_time ke bentuk jam dan menit
                start_hour = int(start_time)
                start_minute = int((start_time - start_hour) * 60)

                end_hour = int(end_time)
                end_minute = int((end_time - end_hour) * 60)

                # Membuat objek datetime dengan menggabungkan tanggal dan waktu
                start_datetime = datetime.combine(start_date, datetime.min.time()) + timedelta(hours=start_hour, minutes=start_minute)
                end_datetime = datetime.combine(end_date, datetime.min.time()) + timedelta(hours=end_hour, minutes=end_minute)

                # Menghitung selisih waktu
                selisih = end_datetime - start_datetime

                # Mengambil total detik dari selisih waktu
                total_detik = selisih.total_seconds()

                # Menghitung jam dan menit
                selisih_jam = total_detik // 3600  # Mengambil jam penuh
                selisih_menit = (total_detik % 3600) // 60  # Mengambil menit penuh

                # Konversi ke format float
                selisih_float = selisih_jam + (selisih_menit / 60)
                if selisih_float < 0:
                    selisih_float = 0
                blocktime.duration = selisih_float*60

            productivity_id = self.env.ref('mrp.block_reason7').id
            if blocktime.loss_id:
                if blocktime.loss_id.id == productivity_id:
                    blocktime.duration = (blocktime.workorder_id.eran_duration-\
                        (sum(blocktime.workorder_id.time_ids.filtered(lambda x: x.loss_id.id != productivity_id).mapped('duration'))/60))*60

    @api.depends('workorder_id', 'workorder_id.time_ids')
    def _compute_real_duration(self):
        for record in self:
            total_duration = 0
            if record.workorder_id:
                for time_line in record.workorder_id.time_ids:
                    total_duration += time_line.duration

            record.real_duration = total_duration



class EranWorkCenterOverhead(models.Model):
    _name = 'eran.work.center.overhead'
    _description = 'Eran Work Center Overhead'


    workcenter_id = fields.Many2one('mrp.workcenter', odelete='cascade')
    demand_id = fields.Many2one('dsn.demand.planning', ondelete='cascade', tracking=True)
    demand_workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    product_id = fields.Many2one('product.product', string='Product')
    min_capacity = fields.Float(string='Min Capacity')
    max_capacity = fields.Float(string='Max Capacity')
    qty = fields.Float(string='Quantity')
    uom_id = fields.Many2one('uom.uom', string='UoM')
    bom_id = fields.Many2one('mrp.bom', string='Bill of Material Ref.', tracking=True)


    @api.onchange('product_id')
    def _onchange_product(self):
        self.uom_id = False
        if self.product_id:
            self.uom_id = self.product_id.uom_po_id