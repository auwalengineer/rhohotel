/* eslint-disable no-unused-vars */

(() => {
    const BILL_TO_ROOM_LABEL = "bill to room";

    const is_bill_to_room_mode = (mode_of_payment) =>
        (mode_of_payment || "").toLowerCase().trim() === BILL_TO_ROOM_LABEL;

    const apply_patch = () => {
        const Payment = erpnext?.PointOfSale?.Payment;
        if (!Payment || !Payment.prototype || Payment.prototype.__rhohotel_bill_to_room_patched) {
            return;
        }

        const original_bind_events = Payment.prototype.bind_events;
        const original_render_payment_mode_dom = Payment.prototype.render_payment_mode_dom;
        const original_auto_set_remaining_amount = Payment.prototype.auto_set_remaining_amount;
        const original_focus_on_default_mop = Payment.prototype.focus_on_default_mop;

        Payment.prototype.bind_events = function () {
            original_bind_events.call(this);

            // Replace default submit validation with Bill-to-Room aware validation.
            this.$component.off("click", ".submit-order-btn");
            this.$component.on("click", ".submit-order-btn", () => {
                const doc = this.events.get_frm().doc;
                const paid_amount = flt(doc.paid_amount);
                const items = doc.items || [];
                const discount_is_full = flt(doc.additional_discount_percentage) === 100;
                const has_bill_to_room = (doc.payments || []).some((p) =>
                    is_bill_to_room_mode(p.mode_of_payment)
                );

                if (!this.validate_reqd_invoice_fields()) {
                    return;
                }

                if (!items.length) {
                    frappe.show_alert({ message: __("You cannot submit empty order."), indicator: "orange" });
                    frappe.utils.play_sound("error");
                    return;
                }

                if (paid_amount === 0 && !discount_is_full && !has_bill_to_room) {
                    frappe.show_alert({
                        message: __("You cannot submit the order without payment."),
                        indicator: "orange",
                    });
                    frappe.utils.play_sound("error");
                    return;
                }

                this.events.submit_invoice();
            });
        };

        Payment.prototype.render_payment_mode_dom = function () {
            original_render_payment_mode_dom.call(this);

            const doc = this.events.get_frm().doc;
            const payments = doc.payments || [];
            const currency = doc.currency;

            payments.forEach((p) => {
                if (!is_bill_to_room_mode(p.mode_of_payment)) return;

                const mode = this.sanitize_mode_of_payment(p.mode_of_payment);
                const control = this[`${mode}_control`];

                if (flt(p.amount) !== 0) {
                    frappe.model.set_value(p.doctype, p.name, "amount", 0);
                }

                if (control) {
                    control.set_value(0);
                    if (control.$input) {
                        control.$input.prop("readonly", true).prop("disabled", true);
                    }
                }

                this.$payment_modes.find(`.${mode}-amount`).html(format_currency(0, currency));
            });
        };

        Payment.prototype.auto_set_remaining_amount = function () {
            if (this.selected_mode) {
                const doc = this.events.get_frm().doc;
                const payments = doc.payments || [];
                for (const p of payments) {
                    if (!is_bill_to_room_mode(p.mode_of_payment)) continue;
                    const mode = this.sanitize_mode_of_payment(p.mode_of_payment);
                    if (this.selected_mode === this[`${mode}_control`]) {
                        return;
                    }
                }
            }

            original_auto_set_remaining_amount.call(this);
        };

        Payment.prototype.focus_on_default_mop = function () {
            if (this.disable_grand_total_to_default_mop) return;

            const doc = this.events.get_frm().doc;
            const payments = doc.payments || [];

            payments.forEach((p) => {
                if (is_bill_to_room_mode(p.mode_of_payment)) return;
                const mode = this.sanitize_mode_of_payment(p.mode_of_payment);
                if (p.default) {
                    setTimeout(() => {
                        this.$payment_modes.find(`.${mode}.mode-of-payment-control`).parent().click();
                    }, 500);
                }
            });
        };

        Payment.prototype.__rhohotel_bill_to_room_patched = true;
    };

    const start_patch_interval = () => {
        apply_patch();
        const interval = setInterval(() => {
            apply_patch();
            if (erpnext?.PointOfSale?.Payment?.prototype?.__rhohotel_bill_to_room_patched) {
                clearInterval(interval);
            }
        }, 300);
    };

    if (frappe.ready) {
        frappe.ready(start_patch_interval);
    } else {
        start_patch_interval();
    }
})();