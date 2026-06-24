
from odoo import api, fields, models, _
import logging
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class PurchaseRequest(models.Model):
    _inherit = "purchase.request"

    # PO Creation: desire the purchase request is capable to create Purchase Order by count the quantity
    po_creations = fields.Boolean(string="PO Creation", compute="_compute_po_creations")
    qty_request = fields.Float(string="Quantity Purchase Request", compute="_compute_qty_request")
    is_all_create_po = fields.Boolean(string="Is All Create PO?", help="Check whether all purchase orders have been made or not.", compute="_compute_qty_request", store=True)
    purchase_order_ids = fields.Many2many("purchase.order", string="Purchase Order", compute="_compute_purchase_order")
    department_id = fields.Many2one('hr.department', string="Department", readonly=True)
    total_vendor_price = fields.Monetary('Total Vendor Price', compute='_compute_total_vendor_price', store=True)

    @api.depends("line_ids", "line_ids.vendor_price")
    def _compute_total_vendor_price(self):
        for rec in self:
            rec.total_vendor_price = sum([line.product_qty * line.vendor_price for line in rec.line_ids])

    @api.depends("line_ids", "line_ids.estimated_cost")
    def _compute_estimated_cost(self):
        for rec in self:
            rec.estimated_cost = sum([line.product_qty * line.estimated_cost for line in rec.line_ids])

    def _compute_purchase_order(self):
        for rec in self:
            lines = rec.mapped("line_ids.purchase_lines.order_id")
            rec.purchase_order_ids = lines

    # def replace_name(self):
    #     employee_ids = self.env['hr.employee'].search([('user_id', '=', self.create_uid.id)], limit=1)
    #     if employee_ids:
    #         self.department_id = employee_ids.department_id.id
    #         department_code = employee_ids.department_id.code
            
    #     sequences_setting = self.env['dsn.purchase.sequence.setting'].search([
    #         ('type', '=', 'purchase_request'), ('company_id', '=', self.env.company.id)], limit=1)
        
    #     if not sequences_setting or not sequences_setting.sequence_id:
    #         raise UserError("You must set sequence Purchase Request in Purchase Sequences Settings")
        
    #     if not department_code:
    #         raise UserError("Please ensure department code isn't empty!")
        
    #     name = sequences_setting.sequence_id.next_by_id(sequence_date=fields.date.today())
    #     suffix = sequences_setting.code
        
    #     number_sequence = name.rsplit('/')[-4]
    #     month = name.rsplit('/')[-2]
    #     year = name.rsplit('/')[-1]
    #     name = number_sequence + '/' + department_code + '/' + suffix + '/' + month + '/' + year
    #     self.name = name
    #     return name
    
    def button_to_approve(self):
        for rec in self.line_ids:
            if rec.vendor_price <= 0 and rec.estimated_cost <= 0:
                raise ValidationError(_("Ensure one of 'vendor price' and 'estimated cost' is not 0"))
            
        res = super(PurchaseRequest, self).button_to_approve()
        return res
                
    @api.model
    def create(self,values):
        employee_id = self.env.user.employee_id
        department_code = False
        if employee_id:
            values['department_id'] = employee_id.department_id.id
            department_code = employee_id.department_id.code
        if not department_code:
            raise UserError("Please ensure department code isn't empty!")
        res  = super(PurchaseRequest, self).create(values)
        name = res.name
        list_name = name.rsplit('/')
        first = [list_name[0], department_code + '/']
        merged = "/".join(first) + "/".join(list_name[1:])
        res.name = merged

        return res
        
    @api.depends('line_ids', 'purchase_count')
    def _compute_po_creations(self):
        self.line_ids.mapped('product_id')
        
        balance_qty = []

        pr_list = []
        for line in self.line_ids:
            balance_qty.append(line.product_qty >= line.purchased_qty)
            pr_dict = {line.product_id.name: line.product_qty}
            pr_list.append(pr_dict)

        balance_qty = False in balance_qty

        pr_combined_data = {}
        for item in pr_list:
            for key, value in item.items():
                if key in pr_combined_data:
                    pr_combined_data[key] += value
                else:
                    pr_combined_data[key] = value

        pr_output_data = [pr_combined_data]
        
        po_list = []
        po_ids = self.line_ids.mapped("purchase_lines.order_id")
        for po in po_ids:
            if po.state != 'cancel':
                for po_line in po.order_line:
                    po_dict = {po_line.product_id.name: po_line.product_qty}
                    po_list.append(po_dict)

        po_combined_data = {}
        for item in po_list:
            for key, value in item.items():
                if key in po_combined_data:
                    po_combined_data[key] += value
                else:
                    po_combined_data[key] = value

        po_output_data = [po_combined_data]

        self.po_creations = len(po_output_data) > 0 and  pr_output_data == po_output_data or balance_qty
        
    @api.depends('line_ids.product_qty', 'line_ids.purchased_qty')
    def _compute_qty_request(self):
        for rec in self:
            res = 0
            res_po = 0
            for line in rec.line_ids:
                if line.purchase_state != 'cancel':
                    res += line.product_qty
                    res_po += line.purchased_qty
            rec.qty_request = res
            
            if res != 0 and res_po != 0:
                if res == res_po:
                    rec.is_all_create_po = True
                else:
                    rec.is_all_create_po = False
            else:
                rec.is_all_create_po = False
        

class PurchaseRequestLine(models.Model):
    _inherit = "purchase.request.line"

    mrp_non_material_id = fields.Many2one('eran.mrp.non.material', string='MRP Non Material')
    outstanding_pr = fields.Float(string='Outstanding PR', compute='compute_outstanding', store=True)
    additional_uom_id = fields.Many2one(related="product_id.additional_uom_id", string='Alternative Uom')
    additional_qty = fields.Float(string="Alternative Qty", compute="_get_additional_qty", inverse="_inverse_additional_qty", store=True)
    po_additional_qty = fields.Float(string="PO Alternative Qty", compute="_get_po_additional_qty")
    department_id = fields.Many2one('hr.department', related="request_id.department_id", string="Department", store=True)
    vendor_price = fields.Float(string="Vendor Price", compute="_ern_get_vendor_price")
    category_group_id = fields.Many2one('eran.category.group', string='Category Group', related='product_id.category_group_id', store=True)
    cost = fields.Float('Cost', compute="_compute_cost", store=True)
    cost_amount = fields.Float('Cost Amount', compute="_compute_cost", store=True)

    @api.depends('product_id','product_qty')
    def _compute_cost(self):
        for line in self:
            cost = 0
            cost_amount = 0
            if line.product_id:
                cost = line.product_id.standard_price
                cost_amount = line.product_id.standard_price * line.product_qty
            line.cost = cost
            line.cost_amount = cost_amount

    # @api.constrains('estimated_cost')
    # def _check_estimated_cost(self):
    #     for rec in self:
    # Dipindah saat request approval
    #         if rec.vendor_price <= 0:
    #             if rec.estimated_cost <= 0:
    #                 raise ValidationError(_('Estimated Cost tidak boleh 0.'))

    @api.depends('product_id', 'date_required')
    def _ern_get_vendor_price(self):
        for rec in self:
            price_v = 0
            v_price_ids = self.env['product.supplierinfo'].search([('product_tmpl_id.id', '=', rec.product_id.product_tmpl_id.id), ('date_start', '<=', rec.date_required), ('date_end', '>=', rec.date_required), ('state', '=', 'done'), ('currency_id', '=', rec.currency_id.id)], order='price asc')
            for v_pr in v_price_ids:
                price_v = v_pr.price
            rec.vendor_price = price_v

    @api.onchange("product_id")
    def onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name
            self.product_uom_id = self.product_id.uom_id.id
            self.product_qty = 1
            
    @api.depends('purchased_qty')
    def _get_po_additional_qty(self):
        for rec in self:
            rec.po_additional_qty = rec.purchased_qty * rec.product_id.additional_qty if rec.product_id.additional_qty else 0

    @api.depends('product_qty')
    def _get_additional_qty(self):
        for rec in self:
            if rec.product_id.additional_qty > 0 :
                rec.additional_qty = rec.product_qty * rec.product_id.additional_qty if rec.product_id.additional_qty else 0
    
    @api.onchange('additional_qty')
    def _inverse_additional_qty(self):
        for rec in self:
            if rec.product_id.additional_qty > 0 :
                rec.product_qty = rec.additional_qty / rec.product_id.additional_qty if rec.product_id.additional_qty else 0

    @api.depends('product_qty', 'purchased_qty')
    def compute_outstanding(self):
        for line in self:
            line.outstanding_pr = line.product_qty - line.purchased_qty
            if line.outstanding_pr < 0:
                line.outstanding_pr = 0

    # @api.constrains('product_qty')
    # def _check_product_qty_line(self):
    #     for line in self:
    #         val = 1
    #         temp = []
    #         round_vals = []
    #         round_ids = line.env['product.supplierinfo'].sudo().search([('product_tmpl_id.id', '=', line.product_id.product_tmpl_id.id), ('state', '=', 'done')])
    #         for ids in round_ids:
    #             round_vals.append(ids.rounding_value)
    #             for x in range(1, int(line.product_qty)+1):
    #                 if (x % ids.rounding_value) == 0:
    #                     temp.append(x)
            
    #         if len(round_vals) != 0 and min(round_vals) > line.product_qty:
    #             raise ValidationError(_('The Purchase Request quantity cannot be Less than the Rounding Value'))
    #         else:
    #             pass
                        
    #         if len(temp)!=0:
    #             if line.product_qty in temp:
    #                 pass
    #             else:
    #                 raise ValidationError(_("The quantity of PR %s must be a multiple of either %s." %(line.product_id.name, round_vals)))