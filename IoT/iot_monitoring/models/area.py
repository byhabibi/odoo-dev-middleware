from odoo import models, fields, api

class IoTArea(models.Model):
    _name = 'iot.area'
    _description = 'IoT Area'

    name = fields.Char(required=True)
    machine_ids = fields.One2many('iot.machine', 'area_id', string='Machines')
    machine_count = fields.Integer(
        string='Jumlah Mesin',
        compute='_compute_machine_count',
        store=True
    )

    running_machine = fields.Integer(compute="_compute_machine_summary")
    stop_machine = fields.Integer(compute="_compute_machine_summary")

    @api.depends('machine_ids.production_status')
    def _compute_machine_summary(self):
            for area in self:
                # Menggunakan loop Python biasa yang 100% aman dari IndexError XML-RPC
                run_count = 0
                stop_count = 0
                for m in area.machine_ids:
                    if m.current_product and m.current_product != '-':
                        run_count += 1
                    else:
                        stop_count += 1
                
                area.running_machine = run_count
                area.stop_machine = stop_count
