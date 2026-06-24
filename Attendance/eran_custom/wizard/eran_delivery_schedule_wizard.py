from odoo import api, fields, models, _

class EranDeliveryScheduleReport(models.Model):
    _name = 'eran.delivery.schedule.report'
    _description = 'Eran Delivery Schedule Report'

    def _default_notes(self):
        html= """
            <ol style="padding-left:1rem;">
                <li>WAKTU PENERIMAAN ITEM JAM 08:00 S/D 15.30 WIB (MOON KONFIRMASI JIKA DILUAR JAM TERSEBUT)</li>
                <li>MOHON SEGERA KONFIRMASI JIKA ADA DELIVERY TIDAK SESUAI SCHEDULE INI MINIMAL H-1.</li>
                <li>BERAT PALLET TIDAK MELEBIHI QTY 2.500 KG</li>
            </ol>"""
        return html

    create_date = fields.Datetime('Create Date')
    create_uid = fields.Many2one('res.users', string='Create By')
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order')
    notes = fields.Html('Notes', default=_default_notes)

    def print_delivery_schedule_pdf(self):
        action = self.env['ir.actions.actions']._for_xml_id('eran_custom.action_report_delivery_schedule')
        return action