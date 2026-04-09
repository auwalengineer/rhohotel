frappe.ui.form.on('Hotel Front Desk Reservation', {
    refresh: function (frm) {

        if (frm.is_new && frm.doc.rooms && frm.doc.rooms.length === 1 && !frm.doc.rooms[0].room_number) {
            frm.doc.rooms = [];
            frm.refresh_field('rooms');
        }
        add_custom_buttons(frm);
        add_adjust_stay_button(frm);

        frm.set_query('filter_by_room_type', function () {
            return { filters: { 'is_active': 1 } };
        });

        // Filter corporate_guest to only show Corporate type guests
        frm.set_query('corporate_guest', function () {
            return { filters: { 'guest_type': 'Corporate' } };
        });

        // ═════════════════════════════════════════════════════════════════════════
        // ROOM NUMBER QUERY - UNPAGINATED, ALL AVAILABLE ROOMS
        // ═════════════════════════════════════════════════════════════════════════
        frm.set_query('room_number', 'rooms', function (doc, cdt, cdn) {
            // If dates are not selected, just return all rooms
            if (!doc.from_date || !doc.to_date) {
                frappe.show_alert({
                    message: __('Select check-in and check-out dates to see available rooms'),
                    indicator: 'orange'
                }, 3);
                return {};  // Allow all rooms to be shown
            }

            // Get already selected rooms to exclude them
            let selected_rooms = [];
            if (doc.rooms) {
                selected_rooms = doc.rooms
                    .map(row => row.room_number)
                    .filter(room => room && room !== '__none__');
            }

            // Use custom endpoint that returns ALL rooms (no pagination)
            return {
                query: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms_for_dropdown',
                filters: {
                    'from_date': doc.from_date,
                    'to_date': doc.to_date,
                    'room_type': doc.filter_by_room_type || null,
                    'exclude_rooms': selected_rooms
                }
            };
        });
    },

    from_date: function (frm) {
        calculate_nights(frm);
        refresh_available_rooms(frm);
    },

    to_date: function (frm) {
        calculate_nights(frm);
        refresh_available_rooms(frm);
    },

    filter_by_room_type: function (frm) {
        refresh_available_rooms(frm);
    },

    corporate_guest: function (frm) {
        if (frm.doc.corporate_guest) {
            fetch_corporate_details(frm);
        }
    },

    discount_type: function (frm) {
        calculate_total(frm);
    },

    discount: function (frm) {
        calculate_total(frm);
    }
});

frappe.ui.form.on('Front Desk Reservation Room', {
    room_number: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Only proceed if we have a room number and dates
        if (!row.room_number || !frm.doc.from_date || !frm.doc.to_date) {
            return;
        }

        // Set number_of_nights immediately
        if (!row.number_of_nights && frm.doc.number_of_nights) {
            frappe.model.set_value(cdt, cdn, 'number_of_nights', frm.doc.number_of_nights);
        }

        // Wait for fetch_from to populate room_type, then fetch rate
        setTimeout(() => {
            let current_row = locals[cdt][cdn];
            if (current_row && current_row.room_number && current_row.room_type) {
                fetch_rate_for_room(frm, cdt, cdn);
            }
        }, 500);
    },

    room_type: function (frm, cdt, cdn) {
        // When room_type is populated (by fetch_from), fetch the rate
        let row = locals[cdt][cdn];
        if (row.room_number && row.room_type && !row.rate_per_night) {
            fetch_rate_for_room(frm, cdt, cdn);
        }
    },

    rooms_remove: function (frm) {
        calculate_total(frm);
    }
});

function fetch_rate_for_room(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.room_type || !frm.doc.from_date) {
        return;
    }

    frappe.call({
        method: 'rhohotel.api.get_room_rate',
        args: {
            room_type: row.room_type,
            check_in_date: frm.doc.from_date
        },
        callback: function (r) {
            if (r.message) {
                let rate = r.message;
                let nights = frm.doc.number_of_nights || 1;

                frappe.model.set_value(cdt, cdn, 'rate_per_night', rate);
                frappe.model.set_value(cdt, cdn, 'number_of_nights', nights);
                frappe.model.set_value(cdt, cdn, 'room_total', rate * nights);

                // Recalculate totals
                setTimeout(() => calculate_total(frm), 100);
            }
        }
    });
}

// ═════════════════════════════════════════════════════════════════════════
// CUSTOM BUTTONS
// ═════════════════════════════════════════════════════════════════════════

function add_custom_buttons(frm) {
    if (frm.doc.docstatus === 0) {
        frm.add_custom_button(__('Add Available Rooms'), function () {
            show_available_rooms_dialog(frm);
        });
    }

    if (frm.doc.docstatus === 1) {
        // if (frm.doc.reservation_type === 'Corporate') {
        frm.add_custom_button(__('Check In All Guests'), function () {
            frappe.confirm(
                __('Check in all {0} rooms?', [frm.doc.total_rooms]),
                function () {
                    check_in_all_rooms_corporate(frm);
                }
            );
        }, __('Check In'));

        frm.add_custom_button(__('Check In Selected Rooms'), function () {
            show_corporate_checkin_dialog(frm);
        }, __('Check In'));

        // ✅ NEW: Check In Rooms (Bulk Invoice) button
        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__('Check In Rooms (Bulk Invoice)'), function () {
                show_bulk_invoice_checkin_dialog(frm);
            }, __('Check In')).addClass('btn-primary');
        }

        if (!frm.doc.sales_invoice) {
            frm.add_custom_button(__('Create Invoice'), function () {
                create_invoice_for_reservation(frm);
            }, __('Create'));
        }
        // }

        let missing_names = frm.doc.rooms.filter(r =>
            !r.guest_name || r.guest_name.startsWith('Guest - Room')
        );

        if (missing_names.length > 0) {
            frm.add_custom_button(__('Add Guest Names'), function () {
                show_guest_names_dialog(frm);
            }, __('Actions')).css({ 'background-color': '#ffc107', 'color': 'white' });
        }

        frm.add_custom_button(__('Edit Guest Details'), function () {
            show_edit_guest_details_dialog(frm);
        }, __('Actions'));

        if (frm.doc.reservation_type !== 'Corporate' && frm.doc.status === 'Confirmed') {
            frm.add_custom_button(__('Check In All Rooms'), function () {
                check_in_all_rooms(frm);
            }, __('Actions'));
        }

        if (frm.doc.status === 'Checked In') {
            frm.add_custom_button(__('View Check-Ins'), function () {
                frappe.route_options = { "front_desk_reservation": frm.doc.name };
                frappe.set_route("List", "Hotel Room Check In");
            }, __('View'));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__('View Bulk Invoice'), function () {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __('View'));
        }

        frm.add_custom_button(__('View Room Reservations'), function () {
            frappe.route_options = { "front_desk_reservation": frm.doc.name };
            frappe.set_route("List", "Hotel Room Reservation");
        }, __('View'));
    }
}


// ═════════════════════════════════════════════════════════════════════════
// BULK INVOICE CHECK-IN DIALOG (NEW)
// ═════════════════════════════════════════════════════════════════════════

function show_bulk_invoice_checkin_dialog(frm) {
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_rooms_in_bulk_invoice',
        args: { reservation_name: frm.doc.name },
        callback: function (r) {
            if (!r.message || !r.message.success) {
                frappe.msgprint({
                    title: __('Error'),
                    message: r.message ? r.message.message : __('Failed to fetch rooms'),
                    indicator: 'red'
                });
                return;
            }

            if (!r.message.has_bulk_invoice) {
                frappe.msgprint({
                    title: __('No Bulk Invoice'),
                    message: __('This reservation does not have a bulk invoice. Use "Check In Selected Rooms" instead.'),
                    indicator: 'orange'
                });
                return;
            }

            const data = r.message;

            let d = new frappe.ui.Dialog({
                title: __('Check In Rooms (Bulk Invoice)'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'info_html',
                        options: `<div class="alert alert-info">
                            <strong><i class="fa fa-info-circle"></i> Bulk Invoice Check-In</strong><br/>
                            These rooms are already included in the bulk invoice: <strong>${data.bulk_invoice}</strong><br/>
                            <span class="text-success">✓ No new invoice will be created when checking in.</span>
                            <hr style="margin: 8px 0;"/>
                            <small>
                                <strong>Total Rooms:</strong> ${data.total_rooms} | 
                                <strong>Checked In:</strong> ${data.rooms_checked_in} | 
                                <strong>Pending:</strong> ${data.rooms_pending}
                            </small>
                        </div>`
                    },
                    { fieldname: 'rooms_html', fieldtype: 'HTML' },
                    { fieldtype: 'Section Break', label: 'Check-In Notes' },
                    { fieldname: 'check_in_notes', fieldtype: 'Small Text', label: 'Notes (Optional)' }
                ],
                size: 'large',
                primary_action_label: __('Check In Selected'),
                primary_action: function (values) {
                    let selected = [];
                    d.$wrapper.find('input[type="checkbox"]:checked').each(function () {
                        let room_idx = $(this).data('room-idx');
                        if (room_idx !== undefined) selected.push(parseInt(room_idx));
                    });

                    if (selected.length === 0) {
                        frappe.msgprint(__('Please select at least one room'));
                        return;
                    }

                    check_in_rooms_bulk_invoice(frm, selected, values.check_in_notes || '');
                    d.hide();
                }
            });

            let html = `<table class="table table-bordered table-hover" style="margin: 15px 0;">
                <thead><tr style="background-color: #f5f5f5;">
                    <th width="8%"><input type="checkbox" id="select-all-bulk"></th>
                    <th width="15%">Room</th>
                    <th width="15%">Type</th>
                    <th width="25%">Guest Name</th>
                    <th width="17%">Rate/Night</th>
                    <th width="20%">Status</th>
                </tr></thead><tbody>`;

            data.rooms.forEach(function (room) {
                let status_badge = room.has_checkin
                    ? `<span class="badge badge-success"><i class="fa fa-check"></i> ${room.checkin_status || 'Checked In'}</span>`
                    : '<span class="badge badge-warning"><i class="fa fa-clock-o"></i> Pending</span>';

                let row_style = room.has_checkin ? 'style="opacity: 0.6; background-color: #f9f9f9;"' : '';
                let checkbox_html = room.has_checkin
                    ? `<input type="checkbox" disabled title="Already checked in">`
                    : `<input type="checkbox" data-room-idx="${room.idx - 1}">`;

                html += `<tr ${row_style}>
                    <td>${checkbox_html}</td>
                    <td><strong>${room.room_number}</strong></td>
                    <td>${room.room_type || '-'}</td>
                    <td>${room.guest_name || '<em class="text-muted">(No guest name)</em>'}</td>
                    <td>${format_currency(room.rate_per_night)}</td>
                    <td>${status_badge}</td>
                </tr>`;
            });

            html += '</tbody></table>';

            if (data.rooms_pending === 0) {
                html = `<div class="alert alert-success">
                    <i class="fa fa-check-circle"></i> All rooms in this bulk invoice have been checked in.
                </div>`;
            }

            d.fields_dict.rooms_html.$wrapper.html(html);

            d.$wrapper.find('#select-all-bulk').on('change', function () {
                d.$wrapper.find('input[type="checkbox"]:not(:disabled)').prop('checked', this.checked);
            });

            d.show();
        }
    });
}


function check_in_rooms_bulk_invoice(frm, room_indices, check_in_notes) {
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_rooms_in_bulk_invoice',
        args: {
            reservation_name: frm.doc.name,
            room_indices: room_indices,
            check_in_notes: check_in_notes
        },
        freeze: true,
        freeze_message: __('Checking in rooms...'),
        callback: function (r) {
            if (r.message && r.message.success) {
                frappe.show_alert({ message: r.message.message, indicator: 'green' }, 7);

                let msg = `<div style="padding: 10px;">
                    <strong style="color: #28a745;">✓ ${r.message.message}</strong>
                    <hr/>
                    <strong>Bulk Invoice:</strong> <a href="/app/sales-invoice/${r.message.bulk_invoice}">${r.message.bulk_invoice}</a><br/><br/>`;

                if (r.message.checked_in_rooms && r.message.checked_in_rooms.length > 0) {
                    msg += `<strong>Rooms Checked In:</strong><ul>`;
                    r.message.checked_in_rooms.forEach(function (room) {
                        msg += `<li>${room.room_number} - ${room.guest_name} 
                            (<a href="/app/hotel-room-check-in/${room.checkin_name}">${room.checkin_name}</a>)</li>`;
                    });
                    msg += `</ul>`;
                }

                if (r.message.skipped_rooms && r.message.skipped_rooms.length > 0) {
                    msg += `<strong style="color: #ffc107;">Skipped Rooms:</strong><ul>`;
                    r.message.skipped_rooms.forEach(function (room) {
                        msg += `<li>${room.room_number || 'Index ' + room.idx} - ${room.reason}</li>`;
                    });
                    msg += `</ul>`;
                }

                msg += `</div>`;

                frappe.msgprint({ title: __('Check-In Complete'), message: msg, indicator: 'green', wide: true });
                frm.reload_doc();
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: r.message ? r.message.message : __('Failed to check in rooms'),
                    indicator: 'red'
                });
            }
        }
    });
}


// ═════════════════════════════════════════════════════════════════════════
// ADJUST STAY BUTTON & DIALOG
// ═════════════════════════════════════════════════════════════════════════

function add_adjust_stay_button(frm) {
    if (frm.doc.docstatus === 1) {
        frm.add_custom_button(__('Adjust Stay'), function () {
            show_adjust_stay_dialog(frm);
        }, __('Actions')).addClass("btn-info");
    }
}


function show_adjust_stay_dialog(frm) {
    frappe.call({
        method: "rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_reservation_status_info",
        args: { reservation_name: frm.doc.name },
        callback: function (r) {
            if (r.message && !r.message.valid) {
                frappe.msgprint({ title: __("Cannot Adjust"), message: r.message.message, indicator: "red" });
                return;
            }

            const status_info = r.message;
            const is_checked_in = status_info.is_checked_in;
            const checked_in_count = status_info.checked_in_count;

            frappe.call({
                method: "rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time",
                callback: function (res) {
                    const default_checkout_time = res.message || "12:00:00";
                    const now_dt = frappe.datetime.str_to_obj(frappe.datetime.now_datetime());

                    let info_message = `<div class="alert alert-info"><strong>Adjust Stay Duration</strong><br/>`;
                    if (is_checked_in) {
                        info_message += `✓ <strong>${checked_in_count} room(s) currently checked in</strong><br/>
                        You can extend or reduce the checkout date.`;
                    } else {
                        info_message += `<strong>Pre-Check-In Reservation</strong><br/>
                        You can extend or reduce the stay before guests check in.`;
                    }
                    info_message += `</div>`;

                    let d = new frappe.ui.Dialog({
                        title: __('Adjust Stay Duration'),
                        fields: [
                            { fieldtype: 'HTML', fieldname: 'info_html', options: info_message },
                            { fieldtype: 'Section Break', label: __('Current Stay Information') },
                            { label: __('Check-In Date'), fieldname: 'current_checkin', fieldtype: 'Date', default: frm.doc.from_date, read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('Current Check-Out Date'), fieldname: 'current_checkout', fieldtype: 'Date', default: frm.doc.to_date, read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('Current Nights'), fieldname: 'current_nights', fieldtype: 'Int', default: frm.doc.number_of_nights || 1, read_only: 1 },
                            { fieldtype: 'Section Break', label: __('Rooms & Pricing') },
                            { label: __('Total Rooms'), fieldname: 'total_rooms', fieldtype: 'Int', default: frm.doc.total_rooms || 0, read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('Rooms Checked In'), fieldname: 'checked_in_rooms', fieldtype: 'Int', default: checked_in_count || 0, read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('Current Subtotal'), fieldname: 'current_subtotal', fieldtype: 'Currency', default: frm.doc.subtotal || 0, read_only: 1 },
                            { fieldtype: 'Section Break', label: __('New Stay Details') },
                            {
                                label: __('New Check-Out Date'), fieldname: 'new_checkout', fieldtype: 'Date', reqd: 1,
                                description: __("Select new check-out date. Can be earlier (reduction) or later (extension)."),
                                onchange: function () { update_adjustment_calculations(d, frm, default_checkout_time, is_checked_in); }
                            },
                            { fieldtype: 'Column Break' },
                            { label: __('Check-Out Time'), fieldname: 'new_checkout_time', fieldtype: 'Time', default: default_checkout_time },
                            { fieldtype: 'Section Break', label: __('Adjustment Analysis') },
                            { label: __('Adjustment Type'), fieldname: 'adjustment_type', fieldtype: 'Data', read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('New Number of Nights'), fieldname: 'new_nights', fieldtype: 'Int', read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('Night Difference'), fieldname: 'nights_difference', fieldtype: 'Int', read_only: 1 },
                            { fieldtype: 'Section Break', label: __('Financial Impact') },
                            { label: __('Amount Change'), fieldname: 'amount_change', fieldtype: 'Currency', read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('New Subtotal'), fieldname: 'new_subtotal', fieldtype: 'Currency', read_only: 1 },
                            { fieldtype: 'Column Break' },
                            { label: __('New Total Amount'), fieldname: 'new_total_amount', fieldtype: 'Currency', read_only: 1, bold: 1 },
                            { fieldtype: 'Section Break', label: __('Discount Adjustment (Optional)') },
                            { label: __('Current Discount'), fieldname: 'current_discount', fieldtype: 'Currency', default: frm.doc.discount_amount || 0, read_only: 1 },
                            { fieldtype: 'Column Break' },
                            {
                                label: __('New Discount'), fieldname: 'new_discount', fieldtype: 'Currency', default: frm.doc.discount_amount || 0,
                                onchange: function () { update_adjustment_calculations(d, frm, default_checkout_time, is_checked_in); }
                            }
                        ],
                        primary_action_label: __('Confirm Adjustment'),
                        primary_action: (values) => {
                            if (!values.new_checkout) {
                                frappe.msgprint({ title: __("Invalid"), message: __("Please select new checkout date."), indicator: "orange" });
                                return;
                            }

                            const new_checkout_time = values.new_checkout_time || default_checkout_time;
                            const new_dt = frappe.datetime.str_to_obj(values.new_checkout + " " + new_checkout_time);
                            const checkin_dt = frappe.datetime.str_to_obj(frm.doc.from_date + " 00:00:00");

                            if (new_dt <= checkin_dt) {
                                frappe.msgprint({
                                    title: __("Invalid Date"), indicator: "red",
                                    message: __("New checkout must be after check-in date: {0}", [frappe.datetime.global_date_format(frm.doc.from_date)])
                                });
                                return;
                            }

                            if (is_checked_in && new_dt < now_dt) {
                                frappe.msgprint({ title: __("Invalid Date"), indicator: "red", message: __("New checkout cannot be in the past.") });
                                return;
                            }

                            if (values.new_checkout === frm.doc.to_date) {
                                frappe.msgprint({ title: __("No Change"), message: __("New checkout date is the same as current."), indicator: "blue" });
                                return;
                            }

                            proceed_with_adjustment(frm, values, d, is_checked_in);
                        }
                    });

                    d.show();
                }
            });
        }
    });
}


function update_adjustment_calculations(d, frm, default_checkout_time, is_checked_in) {
    let new_checkout_str = d.get_value('new_checkout');
    if (!new_checkout_str) return;

    let current_dt = frappe.datetime.str_to_obj(frm.doc.to_date + " 12:00:00");
    let selected_dt = frappe.datetime.str_to_obj(new_checkout_str + " " + (d.get_value('new_checkout_time') || default_checkout_time));

    let type = selected_dt > current_dt ? 'Extension' : (selected_dt < current_dt ? 'Reduction' : 'No Change');
    let type_color = type === 'Extension' ? '#0056b3' : (type === 'Reduction' ? '#d9534f' : '#6c757d');

    d.set_value('adjustment_type', type);
    d.fields_dict.adjustment_type.$wrapper.find('.control-value').css('color', type_color);

    let diff_days = Math.max(1, frappe.datetime.get_day_diff(new_checkout_str, frm.doc.from_date));
    d.set_value('new_nights', diff_days);
    d.set_value('nights_difference', diff_days - (frm.doc.number_of_nights || 1));

    let new_subtotal = 0;
    frm.doc.rooms.forEach(room => { new_subtotal += (room.rate_per_night || 0) * diff_days; });

    d.set_value('new_subtotal', new_subtotal);
    d.set_value('amount_change', new_subtotal - (frm.doc.subtotal || 0));
    d.set_value('new_total_amount', new_subtotal - (d.get_value('new_discount') || 0));
}


function proceed_with_adjustment(frm, values, d, is_checked_in) {
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.adjust_front_desk_reservation',
        args: {
            reservation_name: frm.doc.name,
            new_checkout_date: values.new_checkout,
            new_checkout_time: values.new_checkout_time || "12:00:00",
            new_discount: values.new_discount || 0
        },
        freeze: true,
        freeze_message: __("Processing stay adjustment..."),
        callback: (r) => {
            if (r.message && r.message.success) {
                const result = r.message;
                frappe.show_alert({ message: __("Stay {0} completed successfully!", [result.adjustment_type]), indicator: 'green' }, 7);

                let msg = `<div style="padding: 10px;">
                    <strong style="font-size: 1.1em; color: #28a745;">✓ Stay ${result.adjustment_type} Completed</strong>
                    <table style="margin-top: 15px; width: 100%; border-collapse: collapse;">
                        <tr style="border-bottom: 1px solid #ddd;"><td style="padding: 8px; font-weight: bold;">Old Checkout:</td><td style="padding: 8px; text-align: right;">${result.old_checkout}</td></tr>
                        <tr style="border-bottom: 1px solid #ddd;"><td style="padding: 8px; font-weight: bold;">New Checkout:</td><td style="padding: 8px; text-align: right;">${result.new_checkout}</td></tr>
                        <tr style="border-bottom: 1px solid #ddd;"><td style="padding: 8px; font-weight: bold;">Nights:</td><td style="padding: 8px; text-align: right;">${result.old_nights} → ${result.new_nights} (${result.night_difference > 0 ? '+' : ''}${result.night_difference})</td></tr>
                        <tr style="border-bottom: 1px solid #ddd;"><td style="padding: 8px; font-weight: bold;">Amount Change:</td><td style="padding: 8px; text-align: right; color: ${result.amount_change > 0 ? '#0056b3' : '#d9534f'}; font-weight: bold;">${result.amount_change > 0 ? '+' : ''}${format_currency(Math.abs(result.amount_change))}</td></tr>
                    </table>`;

                if (result.additional_invoice) {
                    msg += `<div style="margin-top: 15px; padding: 10px; background-color: #fff3cd; border-radius: 4px;">
                        <strong>✓ Extension Invoice:</strong> <a href="/app/sales-invoice/${result.additional_invoice}">${result.additional_invoice}</a>
                    </div>`;
                }

                if (result.recreated_invoice) {
                    msg += `<div style="margin-top: 15px; padding: 10px; background-color: #d1ecf1; border-radius: 4px;">
                        <strong>✓ Recreated Invoice:</strong> <a href="/app/sales-invoice/${result.recreated_invoice}">${result.recreated_invoice}</a>
                    </div>`;
                }

                if (result.credit_note) {
                    msg += `<div style="margin-top: 15px; padding: 10px; background-color: #d4edda; border-radius: 4px;">
                        <strong>✓ Credit Note:</strong> <a href="/app/sales-invoice/${result.credit_note}">${result.credit_note}</a>
                    </div>`;
                }

                msg += `</div>`;

                frappe.msgprint({ title: __("Adjustment Successful"), message: msg, indicator: 'green', wide: true });
                d.hide();
                setTimeout(() => { frm.reload_doc(); }, 500);
            } else {
                frappe.msgprint({ title: __("Error"), message: r.message?.message || __("Failed to adjust stay."), indicator: "red" });
            }
        },
        error: (r) => {
            frappe.msgprint({ title: __("Error"), message: __("Failed to adjust stay. Please try again."), indicator: "red" });
        }
    });
}


// ═════════════════════════════════════════════════════════════════════════
// CORPORATE CHECK-IN DIALOG
// ═════════════════════════════════════════════════════════════════════════

// function show_corporate_checkin_dialog(frm) {
//     let d = new frappe.ui.Dialog({
//         title: __('Check In Selected Rooms'),
//         fields: [
//             { fieldtype: 'HTML', fieldname: 'info_html', options: `<div class="alert alert-info"><strong>Check In Rooms</strong><br>Select which rooms to check in. You can only check in rooms that don't already have check-ins.</div>` },
//             { fieldname: 'rooms_html', fieldtype: 'HTML', options: '<p class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading rooms...</p>' },
//             { fieldtype: 'Section Break', label: 'Check-In Notes' },
//             { fieldname: 'check_in_notes', fieldtype: 'Small Text', label: 'Notes (Optional)' }
//         ],
//         size: 'large',
//         primary_action_label: __('Check In Selected'),
//         primary_action: function (values) {
//             let selected = [];
//             d.$wrapper.find('input[type="checkbox"]:checked').each(function () {
//                 let room_idx = $(this).data('room-idx');
//                 selected.push(parseInt(room_idx));
//             });

//             if (selected.length === 0) {
//                 frappe.msgprint(__('Please select at least one room'));
//                 return;
//             }

//             check_in_selected_rooms_only(frm, selected, values.check_in_notes || '');
//             d.hide();
//         }
//     });

//     function fetch_and_render_rooms() {
//         frappe.call({
//             method: 'frappe.client.get',
//             args: { doctype: 'Hotel Front Desk Reservation', name: frm.doc.name },
//             callback: function (r) {
//                 if (!r.message) return;

//                 let fresh_doc = r.message;
//                 let room_numbers = fresh_doc.rooms.map(room => room.room_number);

//                 frappe.call({
//                     method: 'frappe.client.get_list',
//                     args: {
//                         doctype: 'Hotel Room Reservation',
//                         filters: { 'front_desk_reservation': frm.doc.name, 'room_number': ['in', room_numbers] },
//                         fields: ['name', 'room_number', 'status']
//                     },
//                     callback: function (r2) {
//                         let reservations_in_db = {};
//                         if (r2.message) r2.message.forEach(res => { reservations_in_db[res.room_number] = res.name; });

//                         frappe.call({
//                             method: 'frappe.client.get_list',
//                             args: {
//                                 doctype: 'Hotel Room Check In',
//                                 filters: { 'front_desk_reservation': frm.doc.name, 'room_number': ['in', room_numbers], 'status': ['in', ['Draft', 'Checked In']] },
//                                 fields: ['name', 'room_number', 'status', 'check_in_datetime']
//                             },
//                             callback: function (r3) {
//                                 let checkins_in_db = {};
//                                 if (r3.message) r3.message.forEach(checkin => { checkins_in_db[checkin.room_number] = { name: checkin.name, status: checkin.status }; });

//                                 let html = `<table class="table table-bordered table-hover" style="margin: 15px 0;">
//                                     <thead><tr>
//                                         <th width="8%"><input type="checkbox" id="select-all-checkin"></th>
//                                         <th width="18%">Room</th>
//                                         <th width="30%">Guest Name</th>
//                                         <th width="22%">Reservation</th>
//                                         <th width="22%">Check-In Status</th>
//                                     </tr></thead><tbody>`;

//                                 fresh_doc.rooms.forEach(function (room, idx) {
//                                     let has_reservation = reservations_in_db.hasOwnProperty(room.room_number);
//                                     let has_checkin = checkins_in_db.hasOwnProperty(room.room_number);

//                                     let reservation_badge = has_reservation ? '<span class="badge badge-success"><i class="fa fa-check"></i> Created</span>' : '<span class="badge badge-secondary">Not Created</span>';
//                                     let checkin_badge = has_checkin ? `<span class="badge badge-info"><i class="fa fa-check"></i> ${checkins_in_db[room.room_number].status}</span>` : '<span class="badge badge-warning">Not Checked In</span>';
//                                     let checkbox_html = has_checkin ? `<input type="checkbox" data-room-idx="${idx}" disabled title="Already checked in">` : `<input type="checkbox" data-room-idx="${idx}">`;

//                                     html += `<tr ${has_checkin ? 'style="opacity: 0.6;"' : ''}>
//                                         <td>${checkbox_html}</td>
//                                         <td><strong>${room.room_number}</strong></td>
//                                         <td>${room.guest_name || '<em>(No guest name)</em>'}</td>
//                                         <td>${reservation_badge}</td>
//                                         <td>${checkin_badge}</td>
//                                     </tr>`;
//                                 });

//                                 html += '</tbody></table>';
//                                 d.fields_dict.rooms_html.$wrapper.html(html);

//                                 d.$wrapper.find('#select-all-checkin').on('change', function () {
//                                     d.$wrapper.find('input[type="checkbox"]:not(:disabled)').prop('checked', this.checked);
//                                 });
//                             }
//                         });
//                     }
//                 });
//             }
//         });
//     }

//     let original_show = d.show.bind(d);
//     d.show = function () { fetch_and_render_rooms(); original_show(); };
//     d.show();
// }

function show_corporate_checkin_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Check In Selected Rooms'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'info_html',
                options: `<div class="alert alert-info"><strong>Check In Rooms</strong><br>Select rooms to check in and optionally apply a discount per room.</div>`
            },
            {
                fieldname: 'rooms_html',
                fieldtype: 'HTML',
                options: '<p class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading rooms...</p>'
            },
            { fieldtype: 'Section Break', label: 'Check-In Notes' },
            {
                fieldname: 'check_in_notes',
                fieldtype: 'Small Text',
                label: 'Notes (Optional)'
            }
        ],
        size: 'extra-large',
        primary_action_label: __('Check In Selected'),
        primary_action: function (values) {
            let selected = [];
            let errors = [];

            d.$wrapper.find('tr[data-room-idx]').each(function () {
                let $row = $(this);
                let $checkbox = $row.find('input[type="checkbox"]');

                if (!$checkbox.is(':checked') || $checkbox.is(':disabled')) return;

                let room_idx = parseInt($row.data('room-idx'));
                let discount_type = $row.find('.discount-type-select').val();
                let discount = parseFloat($row.find('.discount-input').val()) || 0;
                let room_number = $row.data('room-number');
                let room_total = parseFloat($row.data('room-total'));

                // Validate
                if (discount_type && !discount) {
                    errors.push(`${room_number}: Discount type selected but no value entered`);
                    return;
                }

                if (!discount_type && discount) {
                    errors.push(`${room_number}: Discount value entered but no type selected`);
                    return;
                }

                if (discount_type === 'Percentage' && discount > 100) {
                    errors.push(`${room_number}: Percentage cannot exceed 100%`);
                    return;
                }

                if (discount_type === 'Fixed Amount' && discount > room_total) {
                    errors.push(`${room_number}: Fixed discount (₦${discount.toLocaleString()}) cannot exceed room total (₦${room_total.toLocaleString()})`);
                    return;
                }

                if (discount < 0) {
                    errors.push(`${room_number}: Discount cannot be negative`);
                    return;
                }

                selected.push({
                    room_idx: room_idx,
                    discount_type: discount_type || '',
                    discount: discount || 0
                });
            });

            if (errors.length > 0) {
                frappe.msgprint({
                    title: __('Validation Errors'),
                    message: errors.join('<br>'),
                    indicator: 'red'
                });
                return;
            }

            if (selected.length === 0) {
                frappe.msgprint(__('Please select at least one room'));
                return;
            }

            check_in_selected_rooms_only(
                frm,
                selected,
                values.check_in_notes || ''
            );
            d.hide();
        }
    });

    function fetch_and_render_rooms() {
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Hotel Front Desk Reservation', name: frm.doc.name },
            callback: function (r) {
                if (!r.message) return;

                let fresh_doc = r.message;
                let room_numbers = fresh_doc.rooms.map(room => room.room_number);

                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Hotel Room Check In',
                        filters: {
                            'front_desk_reservation': frm.doc.name,
                            'room_number': ['in', room_numbers],
                            'status': ['in', ['Draft', 'Checked In']]
                        },
                        fields: ['name', 'room_number', 'status']
                    },
                    callback: function (r3) {
                        let checkins_in_db = {};
                        if (r3.message) {
                            r3.message.forEach(checkin => {
                                checkins_in_db[checkin.room_number] = {
                                    name: checkin.name,
                                    status: checkin.status
                                };
                            });
                        }

                        let pending_count = fresh_doc.rooms.filter(room =>
                            !checkins_in_db.hasOwnProperty(room.room_number)
                        ).length;

                        let html = `
                            <div class="alert alert-warning" style="margin-bottom: 10px;">
                                <strong>${pending_count}</strong> room(s) pending check-in out of 
                                <strong>${fresh_doc.rooms.length}</strong> total rooms.
                            </div>
                            <table class="table table-bordered" style="margin: 10px 0; font-size: 13px;">
                                <thead>
                                    <tr style="background-color: #f5f5f5;">
                                        <th width="5%">
                                            <input type="checkbox" id="select-all-checkin" title="Select all pending rooms">
                                        </th>
                                        <th width="12%">Room</th>
                                        <th width="15%">Type</th>
                                        <th width="20%">Guest Name</th>
                                        <th width="13%">Rate/Night</th>
                                        <th width="13%">Room Total</th>
                                        <th width="12%">Discount Type</th>
                                        <th width="10%">Discount</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                        fresh_doc.rooms.forEach(function (room, idx) {
                            let has_checkin = checkins_in_db.hasOwnProperty(room.room_number);
                            let row_style = has_checkin ? 'style="opacity: 0.5; background-color: #f9f9f9;"' : '';

                            let checkbox_html = has_checkin
                                ? `<input type="checkbox" disabled title="Already checked in">`
                                : `<input type="checkbox" data-room-idx="${idx}">`;

                            let status_badge = has_checkin
                                ? `<br><span class="badge badge-info" style="font-size:10px;">${checkins_in_db[room.room_number].status}</span>`
                                : '';
                            let room_invoice_info = (fresh_doc.sales_invoices || []).find(inv => inv.room_number === room.room_number);

                            //                         let discount_fields = has_checkin
                            //                             ? `<td>-</td><td>-</td>`
                            //                             : `
                            //                                 <td>
                            //                                     <select class="form-control form-control-sm discount-type-select" style="font-size:12px; padding: 2px 4px;">
                            //                                         <option value="">None</option>
                            //                                        <option value="Percentage">Percentage</option>
                            // <option value="Fixed Amount">Fixed</option>
                            //                                     </select>
                            //                                 </td>
                            //                                 <td>
                            //                                     <input 
                            //                                         type="number" 
                            //                                         class="form-control form-control-sm discount-input" 
                            //                                         placeholder="0"
                            //                                         min="0"
                            //                                         style="font-size:12px; padding: 2px 4px;"
                            //                                     >
                            //                                 </td>`;

                            let discount_fields = has_checkin
                                ? `
        <td>
            ${room_invoice_info && room_invoice_info.discount_amount > 0
                                    ? `<span class="badge badge-success">Applied</span>`
                                    : `<span class="text-muted">None</span>`}
        </td>
        <td>
            ${room_invoice_info && room_invoice_info.discount_amount > 0
                                    ? `<strong style="color: green;">- ${frappe.format(room_invoice_info.discount_amount, { fieldtype: 'Currency' })}</strong>`
                                    : `<span class="text-muted">-</span>`}
        </td>`
                                : `
        <td>
            <select class="form-control form-control-sm discount-type-select" style="font-size:12px; padding: 2px 4px;">
                <option value="">None</option>
                <option value="Percentage">Percentage</option>
                <option value="Fixed Amount">Fixed</option>
            </select>
        </td>
        <td>
            <input 
                type="number" 
                class="form-control form-control-sm discount-input" 
                placeholder="0"
                min="0"
                style="font-size:12px; padding: 2px 4px;"
            >
        </td>`;

                            html += `
                                <tr 
                                    ${row_style} 
                                    data-room-idx="${idx}" 
                                    data-room-number="${room.room_number}"
                                    data-room-total="${room.room_total || 0}"
                                >
                                    <td>${checkbox_html}</td>
                                    <td>
                                        <strong>${room.room_number}</strong>
                                        ${status_badge}
                                    </td>
                                    <td>${room.room_type || '-'}</td>
                                    <td>${room.guest_name || '<em class="text-muted">(No name)</em>'}</td>
                                    <td>${frappe.format(room.rate_per_night, { fieldtype: 'Currency' })}</td>
                                    <td>${frappe.format(room.room_total, { fieldtype: 'Currency' })}</td>
                                    ${discount_fields}
                                </tr>`;
                        });

                        html += `</tbody></table>`;

                        if (pending_count === 0) {
                            html = `<div class="alert alert-success">
                                <i class="fa fa-check-circle"></i> All rooms have already been checked in.
                            </div>`;
                        }

                        d.fields_dict.rooms_html.$wrapper.html(html);

                        // Select all checkbox
                        d.$wrapper.find('#select-all-checkin').on('change', function () {
                            d.$wrapper.find('input[type="checkbox"]:not(:disabled)').prop('checked', this.checked);
                        });
                    }
                });
            }
        });
    }

    let original_show = d.show.bind(d);
    d.show = function () {
        fetch_and_render_rooms();
        original_show();
    };
    d.show();
}


function check_in_selected_rooms_only(frm, selected_rooms, check_in_notes) {
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms',
        args: {
            reservation_name: frm.doc.name,
            room_indices: selected_rooms,   // now an array of {room_idx, discount_type, discount}
            check_in_notes: check_in_notes
        },
        freeze: true,
        freeze_message: __('Checking in rooms...'),
        callback: function (r) {
            if (r.message && r.message.success) {
                frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                frappe.msgprint({
                    title: __('Success'),
                    message: r.message.message,
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}


// function check_in_selected_rooms_only(frm, room_indices, check_in_notes) {
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms',
//         args: { reservation_name: frm.doc.name, room_indices: room_indices, check_in_notes: check_in_notes },
//         callback: function (r) {
//             if (r.message && r.message.success) {
//                 frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
//                 frappe.msgprint({ title: __('Success'), message: r.message.message, indicator: 'green' });
//                 frm.reload_doc();
//             }
//         }
//     });
// }




function check_in_all_rooms_corporate(frm) {
    frappe.prompt([{ fieldname: 'check_in_notes', fieldtype: 'Small Text', label: __('Check-In Notes (Optional)') }],
        function (values) {
            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_all_rooms',
                args: { reservation_name: frm.doc.name, check_in_notes: values.check_in_notes || '' },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                        frappe.msgprint({ title: __('Success'), message: r.message.message, indicator: 'green' });
                        frm.reload_doc();
                    }
                }
            });
        }, __('Check In All Rooms'), __('Check In'));
}


function check_in_all_rooms(frm) {
    frappe.prompt([{ fieldname: 'check_in_notes', fieldtype: 'Small Text', label: __('Check-In Notes (Optional)') }],
        function (values) {
            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_reservation',
                args: { reservation_name: frm.doc.name, check_in_notes: values.check_in_notes || '', create_reservations: false },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                        frappe.msgprint({ title: __('Success'), message: r.message.message, indicator: 'green' });
                        frm.reload_doc();
                    }
                }
            });
        }, __('Check In All Rooms'), __('Check In'));
}


function create_invoice_for_reservation(frm) {
    frappe.confirm(__('Create Sales Invoice for this reservation?'), function () {
        frappe.call({
            method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.create_sales_invoice_for_reservation',
            args: { reservation_name: frm.doc.name },
            callback: function (r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                    frappe.msgprint({ title: __('Success'), message: r.message.message, indicator: 'green' });
                    frm.reload_doc();
                }
            }
        });
    });
}


// ═════════════════════════════════════════════════════════════════════════
// GUEST NAME DIALOGS
// ═════════════════════════════════════════════════════════════════════════

function show_guest_names_dialog(frm) {
    let rooms_needing_names = frm.doc.rooms.filter(r => !r.guest_name || r.guest_name.startsWith('Guest - Room'));

    if (rooms_needing_names.length === 0) {
        frappe.msgprint(__('All rooms already have guest names assigned'));
        return;
    }

    let fields = [{ fieldtype: 'HTML', fieldname: 'instructions', options: `<div class="alert alert-info"><strong>Add Guest Names</strong><br>Please provide guest names for the following rooms.</div>` }];

    rooms_needing_names.forEach(function (room, idx) {
        fields.push({ fieldtype: 'Section Break', label: `Room ${room.room_number}` });
        fields.push({ fieldname: `guest_name_${idx}`, fieldtype: 'Data', label: 'Guest Name', reqd: 1 });
        fields.push({ fieldtype: 'Column Break' });
        fields.push({ fieldname: `guest_email_${idx}`, fieldtype: 'Data', label: 'Email (Optional)', options: 'Email' });
        fields.push({ fieldtype: 'Column Break' });
        fields.push({ fieldname: `guest_phone_${idx}`, fieldtype: 'Data', label: 'Phone (Optional)' });
    });

    let d = new frappe.ui.Dialog({
        title: __('Add Guest Names'),
        fields: fields,
        size: 'large',
        primary_action_label: __('Update Guest Names'),
        primary_action: function (values) {
            let updates = [];
            rooms_needing_names.forEach(function (room, idx) {
                let guest_name = values[`guest_name_${idx}`];
                if (guest_name) {
                    updates.push({
                        room_idx: frm.doc.rooms.indexOf(room),
                        guest_name: guest_name,
                        guest_email: values[`guest_email_${idx}`] || '',
                        guest_phone: values[`guest_phone_${idx}`] || ''
                    });
                }
            });

            if (updates.length === 0) {
                frappe.msgprint(__('No updates to save'));
                return;
            }

            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.update_guest_names',
                args: { reservation_name: frm.doc.name, guest_updates: updates },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                        d.hide();
                        frm.reload_doc();
                    }
                }
            });
        }
    });

    d.show();
}


function show_edit_guest_details_dialog(frm) {
    let rooms_with_guests = frm.doc.rooms.map((room, idx) => ({
        index: idx, room_number: room.room_number, guest_name: room.guest_name, guest_email: room.guest_email, guest_phone: room.guest_phone
    }));

    if (rooms_with_guests.length === 0) {
        frappe.msgprint(__('No rooms added to this reservation'));
        return;
    }

    let d = new frappe.ui.Dialog({
        title: __('Edit Guest Details'),
        fields: [
            { fieldtype: 'HTML', fieldname: 'instructions', options: `<div class="alert alert-info"><strong>Edit Guest Details</strong><br>Click on any room below to edit guest information.</div>` },
            { fieldname: 'rooms_html', fieldtype: 'HTML' }
        ],
        size: 'large',
        primary_action_label: __('Close'),
        primary_action: function () { d.hide(); frm.reload_doc(); }
    });

    let html = `<table class="table table-bordered table-hover" style="margin: 15px 0;">
        <thead><tr><th width="20%">Room</th><th width="30%">Guest Name</th><th width="25%">Email</th><th width="15%">Phone</th><th width="10%">Action</th></tr></thead><tbody>`;

    rooms_with_guests.forEach(function (room) {
        html += `<tr><td><strong>${room.room_number}</strong></td><td>${room.guest_name || '(Not set)'}</td><td>${room.guest_email || '(Not set)'}</td><td>${room.guest_phone || '(Not set)'}</td>
            <td><button class="btn btn-sm btn-primary edit-guest-btn" data-room-idx="${room.index}"><i class="fa fa-edit"></i> Edit</button></td></tr>`;
    });

    html += '</tbody></table>';
    d.fields_dict.rooms_html.$wrapper.html(html);

    d.$wrapper.find('.edit-guest-btn').on('click', function () {
        show_single_guest_edit_dialog(frm, $(this).data('room-idx'), d);
    });

    d.show();
}

function show_single_guest_edit_dialog(frm, room_idx, parent_dialog) {
    let room = frm.doc.rooms[room_idx];

    let d = new frappe.ui.Dialog({
        title: __('Edit Guest Details - Room {0}', [room.room_number]),
        fields: [
            { fieldname: 'guest_name', fieldtype: 'Data', label: 'Guest Name', reqd: 1, default: room.guest_name },
            { fieldtype: 'Column Break' },
            { fieldname: 'guest_email', fieldtype: 'Data', label: 'Email (Optional)', options: 'Email', default: room.guest_email },
            { fieldtype: 'Column Break' },
            { fieldname: 'guest_phone', fieldtype: 'Data', label: 'Phone', reqd: 1, default: room.guest_phone },
            { fieldtype: 'Section Break', label: 'Info' },
            {
                fieldtype: 'HTML', fieldname: 'info_html',
                options: `
                    <div class="alert alert-info" style="margin-bottom: 8px;">
                        <small>
                            <strong>Note:</strong> If <strong>Email</strong> or <strong>Phone</strong> are left empty, the primary guest email/phone will be used.
                        </small>
                    </div>
                    <div class="alert alert-info" style="margin-bottom: 0;">
                        <small>
                            <strong>Note:</strong> Change the <strong>Email</strong> and <strong>Phone number</strong> here to ensure guest details appear correctly in both the reservation and the check-in at the front desk.
                        </small>
                    </div>
                `
            }
        ],
        size: 'large',
        primary_action_label: __('Save Changes'),
        primary_action: function (values) {
            if (!values.guest_name) {
                frappe.msgprint(__('Guest Name is required'));
                return;
            }

            let name_changed = values.guest_name !== (room.guest_name || '');
            let phone_changed = values.guest_phone !== (room.guest_phone || '');

            if (!name_changed || !phone_changed) {
                frappe.msgprint({
                    title: __('No Changes'),
                    message: __('Please update both Guest Name and Phone Number to save.'),
                    indicator: 'orange'
                });
                return;
            }

            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.edit_guest_details',
                args: {
                    reservation_name: frm.doc.name,
                    room_idx: room_idx,
                    guest_name: values.guest_name,
                    guest_email: values.guest_email || frm.doc.primary_guest_email || '',
                    guest_phone: values.guest_phone || frm.doc.primary_guest_phone || '',
                    room_number: room.room_number
                },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                        d.hide();

                        // Reload the form data
                        frm.reload_doc().then(() => {
                            // Close and reopen the parent dialog with fresh data
                            parent_dialog.hide();
                            show_edit_guest_details_dialog(frm);
                        });
                    }
                }
            });
        }
    });

    d.show();
}


function calculate_nights(frm) {
    if (frm.doc.from_date && frm.doc.to_date) {
        let nights = frappe.datetime.get_day_diff(frappe.datetime.str_to_obj(frm.doc.to_date), frappe.datetime.str_to_obj(frm.doc.from_date));
        if (nights > 0) {
            frm.set_value('number_of_nights', nights);
            frm.doc.rooms.forEach(function (row) {
                frappe.model.set_value(row.doctype, row.name, 'number_of_nights', nights);
                if (row.rate_per_night) frappe.model.set_value(row.doctype, row.name, 'room_total', row.rate_per_night * nights);
            });
            frm.refresh_field('rooms');
            calculate_total(frm);
        }
    }
}


function calculate_total(frm) {
    let subtotal = 0;
    if (frm.doc.rooms) frm.doc.rooms.forEach(function (row) { if (row.room_total) subtotal += row.room_total; });

    frm.set_value('subtotal', subtotal);
    frm.set_value('total_rooms', frm.doc.rooms ? frm.doc.rooms.length : 0);

    let discount_amount = 0;
    if (frm.doc.discount_type && frm.doc.discount) {
        discount_amount = frm.doc.discount_type === 'Percentage' ? (subtotal * frm.doc.discount) / 100 : frm.doc.discount;
    }

    frm.set_value('discount_amount', discount_amount);
    frm.set_value('total_amount', subtotal - discount_amount);
}


function fetch_corporate_details(frm) {
    frappe.call({
        method: 'frappe.client.get',
        args: { doctype: 'Hotel Guest', name: frm.doc.corporate_guest },
        callback: function (r) {
            if (r.message) {
                let guest = r.message;
                frm.set_value('customer', guest.customer);
                frm.set_value('primary_guest_name', guest.hotel_guest_name);
                frm.set_value('primary_guest_email', guest.email || '');
                frm.set_value('primary_guest_phone', guest.phone_number || '');
                frm.refresh_fields(['primary_guest_name', 'primary_guest_email', 'primary_guest_phone']);

                frm.set_value('primary_guest_phone', guest.phone_number || '').then(function () {
                    console.log('Phone set. Current form value:', frm.doc.primary_guest_phone);
                });
            }
        }
    });
}


function refresh_available_rooms(frm) {
    if (frm.doc.from_date && frm.doc.to_date) {
        // Refresh the child table query
        if (frm.fields_dict.rooms && frm.fields_dict.rooms.grid) {
            frm.fields_dict.rooms.grid.refresh();
        }

        frappe.show_alert({
            message: __('Dates updated. Room dropdown now shows available rooms for selected dates'),
            indicator: 'blue'
        }, 3);
    }
}


function show_available_rooms_dialog(frm) {
    if (!frm.doc.from_date || !frm.doc.to_date) {
        frappe.msgprint(__('Please select check-in and check-out dates first'));
        return;
    }

    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms',
        args: { from_date: frm.doc.from_date, to_date: frm.doc.to_date, room_type: frm.doc.filter_by_room_type || null },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                show_room_selection_dialog(frm, r.message);
            } else {
                frappe.msgprint(__('No rooms available for selected dates'));
            }
        }
    });
}


function show_room_selection_dialog(frm, available_rooms) {
    let d = new frappe.ui.Dialog({
        title: __('Select Rooms to Add'),
        fields: [{ fieldname: 'rooms_html', fieldtype: 'HTML' }],
        primary_action_label: __('Add Selected'),
        primary_action: function () {
            let selected = [];
            d.$wrapper.find('input[type="checkbox"]:checked').each(function () {
                let room_data = available_rooms.find(r => r.name === $(this).data('room'));
                if (room_data) selected.push(room_data);
            });

            if (selected.length === 0) {
                frappe.msgprint(__('Please select at least one room'));
                return;
            }

            selected.forEach(function (room) {
                let row = frm.add_child('rooms');
                row.room_number = room.name;
                row.room_type = room.room_type;
                row.rate_per_night = room.rate_per_night;
                row.number_of_nights = frm.doc.number_of_nights;
                row.room_total = room.total_amount;
            });

            frm.refresh_field('rooms');
            calculate_total(frm);
            d.hide();
            frappe.show_alert({ message: __('Added {0} room(s)', [selected.length]), indicator: 'green' });
        }
    });

    let html = `<table class="table table-bordered table-hover" style="margin-top: 10px;">
        <thead><tr><th width="10%"><input type="checkbox" id="select-all-rooms"></th><th width="20%">Room</th><th width="25%">Type</th><th width="15%">Floor</th><th width="15%">Capacity</th><th width="15%">Rate/Night</th></tr></thead><tbody>`;

    available_rooms.forEach(function (room) {
        html += `<tr><td><input type="checkbox" data-room="${room.name}"></td><td><strong>${room.name}</strong></td><td>${room.room_type}</td><td>${room.floor || 'N/A'}</td><td>${room.capacity}</td><td>${format_currency(room.rate_per_night)}</td></tr>`;
    });

    html += '</tbody></table>';
    d.fields_dict.rooms_html.$wrapper.html(html);

    d.$wrapper.find('#select-all-rooms').on('change', function () {
        d.$wrapper.find('input[type="checkbox"]').not(this).prop('checked', this.checked);
    });

    d.show();
}


function format_currency(value) {
    if (value === undefined || value === null) return '₦0.00';
    return frappe.format(value, { fieldtype: 'Currency' });
}
