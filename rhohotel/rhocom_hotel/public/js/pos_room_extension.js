
function setupRoomExtension() {
    if (!window.erpnext || !window.erpnext.PointOfSale || !window.erpnext.PointOfSale.ItemCart) {
        setTimeout(setupRoomExtension, 100);
        return;
    }

    // Hook into the actual ItemCart initialization
    const originalItemCartInit = erpnext.PointOfSale.ItemCart.prototype.init_component;

    erpnext.PointOfSale.ItemCart.prototype.init_component = function () {
        // Call original init
        originalItemCartInit.call(this);

        // Override make_customer_selector
        const originalMakeCustomerSelector = this.make_customer_selector;

        this.make_customer_selector = function () {
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

        this.make_room_selector = function () {
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
                                status: ["in", ["Occupied", "Reserved"]],
                            },
                        };
                    },
                    onchange: function () {
                        if (this.value) {
                            me.set_customer_from_room(this.value);
                        }
                    },
                },
                parent: this.$customer_section.find(".room-field-wrapper"),
                render_input: true,
            });

            this.room_field.toggle_label(false);
        };

        this.set_customer_from_room = function (room_name) {
            const me = this;

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
                        frappe.msgprint(__('No guest in this room'));
                        return;
                    }

                    frappe.call({
                        method: 'frappe.client.get',
                        args: {
                            doctype: 'Hotel Guest',
                            name: room.current_guest,
                        },
                        callback: function (r2) {
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