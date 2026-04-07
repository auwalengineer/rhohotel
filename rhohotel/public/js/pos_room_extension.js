// SOLUTION: Hook into POS checkout to capture the check-in value
// This needs to run in the POS Point of Sale interface

function setupRoomExtension() {
    if (!window.erpnext || !window.erpnext.PointOfSale || !window.erpnext.PointOfSale.ItemCart) {
        setTimeout(setupRoomExtension, 100);
        return;
    }
    
    // Hook into the actual ItemCart initialization
    const originalItemCartInit = erpnext.PointOfSale.ItemCart.prototype.init_component;

    erpnext.PointOfSale.ItemCart.prototype.init_component = function() {
        // Call original init
        originalItemCartInit.call(this);
        
        // Store current check-in ID
        this.current_check_in = null;
        
        // Override make_customer_selector
        this.make_customer_selector = function() {
            // Add room field BEFORE customer field
            this.$customer_section.html(`
                <div class="room-field-wrapper" style="margin-bottom: 10px;"></div>
                <div class="customer-field"></div>
            `);
            
            this.make_room_selector.call(this);
            
            // Then initialize customer field normally
            const me = this;
            const allowed_customer_group = this.allowed_customer_groups || [];
            let filters = {};
            if (allowed_customer_group.length) {
                filters = {
                    customer_group: ["in", allowed_customer_group],
                };
            }
            
            this.customer_field = frappe.ui.form.make_control({
                df: {
                    label: __("Customer"),
                    fieldtype: "Link",
                    options: "Customer",
                    placeholder: __("Search by customer name, phone, email."),
                    get_query: function () {
                        return {
                            filters: filters,
                        };
                    },
                    onchange: function () {
                        if (this.value) {
                            const frm = me.events.get_frm();
                            frappe.dom.freeze();
                            frappe.model.set_value(frm.doc.doctype, frm.doc.name, "customer", this.value);
                            frm.script_manager.trigger("customer", frm.doc.doctype, frm.doc.name).then(() => {
                                frappe.run_serially([
                                    () => me.fetch_customer_details(this.value),
                                    () => me.events.customer_details_updated(me.customer_info),
                                    () => me.update_customer_section(),
                                    () => me.update_totals_section(),
                                    () => frappe.dom.unfreeze(),
                                ]);
                            });
                        }
                    },
                },
                parent: this.$customer_section.find(".customer-field"),
                render_input: true,
            });
            this.customer_field.toggle_label(false);
        };
        
        this.make_room_selector = function() {
            const me = this;
            
            this.room_field = frappe.ui.form.make_control({
                df: {
                    label: __("Room"),
                    fieldtype: "Link",
                    options: "Hotel Room",
                    placeholder: __("Select room"),
                    get_query: function () {
                        return {
                            filters: {
                                status: "Occupied"
                            },
                        };
                    },
                    onchange: function () {
                        if (this.value) {
                            me.set_customer_from_room(this.value);
                        } else {
                            // Clear check-in if room is cleared
                            me.current_check_in = null;
                        }
                    },
                },
                parent: this.$customer_section.find(".room-field-wrapper"),
                render_input: true,
            });
            
            this.room_field.toggle_label(false);
        };
        
        this.set_customer_from_room = function(room_name) {
            const me = this;
            
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Hotel Room',
                    name: room_name,
                },
                callback: function(r) {
                    if (!r.message) return;
                    
                    const room = r.message;
                    
                    if (!room.current_guest) {
                        frappe.msgprint(__('No guest assigned to this room'));
                        me.room_field.set_value("");
                        me.current_check_in = null;
                        return;
                    }
                    
                    // Store the current_check_in from the room - CRITICAL STEP
                    me.current_check_in = room.current_check_in || null;
                    console.log('✓ Room check-in stored in cart:', me.current_check_in);
                    
                    frappe.call({
                        method: 'frappe.client.get',
                        args: {
                            doctype: 'Hotel Guest',
                            name: room.current_guest,
                        },
                        callback: function(r2) {
                            if (!r2.message) return;
                            
                            const guest = r2.message;
                            me.customer_field.set_value(guest.hotel_guest_name);
                        }
                    });
                }
            });
        };
    };
    
    console.log('✓ POS Room Extension loaded successfully');
}

setupRoomExtension();

// ===================================================================
// SOLUTION: Hook into POS payment/completion to save check-in
// This is where the invoice is created, BEFORE it's submitted
// ===================================================================

function setupPaymentSubmitHook() {
    if (!window.erpnext || !window.erpnext.PointOfSale || !window.erpnext.PointOfSale.Payment) {
        setTimeout(setupPaymentSubmitHook, 100);
        return;
    }

    const paymentPrototype = erpnext.PointOfSale.Payment.prototype;
    if (!paymentPrototype || !paymentPrototype.submit_invoice || paymentPrototype.__rhohotel_submit_hooked) {
        return;
    }

    const originalSubmitInvoice = paymentPrototype.submit_invoice;

    paymentPrototype.submit_invoice = function() {
        console.log('='.repeat(80));
        console.log('CUSTOM: submit_invoice - BEFORE original submission');
        
        // Get current check-in from cart
        const current_check_in = window.cur_pos?.cart?.current_check_in;
        console.log('Current check-in from cart:', current_check_in);
        
        // Store in sessionStorage as backup
        if (current_check_in) {
            sessionStorage.setItem('pos_current_check_in', current_check_in);
            console.log('✓ Stored check-in in sessionStorage:', current_check_in);
        }
        
        // Call original function
        return originalSubmitInvoice.call(this);
    };

    paymentPrototype.__rhohotel_submit_hooked = true;
    console.log('✓ Hooked into Payment.submit_invoice');
}

setupPaymentSubmitHook();

// ===================================================================
// Hook into POS Invoice form when opened from POS
// ===================================================================
frappe.ui.form.on('POS Invoice', {
    onload: function(frm) {
        console.log('='.repeat(80));
        console.log('POS Invoice ONLOAD');
        
        // Try to get check-in from sessionStorage (fallback)
        let check_in_value = window.cur_pos?.cart?.current_check_in;
        
        if (!check_in_value) {
            const session_check_in = sessionStorage.getItem('pos_current_check_in');
            if (session_check_in) {
                check_in_value = session_check_in;
                console.log('✓ Retrieved check-in from sessionStorage:', check_in_value);
                sessionStorage.removeItem('pos_current_check_in'); // Clear after use
            }
        }
        
        console.log('Check-in value:', check_in_value);
        
        if (check_in_value) {
            console.log('✓ Setting custom_hotel_room_check_in:', check_in_value);
            frm.set_value('custom_hotel_room_check_in', check_in_value);
        }
    },

    before_save: function(frm) {
        const check_in_value = window.cur_pos?.cart?.current_check_in;
        if (check_in_value) {
            console.log('before_save: Setting check-in:', check_in_value);
            frm.doc.custom_hotel_room_check_in = check_in_value;
        }
    },
    
    before_submit: function(frm) {
        const check_in_value = window.cur_pos?.cart?.current_check_in;
        console.log('before_submit: check-in value:', check_in_value);
        if (check_in_value) {
            frm.doc.custom_hotel_room_check_in = check_in_value;
            console.log('✓ Check-in set before submit');
        }
    }
});
