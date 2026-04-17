// File: your_custom_app/public/js/pos_print_invoice_extension.js
// POS Extension - Print Invoice Button
// Compatible with Frappe v13+

(function () {
    'use strict';

    // Method: Wait for window load and then extend
    function extendPOS() {
        // Check if POS is available
        if (typeof erpnext === 'undefined' || !erpnext.PointOfSale) {
            console.debug('[POS Extension] erpnext.PointOfSale not found yet');
            return false;
        }

        if (!erpnext.PointOfSale.PastOrderSummary) {
            console.debug('[POS Extension] PastOrderSummary class not found yet');
            return false;
        }

        console.log('[POS Extension] Successfully extending PastOrderSummary');

        // Store the original class
        const OriginalPastOrderSummary = erpnext.PointOfSale.PastOrderSummary;

        // Replace with extended class
        erpnext.PointOfSale.PastOrderSummary = class ExtendedPastOrderSummary extends OriginalPastOrderSummary {
            constructor(opts) {
                super(opts);
                this._print_invoice_button_added = false;
            }

            // Override the method that renders buttons
            add_summary_btns(map) {
                // Call original implementation
                super.add_summary_btns(map);

                // Add our custom button
                this.add_print_invoice_button();
            }

            // New method to add Print Invoice button
            add_print_invoice_button() {
                const $delete_btn = this.$summary_btns.find('.delete-btn');

                // Prevent adding button multiple times
                if (!$delete_btn.length || this._print_invoice_button_added) {
                    return;
                }

                // Insert button after Delete Order button
                $delete_btn.after(
                    `<div class="summary-btn btn btn-default print-invoice-btn">
                        ${__("Print Invoice")}
                    </div>`
                );

                // Remove any existing listeners to prevent duplicates
                this.$summary_btns.off('click.print_invoice_btn');

                // Add click handler
                this.$summary_btns.on('click.print_invoice_btn', '.print-invoice-btn', () => {
                    this.print_invoice_summary();
                });

                this._print_invoice_button_added = true;
                console.log('[POS Extension] Print Invoice button added');
            }

            // New method to handle printing
            print_invoice_summary() {
                if (!this.doc) {
                    frappe.msgprint(__('No invoice selected'));
                    return;
                }

                console.log('[POS Extension] Printing invoice:', this.doc.name);

                const frm = this.events.get_frm();

                // Use same print settings as Print Receipt button
                frappe.utils.print(
                    this.doc.doctype,
                    this.doc.name,
                    frm.pos_print_format || 'Standard',
                    this.doc.letter_head,
                    this.doc.language || frappe.boot.lang
                );
            }
        };

        return true;
    }

    // Try to extend immediately
    if (document.readyState === 'loading') {
        // DOM is still loading
        document.addEventListener('DOMContentLoaded', extendPOS);
    } else {
        // DOM is already loaded
        extendPOS();
    }

    // Also try on window load as fallback
    window.addEventListener('load', extendPOS);

    // Periodic check in case POS loads dynamically
    let checkAttempts = 0;
    const checkInterval = setInterval(() => {
        if (extendPOS()) {
            clearInterval(checkInterval);
            console.log('[POS Extension] Extension complete');
        }
        checkAttempts++;

        // Stop checking after 30 seconds
        if (checkAttempts > 60) {
            clearInterval(checkInterval);
            console.warn('[POS Extension] Could not extend POS after 30 seconds');
        }
    }, 500);

})();