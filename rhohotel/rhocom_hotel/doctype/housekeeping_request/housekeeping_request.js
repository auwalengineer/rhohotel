frappe.ui.form.on('Housekeeping Request', {
    onload: function(frm) {
        // Set request_date to today when form is loaded (if new form)
        if (frm.doc.__islocal) {
            frm.set_value('request_date', frappe.datetime.get_today());
        }
        
        // Set filter for room field to only show occupied rooms
        frm.set_df_property('room', 'get_query', function() {
            return {
                filters: {
                    "status": "Occupied"
                }
            }
        });
    },
    
    refresh: function(frm) {
        // Show Approve button only if:
        // 1. Document is submitted (docstatus === 1)
        // 2. Status is not already Approved
        // 3. User has Hotel Manager role
        if (frm.doc.docstatus === 1 && 
            frm.doc.status !== 'Approved' && 
            frappe.user.has_role('Hotel Manager')) {
            
            frm.add_custom_button(__('Approve'), function() {
                frappe.call({
                    method: 'rhohotel.rhocom_hotel.doctype.housekeeping_request.housekeeping_request.approve_housekeeping_request',
                    args: {
                        request_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frm.reload_doc();
                            frappe.msgprint({
                                message: __('Request approved successfully'),
                                title: __('Approved'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            });
        }
    },
    
    room: function(frm) {
        // When room is selected, fetch the guest name from the room's current guest
        if (frm.doc.room) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Hotel Room',
                    name: frm.doc.room
                },
                callback: function(r) {
                    if (r.message) {
                        // Validate that room is occupied
                        if (r.message.status !== 'Occupied') {
                            frappe.msgprint({
                                title: __('Invalid Room'),
                                message: __('Only occupied rooms can have housekeeping requests'),
                                indicator: 'red'
                            });
                            frm.set_value('room', '');
                            return;
                        }
                        
                        let current_guest_id = r.message.current_guest;
                        
                        if (current_guest_id) {
                            frappe.call({
                                method: 'frappe.client.get',
                                args: {
                                    doctype: 'Hotel Guest',
                                    name: current_guest_id
                                },
                                callback: function(guest_r) {
                                    if (guest_r.message) {
                                        frm.set_value('guest_name', guest_r.message.hotel_guest_name);
                                    }
                                }
                            });
                        } else {
                            frm.set_value('guest_name', '');
                            frappe.msgprint('No guest currently in this room');
                        }
                    }
                }
            });
        }
    },
    
    before_save: function(frm) {
        // Final validation before saving
        if (frm.doc.room) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Hotel Room',
                    name: frm.doc.room
                },
                async: false,
                callback: function(r) {
                    if (r.message && r.message.status !== 'Occupied') {
                        frappe.throw(__('Only occupied rooms can have housekeeping requests'));
                    }
                }
            });
        }
    },
    
    after_submit: function(frm) {
        frm.reload_doc();
    }
});