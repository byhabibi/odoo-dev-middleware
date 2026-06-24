# -*- coding: utf-8 -*-


from odoo import models, fields, api, _
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError, UserError
import logging
_logger = logging.getLogger(__name__)

class EranQuotationLoiWiz(models.TransientModel):
    _name = "eran.quotation.loi.wiz"


    partner_id = fields.Many2one('res.partner', 'Customer')
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist')
    quotation_loi_line = fields.One2many('eran.quotation.loi.wiz.line', 'quotation_loi_id' ,'Line')
    
    def btn_confirm(self):
        pricelist_id = self.pricelist_id
        # store quotation loi
        sequences_setting = self.env['dsn.sales.sequence.setting'].search([
            ('type', '=', 'loi'), ('company_id', '=', self.env.company.id)], limit=1)
        
        if not sequences_setting or not sequences_setting.sequence_id:
            raise UserError("You must set sequence Sale Order in Sales Sequences Settings")
        
        new_name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
        parent = self.env['eran.quotation'].browse(self._context['parent_id'])
        
        val_loi = self.env['eran.quotation.loi'].create({
            'name': new_name,
            'partner_id': self.partner_id.id,
            'pricelist_id': self.pricelist_id.id,
            'quotation_id': parent.id,
            'quotation_loi_line': [(0, 0, {
                'product_id': line.product_id.id,
                'min_qty': line.min_qty,
                'price': line.price,
                'start_date': line.start_date,
                'end_date': line.end_date
            }) for line in self.quotation_loi_line]
        })
        val_loi.btn_waiting_approval()
        
        
        for line in self.quotation_loi_line:
            # store quotation loi line
            # self.env['eran.quotation.loi.line'].create({
            #     'quotation_loi_id':loi_id.id,
            #     'product_id':line.product_id.id,
            #     'min_qty':line.min_qty,
            #     'price':line.price,
            #     'start_date':line.start_date,
            #     'end_date':line.end_date
            # })
            
            # ini nanti aja pas approved
            # vals = {
            #     'product_tmpl_id':line.product_id.product_tmpl_id.id,
            #     'min_quantity':line.min_qty,
            #     'fixed_price':line.price,
            #     'date_start':line.start_date,
            #     'date_end':line.end_date,
            #     'pricelist_id':pricelist_id.id
            # }
            # self.env['product.pricelist.item'].create(vals)
            
            msg = "LOI CREATED<br/>Product %s Sales Price %s <br/> Start date %s <br/> End date %s"  % (line.product_id.product_tmpl_id.name, line.price, line.start_date, line.end_date)                        
            parent.message_post(body=msg)
        parent.write({
            'is_loi_created': True
        })


class EranQuotationLoiWizLine(models.TransientModel):
    _name = "eran.quotation.loi.wiz.line"

    quotation_loi_id = fields.Many2one('eran.quotation.loi.wiz', 'Quotation Loi')
    product_id = fields.Many2one('product.product', 'Product')
    min_qty = fields.Float('Min. Quantity')
    price = fields.Float('Price')
    start_date = fields.Datetime('Start date')
    end_date = fields.Datetime('End date')
                
        