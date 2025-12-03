// Hotel Front Desk Reservation - Client Script v3 FINAL CORRECT
// ✅ FIXED: Shows all rooms with reservations, updates status in real-time
// ✅ ALLOWS: Check in multiple times, status updates immediately

frappe.ui.form.on('Hotel Front Desk Reservation', {
    refresh: function(frm) {
        add_custom_buttons(frm);
        
        frm.set_query('filter_by_room_type', function() {
            return {
                filters: {
                    'is_active': 1
                }
            };
        });
        
        frm.set_query('corporate_guest', function() {
            return {
                filters: {
                    'guest_type': 'Corporate'
                }
            };
        });
        
        // ✅ Filter room_number dropdown by available rooms based on dates
        frm.set_query('room_number', 'rooms', function(doc, cdt, cdn) {
            if (!doc.from_date || !doc.to_date) {
                frappe.msgprint(__('Please select check-in and check-out dates first'));
                return;
            }
            
            return {
                filters: [
                    ['Hotel Room', 'status', '=', 'Vacant'],
                    ['Hotel Room', 'operational_status', '=', 'In Service'],
                    ['Hotel Room', 'maintenance_flag', '=', 0]
                ],
                query: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms_for_dropdown',
                args: {
                    from_date: doc.from_date,
                    to_date: doc.to_date,
                    room_type: doc.filter_by_room_type || null
                }
            };
        });
    },
    
    from_date: function(frm) {
        calculate_nights(frm);
        refresh_available_rooms(frm);
    },
    
    to_date: function(frm) {
        calculate_nights(frm);
        refresh_available_rooms(frm);
    },
    
    filter_by_room_type: function(frm) {
        refresh_available_rooms(frm);
    },
    
    reservation_type: function(frm) {
        if (frm.doc.reservation_type !== 'Corporate') {
            frm.set_value('corporate_guest', '');
            frm.set_value('customer', '');
        }
    },
    
    corporate_guest: function(frm) {
        if (frm.doc.corporate_guest && frm.doc.reservation_type === 'Corporate') {
            fetch_corporate_details(frm);
        }
    },
    
    discount_type: function(frm) {
        calculate_total(frm);
    },
    
    discount: function(frm) {
        calculate_total(frm);
    }
});


frappe.ui.form.on('Front Desk Reservation Room', {
    room_number: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.room_number && frm.doc.from_date && frm.doc.to_date) {
            fetch_room_rate(frm, row);
        }
    },
    
    rooms_remove: function(frm) {
        calculate_total(frm);
    }
});


// ═════════════════════════════════════════════════════════════════════════
// CUSTOM BUTTONS
// ═════════════════════════════════════════════════════════════════════════

function add_custom_buttons(frm) {
    if (frm.doc.docstatus === 0) {
        // Draft state
        frm.add_custom_button(__('Add Available Rooms'), function() {
            show_available_rooms_dialog(frm);
        });
    }
    
    if (frm.doc.docstatus === 1) {
        // Submitted state
        
        // ✅ CORPORATE BUTTONS
        if (frm.doc.reservation_type === 'Corporate') {
            // Button 1: Check in ALL guests (automatically creates reservations)
            frm.add_custom_button(__('Check In All Guests'), function() {
                frappe.confirm(
                    __('Check in all {0} rooms? Reservations will be created automatically.', [frm.doc.total_rooms]),
                    function() {
                        check_in_all_rooms_corporate(frm);
                    }
                );
            }, __('Check In'));
            
            // Button 2: Check in SELECTED rooms (automatically creates reservations)
            frm.add_custom_button(__('Check In Selected Rooms'), function() {
                show_corporate_checkin_dialog(frm);
            }, __('Check In'));
            
            // Button 3: Create Invoice button for corporate bookings
            if (!frm.doc.sales_invoice) {
                frm.add_custom_button(__('Create Invoice'), function() {
                    create_invoice_for_reservation(frm);
                }, __('Create'));
            }
        }
        
        // Check if any rooms missing guest names
        let missing_names = frm.doc.rooms.filter(r => 
            !r.guest_name || r.guest_name.startsWith('Guest - Room')
        );
        
        if (missing_names.length > 0) {
            frm.add_custom_button(__('Add Guest Names'), function() {
                show_guest_names_dialog(frm);
            }, __('Actions')).css({'background-color': '#ffc107', 'color': 'white'});
        }
        
        // Non-corporate check-in
        if (frm.doc.reservation_type !== 'Corporate' && frm.doc.status === 'Confirmed') {
            frm.add_custom_button(__('Check In All Rooms'), function() {
                check_in_all_rooms(frm);
            }, __('Actions'));
        }
        
        if (frm.doc.status === 'Checked In') {
            frm.add_custom_button(__('View Check-Ins'), function() {
                frappe.route_options = {
                    "front_desk_reservation": frm.doc.name
                };
                frappe.set_route("List", "Hotel Room Check In");
            }, __('View'));
        }
        
        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__('View Invoice'), function() {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __('View'));
        }
        
        frm.add_custom_button(__('View Room Reservations'), function() {
            frappe.route_options = {
                "front_desk_reservation": frm.doc.name
            };
            frappe.set_route("List", "Hotel Room Reservation");
        }, __('View'));
    }
}


// ═════════════════════════════════════════════════════════════════════════
// CORPORATE CHECK-IN DIALOG (SELECTED ROOMS ONLY)
// ═════════════════════════════════════════════════════════════════════════

function show_corporate_checkin_dialog(frm) {
    /**
     * Dialog to check in SELECTED rooms only
     * ✅ Shows all rooms with reservations
     * ✅ Shows real-time status (Created ✓ or Not Created)
     * ✅ Allows checking in without filtering
     */
    
    let d = new frappe.ui.Dialog({
        title: __('Check In Selected Rooms'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'info_html',
                options: `<div class="alert alert-info">
                    <strong>Check In Rooms</strong><br>
                    Select which rooms to check in. Reservations are created automatically during check-in.
                </div>`
            },
            {
                fieldname: 'rooms_html',
                fieldtype: 'HTML',
                options: '<p class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading rooms...</p>'
            },
            {
                fieldtype: 'Section Break',
                label: 'Check-In Notes'
            },
            {
                fieldname: 'check_in_notes',
                fieldtype: 'Small Text',
                label: 'Notes (Optional)'
            }
        ],
        size: 'large',
        primary_action_label: __('Check In Selected'),
        primary_action: function(values) {
            let selected = [];
            d.$wrapper.find('input[type="checkbox"]:checked').each(function() {
                let room_idx = $(this).data('room-idx');
                selected.push(parseInt(room_idx));
            });
            
            if (selected.length === 0) {
                frappe.msgprint(__('Please select at least one room'));
                return;
            }
            
            // Check in SELECTED rooms
            check_in_selected_rooms_only(frm, selected, values.check_in_notes || '');
            d.hide();
        }
    });
    
    // Function to fetch fresh data and render rooms with real-time status
    function fetch_and_render_rooms() {
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Hotel Front Desk Reservation',
                name: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    let fresh_doc = r.message;
                    let room_numbers = fresh_doc.rooms.map(room => room.room_number);
                    
                    // Get actual reservations from database
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Hotel Room Reservation',
                            filters: {
                                'front_desk_reservation': frm.doc.name,
                                'room_number': ['in', room_numbers]
                            },
                            fields: ['name', 'room_number', 'status']
                        },
                        callback: function(r2) {
                            let reservations_in_db = {};
                            if (r2.message) {
                                r2.message.forEach(res => {
                                    reservations_in_db[res.room_number] = res.name;
                                });
                            }
                            
                            // Build rooms list with status from database
                            let rooms_list = fresh_doc.rooms.map((room, idx) => ({
                                index: idx,
                                room_number: room.room_number,
                                guest_name: room.guest_name,
                                has_reservation: reservations_in_db.hasOwnProperty(room.room_number)
                            }));
                            
                            // Build HTML - showing ALL rooms
                            let html = `
                                <table class="table table-bordered table-hover" style="margin: 15px 0;">
                                    <thead>
                                        <tr>
                                            <th width="10%"><input type="checkbox" id="select-all-checkin"></th>
                                            <th width="25%">Room</th>
                                            <th width="40%">Guest Name</th>
                                            <th width="25%">Reservation Status</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                            `;
                            
                            rooms_list.forEach(function(room) {
                                let status_badge = room.has_reservation 
                                    ? '<span class="badge badge-success">✓ Created</span>'
                                    : '<span class="badge badge-secondary">Not Created</span>';
                                
                                html += `
                                    <tr>
                                        <td><input type="checkbox" data-room-idx="${room.index}"></td>
                                        <td><strong>${room.room_number}</strong></td>
                                        <td>${room.guest_name || '(No guest name)'}</td>
                                        <td>${status_badge}</td>
                                    </tr>
                                `;
                            });
                            
                            html += `
                                    </tbody>
                                </table>
                            `;
                            
                            d.fields_dict.rooms_html.$wrapper.html(html);
                            
                            // Attach select all checkbox listener
                            d.$wrapper.find('#select-all-checkin').on('change', function() {
                                d.$wrapper.find('input[type="checkbox"]').not(this).prop('checked', this.checked);
                            });
                        }
                    });
                }
            }
        });
    }
    
    // Store original show method
    let original_show = d.show.bind(d);
    
    // Override show to fetch fresh data each time dialog opens
    d.show = function() {
        fetch_and_render_rooms();
        original_show();
    };
    
    d.show();
}


// ═════════════════════════════════════════════════════════════════════════
// CHECK IN FUNCTIONS
// ═════════════════════════════════════════════════════════════════════════

function check_in_selected_rooms_only(frm, room_indices, check_in_notes) {
    /**
     * Check in SELECTED rooms - automatically creates reservations
     * For corporate: User selects which rooms to check in
     */
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms',
        args: {
            reservation_name: frm.doc.name,
            room_indices: room_indices,
            check_in_notes: check_in_notes
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.msgprint({
                    title: __('Success'),
                    message: r.message.message,
                    indicator: 'green'
                });
                frm.reload_doc();
            } else if (r.message && r.message.missing_guest_names) {
                frappe.msgprint({
                    title: __('Guest Names Required'),
                    message: r.message.message,
                    indicator: 'orange'
                });
                setTimeout(function() {
                    show_guest_names_dialog(frm);
                }, 1000);
            }
        }
    });
}


function check_in_all_rooms_corporate(frm) {
    /**
     * Check in ALL rooms - automatically creates reservations
     * For corporate: Checks in all rooms at once
     */
    frappe.prompt([
        {
            fieldname: 'check_in_notes',
            fieldtype: 'Small Text',
            label: __('Check-In Notes (Optional)')
        }
    ],
    function(values) {
        frappe.call({
            method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_all_rooms',
            args: {
                reservation_name: frm.doc.name,
                check_in_notes: values.check_in_notes || ''
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Success'),
                        message: r.message.message,
                        indicator: 'green'
                    });
                    frm.reload_doc();
                } else if (r.message && r.message.missing_guest_names) {
                    frappe.msgprint({
                        title: __('Guest Names Required'),
                        message: r.message.message,
                        indicator: 'orange'
                    });
                    setTimeout(function() {
                        show_guest_names_dialog(frm);
                    }, 1000);
                }
            }
        });
    },
    __('Check In All Rooms'),
    __('Check In')
    );
}


function check_in_all_rooms(frm) {
    /**
     * Check in all rooms at once
     * For non-corporate bookings
     */
    frappe.prompt([
        {
            fieldname: 'check_in_notes',
            fieldtype: 'Small Text',
            label: __('Check-In Notes (Optional)')
        }
    ],
    function(values) {
        frappe.call({
            method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_reservation',
            args: {
                reservation_name: frm.doc.name,
                check_in_notes: values.check_in_notes || '',
                create_reservations: false
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Success'),
                        message: r.message.message,
                        indicator: 'green'
                    });
                    frm.reload_doc();
                } else if (r.message && r.message.missing_guest_names) {
                    frappe.msgprint({
                        title: __('Guest Names Required'),
                        message: r.message.message,
                        indicator: 'orange'
                    });
                    setTimeout(function() {
                        show_guest_names_dialog(frm);
                    }, 1000);
                }
            }
        });
    },
    __('Check In All Rooms'),
    __('Check In')
    );
}


// ═════════════════════════════════════════════════════════════════════════
// CREATE INVOICE
// ═════════════════════════════════════════════════════════════════════════

function create_invoice_for_reservation(frm) {
    frappe.confirm(
        __('Create Sales Invoice for this reservation?'),
        function() {
            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.create_sales_invoice_for_reservation',
                args: {
                    reservation_name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
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
    );
}


// ═════════════════════════════════════════════════════════════════════════
// GUEST NAMES DIALOG
// ═════════════════════════════════════════════════════════════════════════

function show_guest_names_dialog(frm) {
    let rooms_needing_names = frm.doc.rooms.filter(r => 
        !r.guest_name || r.guest_name.startsWith('Guest - Room')
    );
    
    if (rooms_needing_names.length === 0) {
        frappe.msgprint(__('All rooms already have guest names assigned'));
        return;
    }
    
    let fields = [
        {
            fieldtype: 'HTML',
            fieldname: 'instructions',
            options: `<div class="alert alert-info">
                <strong>Add Guest Names</strong><br>
                Please provide guest names for the following rooms. 
                This information is required for check-in.
            </div>`
        }
    ];
    
    rooms_needing_names.forEach(function(room, idx) {
        fields.push({
            fieldtype: 'Section Break',
            label: `Room ${room.room_number}`
        });
        
        fields.push({
            fieldname: `guest_name_${idx}`,
            fieldtype: 'Data',
            label: 'Guest Name',
            reqd: 1
        });
        
        fields.push({
            fieldtype: 'Column Break'
        });
        
        fields.push({
            fieldname: `guest_email_${idx}`,
            fieldtype: 'Data',
            label: 'Email (Optional)',
            options: 'Email'
        });
        
        fields.push({
            fieldtype: 'Column Break'
        });
        
        fields.push({
            fieldname: `guest_phone_${idx}`,
            fieldtype: 'Data',
            label: 'Phone (Optional)'
        });
    });
    
    let d = new frappe.ui.Dialog({
        title: __('Add Guest Names'),
        fields: fields,
        size: 'large',
        primary_action_label: __('Update Guest Names'),
        primary_action: function(values) {
            let updates = [];
            
            rooms_needing_names.forEach(function(room, idx) {
                let guest_name = values[`guest_name_${idx}`];
                if (guest_name) {
                    let room_idx = frm.doc.rooms.indexOf(room);
                    
                    updates.push({
                        room_idx: room_idx,
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
                args: {
                    reservation_name: frm.doc.name,
                    guest_updates: updates
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.msgprint({
                            title: __('Success'),
                            message: r.message.message,
                            indicator: 'green'
                        });
                        d.hide();
                        frm.reload_doc();
                    }
                }
            });
        }
    });
    
    d.show();
}


// ═════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═════════════════════════════════════════════════════════════════════════

function calculate_nights(frm) {
    if (frm.doc.from_date && frm.doc.to_date) {
        let from = frappe.datetime.str_to_obj(frm.doc.from_date);
        let to = frappe.datetime.str_to_obj(frm.doc.to_date);
        let nights = frappe.datetime.get_day_diff(to, from);
        
        if (nights > 0) {
            frm.set_value('number_of_nights', nights);
            
            frm.doc.rooms.forEach(function(row) {
                frappe.model.set_value(row.doctype, row.name, 'number_of_nights', nights);
                if (row.rate_per_night) {
                    frappe.model.set_value(row.doctype, row.name, 'room_total', 
                        row.rate_per_night * nights);
                }
            });
            
            frm.refresh_field('rooms');
            calculate_total(frm);
        }
    }
}


function calculate_total(frm) {
    let subtotal = 0;
    
    if (frm.doc.rooms) {
        frm.doc.rooms.forEach(function(row) {
            if (row.room_total) {
                subtotal += row.room_total;
            }
        });
    }
    
    frm.set_value('subtotal', subtotal);
    frm.set_value('total_rooms', frm.doc.rooms ? frm.doc.rooms.length : 0);
    
    let discount_amount = 0;
    if (frm.doc.discount_type && frm.doc.discount) {
        if (frm.doc.discount_type === 'Percentage') {
            discount_amount = (subtotal * frm.doc.discount) / 100;
        } else if (frm.doc.discount_type === 'Amount') {
            discount_amount = frm.doc.discount;
        }
    }
    
    frm.set_value('discount_amount', discount_amount);
    frm.set_value('total_amount', subtotal - discount_amount);
}


function fetch_room_rate(frm, row) {
    frappe.call({
        method: 'rhohotel.api.get_room_rate',
        args: {
            room_type: row.room_type,
            check_in_date: frm.doc.from_date
        },
        callback: function(r) {
            if (r.message) {
                frappe.model.set_value(row.doctype, row.name, 'rate_per_night', r.message);
                
                if (frm.doc.number_of_nights) {
                    frappe.model.set_value(row.doctype, row.name, 'room_total', 
                        r.message * frm.doc.number_of_nights);
                }
                
                calculate_total(frm);
            }
        }
    });
}


function fetch_corporate_details(frm) {
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Hotel Guest',
            name: frm.doc.corporate_guest
        },
        callback: function(r) {
            if (r.message) {
                let guest = r.message;
                
                if (guest.guest_type !== 'Corporate') {
                    frappe.msgprint(__('Selected guest is not a corporate client'));
                    frm.set_value('corporate_guest', '');
                    return;
                }
                
                frm.set_value('customer', guest.customer);
                frm.set_value('primary_guest_name', guest.hotel_guest_name);
                frm.set_value('primary_guest_email', guest.email || '');
                frm.set_value('primary_guest_phone', guest.phone_number || '');
            }
        }
    });
}


function refresh_available_rooms(frm) {
    if (frm.doc.from_date && frm.doc.to_date) {
        frappe.show_alert({
            message: __('Dates updated. Click "Add Available Rooms" to see availability'),
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
        args: {
            from_date: frm.doc.from_date,
            to_date: frm.doc.to_date,
            room_type: frm.doc.filter_by_room_type || null
        },
        callback: function(r) {
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
        fields: [
            {
                fieldname: 'rooms_html',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: __('Add Selected'),
        primary_action: function() {
            let selected = [];
            d.$wrapper.find('input[type="checkbox"]:checked').each(function() {
                let room_number = $(this).data('room');
                let room_data = available_rooms.find(r => r.name === room_number);
                if (room_data) {
                    selected.push(room_data);
                }
            });
            
            if (selected.length === 0) {
                frappe.msgprint(__('Please select at least one room'));
                return;
            }
            
            selected.forEach(function(room) {
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
            
            frappe.show_alert({
                message: __('Added {0} room(s)', [selected.length]),
                indicator: 'green'
            });
        }
    });
    
    let html = `
        <table class="table table-bordered table-hover" style="margin-top: 10px;">
            <thead>
                <tr>
                    <th width="10%"><input type="checkbox" id="select-all-rooms"></th>
                    <th width="20%">Room</th>
                    <th width="25%">Type</th>
                    <th width="15%">Floor</th>
                    <th width="15%">Capacity</th>
                    <th width="15%">Rate/Night</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    available_rooms.forEach(function(room) {
        html += `
            <tr>
                <td><input type="checkbox" data-room="${room.name}"></td>
                <td><strong>${room.name}</strong></td>
                <td>${room.room_type}</td>
                <td>${room.floor || 'N/A'}</td>
                <td>${room.capacity}</td>
                <td>${format_currency(room.rate_per_night)}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    d.fields_dict.rooms_html.$wrapper.html(html);
    
    d.$wrapper.find('#select-all-rooms').on('change', function() {
        d.$wrapper.find('input[type="checkbox"]').not(this).prop('checked', this.checked);
    });
    
    d.show();
}














































// // Hotel Front Desk Reservation - Client Script v4 FINAL
// // ✅ FIXED: Corporate reservations create immediately like others
// // ✅ FIXED: Can edit guest names before check-in with proper linking
// // ✅ FIXED: Check-in creates individual invoices per selected rooms
// // ✅ FIXED: Can pay invoice from FDR doc
// // ✅ FIXED: Track check-in status per room in dialog

// frappe.ui.form.on('Hotel Front Desk Reservation', {
//     refresh: function(frm) {
//         add_custom_buttons(frm);
        
//         frm.set_query('filter_by_room_type', function() {
//             return {
//                 filters: {
//                     'is_active': 1
//                 }
//             };
//         });
        
//         frm.set_query('corporate_guest', function() {
//             return {
//                 filters: {
//                     'guest_type': 'Corporate'
//                 }
//             };
//         });
        
//         // Filter room_number dropdown by available rooms based on dates
//         frm.set_query('room_number', 'rooms', function(doc, cdt, cdn) {
//             if (!doc.from_date || !doc.to_date) {
//                 frappe.msgprint(__('Please select check-in and check-out dates first'));
//                 return;
//             }
            
//             return {
//                 filters: [
//                     ['Hotel Room', 'status', '=', 'Vacant'],
//                     ['Hotel Room', 'operational_status', '=', 'In Service'],
//                     ['Hotel Room', 'maintenance_flag', '=', 0]
//                 ],
//                 query: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms_for_dropdown',
//                 args: {
//                     from_date: doc.from_date,
//                     to_date: doc.to_date,
//                     room_type: doc.filter_by_room_type || null
//                 }
//             };
//         });
//     },
    
//     from_date: function(frm) {
//         calculate_nights(frm);
//         refresh_available_rooms(frm);
//     },
    
//     to_date: function(frm) {
//         calculate_nights(frm);
//         refresh_available_rooms(frm);
//     },
    
//     filter_by_room_type: function(frm) {
//         refresh_available_rooms(frm);
//     },
    
//     reservation_type: function(frm) {
//         if (frm.doc.reservation_type !== 'Corporate') {
//             frm.set_value('corporate_guest', '');
//             frm.set_value('customer', '');
//         }
//     },
    
//     corporate_guest: function(frm) {
//         if (frm.doc.corporate_guest && frm.doc.reservation_type === 'Corporate') {
//             fetch_corporate_details(frm);
//         }
//     },
    
//     discount_type: function(frm) {
//         calculate_total(frm);
//     },
    
//     discount: function(frm) {
//         calculate_total(frm);
//     }
// });


// frappe.ui.form.on('Front Desk Reservation Room', {
//     room_number: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         if (row.room_number && frm.doc.from_date && frm.doc.to_date) {
//             fetch_room_rate(frm, row);
//         }
//     },
    
//     rooms_remove: function(frm) {
//         calculate_total(frm);
//     }
// });


// // ═════════════════════════════════════════════════════════════════════════
// // CUSTOM BUTTONS
// // ═════════════════════════════════════════════════════════════════════════

// function add_custom_buttons(frm) {
//     if (frm.doc.docstatus === 0) {
//         // Draft state
//         frm.add_custom_button(__('Add Available Rooms'), function() {
//             show_available_rooms_dialog(frm);
//         });
//     }
    
//     if (frm.doc.docstatus === 1) {
//         // Submitted state
        
//         // Check if any rooms missing guest names
//         let missing_names = frm.doc.rooms.filter(r => 
//             !r.guest_name || r.guest_name.startsWith('Guest - Room')
//         );
        
//         if (missing_names.length > 0) {
//             frm.add_custom_button(__('Add Guest Names'), function() {
//                 show_guest_names_dialog(frm);
//             }, __('Actions')).css({'background-color': '#ffc107', 'color': 'white'});
//         }
        
//         // ✅ Check in buttons - works for ALL reservation types now
//         if (frm.doc.status === 'Confirmed') {
//             frm.add_custom_button(__('Check In Selected Rooms'), function() {
//                 show_corporate_checkin_dialog(frm);
//             }, __('Check In'));
            
//             frm.add_custom_button(__('Check In All Rooms'), function() {
//                 frappe.confirm(
//                     __('Check in all {0} rooms?', [frm.doc.total_rooms]),
//                     function() {
//                         check_in_all_rooms(frm);
//                     }
//                 );
//             }, __('Check In'));
//         }
        
//         // Create Invoice button
//         if (!frm.doc.sales_invoice) {
//             frm.add_custom_button(__('Create Invoice (All Rooms)'), function() {
//                 create_invoice_for_reservation(frm);
//             }, __('Create'));
//         }
        
//         if (frm.doc.status === 'Checked In') {
//             frm.add_custom_button(__('View Check-Ins'), function() {
//                 frappe.route_options = {
//                     "front_desk_reservation": frm.doc.name
//                 };
//                 frappe.set_route("List", "Hotel Room Check In");
//             }, __('View'));
//         }
        
//         if (frm.doc.sales_invoice) {
//             frm.add_custom_button(__('View Invoice'), function() {
//                 frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
//             }, __('View'));
            
//             frm.add_custom_button(__('Pay Invoice'), function() {
//                 show_payment_dialog(frm);
//             }, __('View'));
//         }
        
//         frm.add_custom_button(__('View Room Reservations'), function() {
//             frappe.route_options = {
//                 "front_desk_reservation": frm.doc.name
//             };
//             frappe.set_route("List", "Hotel Room Reservation");
//         }, __('View'));
//     }
// }


// // ═════════════════════════════════════════════════════════════════════════
// // CHECK IN DIALOG WITH STATUS TRACKING
// // ═════════════════════════════════════════════════════════════════════════

// function show_corporate_checkin_dialog(frm) {
//     /**
//      * Dialog to check in SELECTED rooms
//      * ✅ Shows all rooms with check-in status
//      * ✅ Shows real-time reservation status
//      * ✅ Allows checking in without filtering
//      */
    
//     let d = new frappe.ui.Dialog({
//         title: __('Check In Selected Rooms'),
//         fields: [
//             {
//                 fieldtype: 'HTML',
//                 fieldname: 'info_html',
//                 options: `<div class="alert alert-info">
//                     <strong>Check In Rooms</strong><br>
//                     Select which rooms to check in. Individual invoices will be created for each room.
//                 </div>`
//             },
//             {
//                 fieldname: 'rooms_html',
//                 fieldtype: 'HTML',
//                 options: '<p class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading rooms...</p>'
//             },
//             {
//                 fieldtype: 'Section Break',
//                 label: 'Check-In Notes'
//             },
//             {
//                 fieldname: 'check_in_notes',
//                 fieldtype: 'Small Text',
//                 label: 'Notes (Optional)'
//             }
//         ],
//         size: 'large',
//         primary_action_label: __('Check In Selected'),
//         primary_action: function(values) {
//             let selected = [];
//             d.$wrapper.find('input[type="checkbox"]:checked').each(function() {
//                 let room_idx = $(this).data('room-idx');
//                 selected.push(parseInt(room_idx));
//             });
            
//             if (selected.length === 0) {
//                 frappe.msgprint(__('Please select at least one room'));
//                 return;
//             }
            
//             // Check in SELECTED rooms
//             check_in_selected_rooms_only(frm, selected, values.check_in_notes || '');
//             d.hide();
//         }
//     });
    
//     // Function to fetch fresh data and render rooms with real-time status
//     function fetch_and_render_rooms() {
//         frappe.call({
//             method: 'frappe.client.get',
//             args: {
//                 doctype: 'Hotel Front Desk Reservation',
//                 name: frm.doc.name
//             },
//             callback: function(r) {
//                 if (r.message) {
//                     let fresh_doc = r.message;
//                     let room_numbers = fresh_doc.rooms.map(room => room.room_number);
                    
//                     // Get actual check-ins from database
//                     frappe.call({
//                         method: 'frappe.client.get_list',
//                         args: {
//                             doctype: 'Hotel Room Check In',
//                             filters: {
//                                 'front_desk_reservation': frm.doc.name,
//                                 'room_number': ['in', room_numbers]
//                             },
//                             fields: ['name', 'room_number', 'status']
//                         },
//                         callback: function(r2) {
//                             let checkins_in_db = {};
//                             if (r2.message) {
//                                 r2.message.forEach(res => {
//                                     checkins_in_db[res.room_number] = res.name;
//                                 });
//                             }
                            
//                             // Get reservation statuses
//                             frappe.call({
//                                 method: 'frappe.client.get_list',
//                                 args: {
//                                     doctype: 'Hotel Room Reservation',
//                                     filters: {
//                                         'front_desk_reservation': frm.doc.name,
//                                         'room_number': ['in', room_numbers]
//                                     },
//                                     fields: ['name', 'room_number', 'status']
//                                 },
//                                 callback: function(r3) {
//                                     let reservations_in_db = {};
//                                     if (r3.message) {
//                                         r3.message.forEach(res => {
//                                             reservations_in_db[res.room_number] = res.status;
//                                         });
//                                     }
                                    
//                                     // Build rooms list with status from database
//                                     let rooms_list = fresh_doc.rooms.map((room, idx) => ({
//                                         index: idx,
//                                         room_number: room.room_number,
//                                         guest_name: room.guest_name,
//                                         has_checkin: checkins_in_db.hasOwnProperty(room.room_number),
//                                         reservation_status: reservations_in_db[room.room_number] || 'Booked',
//                                         checkin_status: checkins_in_db[room.room_number] ? 'Checked In' : 'Pending'
//                                     }));
                                    
//                                     // Build HTML - showing ALL rooms with status
//                                     let html = `
//                                         <table class="table table-bordered table-hover" style="margin: 15px 0;">
//                                             <thead>
//                                                 <tr>
//                                                     <th width="8%"><input type="checkbox" id="select-all-checkin"></th>
//                                                     <th width="20%">Room</th>
//                                                     <th width="30%">Guest Name</th>
//                                                     <th width="20%">Reservation</th>
//                                                     <th width="22%">Check-In Status</th>
//                                                 </tr>
//                                             </thead>
//                                             <tbody>
//                                     `;
                                    
//                                     rooms_list.forEach(function(room) {
//                                         let reservation_badge = `<span class="badge badge-info">${room.reservation_status}</span>`;
//                                         let checkin_badge = room.has_checkin 
//                                             ? '<span class="badge badge-success"><i class="fa fa-check"></i> Checked In</span>'
//                                             : '<span class="badge badge-secondary">Pending</span>';
                                        
//                                         // Disable checkbox if already checked in
//                                         let checkbox_disabled = room.has_checkin ? 'disabled' : '';
                                        
//                                         html += `
//                                             <tr>
//                                                 <td><input type="checkbox" data-room-idx="${room.index}" ${checkbox_disabled}></td>
//                                                 <td><strong>${room.room_number}</strong></td>
//                                                 <td>${room.guest_name || '(No guest name)'}</td>
//                                                 <td>${reservation_badge}</td>
//                                                 <td>${checkin_badge}</td>
//                                             </tr>
//                                         `;
//                                     });
                                    
//                                     html += `
//                                             </tbody>
//                                         </table>
//                                     `;
                                    
//                                     d.fields_dict.rooms_html.$wrapper.html(html);
                                    
//                                     // Attach select all checkbox listener
//                                     d.$wrapper.find('#select-all-checkin').on('change', function() {
//                                         d.$wrapper.find('input[type="checkbox"]:not(:disabled)').not(this).prop('checked', this.checked);
//                                     });
//                                 }
//                             });
//                         }
//                     });
//                 }
//             }
//         });
//     }
    
//     // Store original show method
//     let original_show = d.show.bind(d);
    
//     // Override show to fetch fresh data each time dialog opens
//     d.show = function() {
//         fetch_and_render_rooms();
//         original_show();
//     };
    
//     d.show();
// }


// // ═════════════════════════════════════════════════════════════════════════
// // GUEST NAMES DIALOG (BEFORE CHECK-IN)
// // ═════════════════════════════════════════════════════════════════════════

// function show_guest_names_dialog(frm) {
//     let rooms_needing_names = frm.doc.rooms.filter(r => 
//         !r.guest_name || r.guest_name.startsWith('Guest - Room')
//     );
    
//     if (rooms_needing_names.length === 0) {
//         frappe.msgprint(__('All rooms already have guest names assigned'));
//         return;
//     }
    
//     let fields = [
//         {
//             fieldtype: 'HTML',
//             fieldname: 'instructions',
//             options: `<div class="alert alert-info">
//                 <strong>Add/Edit Guest Names</strong><br>
//                 Provide guest names for the following rooms. This ensures proper customer and guest records are created.
//             </div>`
//         }
//     ];
    
//     rooms_needing_names.forEach(function(room, idx) {
//         fields.push({
//             fieldtype: 'Section Break',
//             label: `Room ${room.room_number}`
//         });
        
//         fields.push({
//             fieldname: `guest_name_${idx}`,
//             fieldtype: 'Data',
//             label: 'Guest Name',
//             default: room.guest_name || '',
//             reqd: 1
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         fields.push({
//             fieldname: `guest_email_${idx}`,
//             fieldtype: 'Data',
//             label: 'Email (Optional)',
//             options: 'Email',
//             default: room.guest_email || ''
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         fields.push({
//             fieldname: `guest_phone_${idx}`,
//             fieldtype: 'Data',
//             label: 'Phone (Optional)',
//             default: room.guest_phone || ''
//         });
//     });
    
//     let d = new frappe.ui.Dialog({
//         title: __('Add/Edit Guest Names'),
//         fields: fields,
//         size: 'large',
//         primary_action_label: __('Update Guest Names'),
//         primary_action: function(values) {
//             let updates = [];
            
//             rooms_needing_names.forEach(function(room, idx) {
//                 let guest_name = values[`guest_name_${idx}`];
//                 if (guest_name) {
//                     let room_idx = frm.doc.rooms.indexOf(room);
                    
//                     updates.push({
//                         room_idx: room_idx,
//                         guest_name: guest_name,
//                         guest_email: values[`guest_email_${idx}`] || '',
//                         guest_phone: values[`guest_phone_${idx}`] || ''
//                     });
//                 }
//             });
            
//             if (updates.length === 0) {
//                 frappe.msgprint(__('No updates to save'));
//                 return;
//             }
            
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.update_guest_names_before_checkin',
//                 args: {
//                     reservation_name: frm.doc.name,
//                     guest_updates: updates
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.success) {
//                         frappe.msgprint({
//                             title: __('Success'),
//                             message: r.message.message,
//                             indicator: 'green'
//                         });
//                         d.hide();
//                         frm.reload_doc();
//                     }
//                 }
//             });
//         }
//     });
    
//     d.show();
// }


// // ═════════════════════════════════════════════════════════════════════════
// // PAYMENT DIALOG
// // ═════════════════════════════════════════════════════════════════════════

// function show_payment_dialog(frm) {
//     if (!frm.doc.sales_invoice) {
//         frappe.msgprint(__('No sales invoice linked to this reservation'));
//         return;
//     }
    
//     // Get invoice details
//     frappe.call({
//         method: 'frappe.client.get',
//         args: {
//             doctype: 'Sales Invoice',
//             name: frm.doc.sales_invoice
//         },
//         callback: function(r) {
//             if (r.message) {
//                 let invoice = r.message;
                
//                 let d = new frappe.ui.Dialog({
//                     title: __('Pay Invoice {0}', [invoice.name]),
//                     fields: [
//                         {
//                             fieldtype: 'HTML',
//                             fieldname: 'invoice_info',
//                             options: `
//                                 <div class="alert alert-info">
//                                     <p><strong>Invoice Total:</strong> ${format_currency(invoice.grand_total)}</p>
//                                     <p><strong>Outstanding:</strong> ${format_currency(invoice.outstanding_amount)}</p>
//                                 </div>
//                             `
//                         },
//                         {
//                             fieldname: 'payment_amount',
//                             fieldtype: 'Currency',
//                             label: 'Payment Amount',
//                             default: invoice.outstanding_amount,
//                             reqd: 1
//                         },
//                         {
//                             fieldname: 'payment_method',
//                             fieldtype: 'Select',
//                             label: 'Payment Method',
//                             options: 'Card\nCash\nBank Transfer\nCorporate Account\nOther',
//                             default: 'Card',
//                             reqd: 1
//                         }
//                     ],
//                     size: 'small',
//                     primary_action_label: __('Record Payment'),
//                     primary_action: function(values) {
//                         frappe.call({
//                             method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.pay_sales_invoice',
//                             args: {
//                                 invoice_name: frm.doc.sales_invoice,
//                                 amount: values.payment_amount,
//                                 payment_method: values.payment_method
//                             },
//                             callback: function(r) {
//                                 if (r.message && r.message.success) {
//                                     frappe.msgprint({
//                                         title: __('Success'),
//                                         message: r.message.message,
//                                         indicator: 'green'
//                                     });
//                                     d.hide();
//                                     frm.reload_doc();
//                                 }
//                             }
//                         });
//                     }
//                 });
                
//                 d.show();
//             }
//         }
//     });
// }


// // ═════════════════════════════════════════════════════════════════════════
// // CHECK IN FUNCTIONS
// // ═════════════════════════════════════════════════════════════════════════

// function check_in_selected_rooms_only(frm, room_indices, check_in_notes) {
//     /**
//      * Check in SELECTED rooms - creates individual invoices
//      */
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms',
//         args: {
//             reservation_name: frm.doc.name,
//             room_indices: room_indices,
//             check_in_notes: check_in_notes
//         },
//         callback: function(r) {
//             if (r.message && r.message.success) {
//                 frappe.msgprint({
//                     title: __('Success'),
//                     message: r.message.message,
//                     indicator: 'green'
//                 });
//                 frm.reload_doc();
//             } else if (r.message && r.message.missing_guest_names) {
//                 frappe.msgprint({
//                     title: __('Guest Names Required'),
//                     message: r.message.message,
//                     indicator: 'orange'
//                 });
//                 setTimeout(function() {
//                     show_guest_names_dialog(frm);
//                 }, 1000);
//             }
//         }
//     });
// }


// function check_in_all_rooms(frm) {
//     /**
//      * Check in all rooms - creates individual invoices for each room
//      */
//     frappe.prompt([
//         {
//             fieldname: 'check_in_notes',
//             fieldtype: 'Small Text',
//             label: __('Check-In Notes (Optional)')
//         }
//     ],
//     function(values) {
//         frappe.call({
//             method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_all_rooms',
//             args: {
//                 reservation_name: frm.doc.name,
//                 check_in_notes: values.check_in_notes || ''
//             },
//             callback: function(r) {
//                 if (r.message && r.message.success) {
//                     frappe.msgprint({
//                         title: __('Success'),
//                         message: r.message.message,
//                         indicator: 'green'
//                     });
//                     frm.reload_doc();
//                 } else if (r.message && r.message.missing_guest_names) {
//                     frappe.msgprint({
//                         title: __('Guest Names Required'),
//                         message: r.message.message,
//                         indicator: 'orange'
//                     });
//                     setTimeout(function() {
//                         show_guest_names_dialog(frm);
//                     }, 1000);
//                 }
//             }
//         });
//     },
//     __('Check In All Rooms'),
//     __('Check In')
//     );
// }


// // ═════════════════════════════════════════════════════════════════════════
// // CREATE INVOICE
// // ═════════════════════════════════════════════════════════════════════════

// function create_invoice_for_reservation(frm) {
//     frappe.confirm(
//         __('Create Sales Invoice for ALL rooms in this reservation?'),
//         function() {
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.create_sales_invoice_for_reservation',
//                 args: {
//                     reservation_name: frm.doc.name
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.success) {
//                         frappe.msgprint({
//                             title: __('Success'),
//                             message: r.message.message,
//                             indicator: 'green'
//                         });
//                         frm.reload_doc();
//                     }
//                 }
//             });
//         }
//     );
// }


// // ═════════════════════════════════════════════════════════════════════════
// // HELPER FUNCTIONS
// // ═════════════════════════════════════════════════════════════════════════

// function calculate_nights(frm) {
//     if (frm.doc.from_date && frm.doc.to_date) {
//         let from = frappe.datetime.str_to_obj(frm.doc.from_date);
//         let to = frappe.datetime.str_to_obj(frm.doc.to_date);
//         let nights = frappe.datetime.get_day_diff(to, from);
        
//         if (nights > 0) {
//             frm.set_value('number_of_nights', nights);
            
//             frm.doc.rooms.forEach(function(row) {
//                 frappe.model.set_value(row.doctype, row.name, 'number_of_nights', nights);
//                 if (row.rate_per_night) {
//                     frappe.model.set_value(row.doctype, row.name, 'room_total', 
//                         row.rate_per_night * nights);
//                 }
//             });
            
//             frm.refresh_field('rooms');
//             calculate_total(frm);
//         }
//     }
// }


// function calculate_total(frm) {
//     let subtotal = 0;
    
//     if (frm.doc.rooms) {
//         frm.doc.rooms.forEach(function(row) {
//             if (row.room_total) {
//                 subtotal += row.room_total;
//             }
//         });
//     }
    
//     frm.set_value('subtotal', subtotal);
//     frm.set_value('total_rooms', frm.doc.rooms ? frm.doc.rooms.length : 0);
    
//     let discount_amount = 0;
//     if (frm.doc.discount_type && frm.doc.discount) {
//         if (frm.doc.discount_type === 'Percentage') {
//             discount_amount = (subtotal * frm.doc.discount) / 100;
//         } else if (frm.doc.discount_type === 'Amount') {
//             discount_amount = frm.doc.discount;
//         }
//     }
    
//     frm.set_value('discount_amount', discount_amount);
//     frm.set_value('total_amount', subtotal - discount_amount);
// }


// function fetch_room_rate(frm, row) {
//     frappe.call({
//         method: 'rhohotel.api.get_room_rate',
//         args: {
//             room_type: row.room_type,
//             check_in_date: frm.doc.from_date
//         },
//         callback: function(r) {
//             if (r.message) {
//                 frappe.model.set_value(row.doctype, row.name, 'rate_per_night', r.message);
                
//                 if (frm.doc.number_of_nights) {
//                     frappe.model.set_value(row.doctype, row.name, 'room_total', 
//                         r.message * frm.doc.number_of_nights);
//                 }
                
//                 calculate_total(frm);
//             }
//         }
//     });
// }


// function fetch_corporate_details(frm) {
//     frappe.call({
//         method: 'frappe.client.get',
//         args: {
//             doctype: 'Hotel Guest',
//             name: frm.doc.corporate_guest
//         },
//         callback: function(r) {
//             if (r.message) {
//                 let guest = r.message;
                
//                 if (guest.guest_type !== 'Corporate') {
//                     frappe.msgprint(__('Selected guest is not a corporate client'));
//                     frm.set_value('corporate_guest', '');
//                     return;
//                 }
                
//                 frm.set_value('customer', guest.customer);
//                 frm.set_value('primary_guest_name', guest.hotel_guest_name);
//                 frm.set_value('primary_guest_email', guest.email || '');
//                 frm.set_value('primary_guest_phone', guest.phone_number || '');
//             }
//         }
//     });
// }


// function refresh_available_rooms(frm) {
//     if (frm.doc.from_date && frm.doc.to_date) {
//         frappe.show_alert({
//             message: __('Dates updated. Click "Add Available Rooms" to see availability'),
//             indicator: 'blue'
//         }, 3);
//     }
// }


// function show_available_rooms_dialog(frm) {
//     if (!frm.doc.from_date || !frm.doc.to_date) {
//         frappe.msgprint(__('Please select check-in and check-out dates first'));
//         return;
//     }
    
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms',
//         args: {
//             from_date: frm.doc.from_date,
//             to_date: frm.doc.to_date,
//             room_type: frm.doc.filter_by_room_type || null
//         },
//         callback: function(r) {
//             if (r.message && r.message.length > 0) {
//                 show_room_selection_dialog(frm, r.message);
//             } else {
//                 frappe.msgprint(__('No rooms available for selected dates'));
//             }
//         }
//     });
// }


// function show_room_selection_dialog(frm, available_rooms) {
//     let d = new frappe.ui.Dialog({
//         title: __('Select Rooms to Add'),
//         fields: [
//             {
//                 fieldname: 'rooms_html',
//                 fieldtype: 'HTML'
//             }
//         ],
//         primary_action_label: __('Add Selected'),
//         primary_action: function() {
//             let selected = [];
//             d.$wrapper.find('input[type="checkbox"]:checked').each(function() {
//                 let room_number = $(this).data('room');
//                 let room_data = available_rooms.find(r => r.name === room_number);
//                 if (room_data) {
//                     selected.push(room_data);
//                 }
//             });
            
//             if (selected.length === 0) {
//                 frappe.msgprint(__('Please select at least one room'));
//                 return;
//             }
            
//             selected.forEach(function(room) {
//                 let row = frm.add_child('rooms');
//                 row.room_number = room.name;
//                 row.room_type = room.room_type;
//                 row.rate_per_night = room.rate_per_night;
//                 row.number_of_nights = frm.doc.number_of_nights;
//                 row.room_total = room.total_amount;
//             });
            
//             frm.refresh_field('rooms');
//             calculate_total(frm);
//             d.hide();
            
//             frappe.show_alert({
//                 message: __('Added {0} room(s)', [selected.length]),
//                 indicator: 'green'
//             });
//         }
//     });
    
//     let html = `
//         <table class="table table-bordered table-hover" style="margin-top: 10px;">
//             <thead>
//                 <tr>
//                     <th width="10%"><input type="checkbox" id="select-all-rooms"></th>
//                     <th width="20%">Room</th>
//                     <th width="25%">Type</th>
//                     <th width="15%">Floor</th>
//                     <th width="15%">Capacity</th>
//                     <th width="15%">Rate/Night</th>
//                 </tr>
//             </thead>
//             <tbody>
//     `;
    
//     available_rooms.forEach(function(room) {
//         html += `
//             <tr>
//                 <td><input type="checkbox" data-room="${room.name}"></td>
//                 <td><strong>${room.name}</strong></td>
//                 <td>${room.room_type}</td>
//                 <td>${room.floor || 'N/A'}</td>
//                 <td>${room.capacity}</td>
//                 <td>${format_currency(room.rate_per_night)}</td>
//             </tr>
//         `;
//     });
    
//     html += `
//             </tbody>
//         </table>
//     `;
    
//     d.fields_dict.rooms_html.$wrapper.html(html);
    
//     d.$wrapper.find('#select-all-rooms').on('change', function() {
//         d.$wrapper.find('input[type="checkbox"]').not(this).prop('checked', this.checked);
//     });
    
//     d.show();
// }



























// // Hotel Front Desk Reservation - Client Script v5
// // ✅ Edit Guest Data modal - edit individual room guest info
// // ✅ Creates Individual Hotel Guests (not corporate) when editing
// // ✅ Corporate bookings without guest names use corporate customer

// frappe.ui.form.on('Hotel Front Desk Reservation', {
//     refresh: function(frm) {
//         add_custom_buttons(frm);
        
//         frm.set_query('filter_by_room_type', function() {
//             return {
//                 filters: {
//                     'is_active': 1
//                 }
//             };
//         });
        
//         frm.set_query('corporate_guest', function() {
//             return {
//                 filters: {
//                     'guest_type': 'Corporate'
//                 }
//             };
//         });
        
//         // Filter room_number dropdown by available rooms based on dates
//         frm.set_query('room_number', 'rooms', function(doc, cdt, cdn) {
//             if (!doc.from_date || !doc.to_date) {
//                 frappe.msgprint(__('Please select check-in and check-out dates first'));
//                 return;
//             }
            
//             return {
//                 filters: [
//                     ['Hotel Room', 'status', '=', 'Vacant'],
//                     ['Hotel Room', 'operational_status', '=', 'In Service'],
//                     ['Hotel Room', 'maintenance_flag', '=', 0]
//                 ],
//                 query: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms_for_dropdown',
//                 args: {
//                     from_date: doc.from_date,
//                     to_date: doc.to_date,
//                     room_type: doc.filter_by_room_type || null
//                 }
//             };
//         });
//     },
    
//     from_date: function(frm) {
//         calculate_nights(frm);
//         refresh_available_rooms(frm);
//     },
    
//     to_date: function(frm) {
//         calculate_nights(frm);
//         refresh_available_rooms(frm);
//     },
    
//     filter_by_room_type: function(frm) {
//         refresh_available_rooms(frm);
//     },
    
//     reservation_type: function(frm) {
//         if (frm.doc.reservation_type !== 'Corporate') {
//             frm.set_value('corporate_guest', '');
//             frm.set_value('customer', '');
//         }
//     },
    
//     corporate_guest: function(frm) {
//         if (frm.doc.corporate_guest && frm.doc.reservation_type === 'Corporate') {
//             fetch_corporate_details(frm);
//         }
//     },
    
//     discount_type: function(frm) {
//         calculate_total(frm);
//     },
    
//     discount: function(frm) {
//         calculate_total(frm);
//     }
// });


// frappe.ui.form.on('Front Desk Reservation Room', {
//     room_number: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         if (row.room_number && frm.doc.from_date && frm.doc.to_date) {
//             fetch_room_rate(frm, row);
//         }
//     },
    
//     rooms_remove: function(frm) {
//         calculate_total(frm);
//     }
// });


// // ═════════════════════════════════════════════════════════════════════════
// // CUSTOM BUTTONS
// // ═════════════════════════════════════════════════════════════════════════

// function add_custom_buttons(frm) {
//     if (frm.doc.docstatus === 0) {
//         // Draft state
//         frm.add_custom_button(__('Add Available Rooms'), function() {
//             show_available_rooms_dialog(frm);
//         });
//     }
    
//     if (frm.doc.docstatus === 1) {
//         // Submitted state
        
//         // ✅ Edit Guest Data button - for editing individual guest info
//         frm.add_custom_button(__('Edit Guest Data'), function() {
//             show_edit_guest_data_dialog(frm);
//         }, __('Actions')).css({'background-color': '#17a2b8', 'color': 'white'});
        
//         // ✅ Check in buttons - works for ALL reservation types
//         if (frm.doc.status === 'Confirmed') {
//             frm.add_custom_button(__('Check In Selected Rooms'), function() {
//                 show_corporate_checkin_dialog(frm);
//             }, __('Check In'));
            
//             frm.add_custom_button(__('Check In All Rooms'), function() {
//                 frappe.confirm(
//                     __('Check in all {0} rooms?', [frm.doc.total_rooms]),
//                     function() {
//                         check_in_all_rooms(frm);
//                     }
//                 );
//             }, __('Check In'));
//         }
        
//         // Create Invoice button
//         if (!frm.doc.sales_invoice) {
//             frm.add_custom_button(__('Create Invoice (All Rooms)'), function() {
//                 create_invoice_for_reservation(frm);
//             }, __('Create'));
//         }
        
//         if (frm.doc.status === 'Checked In') {
//             frm.add_custom_button(__('View Check-Ins'), function() {
//                 frappe.route_options = {
//                     "front_desk_reservation": frm.doc.name
//                 };
//                 frappe.set_route("List", "Hotel Room Check In");
//             }, __('View'));
//         }
        
//         if (frm.doc.sales_invoice) {
//             frm.add_custom_button(__('View Invoice'), function() {
//                 frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
//             }, __('View'));
            
//             frm.add_custom_button(__('Pay Invoice'), function() {
//                 show_payment_dialog(frm);
//             }, __('View'));
//         }
        
//         frm.add_custom_button(__('View Room Reservations'), function() {
//             frappe.route_options = {
//                 "front_desk_reservation": frm.doc.name
//             };
//             frappe.set_route("List", "Hotel Room Reservation");
//         }, __('View'));
//     }
// }


// // ═════════════════════════════════════════════════════════════════════════
// // EDIT GUEST DATA MODAL - Edit individual room guest details
// // ═════════════════════════════════════════════════════════════════════════

// function show_edit_guest_data_dialog(frm) {
//     /**
//      * Modal to edit guest details for each room
//      * ✅ Shows one form per room
//      * ✅ Editable: Name, Gender, ID Type, ID Number, Phone, Email
//      * ✅ Creates Individual Hotel Guests (not corporate)
//      */
    
//     // Build all fields for all rooms first
//     let fields = [
//         {
//             fieldtype: 'HTML',
//             fieldname: 'info_html',
//             options: `<div class="alert alert-info">
//                 <strong>Edit Guest Information</strong><br>
//                 Update guest details for each room. Individual guest records will be created for any edited information.
//             </div>`
//         }
//     ];
    
//     // Add a section for each room with editable fields
//     frm.doc.rooms.forEach(function(room, idx) {
//         fields.push({
//             fieldtype: 'Section Break',
//             label: `Room ${room.room_number}`
//         });
        
//         // Guest Name (required)
//         fields.push({
//             fieldname: `guest_name_${idx}`,
//             fieldtype: 'Data',
//             label: 'Guest Name',
//             default: room.guest_name || '',
//             reqd: 1
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         // Gender
//         fields.push({
//             fieldname: `guest_gender_${idx}`,
//             fieldtype: 'Select',
//             label: 'Gender',
//             options: '\nMale\nFemale\nOther',
//             default: room.guest_gender || 'Male'
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         // ID Type
//         fields.push({
//             fieldname: `guest_id_type_${idx}`,
//             fieldtype: 'Select',
//             label: 'ID Type',
//             options: '\nPassport\nNational ID\nDriver\'s License\nOther',
//             default: room.guest_id_type || ''
//         });
        
//         // ID Number and Phone on same row
//         fields.push({
//             fieldtype: 'Section Break'
//         });
        
//         fields.push({
//             fieldname: `guest_id_number_${idx}`,
//             fieldtype: 'Data',
//             label: 'ID Number',
//             default: room.guest_id_number || ''
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         fields.push({
//             fieldname: `guest_phone_${idx}`,
//             fieldtype: 'Data',
//             label: 'Phone Number',
//             default: room.guest_phone || ''
//         });
        
//         // Email
//         fields.push({
//             fieldtype: 'Section Break'
//         });
        
//         fields.push({
//             fieldname: `guest_email_${idx}`,
//             fieldtype: 'Data',
//             label: 'Email',
//             options: 'Email',
//             default: room.guest_email || ''
//         });
//     });
    
//     // Create dialog with all fields at once
//     let d = new frappe.ui.Dialog({
//         title: __('Edit Guest Details for Each Room'),
//         fields: fields,
//         size: 'large',
//         primary_action_label: __('Save Guest Details'),
//         primary_action: function(values) {
//             save_guest_details(frm, d);
//         }
//     });
    
//     d.show();
// }


// function save_guest_details(frm, dialog) {
//     /**
//      * Save guest details for all rooms
//      * Calls backend to create/update customers and individual hotel guests
//      */
//     let updates = [];
    
//     frm.doc.rooms.forEach(function(room, idx) {
//         // Get values from dialog
//         let guest_name = dialog.get_value(`guest_name_${idx}`);
//         let guest_gender = dialog.get_value(`guest_gender_${idx}`) || 'Male';
//         let guest_id_type = dialog.get_value(`guest_id_type_${idx}`) || '';
//         let guest_id_number = dialog.get_value(`guest_id_number_${idx}`) || '';
//         let guest_phone = dialog.get_value(`guest_phone_${idx}`) || '';
//         let guest_email = dialog.get_value(`guest_email_${idx}`) || '';
        
//         // Only add to updates if guest has a name
//         if (guest_name && guest_name.trim()) {
//             updates.push({
//                 room_idx: idx,
//                 guest_name: guest_name.trim(),
//                 guest_gender: guest_gender || 'Male',
//                 guest_id_type: guest_id_type || '',
//                 guest_id_number: guest_id_number || '',
//                 guest_phone: guest_phone || '',
//                 guest_email: guest_email || ''
//             });
//         }
//     });
    
//     if (updates.length === 0) {
//         frappe.msgprint(__('Please enter at least one guest name'));
//         return;
//     }
    
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.update_guest_details_all_rooms',
//         args: {
//             reservation_name: frm.doc.name,
//             guest_updates: updates
//         },
//         callback: function(r) {
//             if (r.message && r.message.success) {
//                 frappe.msgprint({
//                     title: __('Success'),
//                     message: r.message.message,
//                     indicator: 'green'
//                 });
//                 dialog.hide();
//                 frm.reload_doc();
//             } else if (r.message && r.message.error) {
//                 frappe.msgprint({
//                     title: __('Error'),
//                     message: r.message.error,
//                     indicator: 'red'
//                 });
//             }
//         },
//         error: function(err) {
//             frappe.msgprint({
//                 title: __('Error'),
//                 message: __('Failed to save guest details: {0}', [err.message]),
//                 indicator: 'red'
//             });
//         }
//     });
// }


// // ═════════════════════════════════════════════════════════════════════════
// // CHECK IN DIALOG WITH STATUS TRACKING
// // ═════════════════════════════════════════════════════════════════════════

// function show_corporate_checkin_dialog(frm) {
//     /**
//      * Dialog to check in SELECTED rooms
//      * ✅ Shows all rooms with check-in status
//      * ✅ Shows real-time reservation status
//      */
    
//     let d = new frappe.ui.Dialog({
//         title: __('Check In Selected Rooms'),
//         fields: [
//             {
//                 fieldtype: 'HTML',
//                 fieldname: 'info_html',
//                 options: `<div class="alert alert-info">
//                     <strong>Check In Rooms</strong><br>
//                     Select which rooms to check in. Individual invoices will be created for each room.
//                 </div>`
//             },
//             {
//                 fieldname: 'rooms_html',
//                 fieldtype: 'HTML',
//                 options: '<p class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading rooms...</p>'
//             },
//             {
//                 fieldtype: 'Section Break',
//                 label: 'Check-In Notes'
//             },
//             {
//                 fieldname: 'check_in_notes',
//                 fieldtype: 'Small Text',
//                 label: 'Notes (Optional)'
//             }
//         ],
//         size: 'large',
//         primary_action_label: __('Check In Selected'),
//         primary_action: function(values) {
//             let selected = [];
//             d.$wrapper.find('input[type="checkbox"]:checked').each(function() {
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
//             args: {
//                 doctype: 'Hotel Front Desk Reservation',
//                 name: frm.doc.name
//             },
//             callback: function(r) {
//                 if (r.message) {
//                     let fresh_doc = r.message;
//                     let room_numbers = fresh_doc.rooms.map(room => room.room_number);
                    
//                     // Get actual check-ins from database
//                     frappe.call({
//                         method: 'frappe.client.get_list',
//                         args: {
//                             doctype: 'Hotel Room Check In',
//                             filters: {
//                                 'front_desk_reservation': frm.doc.name,
//                                 'room_number': ['in', room_numbers]
//                             },
//                             fields: ['name', 'room_number', 'status']
//                         },
//                         callback: function(r2) {
//                             let checkins_in_db = {};
//                             if (r2.message) {
//                                 r2.message.forEach(res => {
//                                     checkins_in_db[res.room_number] = res.name;
//                                 });
//                             }
                            
//                             // Get reservation statuses
//                             frappe.call({
//                                 method: 'frappe.client.get_list',
//                                 args: {
//                                     doctype: 'Hotel Room Reservation',
//                                     filters: {
//                                         'front_desk_reservation': frm.doc.name,
//                                         'room_number': ['in', room_numbers]
//                                     },
//                                     fields: ['name', 'room_number', 'status']
//                                 },
//                                 callback: function(r3) {
//                                     let reservations_in_db = {};
//                                     if (r3.message) {
//                                         r3.message.forEach(res => {
//                                             reservations_in_db[res.room_number] = res.status;
//                                         });
//                                     }
                                    
//                                     // Build rooms list
//                                     let rooms_list = fresh_doc.rooms.map((room, idx) => ({
//                                         index: idx,
//                                         room_number: room.room_number,
//                                         guest_name: room.guest_name,
//                                         has_checkin: checkins_in_db.hasOwnProperty(room.room_number),
//                                         reservation_status: reservations_in_db[room.room_number] || 'Booked',
//                                         checkin_status: checkins_in_db[room.room_number] ? 'Checked In' : 'Pending'
//                                     }));
                                    
//                                     // Build HTML table
//                                     let html = `
//                                         <table class="table table-bordered table-hover" style="margin: 15px 0;">
//                                             <thead>
//                                                 <tr>
//                                                     <th width="8%"><input type="checkbox" id="select-all-checkin"></th>
//                                                     <th width="20%">Room</th>
//                                                     <th width="30%">Guest Name</th>
//                                                     <th width="20%">Reservation</th>
//                                                     <th width="22%">Check-In Status</th>
//                                                 </tr>
//                                             </thead>
//                                             <tbody>
//                                     `;
                                    
//                                     rooms_list.forEach(function(room) {
//                                         let reservation_badge = `<span class="badge badge-info">${room.reservation_status}</span>`;
//                                         let checkin_badge = room.has_checkin 
//                                             ? '<span class="badge badge-success"><i class="fa fa-check"></i> Checked In</span>'
//                                             : '<span class="badge badge-secondary">Pending</span>';
                                        
//                                         let checkbox_disabled = room.has_checkin ? 'disabled' : '';
                                        
//                                         html += `
//                                             <tr>
//                                                 <td><input type="checkbox" data-room-idx="${room.index}" ${checkbox_disabled}></td>
//                                                 <td><strong>${room.room_number}</strong></td>
//                                                 <td>${room.guest_name || '(No guest name)'}</td>
//                                                 <td>${reservation_badge}</td>
//                                                 <td>${checkin_badge}</td>
//                                             </tr>
//                                         `;
//                                     });
                                    
//                                     html += `
//                                             </tbody>
//                                         </table>
//                                     `;
                                    
//                                     d.fields_dict.rooms_html.$wrapper.html(html);
                                    
//                                     // Select all checkbox
//                                     d.$wrapper.find('#select-all-checkin').on('change', function() {
//                                         d.$wrapper.find('input[type="checkbox"]:not(:disabled)').not(this).prop('checked', this.checked);
//                                     });
//                                 }
//                             });
//                         }
//                     });
//                 }
//             }
//         });
//     }
    
//     let original_show = d.show.bind(d);
//     d.show = function() {
//         fetch_and_render_rooms();
//         original_show();
//     };
    
//     d.show();
// }


// // ═════════════════════════════════════════════════════════════════════════
// // CHECK IN FUNCTIONS
// // ═════════════════════════════════════════════════════════════════════════

// function check_in_selected_rooms_only(frm, room_indices, check_in_notes) {
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms',
//         args: {
//             reservation_name: frm.doc.name,
//             room_indices: room_indices,
//             check_in_notes: check_in_notes
//         },
//         callback: function(r) {
//             if (r.message && r.message.success) {
//                 frappe.msgprint({
//                     title: __('Success'),
//                     message: r.message.message,
//                     indicator: 'green'
//                 });
//                 frm.reload_doc();
//             } else if (r.message && r.message.missing_guest_names) {
//                 frappe.msgprint({
//                     title: __('Guest Names Required'),
//                     message: r.message.message,
//                     indicator: 'orange'
//                 });
//                 setTimeout(function() {
//                     show_edit_guest_data_dialog(frm);
//                 }, 1000);
//             }
//         }
//     });
// }


// function check_in_all_rooms(frm) {
//     frappe.prompt([
//         {
//             fieldname: 'check_in_notes',
//             fieldtype: 'Small Text',
//             label: __('Check-In Notes (Optional)')
//         }
//     ],
//     function(values) {
//         frappe.call({
//             method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_all_rooms',
//             args: {
//                 reservation_name: frm.doc.name,
//                 check_in_notes: values.check_in_notes || ''
//             },
//             callback: function(r) {
//                 if (r.message && r.message.success) {
//                     frappe.msgprint({
//                         title: __('Success'),
//                         message: r.message.message,
//                         indicator: 'green'
//                     });
//                     frm.reload_doc();
//                 } else if (r.message && r.message.missing_guest_names) {
//                     frappe.msgprint({
//                         title: __('Guest Names Required'),
//                         message: r.message.message,
//                         indicator: 'orange'
//                     });
//                     setTimeout(function() {
//                         show_edit_guest_data_dialog(frm);
//                     }, 1000);
//                 }
//             }
//         });
//     },
//     __('Check In All Rooms'),
//     __('Check In')
//     );
// }


// // ═════════════════════════════════════════════════════════════════════════
// // CREATE INVOICE
// // ═════════════════════════════════════════════════════════════════════════

// function create_invoice_for_reservation(frm) {
//     frappe.confirm(
//         __('Create Sales Invoice for ALL rooms in this reservation?'),
//         function() {
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.create_sales_invoice_for_reservation',
//                 args: {
//                     reservation_name: frm.doc.name
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.success) {
//                         frappe.msgprint({
//                             title: __('Success'),
//                             message: r.message.message,
//                             indicator: 'green'
//                         });
//                         frm.reload_doc();
//                     }
//                 }
//             });
//         }
//     );
// }


// // ═════════════════════════════════════════════════════════════════════════
// // PAYMENT DIALOG
// // ═════════════════════════════════════════════════════════════════════════

// function show_payment_dialog(frm) {
//     if (!frm.doc.sales_invoice) {
//         frappe.msgprint(__('No sales invoice linked to this reservation'));
//         return;
//     }
    
//     frappe.call({
//         method: 'frappe.client.get',
//         args: {
//             doctype: 'Sales Invoice',
//             name: frm.doc.sales_invoice
//         },
//         callback: function(r) {
//             if (r.message) {
//                 let invoice = r.message;
                
//                 let d = new frappe.ui.Dialog({
//                     title: __('Pay Invoice {0}', [invoice.name]),
//                     fields: [
//                         {
//                             fieldtype: 'HTML',
//                             fieldname: 'invoice_info',
//                             options: `
//                                 <div class="alert alert-info">
//                                     <p><strong>Invoice Total:</strong> ${format_currency(invoice.grand_total)}</p>
//                                     <p><strong>Outstanding:</strong> ${format_currency(invoice.outstanding_amount)}</p>
//                                 </div>
//                             `
//                         },
//                         {
//                             fieldname: 'payment_amount',
//                             fieldtype: 'Currency',
//                             label: 'Payment Amount',
//                             default: invoice.outstanding_amount,
//                             reqd: 1
//                         },
//                         {
//                             fieldname: 'payment_method',
//                             fieldtype: 'Select',
//                             label: 'Payment Method',
//                             options: 'Card\nCash\nBank Transfer\nCorporate Account\nOther',
//                             default: 'Card',
//                             reqd: 1
//                         }
//                     ],
//                     size: 'small',
//                     primary_action_label: __('Record Payment'),
//                     primary_action: function(values) {
//                         frappe.call({
//                             method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.pay_sales_invoice',
//                             args: {
//                                 invoice_name: frm.doc.sales_invoice,
//                                 amount: values.payment_amount,
//                                 payment_method: values.payment_method
//                             },
//                             callback: function(r) {
//                                 if (r.message && r.message.success) {
//                                     frappe.msgprint({
//                                         title: __('Success'),
//                                         message: r.message.message,
//                                         indicator: 'green'
//                                     });
//                                     d.hide();
//                                     frm.reload_doc();
//                                 }
//                             }
//                         });
//                     }
//                 });
                
//                 d.show();
//             }
//         }
//     });
// }


// // ═════════════════════════════════════════════════════════════════════════
// // HELPER FUNCTIONS
// // ═════════════════════════════════════════════════════════════════════════

// function calculate_nights(frm) {
//     if (frm.doc.from_date && frm.doc.to_date) {
//         let from = frappe.datetime.str_to_obj(frm.doc.from_date);
//         let to = frappe.datetime.str_to_obj(frm.doc.to_date);
//         let nights = frappe.datetime.get_day_diff(to, from);
        
//         if (nights > 0) {
//             frm.set_value('number_of_nights', nights);
            
//             frm.doc.rooms.forEach(function(row) {
//                 frappe.model.set_value(row.doctype, row.name, 'number_of_nights', nights);
//                 if (row.rate_per_night) {
//                     frappe.model.set_value(row.doctype, row.name, 'room_total', 
//                         row.rate_per_night * nights);
//                 }
//             });
            
//             frm.refresh_field('rooms');
//             calculate_total(frm);
//         }
//     }
// }


// function calculate_total(frm) {
//     let subtotal = 0;
    
//     if (frm.doc.rooms) {
//         frm.doc.rooms.forEach(function(row) {
//             if (row.room_total) {
//                 subtotal += row.room_total;
//             }
//         });
//     }
    
//     frm.set_value('subtotal', subtotal);
//     frm.set_value('total_rooms', frm.doc.rooms ? frm.doc.rooms.length : 0);
    
//     let discount_amount = 0;
//     if (frm.doc.discount_type && frm.doc.discount) {
//         if (frm.doc.discount_type === 'Percentage') {
//             discount_amount = (subtotal * frm.doc.discount) / 100;
//         } else if (frm.doc.discount_type === 'Amount') {
//             discount_amount = frm.doc.discount;
//         }
//     }
    
//     frm.set_value('discount_amount', discount_amount);
//     frm.set_value('total_amount', subtotal - discount_amount);
// }


// function fetch_room_rate(frm, row) {
//     frappe.call({
//         method: 'rhohotel.api.get_room_rate',
//         args: {
//             room_type: row.room_type,
//             check_in_date: frm.doc.from_date
//         },
//         callback: function(r) {
//             if (r.message) {
//                 frappe.model.set_value(row.doctype, row.name, 'rate_per_night', r.message);
                
//                 if (frm.doc.number_of_nights) {
//                     frappe.model.set_value(row.doctype, row.name, 'room_total', 
//                         r.message * frm.doc.number_of_nights);
//                 }
                
//                 calculate_total(frm);
//             }
//         }
//     });
// }


// function fetch_corporate_details(frm) {
//     frappe.call({
//         method: 'frappe.client.get',
//         args: {
//             doctype: 'Hotel Guest',
//             name: frm.doc.corporate_guest
//         },
//         callback: function(r) {
//             if (r.message) {
//                 let guest = r.message;
                
//                 if (guest.guest_type !== 'Corporate') {
//                     frappe.msgprint(__('Selected guest is not a corporate client'));
//                     frm.set_value('corporate_guest', '');
//                     return;
//                 }
                
//                 frm.set_value('customer', guest.customer);
//                 frm.set_value('primary_guest_name', guest.hotel_guest_name);
//                 frm.set_value('primary_guest_email', guest.email || '');
//                 frm.set_value('primary_guest_phone', guest.phone_number || '');
//             }
//         }
//     });
// }


// function refresh_available_rooms(frm) {
//     if (frm.doc.from_date && frm.doc.to_date) {
//         frappe.show_alert({
//             message: __('Dates updated. Click "Add Available Rooms" to see availability'),
//             indicator: 'blue'
//         }, 3);
//     }
// }


// function show_available_rooms_dialog(frm) {
//     if (!frm.doc.from_date || !frm.doc.to_date) {
//         frappe.msgprint(__('Please select check-in and check-out dates first'));
//         return;
//     }
    
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_available_rooms',
//         args: {
//             from_date: frm.doc.from_date,
//             to_date: frm.doc.to_date,
//             room_type: frm.doc.filter_by_room_type || null
//         },
//         callback: function(r) {
//             if (r.message && r.message.length > 0) {
//                 show_room_selection_dialog(frm, r.message);
//             } else {
//                 frappe.msgprint(__('No rooms available for selected dates'));
//             }
//         }
//     });
// }


// function show_room_selection_dialog(frm, available_rooms) {
//     let d = new frappe.ui.Dialog({
//         title: __('Select Rooms to Add'),
//         fields: [
//             {
//                 fieldname: 'rooms_html',
//                 fieldtype: 'HTML'
//             }
//         ],
//         primary_action_label: __('Add Selected'),
//         primary_action: function() {
//             let selected = [];
//             d.$wrapper.find('input[type="checkbox"]:checked').each(function() {
//                 let room_number = $(this).data('room');
//                 let room_data = available_rooms.find(r => r.name === room_number);
//                 if (room_data) {
//                     selected.push(room_data);
//                 }
//             });
            
//             if (selected.length === 0) {
//                 frappe.msgprint(__('Please select at least one room'));
//                 return;
//             }
            
//             selected.forEach(function(room) {
//                 let row = frm.add_child('rooms');
//                 row.room_number = room.name;
//                 row.room_type = room.room_type;
//                 row.rate_per_night = room.rate_per_night;
//                 row.number_of_nights = frm.doc.number_of_nights;
//                 row.room_total = room.total_amount;
//             });
            
//             frm.refresh_field('rooms');
//             calculate_total(frm);
//             d.hide();
            
//             frappe.show_alert({
//                 message: __('Added {0} room(s)', [selected.length]),
//                 indicator: 'green'
//             });
//         }
//     });
    
//     let html = `
//         <table class="table table-bordered table-hover" style="margin-top: 10px;">
//             <thead>
//                 <tr>
//                     <th width="10%"><input type="checkbox" id="select-all-rooms"></th>
//                     <th width="20%">Room</th>
//                     <th width="25%">Type</th>
//                     <th width="15%">Floor</th>
//                     <th width="15%">Capacity</th>
//                     <th width="15%">Rate/Night</th>
//                 </tr>
//             </thead>
//             <tbody>
//     `;
    
//     available_rooms.forEach(function(room) {
//         html += `
//             <tr>
//                 <td><input type="checkbox" data-room="${room.name}"></td>
//                 <td><strong>${room.name}</strong></td>
//                 <td>${room.room_type}</td>
//                 <td>${room.floor || 'N/A'}</td>
//                 <td>${room.capacity}</td>
//                 <td>${format_currency(room.rate_per_night)}</td>
//             </tr>
//         `;
//     });
    
//     html += `
//             </tbody>
//         </table>
//     `;
    
//     d.fields_dict.rooms_html.$wrapper.html(html);
    
//     d.$wrapper.find('#select-all-rooms').on('change', function() {
//         d.$wrapper.find('input[type="checkbox"]').not(this).prop('checked', this.checked);
//     });
    
//     d.show();
// }



































// /**
//  * Hotel Front Desk Reservation - Complete Frontend Code
//  * Full implementation of Edit Guest Data, Check-In, and Payment features
//  */

// frappe.ui.form.on('Hotel Front Desk Reservation', {
    
//     // ====================================================================
//     // FORM LIFECYCLE
//     // ====================================================================
    
//     onload: function(frm) {
//         /**
//          * Initialize form on load
//          */
//         set_action_buttons(frm);
//     },
    
//     after_save: function(frm) {
//         /**
//          * Refresh after save
//          */
//         if (frm.doc.docstatus === 1) {
//             set_action_buttons(frm);
//         }
//     },
    
//     // ====================================================================
//     // ACTION BUTTONS
//     // ====================================================================
// });

// function set_action_buttons(frm) {
//     /**
//      * Add action buttons to the form
//      * Only show when form is submitted (docstatus = 1)
//      */
//     if (frm.doc.docstatus !== 1) {
//         return;
//     }
    
//     // Add "Edit Guest Data" button
//     frm.add_custom_button(__('Edit Guest Data'), function() {
//         show_edit_guest_data_dialog(frm);
//     }, __('Actions')).addClass('btn-primary').css('background-color', '#17a2b8');
    
//     // Add "Check In" button
//     frm.add_custom_button(__('Check In Selected Rooms'), function() {
//         show_check_in_dialog(frm);
//     }, __('Actions')).addClass('btn-info');
    
//     // Add "Check In All" button
//     frm.add_custom_button(__('Check In All Rooms'), function() {
//         check_in_all_rooms(frm);
//     }, __('Actions')).addClass('btn-success');
    
//     // Add "Check-In Status" button
//     frm.add_custom_button(__('Check-In Status'), function() {
//         show_check_in_status_dialog(frm);
//     }, __('Actions')).addClass('btn-secondary');
// }

// // ============================================================================
// // EDIT GUEST DATA MODAL
// // ============================================================================

// function show_edit_guest_data_dialog(frm) {
//     /**
//      * Modal to edit guest details for each room
//      * Shows all rooms with 6 editable fields per room
//      * Creates individual customers and guests
//      */
    
//     // Build ALL fields in array FIRST
//     let fields = [
//         {
//             fieldtype: 'HTML',
//             fieldname: 'info_html',
//             options: `<div class="alert alert-info">
//                 <strong>Edit Guest Information</strong><br>
//                 Update guest details for each room. Individual guest records will be created for any edited information.
//             </div>`
//         }
//     ];
    
//     // Add a section for each room with editable fields
//     frm.doc.rooms.forEach(function(room, idx) {
//         fields.push({
//             fieldtype: 'Section Break',
//             label: `Room ${room.room_number}`
//         });
        
//         // Guest Name (required)
//         fields.push({
//             fieldname: `guest_name_${idx}`,
//             fieldtype: 'Data',
//             label: 'Guest Name',
//             default: room.guest_name || '',
//             reqd: 1
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         // Gender
//         fields.push({
//             fieldname: `guest_gender_${idx}`,
//             fieldtype: 'Select',
//             label: 'Gender',
//             options: '\nMale\nFemale\nOther',
//             default: room.guest_gender || 'Male'
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         // ID Type
//         fields.push({
//             fieldname: `guest_id_type_${idx}`,
//             fieldtype: 'Select',
//             label: 'ID Type',
//             options: '\nPassport\nNational ID\nDriver\'s License\nOther',
//             default: room.guest_id_type || ''
//         });
        
//         // ID Number and Phone on same row
//         fields.push({
//             fieldtype: 'Section Break'
//         });
        
//         fields.push({
//             fieldname: `guest_id_number_${idx}`,
//             fieldtype: 'Data',
//             label: 'ID Number',
//             default: room.guest_id_number || ''
//         });
        
//         fields.push({
//             fieldtype: 'Column Break'
//         });
        
//         fields.push({
//             fieldname: `guest_phone_${idx}`,
//             fieldtype: 'Data',
//             label: 'Phone Number',
//             default: room.guest_phone || ''
//         });
        
//         // Email
//         fields.push({
//             fieldtype: 'Section Break'
//         });
        
//         fields.push({
//             fieldname: `guest_email_${idx}`,
//             fieldtype: 'Data',
//             label: 'Email',
//             fieldtype: 'Data',
//             default: room.guest_email || ''
//         });
//     });
    
//     // Create dialog with all fields at once
//     let d = new frappe.ui.Dialog({
//         title: __('Edit Guest Details for Each Room'),
//         fields: fields,
//         size: 'large',
//         primary_action_label: __('Save Guest Details'),
//         primary_action: function(values) {
//             save_guest_details(frm, d);
//         }
//     });
    
//     d.show();
// }

// function save_guest_details(frm, dialog) {
//     /**
//      * Save guest details for all rooms
//      * Calls backend to create/update customers and individual hotel guests
//      * Syncs changes to Hotel Room Reservation
//      */
//     let updates = [];
    
//     frm.doc.rooms.forEach(function(room, idx) {
//         // Get values from dialog
//         let guest_name = dialog.get_value(`guest_name_${idx}`);
//         let guest_gender = dialog.get_value(`guest_gender_${idx}`) || 'Male';
//         let guest_id_type = dialog.get_value(`guest_id_type_${idx}`) || '';
//         let guest_id_number = dialog.get_value(`guest_id_number_${idx}`) || '';
//         let guest_phone = dialog.get_value(`guest_phone_${idx}`) || '';
//         let guest_email = dialog.get_value(`guest_email_${idx}`) || '';
        
//         // Only add to updates if guest has a name
//         if (guest_name && guest_name.trim()) {
//             updates.push({
//                 room_idx: idx,
//                 guest_name: guest_name.trim(),
//                 guest_gender: guest_gender || 'Male',
//                 guest_id_type: guest_id_type || '',
//                 guest_id_number: guest_id_number || '',
//                 guest_phone: guest_phone || '',
//                 guest_email: guest_email || ''
//             });
//         }
//     });
    
//     if (updates.length === 0) {
//         frappe.msgprint(__('Please enter at least one guest name'));
//         return;
//     }
    
//     // Show loading
//     frappe.show_alert({
//         message: __('Saving guest details...'),
//         indicator: 'blue'
//     });
    
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.update_guest_details_all_rooms',
//         args: {
//             reservation_name: frm.doc.name,
//             guest_updates: updates
//         },
//         callback: function(r) {
//             if (r.message && r.message.success) {
//                 frappe.msgprint({
//                     title: __('Success'),
//                     message: r.message.message,
//                     indicator: 'green'
//                 });
//                 dialog.hide();
//                 frm.reload_doc();
//             } else if (r.message && r.message.error) {
//                 frappe.msgprint({
//                     title: __('Error'),
//                     message: r.message.error,
//                     indicator: 'red'
//                 });
//             }
//         },
//         error: function(err) {
//             frappe.msgprint({
//                 title: __('Error'),
//                 message: __('Failed to save guest details. Please try again.'),
//                 indicator: 'red'
//             });
//         }
//     });
// }

// // ============================================================================
// // CHECK-IN FUNCTIONALITY
// // ============================================================================

// function show_check_in_dialog(frm) {
//     /**
//      * Dialog to select rooms for check-in
//      * Shows checkboxes for each room
//      */
    
//     // Get check-in status
//     get_check_in_status(frm.doc.name, function(statuses) {
//         let html = `
//             <div class="container">
//                 <div class="row mb-3">
//                     <div class="col-md-12">
//                         <h6>Select Rooms to Check In</h6>
//                     </div>
//                 </div>
//                 <div class="row">
//         `;
        
//         statuses.forEach(function(status, idx) {
//             let checked = status.is_checked_in ? 'checked disabled' : '';
//             let badge = status.is_checked_in ? '<span class="badge badge-success">✓ Checked In</span>' : '<span class="badge badge-warning">Pending</span>';
            
//             html += `
//                 <div class="col-md-6 mb-2">
//                     <div class="form-check">
//                         <input class="form-check-input room-checkbox" type="checkbox" 
//                                id="room_${idx}" value="${idx}" ${checked}>
//                         <label class="form-check-label" for="room_${idx}">
//                             <strong>${status.room_number}</strong> - ${status.guest_name || 'No Guest'} 
//                             ${badge}
//                         </label>
//                     </div>
//                 </div>
//             `;
//         });
        
//         html += `
//                 </div>
//             </div>
//         `;
        
//         let d = new frappe.ui.Dialog({
//             title: __('Select Rooms to Check In'),
//             fields: [
//                 {
//                     fieldtype: 'HTML',
//                     fieldname: 'rooms_html',
//                     options: html
//                 }
//             ],
//             size: 'large',
//             primary_action_label: __('Check In Selected'),
//             primary_action: function() {
//                 let selected = [];
//                 document.querySelectorAll('.room-checkbox:checked').forEach(function(checkbox) {
//                     selected.push(parseInt(checkbox.value));
//                 });
                
//                 if (selected.length === 0) {
//                     frappe.msgprint(__('Please select at least one room'));
//                     return;
//                 }
                
//                 d.hide();
//                 perform_check_in(frm, selected);
//             }
//         });
        
//         d.show();
//     });
// }

// function get_check_in_status(reservation_name, callback) {
//     /**
//      * Get check-in status for all rooms
//      */
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_check_in_status',
//         args: {
//             reservation_name: reservation_name
//         },
//         callback: function(r) {
//             if (r.message) {
//                 callback(r.message);
//             }
//         }
//     });
// }

// function perform_check_in(frm, room_indices) {
//     /**
//      * Perform check-in for selected rooms
//      */
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms',
//         args: {
//             reservation_name: frm.doc.name,
//             room_indices: room_indices
//         },
//         callback: function(r) {
//             if (r.message && r.message.success) {
//                 frappe.msgprint({
//                     title: __('Success'),
//                     message: r.message.message,
//                     indicator: 'green'
//                 });
//                 frm.reload_doc();
//             } else if (r.message && r.message.error) {
//                 frappe.msgprint({
//                     title: __('Error'),
//                     message: r.message.error,
//                     indicator: 'red'
//                 });
//             }
//         },
//         error: function(err) {
//             frappe.msgprint({
//                 title: __('Error'),
//                 message: __('Check-in failed. Please try again.'),
//                 indicator: 'red'
//             });
//         }
//     });
// }

// function check_in_all_rooms(frm) {
//     /**
//      * Check-in all rooms at once
//      */
//     frappe.confirm(
//         __('Check in ALL rooms?'),
//         function() {
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_all_rooms',
//                 args: {
//                     reservation_name: frm.doc.name
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.success) {
//                         frappe.msgprint({
//                             title: __('Success'),
//                             message: r.message.message,
//                             indicator: 'green'
//                         });
//                         frm.reload_doc();
//                     } else if (r.message && r.message.error) {
//                         frappe.msgprint({
//                             title: __('Error'),
//                             message: r.message.error,
//                             indicator: 'red'
//                         });
//                     }
//                 }
//             });
//         }
//     );
// }

// function show_check_in_status_dialog(frm) {
//     /**
//      * Show check-in status for all rooms
//      */
//     get_check_in_status(frm.doc.name, function(statuses) {
//         let html = `
//             <table class="table table-bordered">
//                 <thead>
//                     <tr>
//                         <th>Room</th>
//                         <th>Guest Name</th>
//                         <th>Status</th>
//                     </tr>
//                 </thead>
//                 <tbody>
//         `;
        
//         statuses.forEach(function(status) {
//             let badge = status.is_checked_in 
//                 ? '<span class="badge badge-success">✓ Checked In</span>'
//                 : '<span class="badge badge-warning">Pending</span>';
            
//             html += `
//                 <tr>
//                     <td><strong>${status.room_number}</strong></td>
//                     <td>${status.guest_name || 'No Guest'}</td>
//                     <td>${badge}</td>
//                 </tr>
//             `;
//         });
        
//         html += `
//                 </tbody>
//             </table>
//         `;
        
//         let d = new frappe.ui.Dialog({
//             title: __('Check-In Status'),
//             fields: [
//                 {
//                     fieldtype: 'HTML',
//                     fieldname: 'status_html',
//                     options: html
//                 }
//             ],
//             size: 'large'
//         });
        
//         d.show();
//     });
// }

// // ============================================================================
// // PAYMENT FUNCTIONALITY
// // ============================================================================

// function show_payment_dialog(invoice_name) {
//     /**
//      * Dialog to record payment for an invoice
//      */
//     let d = new frappe.ui.Dialog({
//         title: __('Record Payment'),
//         fields: [
//             {
//                 fieldname: 'invoice_name',
//                 fieldtype: 'Link',
//                 label: 'Invoice',
//                 options: 'Sales Invoice',
//                 default: invoice_name,
//                 read_only: 1
//             },
//             {
//                 fieldname: 'amount_paid',
//                 fieldtype: 'Currency',
//                 label: 'Amount Paid',
//                 reqd: 1
//             },
//             {
//                 fieldname: 'transaction_id',
//                 fieldtype: 'Data',
//                 label: 'Transaction ID (optional)',
//                 description: 'e.g., Paystack reference'
//             }
//         ],
//         size: 'small',
//         primary_action_label: __('Record Payment'),
//         primary_action: function(values) {
//             record_payment(invoice_name, values.amount_paid, values.transaction_id, d);
//         }
//     });
    
//     d.show();
// }

// function record_payment(invoice_name, amount_paid, transaction_id, dialog) {
//     /**
//      * Record payment for invoice
//      */
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.pay_sales_invoice',
//         args: {
//             invoice_name: invoice_name,
//             amount_paid: amount_paid,
//             transaction_id: transaction_id
//         },
//         callback: function(r) {
//             if (r.message && r.message.success) {
//                 frappe.msgprint({
//                     title: __('Success'),
//                     message: r.message.message,
//                     indicator: 'green'
//                 });
//                 dialog.hide();
//             } else if (r.message && r.message.error) {
//                 frappe.msgprint({
//                     title: __('Error'),
//                     message: r.message.error,
//                     indicator: 'red'
//                 });
//             }
//         }
//     });
// }

// // ============================================================================
// // UTILITY FUNCTIONS
// // ============================================================================

// function show_reservation_summary(frm) {
//     /**
//      * Show summary of reservation
//      */
//     frappe.call({
//         method: 'rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.get_reservation_summary',
//         args: {
//             reservation_name: frm.doc.name
//         },
//         callback: function(r) {
//             if (r.message) {
//                 let summary = r.message;
//                 let html = `
//                     <table class="table">
//                         <tr>
//                             <th>Total Rooms</th>
//                             <td>${summary.total_rooms}</td>
//                         </tr>
//                         <tr>
//                             <th>Checked In</th>
//                             <td>${summary.checked_in_rooms}</td>
//                         </tr>
//                         <tr>
//                             <th>Pending</th>
//                             <td>${summary.pending_rooms}</td>
//                         </tr>
//                         <tr>
//                             <th>Total Amount</th>
//                             <td>${frappe.format(summary.total_amount, {fieldtype: 'Currency'})}</td>
//                         </tr>
//                         <tr>
//                             <th>Total Discount</th>
//                             <td>${frappe.format(summary.total_discount, {fieldtype: 'Currency'})}</td>
//                         </tr>
//                         <tr>
//                             <th><strong>Net Total</strong></th>
//                             <td><strong>${frappe.format(summary.net_total, {fieldtype: 'Currency'})}</strong></td>
//                         </tr>
//                     </table>
//                 `;
                
//                 let d = new frappe.ui.Dialog({
//                     title: __('Reservation Summary'),
//                     fields: [
//                         {
//                             fieldtype: 'HTML',
//                             fieldname: 'summary_html',
//                             options: html
//                         }
//                     ]
//                 });
                
//                 d.show();
//             }
//         }
//     });
// }