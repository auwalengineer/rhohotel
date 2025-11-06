
// Copyright (c) 2025, rhoconnect and contributors
// For license information, please see license.txt

frappe.provide("rhohotel.payment");

rhohotel.payment.open_payment_dialog = function (payment_session_name) {
	let d = new frappe.ui.Dialog({
		title: __('Waiting for Payment'),
		fields: [
			{
				fieldname: 'status',
				fieldtype: 'HTML'
			}
		],
		primary_action_label: __('Complete Payment'),
		primary_action: function () {
			frappe.call({
				method: 'rhohotel.api.complete_payment',
				args: {
					payment_session: payment_session_name
				},
				callback: function (r) {
					if (r.message) {
						frappe.msgprint("Payment completed successfully.");
						d.hide();
						frappe.get_doc("Payment Session", payment_session_name).then(doc => {
							frappe.set_route("Form", "Payment Entry", doc.payment_entry);
						});
					}
				}
			});
		}
	});

	let poll_interval = setInterval(function () {
		frappe.call({
			method: 'rhohotel.api.get_payment_session_status',
			args: {
				payment_session: payment_session_name
			},
			callback: function (r) {
				if (r.message) {
					d.get_field('status').$wrapper.html('Payment Status: ' + r.message.status);
					if (r.message.status === 'Paid') {
						clearInterval(poll_interval);
					}
				}
			}
		});
	}, 10000);

	d.show();
}
