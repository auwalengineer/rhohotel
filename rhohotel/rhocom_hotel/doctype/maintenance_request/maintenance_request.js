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
        if (!frm.doc.approved) {
            frm.add_custom_button(__('Approve Request'), function() {
                // Set the approved field
                frm.set_value('approved', 1);
                frm.set_value('approval_time', frappe.datetime.now_datetime());
                
                // Save the document - this will trigger on_update()
                frm.save().then(() => {
                    frappe.msgprint(__('Request approved successfully.'));
                });
            });
        }
    }
});











// frappe.ui.form.on('Maintenance Request', {
//     refresh: function(frm) {
//         if (frm.doc.name && frm.doc.status === 'Pending' && !frm.doc.approved) {
//             if (frappe.user.has_role(['System Manager', 'Hotel Manager'])) {
//                 frm.add_custom_button(__('Approve Request'), function() {
//                     frappe.confirm(
//                         __('Are you sure you want to approve this maintenance request?'),
//                         function() {
                         
                            
//                             frm.set_value('approved', 1);
//                             frm.set_value('approval_time', frappe.datetime.now_datetime());
                            
                           
                            
//                             frm.save().then(() => {                                
//                                 frappe.show_alert({
//                                     message: __('Request approved successfully'),
//                                     indicator: 'green'
//                                 });
                                
//                                 // Force reload
//                                 setTimeout(() => {
//                                     frm.reload_doc();
//                                 }, 500);
//                             }).catch((error) => {
//                                 console.error('Save promise rejected:', error);
//                                 frappe.msgprint({
//                                     title: __('Error'),
//                                     message: error.message || __('Failed to approve request'),
//                                     indicator: 'red'
//                                 });
//                             });
//                         }
//                     );
//                 }, __('Actions'));
//             }
//         }
//     }
// });