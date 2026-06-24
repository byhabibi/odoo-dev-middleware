from odoo import api, fields, models, _
from datetime import datetime, time
import pytz


class EranLossOpportunity(models.Model):
    _name = 'master.loss.opportunity'

    date = fields.Date(string="Date", default=fields.Date.today())
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)
    category_group_id = fields.Many2one('eran.category.group', string="Category Group")
    target = fields.Monetary(string="Target")
    problem = fields.Char(string="Problem")
    activity = fields.Char(string="Activity")

class EranVendorPerformanceCustomer(models.Model):
    _name ='master.vendor.performance.customer'

    date = fields.Date(string="Date", default=fields.Date.today())
    partner_id = fields.Many2one('res.partner', string="Customer")
    point = fields.Integer(string="Point")

class EranDeliveryAchivementRate(models.Model):
    _name = 'master.delivery.achivement.rate'

    date = fields.Date(string="Date", default=fields.Date.today())
    problem = fields.Char(string="Problem Statement")
    corective_action = fields.Char(string="Corective Action")
    user_pic = fields.Many2one('hr.employee', string="User PIC")
    category_group_id = fields.Many2one('eran.category.group', string="Category Group")
    remark = fields.Char(string="Remark")
    key_message = fields.Char(string="Key Message")

class EranProductionAchivementRate(models.Model):
    _name = 'master.production.achivement.rate'

    date = fields.Date(string="Date", default=fields.Date.today())
    problem = fields.Char(string="Problem Statement")
    corective_action = fields.Char(string="Corective Action")
    user_pic = fields.Many2one('hr.employee', string="User PIC")
    remark = fields.Char(string="Remark")
    key_message = fields.Char(string="Key Message")


class EranProductionAchivementRateLine(models.Model):
    _name = 'master.production.achivement.rate.line'

    date = fields.Date(string="Date", default=fields.Date.today())
    work_center_id = fields.Many2one('mrp.workcenter', string="Work Center")
    key_message = fields.Char(string="Key Message")


class EranLineStop(models.Model):
    _name = 'master.line.stop'

    date = fields.Date(string="Date", default=fields.Date.today())
    work_center_id = fields.Many2one('mrp.workcenter', string="Work Center")
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)
    target = fields.Float(string="Target")
    key_message = fields.Char(string="Key Message")


class EranRejectionRate(models.Model):
    _name = 'master.rejection.rate'

    date = fields.Date(string="Date", default=fields.Date.today())
    work_center_id = fields.Many2one('mrp.workcenter', string="Work Center")
    target = fields.Float(string="Target")
    key_message = fields.Char(string="Key Message")

class EranMasterDate(models.Model):
    _name = 'master.date'

    @api.model
    def _default_local_datetime(self):
        user_tz = self.env.user.tz or 'UTC'
        local = pytz.timezone(user_tz)
        now_local = datetime.now(local)

        now_utc = now_local.astimezone(pytz.utc).replace(tzinfo=None)
        return now_utc

    date = fields.Datetime(string='Date', default=_default_local_datetime)

    @api.model
    def cron_date(self):
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        now_local = datetime.now(user_tz)  # Aware datetime di local TZ

        today_start_local = datetime.combine(now_local.date(), time.min)
        today_end_local = datetime.combine(now_local.date(), time.max)

        today_start_local = user_tz.localize(today_start_local)
        today_end_local = user_tz.localize(today_end_local)

        today_start_utc = today_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc = today_end_local.astimezone(pytz.utc).replace(tzinfo=None)

        now_utc = fields.Datetime.now()

        date = self.env['master.date'].search([
            ('date', '>=', today_start_utc),
            ('date', '<=', today_end_utc)
        ], limit=1)

        if not date:
            self.create({'date': now_utc})

class EranControlDeliveryOrder(models.Model):
    _name = 'master.control.delivery.order.customer'

    date = fields.Datetime(string="Date", default=fields.Datetime.now())
    key_message = fields.Char(string="Key Message")


class EranInventoryControl(models.Model):
    _name ='master.inventory.control'

    date = fields.Datetime(string="Date", default=fields.Datetime.now())
    key_message = fields.Char(string="Key Message")
