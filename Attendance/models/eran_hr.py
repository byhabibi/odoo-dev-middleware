# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import models, fields
from odoo.tools import populate
from datetime import datetime, time

class HrDepartment(models.Model):
    _inherit = 'hr.department'

    code = fields.Char('Code')


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    shift_id = fields.Many2one("eran.master.shift",
        string="Shift",
        help="Master data shift employee module",
        domain="")
    
class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _generate_work_entries(self, date_start, date_end, *args, **kwargs):
        # 1. Cek jika date_start berupa objek date biasa, konversi ke datetime (jam 00:00:00)
        if date_start and not isinstance(date_start, datetime):
            if hasattr(date_start, 'strftime'): # Memastikan ini objek date
                date_start = datetime.combine(date_start, time.min)
            else:
                # Jika string, konversi ke datetime object
                date_start = fields.Datetime.from_string(date_start)

        # 2. Cek jika date_end berupa objek date biasa, konversi ke datetime (jam 23:59:59)
        if date_end and not isinstance(date_end, datetime):
            if hasattr(date_end, 'strftime'):
                date_end = datetime.combine(date_end, time.max)
            else:
                date_end = fields.Datetime.from_string(date_end)

        # 3. fungsi asli bawaan Odoo dengan parameter yang sudah aman
        return super(HrContract, self)._generate_work_entries(date_start, date_end, *args, **kwargs)
