from odoo import models, fields

class EranKPIVendorReport(models.Model):
    _name = 'eran.kpi.vendor.report'
    _auto = False
    _description = 'KPI vendor report'
    
    purchase_id = fields.Many2one('purchase.order', string="Order No.")
    partner_id = fields.Many2one('res.partner', string='Vendor', related='purchase_id.partner_id')
    product_id = fields.Many2one('product.product',string='Product')
    price_unit = fields.Float(string="Price")
    
    order_date = fields.Datetime(string="Order Date", related='purchase_id.date_order')
    order_qty = fields.Float(string="Order Qty")
    sub_total = fields.Float(string="Sub Total (Rp)")
    
    order_sheet_id = fields.Many2one('eran.order.sheet', string="Order Sheet")
    order_sheet_date = fields.Datetime(string="Order Sheet Date", related='order_sheet_id.schedule_date')
    order_sheet_qty = fields.Float(string="Order Sheet Qty")
    sub_total_order_sheet = fields.Float(string="Sub Total OS (Rp)")
    
    picking_id = fields.Many2one('stock.picking', string="Receipt Number")
    receipt_date = fields.Datetime(string="Receipt Date", related='picking_id.date_done')
    receipt_qty = fields.Float(string="Receipt Qty")
    sub_total_receipt = fields.Float(string="Sub Total Receipt (Rp)")
    state_picking = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Another Operation'),
        ('confirmed', 'Waiting'),
        ('assigned', 'Ready'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status Receipt', related='picking_id.state')
    
    def init(self):
        self._cr.execute("""
                        DROP VIEW IF EXISTS eran_kpi_vendor_report;
                        CREATE OR REPLACE VIEW eran_kpi_vendor_report AS (
                            SELECT
                                row_number() over (ORDER BY po_line.id) as id,
                                po_line.product_id as product_id,
                                po_line.price_unit as price_unit,
                                po_line.order_id as purchase_id,
                                po_line.product_qty as order_qty,
                                (po_line.product_qty * po_line.price_unit) as sub_total,
                                order_sheet.order_sheet_id as order_sheet_id,
	                            order_sheet.qty_receipt as order_sheet_qty,
                                (order_sheet.qty_receipt * po_line.price_unit) as sub_total_order_sheet,
                                receipt.picking_id as picking_id,
                                receipt.quantity_done as receipt_qty,
                                (receipt.quantity_done * po_line.price_unit) as sub_total_receipt
                            FROM
                                purchase_order_line as po_line
                            INNER JOIN
                                eran_order_sheet_line as order_sheet on order_sheet.purchase_line_id = po_line.id
                            INNER JOIN
                                stock_move as receipt on receipt.order_sheet_line_id = order_sheet.id
                        )
                         """)