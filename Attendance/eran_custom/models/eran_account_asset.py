import json
import datetime
from dateutil.relativedelta import relativedelta
from math import copysign

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, formatLang, end_of

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    location_asset = fields.Char(string='Location Asset', store=True)
    asset_jig = fields.Boolean(string="Asset Jig")

    def validate(self):
        for rec in self:
            if rec.asset_jig:
                raise UserError("Jika Asset Jig di ceklis, tidak boleh di-Confirm.")
        return super().validate()

    