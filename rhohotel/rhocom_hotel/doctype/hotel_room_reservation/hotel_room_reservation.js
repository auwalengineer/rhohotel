// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hotel Room Reservation', {
	refresh: function (frm) {

		// add Check In button if status is Booked
		if (!frm.is_new() && frm.doc.docstatus === 1) {

			frm.add_custom_button(__('Check In Guest'), () => {

				let nights = frappe.datetime.get_diff(frm.doc.to_date, frm.doc.from_date);

				frappe.route_options = {
					reservation: frm.doc.name,
					//guest: frm.doc.guest_name,
					//room_number: frm.doc.room_number,
					//rate_amount: frm.doc.rate,
					//discount: frm.doc.discount,
					//number_of_nights: nights,
					//check_in_datetime: frm.doc.from_date,
					//expected_check_out_datetime: frm.doc.to_date
				};

				frappe.set_route('Form', 'Hotel Room Check In', 'new-hotel-room-check-in');
			});
		}
		// add create invoice button if sales invoice is not created
		if (!frm.doc.sales_invoice && frm.doc.docstatus == 1) {
			frm.add_custom_button(__('Create Invoice'), function () {
				frm.trigger("make_invoice");
			});
		}

		if (frm.doc.docstatus === 1 && !frm.doc.actual_check_out_datetime) {
			frm.add_custom_button(__('Adjust Reservation'), () => {
				// Fetch default checkout time from hotel settings
				frappe.call({
					method: "rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time",
					callback: function (res) {
						const default_checkout_time = res.message || "11:00:00";
						const today_date = frappe.datetime.get_today();
						const default_dt_str = today_date + " " + default_checkout_time;
						const default_dt = frappe.datetime.str_to_obj(default_dt_str);
						const now_dt = frappe.datetime.str_to_obj(frappe.datetime.now_datetime());

						let d = new frappe.ui.Dialog({
							title: __('Adjust Reservation'),
							fields: [
								{
									label: __('From Date'),
									fieldname: 'from_date',
									fieldtype: 'Datetime',
									default: frm.doc.from_date
								},
								{
									label: __('To Date'),
									fieldname: 'to_date',
									fieldtype: 'Datetime',
									default: frm.doc.to_date,
									read_only: 1
								},
								{
									fieldtype: 'Column Break'
								},
								{
									label: __('Current Nights'),
									fieldname: 'current_nights',
									fieldtype: 'Int',
									default: frm.doc.number_of_nights || 1,
									read_only: 1
								},
								{
									label: __('Room Rate'),
									fieldname: 'rate',
									fieldtype: 'Currency',
									default: frm.doc.rate || 0,
									read_only: 1
								},
								{
									fieldtype: 'Section Break'
								},
								{
									label: __('New Expected Check-out'),
									fieldname: 'new_checkout',
									fieldtype: 'Datetime',
									reqd: 1,
									description: __("Select new check-out date. Time defaults to {0}.", [default_checkout_time]),
									onchange: function () {
										let new_dt_str = d.get_value('new_checkout');
										if (!new_dt_str) return;

										// Auto-set time to default checkout time
										const selected_date = new_dt_str.split(" ")[0];
										const new_datetime_with_default_time = selected_date + " " + default_checkout_time;

										// Update the field with default time
										if (new_dt_str !== new_datetime_with_default_time) {
											d.set_value('new_checkout', new_datetime_with_default_time);
											return; // onchange will trigger again with correct value
										}

										let current_checkout = frm.doc.to_date;
										let current_dt = frappe.datetime.str_to_obj(current_checkout);
										let selected_dt = frappe.datetime.str_to_obj(new_datetime_with_default_time);
										let checkin_dt = frappe.datetime.str_to_obj(frm.doc.from_date);

										// Determine adjustment type
										let type = '';
										let type_color = '';
										if (selected_dt > current_dt) {
											type = 'Extension';
											type_color = 'blue';
										} else if (selected_dt < current_dt) {
											type = 'Reduction';
											type_color = 'orange';
										} else {
											type = 'No Change';
											type_color = 'grey';
										}

										d.set_value('adjustment_type', type);
										d.fields_dict.adjustment_type.$wrapper.find('.control-value').css('color', type_color);

										// Calculate difference in nights
										let diff_days = frappe.datetime.get_day_diff(
											new_datetime_with_default_time,
											frm.doc.from_date
										);
										if (diff_days < 1) diff_days = 1;
										d.set_value('new_nights', diff_days);

										// Calculate night difference
										let current_nights = frm.doc.number_of_nights || 1;
										let nights_diff = diff_days - current_nights;
										d.set_value('nights_difference', nights_diff);

										// Calculate amount
										let room_rate = frm.doc.rate || 0;
										let amount_change = nights_diff * room_rate;
										d.set_value('amount_change', amount_change);

										// Show total new amount
										let new_total = diff_days * room_rate;
										d.set_value('new_total_amount', new_total);
									}
								},
								{
									fieldtype: 'Column Break'
								},
								{
									label: __('Adjustment Type'),
									fieldname: 'adjustment_type',
									fieldtype: 'Data',
									read_only: 1
								},
								{
									label: __('New Number of Nights'),
									fieldname: 'new_nights',
									fieldtype: 'Int',
									read_only: 1
								},
								{
									label: __('Nights Difference'),
									fieldname: 'nights_difference',
									fieldtype: 'Int',
									read_only: 1
								},
								{
									fieldtype: 'Section Break',
									label: __('Financial Impact')
								},
								{
									label: __('Amount Change'),
									fieldname: 'amount_change',
									fieldtype: 'Currency',
									read_only: 1,
									description: __('Positive = Additional charge, Negative = Refund/Credit')
								},
								{
									fieldtype: 'Column Break'
								},
								{
									label: __('New Total Amount'),
									fieldname: 'new_total_amount',
									fieldtype: 'Currency',
									read_only: 1
								},
								{
									fieldtype: 'Section Break',
									label: __('Discount')
								},
								{
									label: __('Current Discount'),
									fieldname: 'current_discount',
									fieldtype: 'Currency',
									default: frm.doc.discount || 0,
									read_only: 1
								},
								{
									fieldtype: 'Column Break'
								},
								{
									label: __('New Discount'),
									fieldname: 'new_discount',
									fieldtype: 'Currency',
									default: frm.doc.discount || 0,
									description: __('Adjust discount for the new stay duration.'),
									onchange: function () {
										let new_discount = d.get_value('new_discount') || 0;
										let new_nights = d.get_value('new_nights') || 1;
										let room_rate = frm.doc.rate_amount || 0;

										let new_total = (new_nights * room_rate) - new_discount;
										d.set_value('new_total_amount', new_total);
									}
								}
							],
							primary_action_label: __('Confirm Adjustment'),
							primary_action: (values) => {
								const new_checkout = values.new_checkout;
								if (!new_checkout) {
									frappe.msgprint({
										title: __("Invalid"),
										message: __("Please select new expected checkout."),
										indicator: "orange"
									});
									return;
								}

								// Convert to Date objects for validation
								const new_dt = frappe.datetime.str_to_obj(new_checkout);
								const current_dt = frappe.datetime.str_to_obj(frm.doc.to_date);
								const checkin_dt = frappe.datetime.str_to_obj(frm.doc.from_date);

								// Determine if this is extension or reduction
								const is_extension = new_dt > current_dt;
								const is_reduction = new_dt < current_dt;

								if (!is_extension && !is_reduction) {
									frappe.msgprint({
										title: __("No Change"),
										message: __("The new checkout time is the same as current. No adjustment needed."),
										indicator: "blue"
									});
									return;
								}

								// VALIDATION 1: Must be after check-in datetime
								if (new_dt <= checkin_dt) {
									frappe.msgprint({
										title: __("Invalid Date"),
										indicator: "red",
										message: __("New checkout must be after the check-in date/time: {0}",
											[frappe.datetime.global_format(checkin_dt)])
									});
									return;
								}

								// VALIDATION 2: Cannot be in the past
								if (new_dt < now_dt) {
									frappe.msgprint({
										title: __("Invalid Date"),
										indicator: "red",
										message: __("New checkout cannot be in the past. Current time is: {0}",
											[frappe.datetime.global_format(now_dt)])
									});
									return;
								}

								// VALIDATION 3: For REDUCTION only - special rules for "today"
								if (is_reduction) {
									const new_date_str = new_checkout.split(" ")[0];

									if (new_date_str === today_date) {
										// If current time has already passed default checkout -> NOT allowed
										if (now_dt > default_dt) {
											frappe.msgprint({
												title: __("Not Allowed"),
												indicator: "red",
												message: __("Reducing stay to today is not allowed because the hotel's default checkout time for today ({0}) has already passed.",
													[frappe.datetime.global_format(default_dt)])
											});
											return;
										}

										// If reducing to today, time must be on or before default checkout
										if (new_dt > default_dt) {
											frappe.msgprint({
												title: __("Invalid Time"),
												indicator: "red",
												message: __("For today, new checkout must be on or before the hotel's default checkout time: {0}",
													[frappe.datetime.global_format(default_dt)])
											});
											return;
										}
									}
								}

								// VALIDATION 4 (Optional): Minimum notice period for reductions
								// Uncomment if you want to enforce advance notice
								/*
								if (is_reduction) {
									const min_notice_hours = 1;
									const earliest_allowed = frappe.datetime.add_to_date(now_dt, {hours: min_notice_hours});
									if (new_dt < earliest_allowed) {
										frappe.msgprint({
											title: __("Insufficient Notice"),
											indicator: "red",
											message: __("Please provide at least {0} hour(s) notice for reductions. Earliest allowed checkout: {1}", 
													   [min_notice_hours, frappe.datetime.global_format(earliest_allowed)])
										});
										return;
									}
								}
								*/

								// All validations passed - proceed with adjustment
								frappe.call({
									method: 'rhohotel.rhocom_hotel.doctype.hotel_room_reservation.hotel_room_reservation.adjust_reservation',
									args: {
										reservation_name: frm.doc.name,
										new_checkout: values.new_checkout,
										new_check_in: values.from_date,
										new_discount: values.new_discount

									},
									freeze: true,
									freeze_message: __("Processing reservation adjustment..."),
									callback: (r) => {
										if (!r.exc) {
											const adjustment_type = r.message?.adjustment_type || values.adjustment_type;
											frappe.show_alert({
												message: __('Reservation {0} completed successfully!', [adjustment_type]),
												indicator: 'green'
											}, 5);
											frm.reload_doc();
											d.hide();
										}
									},
									error: (r) => {
										frappe.msgprint({
											title: __("Error"),
											message: __("Failed to adjust reservation. Please try again or contact support."),
											indicator: "red"
										});
									}
								});
							}
						});

						d.show();
					},
					error: (r) => {
						frappe.msgprint({
							title: __("Error"),
							message: __("Failed to fetch hotel settings. Please try again."),
							indicator: "red"
						});
					}
				});
			});
		}


		// if (frm.doc.docstatus == 1) {


		// 	frm.add_custom_button(__('Extend Reservation'), () => {
		// 		frappe.prompt([
		// 			{
		// 				label: __('New To Date'),
		// 				fieldname: 'to_date',
		// 				fieldtype: 'Date',
		// 				reqd: 1
		// 			}
		// 		], function (values) {
		// 			frappe.call({
		// 				method: 'rhohotel.rhocom_hotel.doctype.hotel_room_reservation.hotel_room_reservation.extend_reservation',
		// 				args: {
		// 					reservation_id: frm.doc.name,
		// 					to_date: values.to_date
		// 				},
		// 				callback: function (r) {
		// 					frappe.set_route('Form', 'Hotel Room Reservation', r.message.name);
		// 				}
		// 			});
		// 		}, __('Extend Reservation'), __('Extend'));
		// 	});
		// }
	},

	guest_name: function (frm) {

	},

	to_date: function (frm) {

		// get number of nights 
		if (frm.doc.from_date && frm.doc.to_date) {
			calculate_nights(frm);
		}


		//frm.trigger("recalculate_rates");
	},
	number_of_nights: function (frm) {

		// make sure to_date is correct
		// if (frm.doc.from_date) {
		// 	actual_to_date = frm.doc.from_date + frm.doc.number_of_nights;

		// 	if (actual_to_date != frm.doc.to_date) {
		// 		frm.set_value("to_date", actual_to_date);
		// 	}
		// }

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

		if (frm.doc.from_date && frm.doc.to_date) {
			calculate_nights(frm);
		}

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
	},

	onload: function (frm) {
		set_default_nigeria_country(frm);
	}
});

function calculate_nights(frm) {
	const check_in = frm.doc.from_date;
	const check_out = frm.doc.to_date;

	if (check_in && check_out) {
		let nights = frappe.datetime.get_diff(check_out, check_in);

		// Prevent negative or zero nights
		if (nights < 1) {
			frm.set_value("number_of_nights", 0);
		} else {
			frm.set_value("number_of_nights", nights);
		}
	}
}

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


function set_default_nigeria_country(frm) {
	const field = frm.get_field('guest_phone');

	// Field not ready yet
	if (!field || !field.$input) return;

	// Do not override if user already entered a phone
	if (frm.doc.guest_phone) return;

	// intl-tel-input initializes after render, so delay a bit
	setTimeout(() => {
		const input = field.$input[0];

		// ERPNext attaches intl-tel-input instance here
		if (input && input.iti) {
			input.iti.setCountry('ng'); // Nigeria 🇳🇬
		}
	}, 300);
}


// frappe.ui.form.on("Hotel Room Reservation", {
//     onload: function(frm) {
//         set_filtered_room_query(frm);
//     },

//     refresh: function(frm) {
//         set_filtered_room_query(frm);
//     },

//     from_date: function(frm) {
//         set_filtered_room_query(frm);
//     },

//     to_date: function(frm) {
//         set_filtered_room_query(frm);
//     },

//     room_type: function(frm) {
//         set_filtered_room_query(frm);
//     }
// });


// function set_filtered_room_query(frm) {
//     // Must have dates before filtering
//     if (!frm.doc.from_date || !frm.doc.to_date) {
//         return;
//     }

//     frm.set_query("room_number", function() {

//         return {
//             query: "rhohotel.api.get_available_rooms",
//             filters: {
//                 from_date: frm.doc.from_date,
//                 to_date: frm.doc.to_date,
//                 room_type: frm.doc.room_type || ""
//             }
//         };
//     });
// }
