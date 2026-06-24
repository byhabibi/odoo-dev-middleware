from odoo import models
from collections import defaultdict

class ReportInvoiceExportExcel(models.AbstractModel):
    _name = 'report.eran_custom.report_invoice_export_excel'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, invoices):
        sheet = workbook.add_worksheet('Invoices')
        bold = workbook.add_format({'bold': True})
        number_format = workbook.add_format({'num_format': '#,##0.00'})
        right_align_format = workbook.add_format({'align': 'right'})
        PAYMENT_STATE_DISPLAY = {
            'not_paid': 'Not Paid',
            'in_payment': 'In Payment',
            'paid': 'Paid',
            'partial': 'Partially Paid',
            'reversed': 'Reversed',
            'invoicing_legacy': 'Invoicing App Legacy',
        }
        STATE_DISPLAY = {
            'draft': 'Draft',
            'posted': 'Posted',
            'cancel': 'Cancelled',
        }

        headers = ['Number', 'Invoice Partner Display Name', 'Product', 'Quantity', 'Unit Price', 'Unit of Measure', 
                   'Due Date', 'Bill Date', 'Payment Status', 'Status', 'Tax Number', 'Total in Currency Signed', 
                   'Total Signed', 'Untaxed Amount Signed']
        column_widths = [20, 35, 35, 10, 10, 15, 15, 15, 15, 10, 20, 20, 20, 22]

        for col, (header, width) in enumerate(zip(headers, column_widths)):
            sheet.set_column(col, col, width)
            sheet.write(0, col, header, bold)

        row = 1
        for invoice in invoices:
            # Gabungkan invoice_line_ids by product & price_unit
            grouped_lines = defaultdict(lambda: {'quantity': 0.0, 'uom': None})
            for line in invoice.invoice_line_ids:
                key = (line.product_id.id, line.price_unit)
                grouped_lines[key]['quantity'] += line.quantity
                grouped_lines[key]['uom'] = line.product_uom_id

            first_line = True
            for (product_id, price_unit), data_line in grouped_lines.items():
                product = self.env['product.product'].browse(product_id)
                if first_line:
                    sheet.write(row, 0, invoice.name)
                    sheet.write(row, 1, invoice.invoice_partner_display_name or '')
                    sheet.write(row, 6, str(invoice.invoice_date_due or ''), right_align_format)
                    sheet.write(row, 7, str(invoice.invoice_date or ''), right_align_format)
                    sheet.write(row, 8, PAYMENT_STATE_DISPLAY.get(invoice.payment_state, invoice.payment_state))
                    sheet.write(row, 9, STATE_DISPLAY.get(invoice.state, invoice.state))
                    sheet.write(row, 10, invoice.l10n_id_tax_number or '')
                    sheet.write_number(row, 11, invoice.amount_total_in_currency_signed, number_format)
                    sheet.write_number(row, 12, invoice.amount_total_signed, number_format)
                    sheet.write_number(row, 13, invoice.amount_untaxed_signed, number_format)
                    first_line = False
                else:
                    # Kosongkan kolom invoice-nya untuk baris selanjutnya
                    for col_idx in [0, 1, 6, 7, 8, 9, 10, 11, 12, 13]:
                        sheet.write(row, col_idx, '')

                # Tulis kolom detail line-nya
                sheet.write(row, 2, product.name or '')
                sheet.write_number(row, 3, data_line['quantity'], number_format)
                sheet.write_number(row, 4, price_unit, number_format)
                sheet.write(row, 5, data_line['uom'].name or '')
                row += 1