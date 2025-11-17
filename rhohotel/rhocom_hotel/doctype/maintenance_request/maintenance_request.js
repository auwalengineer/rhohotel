// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Maintenance Request", {
// 	refresh(frm) {

// 	},
// });
// frappe.ui.form.on('Maintenance Request', {
//     refresh: function(frm) {
//         // Only show button if user has the approval role and request is not yet approved
//         if (!frm.doc.approved && frappe.user.has_role('Hotel Manager')) {
//             frm.add_custom_button(__('Approve Request'), function() {
//                 frappe.call({
//                     method: 'rhohotel.rhocom_hotel.doctype.maintenance_request.maintenance_request.approve_request',
//                     args: { name: frm.doc.name },
//                     callback: function() {
//                         frm.reload_doc();
//                         frappe.msgprint(__('Request approved successfully.'));
//                     }
//                 });
//             });
//         }
//     }
// });


frappe.ui.form.on('Maintenance Request', {
    refresh: function(frm) {
        if (!frm.doc.approved && frappe.user.has_role('Hotel Manager')) {
            frm.add_custom_button(__('Approve Request'), function() {
                frappe.call({
                    method: 'frappe.client.set_value',
                    args: {
                        doctype: 'Maintenance Request',
                        name: frm.doc.name,
                        fieldname: {
                            'approved': 1,
                            'approval_time': frappe.datetime.now_datetime()
                        }
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frm.reload_doc();
                            frappe.msgprint(__('Request approved successfully.'));
                        }
                    }
                });
            });
        }
    }
});
