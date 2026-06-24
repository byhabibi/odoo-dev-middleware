from odoo import api, fields, models, _
import logging
_logger = logging.getLogger(__name__)

class EranWorkCenterGroup(models.Model):
    _name = 'eran.work.center.group' 
    _description = 'Work Center Group'

    name = fields.Char(string='Name')
    