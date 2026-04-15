frappe.ready(() => {
    // Wait until POS is loaded
    if (!frappe.pages['point-of-sale']) return;

    frappe.pages['point-of-sale'].on_page_load = function (wrapper) {
        // Keep reference to the original class
        const OriginalPOS = frappe.views.PointOfSale;

        // Extend it
        frappe.views.PointOfSale = class extends OriginalPOS {
            make_dom() {
                super.make_dom();

                // Inject room selector into header section
                const roomSelector = $(`
                    <div class="pos-room-selector" style="margin: 10px 0;">
                        <label style="font-weight: 600;">Room:</label>
                        <input type="text" id="pos-room" class="form-control" placeholder="Select Room...">
                    </div>
                `);

                // Add it before customer field or after depending on layout
                $(this.wrapper).find('.customer-field').before(roomSelector);

                // Initialize frappe link field
                frappe.ui.form.make_control({
                    df: {
                        fieldtype: 'Link',
                        options: 'Hotel Room',
                        fieldname: 'hotel_room',
                        placeholder: 'Select Room',
                        onchange: () => {
                            const room = $('#pos-room').val();
                            if (!room) return;

                            // Fetch active check-in for selected room
                            frappe.call({
                                method: 'rhohotel.api.get_active_checkin_by_room',
                                args: { room },
                                callback: function (r) {
                                    if (r.message) {
                                        frappe.dom.freeze(); // show loading
                                        // Update current POS invoice in memory
                                        cur_pos.frm.doc.room = room;
                                        cur_pos.frm.doc.hotel_check_in = r.message.name;
                                        cur_pos.frm.doc.customer = r.message.guest_customer;
                                        frappe.show_alert(`Linked to check-in: ${r.message.name}`);
                                        frappe.dom.unfreeze();
                                    } else {
                                        frappe.show_alert({ message: 'No active check-in found', indicator: 'orange' });
                                    }
                                }
                            });
                        }
                    },
                    parent: roomSelector,
                    render_input: true
                });
            }
        };
    };
});