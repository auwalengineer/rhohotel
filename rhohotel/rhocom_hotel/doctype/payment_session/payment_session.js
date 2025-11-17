// Copyright (c) 2025, rhoconnect and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Session', {
	refresh: function (frm) {
		if (frm.doc.status === 'Pending' && frm.doc.payment_url) {
			frm.add_custom_button(__('Verify Payment'), function () {
				frm.events.verify_payment(frm);
			});
		}
	},



	// verify_payment: function (frm) {
	// 	frm.call({
	// 		method: 'rhohotel.api.complete_payment',
	// 		args: {
	// 			payment_session: frm.doc.name
	// 		},
	// 		callback: function (r) {
	// 			if (r.success == true) {
	// 				frappe.msgprint(__('Payment Verified Successfully'));
	// 				frm.reload_doc();
	// 			} else {
	// 				frappe.msgprint(__('Payment Verification Failed'));
	// 			}
	// 		}

	// 	});
	// }
});