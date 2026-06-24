# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.exceptions import AccessError, UserError, ValidationError
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.tools import populate

class EranNoGood(models.Model):
    _name = 'eran.no.good'

    name = fields.Char('NG Name')
    standard = fields.Char('Standard')
    ng_group = fields.Char('NG Group')

    def unlink(self):
        ng = self.env['quality.check.ng'].search([('not_good_id', '=', self.id)])
        if len(ng.mapped('id')) > 0:
            raise UserError(_('Cannot delete %s because already used') % (self.name))
        res = super().unlink()
        return res

