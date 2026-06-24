from odoo import models, fields, api


class IoTSensorData(models.Model):
    _name = 'iot.sensor.data'
    _description = 'IoT Sensor Data'
    _order = 'timestamp desc'

    machine_id = fields.Many2one('iot.machine', required=True)
    status = fields.Selection([
        ('progress', 'In Progress'),
        ('stop', 'Stop Line'),
    ], required=True)
    counter = fields.Integer()
    timestamp = fields.Datetime(required=True)
    product_name = fields.Char()

    @api.model
    def receive_data(self, machine_code, status, counter, timestamp):

        machine_code_clean = (machine_code or "").strip()
        machine = self.env['iot.machine'].search([
            ('name', 'ilike', machine_code_clean)
        ], limit=1)

        if not machine:
            return {'success': False, 'error': f'Machine not found: {machine_code_clean}'}

        # Sync WO dulu
        machine._sync_workorder()

        # Ambil WO aktif setelah sync
        product_name = '-'
        plan_qty = 0
        workorder = False

        if machine.workcenter_id:
            workorder = self.env['mrp.workorder'].search([
                ('workcenter_id', '=', machine.workcenter_id.id),
                ('state', '=', 'progress'),
            ], limit=1)
            if workorder:
                product_name = workorder.product_id.name or '-'
                plan_qty = workorder.production_id.product_qty or 0

        # Reload machine dari DB setelah sync
        machine.refresh()

        # Hitung counter relatif dari WO ini pakai offset
        plc_offset = machine.plc_offset or 0
        new_counter = counter - plc_offset

        # Kalau negatif berarti PLC sudah reset
        if new_counter < 0:
            new_counter = counter
            machine.write({'plc_offset': 0})

        # Simpan log
        self.create({
            'machine_id': machine.id,
            'status': status,
            'counter': new_counter,
            'timestamp': timestamp,
            'product_name': product_name,
        })

        # Update counter di mesin
        machine.write({
            'counter': new_counter,
            'latest_timestamp': timestamp,
        })

        # Cek apakah sudah capai plan → mark WO as done
        if plan_qty > 0 and new_counter >= plan_qty and workorder:
            try:
                workorder.write({'qty_produced': plan_qty})
                workorder.button_finish()
                machine.write({'counter': 0})
                return {'success': True, 'info': 'WO completed, counter reset'}
            except Exception as e:
                return {'success': True, 'warning': f'Counter ok tapi gagal finish WO: {str(e)}'}

        return {'success': True, 'counter': new_counter, 'plan': plan_qty}