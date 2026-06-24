from odoo import api, fields, models, _

class EranPica(models.Model):
    _name = 'eran.pica'
    _order = 'create_date desc'

    name = fields.Char(string='PICA Reference', required=True, copy=False, readonly=True, default='New')
    lmk_id = fields.Many2one('eran.lembar.masalah.kualitas', string='LMK Reference', required=True)
    pica_date = fields.Date(string="Create Date")
    pica_delivery_date = fields.Date(string="Delivery Date")
    lmk_line_id = fields.Many2one('eran.lembar.masalah.kualitas.line', string='LMK Line')
    product_id = fields.Many2one('product.product', string='Product', related='lmk_id.product_id', store=True, readonly=False)
    partner_id = fields.Many2one('res.partner', string='Partner', related='lmk_id.partner_id', store=True, readonly=False)
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('vendor', 'Vendor')
    ], string='Partner Type', related='lmk_id.partner_type', store=True)
    not_good_id = fields.Many2one('eran.no.good', string='Jenis Ng', related='lmk_line_id.not_good_id', store=True, readonly=False)
    quantity_ng = fields.Float(string='Quantity NG', related='lmk_line_id.quantity_ng', store=True, readonly=False)
    problem_identification = fields.Text(string='Problem Identification')
    ilustrasi_ng = fields.Image(string='Ilustrasi NG')
    pi_why_send = fields.Text(string='PI (Why Send)')
    pi_why_made = fields.Text(string='PI (Why Made)')
    corrective_action = fields.Text(string='CA Outflow')
    ca_occure = fields.Text(string='CA Occure')
    pic_id = fields.Many2one('hr.employee', string='PIC')
    remark = fields.Text(string='Remark')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachment')

    def open_attachment(self):
            attachment_view = self.env.ref('eran_custom.view_dsn_eran_pica_attachment_form')
            return {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'eran.pica',
                'res_id': self.id,
                'views': [(attachment_view.id, 'form')],
                'view_id': attachment_view.id,
                'target': 'new',
            }

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('eran.pica') or 'New'
        return super().create(vals)
