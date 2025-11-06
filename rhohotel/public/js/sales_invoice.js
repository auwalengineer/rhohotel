frappe.ui.form.on('Sales Invoice', {
	refresh: function(frm) {
		if (frm.doc.status === 'Unpaid' || frm.doc.status === 'Partially Paid') {
			frm.add_custom_button(__('Pay with Moniepoint'), function() {
				frappe.call({
					method: 'rhohotel.api.initiate_payment',
					args: {
						invoice_names: [frm.doc.name]
					},
					callback: function(r) {
						if (r.message) {
							frappe.msgprint("Payment session created: " + r.message.name);
							let frm = frappe.get_doc("Payment Session", r.message.name);
							frappe.ui.form.get_req_handler("Payment Session", r.message.name).open_payment_dialog(frm);
						}
					}
				});
			});
		}
	}
});