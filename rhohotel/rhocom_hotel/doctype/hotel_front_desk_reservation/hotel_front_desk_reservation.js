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
            }, __('Check In')).css({'background-color': '#28a745', 'color': 'white'});
            
            // Button 2: Check in SELECTED rooms (automatically creates reservations)
            frm.add_custom_button(__('Check In Selected Rooms'), function() {
                show_corporate_checkin_dialog(frm);
            }, __('Check In'));
            
            // Button 3: Create Invoice button for corporate bookings
            if (!frm.doc.sales_invoice) {
                frm.add_custom_button(__('Create Invoice'), function() {
                    create_invoice_for_reservation(frm);
                }, __('Actions')).css({'background-color': '#28a745', 'color': 'white'});
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