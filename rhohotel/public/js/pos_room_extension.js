function setupRoomExtension() {
    if (!window.erpnext || !window.erpnext.PointOfSale || !window.erpnext.PointOfSale.ItemCart) {
        setTimeout(setupRoomExtension, 100);
        return;
    }

    const originalItemCartInit = erpnext.PointOfSale.ItemCart.prototype.init_component;

    erpnext.PointOfSale.ItemCart.prototype.init_component = function () {
        originalItemCartInit.call(this);

        this.current_check_in = null;

        const me = this;

        this.make_customer_selector = function () {
            this.$customer_section.html(`
                <div class="room-field-wrapper" style="margin-bottom: 10px;"></div>
                <div class="customer-field"></div>
            `);

            this.make_room_selector.call(this);

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
                        return { filters: filters };
                    },
                    onchange: function () {
                        if (this.value) {
                            const frm = me.events.get_frm();
                            frappe.dom.freeze();
                            frappe.model.set_value(frm.doc.doctype, frm.doc.name, "customer", this.value);
                            frappe.model.set_value(frm.doc.doctype, frm.doc.name, "title", this.value);
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

        this.make_room_selector = function () {
            this.room_field = frappe.ui.form.make_control({
                df: {
                    label: __("Room"),
                    fieldtype: "Link",
                    options: "Hotel Room",
                    placeholder: __("Select room"),
                    get_query: function () {
                        return {
                            filters: { status: "Occupied" }
                        };
                    },
                    onchange: function () {
                        if (this.value) {
                            me.set_customer_from_room(this.value);
                        } else {
                            me.current_check_in = null;
                        }
                    },
                },
                parent: this.$customer_section.find(".room-field-wrapper"),
                render_input: true,
            });
            this.room_field.toggle_label(false);
        };

        this.set_customer_from_room = function (room_name) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Hotel Room',
                    name: room_name,
                },
                callback: function (r) {
                    if (!r.message) return;

                    const room = r.message;

                    if (!room.current_guest) {
                        frappe.msgprint(__('No guest assigned to this room'));
                        me.room_field.set_value("");
                        me.current_check_in = null;
                        return;
                    }

                    me.current_check_in = room.current_check_in || null;
                    console.log('✓ Room check-in stored in cart:', me.current_check_in);

                    const frm = me.events.get_frm();

                    frappe.call({
                        method: 'frappe.client.get',
                        args: {
                            doctype: 'Hotel Guest',
                            name: room.current_guest,
                        },

                        callback: function (r2) {
                            if (!r2.message) return;
                            const guest = r2.message;
                            const customer_name = guest.hotel_guest_name;
                            console.log('Customer:', customer_name, 'Check-in:', me.current_check_in);

                            if (frm && frm.doc) {
                                // Set directly on frm.doc - no server calls on unsaved doc
                                frm.doc.customer = customer_name;
                                frm.doc.title = customer_name;
                                frm.doc.custom_hotel_room_check_in = me.current_check_in;

                                // Update customer field display
                                me.customer_field.set_value(customer_name);

                                // Update page title
                                if (frm.page) frm.page.set_title(customer_name);

                                // Fetch customer details for loyalty points etc
                                me.fetch_customer_details(customer_name).then(() => {
                                    me.events.customer_details_updated(me.customer_info);
                                    me.update_customer_section();
                                    me.update_totals_section();
                                });

                                console.log('✓ Done. Customer:', customer_name, 'Check-in:', me.current_check_in);
                            } else {
                                console.warn('frm or frm.doc not available');
                            }
                        }
                    });
                }
            });
        };

        // Clear room and check-in when cart editing is re-enabled
        const originalEnableCustomerSelection = this.enable_customer_selection?.bind(this);
        this.enable_customer_selection = function () {
            if (me.room_field) {
                me.room_field.set_value("");
            }
            me.current_check_in = null;
            originalEnableCustomerSelection && originalEnableCustomerSelection();
        };
    };

    console.log('✓ dsssasPOS Room Extension loaded successfully');
}

setupRoomExtension();

// Hook into submit_invoice AFTER POS is fully loaded
// Do NOT use frappe.provide here as it overwrites the existing object
function hookSubmitInvoice() {
    if (!window.erpnext || !window.erpnext.PointOfSale || !window.erpnext.PointOfSale.Payment) {
        setTimeout(hookSubmitInvoice, 500);
        return;
    }

    const originalSubmitInvoice = erpnext.PointOfSale.Payment.prototype.submit_invoice;
    if (originalSubmitInvoice) {
        erpnext.PointOfSale.Payment.prototype.submit_invoice = function () {
            const current_check_in = window.cur_pos?.cart?.current_check_in;
            console.log('submit_invoice: check-in from cart:', current_check_in);

            if (current_check_in) {
                sessionStorage.setItem('pos_current_check_in', current_check_in);
                const frm = window.cur_pos?.frm;
                if (frm && frm.doc) {
                    frm.doc.custom_hotel_room_check_in = current_check_in;
                    console.log('✓ Set on frm.doc at submit_invoice:', current_check_in);
                }
            }

            return originalSubmitInvoice.call(this);
        };
        console.log('✓ Hooked into Payment.submit_invoice');
    }
}

hookSubmitInvoice();