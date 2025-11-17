// Hotel Reservation Guest Profile - Frontend JavaScript
// File: rhohotel/public/js/hotel_reservation_guest_profile.js

frappe.ui.form.on('Hotel Reservation Guest Profile', {
    // Form Load Event
    onload: function(frm) {
        // Load linked reservation details automatically
        load_reservation_details(frm);
        
        // Hide fields that are populated from reservation
        if (frm.doc.hotel_reservation) {
            frm.set_df_property('room_number', 'read_only', 1);
            frm.set_df_property('check_in_date', 'read_only', 1);
            frm.set_df_property('check_out_date', 'read_only', 1);
        }
    },

    // Form Refresh Event
    refresh: function(frm) {
        add_custom_buttons(frm);
        update_read_only_fields(frm);
        
        // Show guest status
        if (frm.doc.is_checked_in && !frm.doc.is_checked_out) {
            frm.page.set_indicator('Checked In', 'green');
        } else if (frm.doc.is_checked_out) {
            frm.page.set_indicator('Checked Out', 'orange');
        } else {
            frm.page.set_indicator('Pending Check-In', 'blue');
        }
    },

    // When Hotel Reservation is selected
    hotel_reservation: function(frm) {
        if (frm.doc.hotel_reservation) {
            load_reservation_details(frm);
        }
    },

    // When First Name changes
    first_name: function(frm) {
        update_profile_title(frm);
    },

    // When Last Name changes
    last_name: function(frm) {
        update_profile_title(frm);
    },

    // Calculate guest count when adults/children changes
    adults: function(frm) {
        calculate_guest_count(frm);
    },

    children: function(frm) {
        calculate_guest_count(frm);
    },

    // Validate form before save
    validate: function(frm) {
        validate_guest_profile(frm);
    },

    // Before Save
    before_save: function(frm) {
        // Ensure created_at is set
        if (!frm.doc.created_at) {
            frm.set_value('created_at', frappe.datetime.now_datetime());
        }
        
        // Set created_by_user
        if (!frm.doc.created_by_user) {
            frm.set_value('created_by_user', frappe.session.user);
        }
    },

    // After Save
    after_save: function(frm) {
        frappe.msgprint({
            title: __('Guest Profile Saved'),
            indicator: 'green',
            message: __('Guest profile for {0} has been saved successfully', [frm.doc.first_name + ' ' + frm.doc.last_name])
        });
    }
});

// ============================================================================
// CUSTOM FUNCTIONS
// ============================================================================

/**
 * Load reservation details from Hotel Room Reservation
 */
function load_reservation_details(frm) {
    if (frm.doc.hotel_reservation) {
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Hotel Room Reservation',
                name: frm.doc.hotel_reservation
            },
            callback: function(r) {
                if (r.message) {
                    const reservation = r.message;
                    
                    // Set read-only fields from reservation
                    frm.set_value('room_number', reservation.room_number);
                    frm.set_value('check_in_date', reservation.from_date);
                    frm.set_value('check_out_date', reservation.to_date);
                    frm.set_value('booking_number', reservation.booking_number);
                    frm.set_value('payment_status', reservation.payment_status || 'Pending');
                    
                    // Get booking details for guest count
                    if (reservation.booking_number) {
                        frappe.call({
                            method: 'rhohotel.rhohotel.hotel_booking.get_booking_details',
                            args: {
                                booking_number: reservation.booking_number
                            },
                            callback: function(booking_response) {
                                if (booking_response.message) {
                                    frm.set_value('guest_count', booking_response.message.total_rooms);
                                    frm.set_value('paid_amount', booking_response.message.total_price);
                                }
                            }
                        });
                    }
                    
                    frm.refresh_field('room_number');
                    frm.refresh_field('check_in_date');
                    frm.refresh_field('check_out_date');
                    frm.refresh_field('booking_number');
                    frm.refresh_field('payment_status');
                }
            }
        });
    }
}

/**
 * Update profile title based on first and last name
 */
function update_profile_title(frm) {
    if (frm.doc.first_name && frm.doc.last_name) {
        frm.set_df_property('profile_id', 'hidden', 0);
    }
}

/**
 * Calculate total guest count (adults + children)
 */
function calculate_guest_count(frm) {
    const adults = frm.doc.adults || 0;
    const children = frm.doc.children || 0;
    const total = adults + children;
    
    if (total > 0) {
        frm.set_value('guest_count', total);
    }
}

/**
 * Add custom buttons to the form
 */
function add_custom_buttons(frm) {
    // Check-In Button
    if (!frm.doc.is_checked_in && !frm.is_new()) {
        frm.add_custom_button(__('Check-In Guest'), function() {
            check_in_guest(frm);
        }, __('Actions'));
    }
    
    // Check-Out Button
    if (frm.doc.is_checked_in && !frm.doc.is_checked_out) {
        frm.add_custom_button(__('Check-Out Guest'), function() {
            check_out_guest(frm);
        }, __('Actions'));
    }
    
    // View Reservation
    if (frm.doc.hotel_reservation) {
        frm.add_custom_button(__('View Reservation'), function() {
            frappe.set_route('Form', 'Hotel Room Reservation', frm.doc.hotel_reservation);
        }, __('Links'));
    }
    
    // View Booking
    if (frm.doc.booking_number) {
        frm.add_custom_button(__('View Booking'), function() {
            frappe.set_route('Form', 'Hotel Booking', frm.doc.booking_number);
        }, __('Links'));
    }
    
    // View Customer
    if (frm.doc.customer_link) {
        frm.add_custom_button(__('View Customer'), function() {
            frappe.set_route('Form', 'Customer', frm.doc.customer_link);
        }, __('Links'));
    }
}

/**
 * Check-in guest
 */
function check_in_guest(frm) {
    frappe.confirm(
        __('Check in {0} {1}?', [frm.doc.first_name, frm.doc.last_name]),
        function() {
            // Call backend check-in function
            frappe.call({
                method: 'rhohotel.rhohotel.api.check_in_booking',
                args: {
                    booking_number: frm.doc.booking_number
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frm.set_value('is_checked_in', 1);
                        frm.set_value('check_in_time', r.message.check_in_time);
                        frm.save();
                        
                        frappe.msgprint({
                            title: __('Check-In Successful'),
                            indicator: 'green',
                            message: __('Guest {0} {1} checked in at {2}', 
                                [frm.doc.first_name, frm.doc.last_name, r.message.check_in_time])
                        });
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: r.message ? r.message.message : __('Failed to check in guest')
                        });
                    }
                },
                error: function(r) {
                    frappe.msgprint({
                        title: __('Error'),
                        indicator: 'red',
                        message: __('Error checking in guest')
                    });
                }
            });
        }
    );
}

/**
 * Check-out guest
 */
function check_out_guest(frm) {
    frappe.confirm(
        __('Check out {0} {1}?', [frm.doc.first_name, frm.doc.last_name]),
        function() {
            // Call backend check-out function
            frappe.call({
                method: 'rhohotel.rhohotel.api.check_out_booking',
                args: {
                    booking_number: frm.doc.booking_number
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frm.set_value('is_checked_out', 1);
                        frm.set_value('check_out_time', r.message.check_out_time);
                        frm.save();
                        
                        frappe.msgprint({
                            title: __('Check-Out Successful'),
                            indicator: 'green',
                            message: __('Guest {0} {1} checked out at {2}', 
                                [frm.doc.first_name, frm.doc.last_name, r.message.check_out_time])
                        });
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: r.message ? r.message.message : __('Failed to check out guest')
                        });
                    }
                },
                error: function(r) {
                    frappe.msgprint({
                        title: __('Error'),
                        indicator: 'red',
                        message: __('Error checking out guest')
                    });
                }
            });
        }
    );
}

/**
 * Update read-only fields based on status
 */
function update_read_only_fields(frm) {
    // If checked out, make all fields read-only
    if (frm.doc.is_checked_out) {
        frm.set_df_property('first_name', 'read_only', 1);
        frm.set_df_property('last_name', 'read_only', 1);
        frm.set_df_property('email', 'read_only', 1);
        frm.set_df_property('phone', 'read_only', 1);
        frm.set_df_property('special_requests', 'read_only', 1);
        frm.set_df_property('dietary_requirements', 'read_only', 1);
    }
    
    frm.refresh_field('first_name');
    frm.refresh_field('last_name');
    frm.refresh_field('email');
    frm.refresh_field('phone');
}

/**
 * Validate guest profile before save
 */
function validate_guest_profile(frm) {
    // Validate required fields
    if (!frm.doc.first_name || !frm.doc.last_name) {
        frappe.throw(__('First Name and Last Name are required'));
    }
    
    // Validate email if provided
    if (frm.doc.email && !frm.doc.email.includes('@')) {
        frappe.throw(__('Please enter a valid email address'));
    }
    
    // Validate ID expiry date if ID type is provided
    if (frm.doc.id_type && frm.doc.id_expiry_date) {
        const today = frappe.datetime.get_today();
        if (frm.doc.id_expiry_date < today) {
            frappe.msgprint({
                title: __('Warning'),
                indicator: 'orange',
                message: __('ID has expired. Please verify with guest.')
            });
        }
    }
    
    // Validate adults/children counts
    if (frm.doc.adults < 1) {
        frappe.throw(__('At least 1 adult is required'));
    }
}

// ============================================================================
// LIST VIEW CUSTOMIZATIONS
// ============================================================================

frappe.listview_settings['Hotel Reservation Guest Profile'] = {
    colwidth: {
        first_name: 2,
        last_name: 2,
        email: 2.5,
        room_number: 1.5,
        check_in_date: 1.5,
        check_out_date: 1.5,
        payment_status: 1.5
    },
    filters: [
        ["Hotel Reservation Guest Profile", "is_checked_in", "=", 0],
    ],
    get_indicator: function(doc) {
        if (doc.is_checked_out) {
            return [__("Checked Out"), "orange"];
        } else if (doc.is_checked_in) {
            return [__("Checked In"), "green"];
        } else {
            return [__("Pending Check-In"), "blue"];
        }
    }
};

// ============================================================================
// REPORT / QUERY REPORT
// ============================================================================

frappe.pages['guest-profile-checkin'] = frappe.pages['guest-profile-checkin'] || {};

frappe.pages['guest-profile-checkin'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Guest Check-In/Check-Out',
        single_column: true
    });
    
    page.add_inner_button(__("Search Guest"), function() {
        search_guest_for_checkin(page);
    });
};

function search_guest_for_checkin(page) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Hotel Reservation Guest Profile',
            filters: {
                is_checked_in: 0,
                is_checked_out: 0
            },
            fields: ['name', 'first_name', 'last_name', 'room_number', 'check_in_date', 'email'],
            order_by: 'check_in_date desc',
            limit_page_length: 100
        },
        callback: function(r) {
            if (r.message) {
                show_checkin_list(page, r.message);
            }
        }
    });
}

function show_checkin_list(page, guests) {
    page.clear_inner_page();
    
    const html = `
        <div class="row">
            <div class="col-md-12">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Room</th>
                            <th>Check-In Date</th>
                            <th>Email</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="guest-list">
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    page.$inner.append(html);
    
    const tbody = page.$inner.find('#guest-list');
    guests.forEach(guest => {
        const row = `
            <tr>
                <td><strong>${guest.first_name} ${guest.last_name}</strong></td>
                <td>${guest.room_number || '-'}</td>
                <td>${frappe.datetime.str_to_user(guest.check_in_date)}</td>
                <td>${guest.email || '-'}</td>
                <td>
                    <button class="btn btn-primary btn-sm" onclick="frappe.set_route('Form', 'Hotel Reservation Guest Profile', '${guest.name}')">
                        View & Check-In
                    </button>
                </td>
            </tr>
        `;
        tbody.append(row);
    });
}