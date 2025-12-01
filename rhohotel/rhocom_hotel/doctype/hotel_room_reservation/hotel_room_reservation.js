// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hotel Room Reservation', {
	refresh: function (frm) {

		// add Check In button if status is Booked
		if (frm.doc.status == "Booked" && frm.doc.docstatus == 1) {
			frm.add_custom_button(__('Check In'), function () {
				frappe.call({
					method: 'rhohotel.rhocom_hotel.doctype.hotel_room_reservation.hotel_room_reservation.check_in_reservation',
					args: {
						reservation_id: frm.doc.name
					},
					callback: function (r) {
						frappe.set_route('Form', 'Hotel Room Reservation', r.message.name);
					}
				});
			});
		}

		// add create invoice button if sales invoice is not created
		if (!frm.doc.sales_invoice && frm.doc.docstatus == 1) {
			frm.add_custom_button(__('Create Invoice'), function () {
				frm.trigger("make_invoice");
			});
		}


		if (frm.doc.docstatus == 1) {


			frm.add_custom_button(__('Extend Reservation'), () => {
				frappe.prompt([
					{
						label: __('New To Date'),
						fieldname: 'to_date',
						fieldtype: 'Date',
						reqd: 1
					}
				], function (values) {
					frappe.call({
						method: 'rhohotel.rhocom_hotel.doctype.hotel_room_reservation.hotel_room_reservation.extend_reservation',
						args: {
							reservation_id: frm.doc.name,
							to_date: values.to_date
						},
						callback: function (r) {
							frappe.set_route('Form', 'Hotel Room Reservation', r.message.name);
						}
					});
				}, __('Extend Reservation'), __('Extend'));
			});
		}
	},

	to_date: function (frm) {
		//frm.trigger("recalculate_rates");
	},
	recalculate_rates: function (frm) {
		if (!frm.doc.from_date || !frm.doc.to_date
			|| !frm.doc.items.length) {
			return;
		}
		frappe.call({
			"method": "rhohotel.rhocom_hotel.doctype.hotel_room_reservation.hotel_room_reservation.get_room_rate",
			"args": { "hotel_room_reservation": frm.doc }
		}).done((r) => {
			for (var i = 0; i < r.message.items.length; i++) {
				frm.doc.items[i].rate = r.message.items[i].rate;
				frm.doc.items[i].amount = r.message.items[i].amount;
			}
			frappe.run_serially([
				() => frm.set_value("net_total", r.message.net_total),
				() => frm.refresh_field("items")
			]);
		});
	},
	make_invoice: function (frm) {
		frappe.call({
			method: "rhohotel.rhocom_hotel.doctype.hotel_room_reservation.hotel_room_reservation.make_invoice",
			args: {
				name: frm.doc.name
			},
			callback: function (r) {
				if (r.message) {
					frappe.msgprint({
						title: "Invoice Created",
						message: `Sales Invoice <b>${r.message}</b> created successfully.`,
						indicator: "green"
					});
					frm.reload_doc();
				}

				frm.reload_doc();
			}
		});
	},

	from_date: function (frm) {
		frm.trigger("recalculate_rates");
		// Step 1: Get room type from selected room
		frappe.db.get_value("Hotel Room", frm.doc.room_number, "room_type")
			.then(res => {
				if (!res.message || !res.message.room_type) return;

				let room_type = res.message.room_type;
				let check_in_date = frm.doc.from_date;

				if (!check_in_date) {
					frappe.msgprint("Please select Check-in Date first.");
					return;
				}

				// Step 2: Call backend to get rate
				frappe.call({
					method: "rhohotel.api.get_room_rate",
					args: {
						room_type: room_type,
						check_in_date: check_in_date
					},
					callback: function (r) {
						if (r.message) {
							frm.set_value("rate", r.message);
						}
					}
				});
			});
	}
});

frappe.ui.form.on('Hotel Room Reservation Item', {
	item: function (frm, doctype, name) {
		frm.trigger("recalculate_rates");
	},
	qty: function (frm) {
		frm.trigger("recalculate_rates");
	}
});

frappe.ui.form.on("Hotel Reservation Room", {
	room_number: function (frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);

		if (!row.room_number) {
			frm.refresh_field("rooms");
			return;
		}

		// Step 1: Get room type from selected room
		frappe.db.get_value("Hotel Room", row.room_number, "room_type")
			.then(res => {
				if (!res.message || !res.message.room_type) return;

				let room_type = res.message.room_type;
				let check_in_date = frm.doc.from_date;

				if (!check_in_date) {
					frappe.msgprint("Please select Check-in Date first.");
					return;
				}

				// Step 2: Call backend to get rate
				frappe.call({
					method: "rhohotel.api.get_room_rate",
					args: {
						room_type: room_type,
						check_in_date: check_in_date
					},
					callback: function (r) {
						if (r.message) {
							frappe.model.set_value(cdt, cdn, "rate", r.message);
						}
					}
				});
			});

		frm.refresh_field("rooms");
	}
});
