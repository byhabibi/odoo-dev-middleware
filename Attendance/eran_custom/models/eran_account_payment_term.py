# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models, _
import logging
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class PaymentTerm(models.Model):
    _inherit = 'account.payment.term'
    _description = 'Account Payment Term Inherit'

    description = fields.Html(string='Description')
    