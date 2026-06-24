from odoo import api, fields, models, _
from odoo.tools import is_html_empty
from odoo.exceptions import ValidationError, UserError
import json
import logging
_logger = logging.getLogger(__name__)


class EranCategoryGroup(models.Model):
    _name = "eran.category.group"
    _description = "Eran Category Group"


    name = fields.Char(string='Name')


