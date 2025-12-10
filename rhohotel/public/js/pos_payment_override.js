// your_app/public/js/pos_payment_override.js

const original_render_payment_mode_dom = erpnext.PointOfSale.Payment.prototype.render_payment_mode_dom;

erpnext.PointOfSale.Payment.prototype.render_payment_mode_dom = function() {
    // Call original method first
    original_render_payment_mode_dom.call(this);
    
    const doc = this.events.get_frm().doc;
    const payments = doc.payments;
    const currency = doc.currency;
    const me = this;
    
    payments.forEach((p) => {
        const mode = this.sanitize_mode_of_payment(p.mode_of_payment);
        
        // Case-insensitive check for "bill to room"
        if (p.mode_of_payment.toLowerCase().trim() === "bill to room") {
            
            // Set amount to 0 in the backend
            frappe.model.set_value(p.doctype, p.name, "amount", 0);
            
            // Recreate the control as read-only
            if (this[`${mode}_control`]) {
                // Destroy existing control
                this[`${mode}_control`].$wrapper.remove();
            }
            
            // Create new read-only control
            this[`${mode}_control`] = frappe.ui.form.make_control({
                df: {
                    label: p.mode_of_payment,
                    fieldtype: "Currency",
                    placeholder: __("Bill to Room - No amount required"),
                    read_only: 1,
                    onchange: function() {
                        // Prevent any changes - always set back to 0
                        this.set_value(0);
                    }
                },
                parent: this.$payment_modes.find(`.${mode}.mode-of-payment-control`),
                render_input: true,
            });
            
            this[`${mode}_control`].toggle_label(false);
            this[`${mode}_control`].set_value(0);
            
            // Update displayed amount
            this.$payment_modes.find(`.${mode}-amount`).html(format_currency(0, currency));
            
            // Extra safety - directly make input read-only and style it
            setTimeout(() => {
                me.$payment_modes
                    .find(`.${mode}.mode-of-payment-control`)
                    .find('input')
                    .prop('readonly', true)
                    .prop('disabled', true)
                    .css({
                        'background-color': '#f0f0f0',
                        'cursor': 'not-allowed'
                    });
            }, 100);
        }
    });
};

// Also override auto_set_remaining_amount to skip Bill to Room
const original_auto_set_remaining_amount = erpnext.PointOfSale.Payment.prototype.auto_set_remaining_amount;

erpnext.PointOfSale.Payment.prototype.auto_set_remaining_amount = function() {
    // Check if selected mode is Bill to Room, skip if so
    if (this.selected_mode) {
        const doc = this.events.get_frm().doc;
        const payments = doc.payments;
        
        for (let p of payments) {
            const mode = this.sanitize_mode_of_payment(p.mode_of_payment);
            if (this.selected_mode === this[`${mode}_control`] && 
                p.mode_of_payment.toLowerCase().trim() === "bill to room") {
                // Don't auto-set amount for Bill to Room
                return;
            }
        }
    }
    
    // Call original for other payment methods
    original_auto_set_remaining_amount.call(this);
};

// Override focus_on_default_mop to handle Bill to Room
const original_focus_on_default_mop = erpnext.PointOfSale.Payment.prototype.focus_on_default_mop;

erpnext.PointOfSale.Payment.prototype.focus_on_default_mop = function() {
    if (this.disable_grand_total_to_default_mop) return;
    
    const doc = this.events.get_frm().doc;
    const payments = doc.payments;
    const me = this;
    
    payments.forEach((p) => {
        // Skip Bill to Room even if it's default
        if (p.mode_of_payment.toLowerCase().trim() === "bill to room") {
            return;
        }
        
        const mode = me.sanitize_mode_of_payment(p.mode_of_payment);
        if (p.default) {
            setTimeout(() => {
                me.$payment_modes.find(`.${mode}.mode-of-payment-control`).parent().click();
            }, 500);
        }
    });
};