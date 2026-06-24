from odoo import fields, models, api

class Company(models.Model):
    _inherit = 'res.company'

    eran_fax = fields.Char('Fax')