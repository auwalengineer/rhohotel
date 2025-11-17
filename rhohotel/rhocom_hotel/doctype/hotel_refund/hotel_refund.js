// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hotel Refund", {
	refresh(frm) {

	},
});

frappe.ui.form.on("Hotel Refund", {
	setup: function (frm) {
		// Limit check_in options to check-ins for the selected guest
		frm.set_query('check_in', function () {
			if (!frm.doc.guest) {
				return { filters: {} };
			}
			return {
				filters: {
					guest: frm.doc.guest
				}
			};
		});

		// Limit sales_invoice options to invoices linked to the selected check-in
		frm.set_query('sales_invoice', function () {
			if (!frm.doc.check_in) {
				// no check-in selected yet, don't restrict by check-in
				return { filters: {} };
			}
			return {
				filters: {
					custom_hotel_room_check_in: frm.doc.check_in
				}
			};
		});
	}
});
