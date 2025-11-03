frappe.ui.form.on('Hotel Room Check Out', {
    refresh: function (frm) {
        // Show submit button only in Draft status
        if (frm.doc.status === "Draft") {
            frm.page.set_primary_action(__('Complete Check Out'), () => {
                frm.savesubmit();
            });
        }

        // Add print button after submission
        if (frm.doc.docstatus === 1) {
            frm.page.add_menu_item(__('Print Invoice'), () => {
                frappe.show_alert(__('Print functionality to be implemented'));
            });
        }
    },

    check_in: function (frm) {
        if (frm.doc.check_in) {
            frappe.db.get_doc('Hotel Room Check In', frm.doc.check_in)
                .then(doc => {
                    frm.set_value('guest_name', doc.guest_name);
                    frm.set_value('room_number', doc.room_number);
                });
        }
    },

    validate: function (frm) {
        if (frm.doc.check_out_datetime) {
            let checkOutDate = frappe.datetime.str_to_obj(frm.doc.check_out_datetime);
            let now = frappe.datetime.now_datetime();
            if (checkOutDate > now) {
                frappe.msgprint(__('Check-out time cannot be in the future'));
                frappe.validated = false;
            }
        }
    }
});