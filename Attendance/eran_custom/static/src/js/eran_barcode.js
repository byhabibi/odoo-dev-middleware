/** @odoo-module **/
import { patch } from '@web/core/utils/patch';
import BarcodePickingModel from '@stock_barcode/models/barcode_picking_model';

patch(BarcodePickingModel.prototype, 'eran_custom.BarcodePickingModel', {

    get canBeProcessed() {
        const isDeliveryOrder = this.record.picking_type_code === 'outgoing';

        if (isDeliveryOrder && this.record.state_dn_out !== 'done') {
            return true;
        }

        return this._super();
    },

    get isDone() {
        const isDeliveryOrder = this.record.picking_type_code === 'outgoing';
        
        if (isDeliveryOrder && this.record.state_dn_out === 'done') {
            if (this.record.dn_out) {
                return true; 
            } else {
                return false;
            }
        }
        return this._super(); 
    },

    // get canBeValidate() {
    //     if (this.isDone || this.isCancelled) {
    //         return false;
    //     }
    //     if (this.record.immediate_transfer) {
    //         return super.canBeValidate; // For immediate transfers, doesn't care about any special condition.
    //     } else if (!this.config.barcode_validation_full && !this.currentState.lines.some(line => line.qty_done)) {
    //         return false; // Can't be validate because "full validation" is forbidden and nothing was processed yet.
    //     }
    //     return super.canBeValidate;
    // },

    async dnOut() {
        await this.orm.call(
            'stock.picking',
            'action_button_dn_out',
            [this.record.id]
        );
        location.reload(); 
    }
});
