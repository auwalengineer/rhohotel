// // Copyright (c) 2024, Rhocom Technologies and contributors
// // For license information, please see license.txt

// frappe.ui.form.on("Corporate Check In", {
//     refresh(frm) {
//         // Set filter for corporate guests only
//         frm.set_query("corporate_guest", function() {
//             return {
//                 filters: {
//                     "guest_type": "Corporate"
//                 }
//             };
//         });
        
//         // Show individual check-ins if submitted
//         if (frm.doc.docstatus === 1) {
//             frm.add_custom_button(__('View Check-Ins'), function() {
//                 frappe.route_options = {
//                     "corporate_check_in": frm.doc.name
//                 };
//                 frappe.set_route("List", "Hotel Room Check In");
//             });
            
//             frm.add_custom_button(__('View Invoice'), function() {
//                 frappe.call({
//                     method: 'frappe.client.get_list',
//                     args: {
//                         doctype: 'Sales Invoice',
//                         filters: {
//                             'custom_corporate_check_in': frm.doc.name
//                         },
//                         fields: ['name'],
//                         limit: 1
//                     },
//                     callback: function(r) {
//                         if (r.message && r.message.length > 0) {
//                             frappe.set_route("Form", "Sales Invoice", r.message[0].name);
//                         } else {
//                             frappe.msgprint(__('No invoice found'));
//                         }
//                     }
//                 });
//             });
//         }
//     },
    
//     check_in_datetime(frm) {
//         frm.trigger('calculate_check_out');
//         frm.trigger('refresh_room_filters');
//     },
    
//     expected_check_out_datetime(frm) {
//         frm.trigger('refresh_room_filters');
//     },
    
//     filter_by_room_type(frm) {
//         frm.trigger('refresh_room_filters');
//     },
    
//     refresh_room_filters(frm) {
//         // This will update the room selection query in child table
//         frm.fields_dict.rooms.grid.get_field('room_number').get_query = function(doc, cdt, cdn) {
//             let filters = {
//                 "status": "Vacant",
//                 "housekeeping_status": "Clean"
//             };
            
//             if (doc.filter_by_room_type) {
//                 filters["room_type"] = doc.filter_by_room_type;
//             }
            
//             return {
//                 filters: filters
//             };
//         };
        
//         frm.refresh_field('rooms');
//     },
    
//     number_of_nights(frm) {
//         frm.trigger('calculate_check_out');
//         frm.trigger('calculate_totals');
//     },
    
//     calculate_check_out(frm) {
//         if (frm.doc.check_in_datetime && frm.doc.number_of_nights) {
//             let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
//             let new_checkout = frappe.datetime.add_days(check_in, frm.doc.number_of_nights);
            
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time',
//                 callback: function(r) {
//                     if (r.message) {
//                         let date_str = frappe.datetime.obj_to_str(new_checkout);
//                         new_checkout = date_str + " " + r.message;
//                     }
//                     frm.set_value('expected_check_out_datetime', new_checkout);
//                 }
//             });
//         }
//     },
    
//     discount_type(frm) {
//         frm.trigger('calculate_totals');
//     },
    
//     discount(frm) {
//         frm.trigger('calculate_totals');
//     },
    
//     calculate_totals(frm) {
//         let total_room_charges = 0;
        
//         (frm.doc.rooms || []).forEach(function(room) {
//             if (room.rate_amount && frm.doc.number_of_nights) {
//                 let room_total = flt(room.rate_amount) * flt(frm.doc.number_of_nights);
//                 frappe.model.set_value(room.doctype, room.name, 'total_amount', room_total);
//                 total_room_charges += room_total;
//             }
//         });
        
//         frm.set_value('total_room_charges', total_room_charges);
        
//         let discount_amount = 0;
//         if (frm.doc.discount_type === "Percentage") {
//             discount_amount = (total_room_charges * flt(frm.doc.discount)) / 100;
//         } else if (frm.doc.discount_type === "Amount") {
//             discount_amount = flt(frm.doc.discount);
            
//             // Validate discount
//             if (discount_amount > total_room_charges) {
//                 frappe.msgprint(__('Discount amount cannot exceed total room charges'));
//                 frm.set_value('discount', 0);
//                 discount_amount = 0;
//             }
//         }
        
//         frm.set_value('discount_amount', discount_amount);
//         frm.set_value('total_charges', total_room_charges - discount_amount);
//     }
// });

// frappe.ui.form.on("Corporate Check In Room", {
//     rooms_add(frm, cdt, cdn) {
//         // Set initial query for room selection
//         frm.trigger('refresh_room_filters');
//     },
    
//     room_number(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
        
//         if (row.room_number && frm.doc.check_in_datetime) {
//             // Fetch room type
//             frappe.call({
//                 method: 'frappe.client.get_value',
//                 args: {
//                     doctype: 'Hotel Room',
//                     filters: {name: row.room_number},
//                     fieldname: ['room_type']
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.room_type) {
//                         frappe.model.set_value(cdt, cdn, 'room_type', r.message.room_type);
                        
//                         // Fetch rate automatically
//                         frappe.call({
//                             method: 'rhohotel.api.get_room_rate',
//                             args: {
//                                 room_type: r.message.room_type,
//                                 rate_type: "",
//                                 check_in_date: frm.doc.check_in_datetime.split(" ")[0]
//                             },
//                             callback: function(rate_response) {
//                                 if (rate_response.message && !rate_response.message.error) {
//                                     frappe.model.set_value(cdt, cdn, 'rate_amount', rate_response.message);
                                    
//                                     // Calculate total for this room
//                                     if (frm.doc.number_of_nights) {
//                                         let room_total = flt(rate_response.message) * flt(frm.doc.number_of_nights);
//                                         frappe.model.set_value(cdt, cdn, 'total_amount', room_total);
//                                     }
                                    
//                                     frm.trigger('calculate_totals');
//                                 } else {
//                                     frappe.msgprint(__('Unable to fetch rate for this room type'));
//                                 }
//                             }
//                         });
//                     }
//                 }
//             });
//         }
//     },
    
//     rate_amount(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
        
//         // Recalculate room total
//         if (row.rate_amount && frm.doc.number_of_nights) {
//             let room_total = flt(row.rate_amount) * flt(frm.doc.number_of_nights);
//             frappe.model.set_value(cdt, cdn, 'total_amount', room_total);
//         }
        
//         frm.trigger('calculate_totals');
//     },
    
//     rooms_remove(frm) {
//         frm.trigger('calculate_totals');
//     }
// });






// Copyright (c) 2024, Rhocom Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Corporate Check In", {
    refresh(frm) {
        // Set filter for corporate guests only
        frm.set_query("corporate_guest", function() {
            return {
                filters: {
                    "guest_type": "Corporate"
                }
            };
        });
        
        // Show individual check-ins if submitted
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('View Check-Ins'), function() {
                frappe.route_options = {
                    "corporate_check_in": frm.doc.name
                };
                frappe.set_route("List", "Hotel Room Check In");
            });
            
            frm.add_custom_button(__('View Invoice'), function() {
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Sales Invoice',
                        filters: {
                            'custom_corporate_check_in': frm.doc.name
                        },
                        fields: ['name'],
                        limit: 1
                    },
                    callback: function(r) {
                        if (r.message && r.message.length > 0) {
                            frappe.set_route("Form", "Sales Invoice", r.message[0].name);
                        } else {
                            frappe.msgprint(__('No invoice found'));
                        }
                    }
                });
            });
        }
    },
    
    check_in_datetime(frm) {
        frm.trigger('calculate_nights_and_refresh'); // CHANGED
    },
    
    expected_check_out_datetime(frm) {
        frm.trigger('calculate_nights_and_refresh'); // CHANGED
    },
    
    // NEW METHOD
    calculate_nights_and_refresh(frm) {
        if (frm.doc.check_in_datetime && frm.doc.expected_check_out_datetime) {
            let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
            let check_out = frappe.datetime.str_to_obj(frm.doc.expected_check_out_datetime);
            
            // Calculate number of nights
            let nights = frappe.datetime.get_day_diff(check_out, check_in);
            
            if (nights > 0) {
                frm.set_value('number_of_nights', nights);
                
                // Refresh room rates for all existing rooms
                frm.trigger('refresh_all_room_rates');
            } else if (nights <= 0) {
                frappe.msgprint(__('Check-out date must be after check-in date'));
                frm.set_value('number_of_nights', 0);
            }
        }
        
        frm.trigger('refresh_room_filters');
    },
    
    // NEW METHOD
    refresh_all_room_rates(frm) {
        // Refresh rates for all rooms in the child table
        if (frm.doc.rooms && frm.doc.check_in_datetime) {
            frm.doc.rooms.forEach(function(room) {
                if (room.room_number && room.room_type) {
                    fetch_and_update_room_rate(frm, room.doctype, room.name, room.room_type);
                }
            });
        }
    },
    
    filter_by_room_type(frm) {
        frm.trigger('refresh_room_filters');
    },
    
    refresh_room_filters(frm) {
        // This will update the room selection query in child table
        frm.fields_dict.rooms.grid.get_field('room_number').get_query = function(doc, cdt, cdn) {
            let filters = {
                "status": "Vacant",
                "housekeeping_status": "Clean"
            };
            
            if (doc.filter_by_room_type) {
                filters["room_type"] = doc.filter_by_room_type;
            }
            
            return {
                filters: filters
            };
        };
        
        frm.refresh_field('rooms');
    },
    
    number_of_nights(frm) {
        frm.trigger('calculate_totals'); // CHANGED - removed calculate_check_out
    },
    
    // REMOVED calculate_check_out method entirely
    
    discount_type(frm) {
        frm.trigger('calculate_totals');
    },
    
    discount(frm) {
        frm.trigger('calculate_totals');
    },
    
    calculate_totals(frm) {
        let total_room_charges = 0;
        
        (frm.doc.rooms || []).forEach(function(room) {
            if (room.rate_amount && frm.doc.number_of_nights) {
                let room_total = flt(room.rate_amount) * flt(frm.doc.number_of_nights);
                frappe.model.set_value(room.doctype, room.name, 'total_amount', room_total);
                total_room_charges += room_total;
            }
        });
        
        frm.set_value('total_room_charges', total_room_charges);
        
        let discount_amount = 0;
        if (frm.doc.discount_type === "Percentage") {
            discount_amount = (total_room_charges * flt(frm.doc.discount)) / 100;
        } else if (frm.doc.discount_type === "Amount") {
            discount_amount = flt(frm.doc.discount);
            
            // Validate discount
            if (discount_amount > total_room_charges) {
                frappe.msgprint(__('Discount amount cannot exceed total room charges'));
                frm.set_value('discount', 0);
                discount_amount = 0;
            }
        }
        
        frm.set_value('discount_amount', discount_amount);
        frm.set_value('total_charges', total_room_charges - discount_amount);
    }
});

frappe.ui.form.on("Corporate Check In Room", {
    rooms_add(frm, cdt, cdn) {
        // Set initial query for room selection
        frm.trigger('refresh_room_filters');
    },
    
    room_number(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        if (row.room_number && frm.doc.check_in_datetime) {
            // ADDED validation
            if (!frm.doc.expected_check_out_datetime) {
                frappe.msgprint(__('Please set check-out date first'));
                frappe.model.set_value(cdt, cdn, 'room_number', '');
                return;
            }
            
            if (!frm.doc.number_of_nights || frm.doc.number_of_nights <= 0) {
                frappe.msgprint(__('Invalid date range. Check-out must be after check-in.'));
                frappe.model.set_value(cdt, cdn, 'room_number', '');
                return;
            }
            
            // Fetch room type
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Hotel Room',
                    filters: {name: row.room_number},
                    fieldname: ['room_type']
                },
                callback: function(r) {
                    if (r.message && r.message.room_type) {
                        frappe.model.set_value(cdt, cdn, 'room_type', r.message.room_type);
                        
                        // CHANGED - use helper function
                        fetch_and_update_room_rate(frm, cdt, cdn, r.message.room_type);
                    }
                }
            });
        }
    },
    
    rate_amount(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        // Recalculate room total
        if (row.rate_amount && frm.doc.number_of_nights) {
            let room_total = flt(row.rate_amount) * flt(frm.doc.number_of_nights);
            frappe.model.set_value(cdt, cdn, 'total_amount', room_total);
        }
        
        frm.trigger('calculate_totals');
    },
    
    rooms_remove(frm) {
        frm.trigger('calculate_totals');
    }
});

// NEW HELPER FUNCTION
function fetch_and_update_room_rate(frm, cdt, cdn, room_type) {
    frappe.call({
        method: 'rhohotel.api.get_room_rate',
        args: {
            room_type: room_type,
            rate_type: "",
            check_in_date: frm.doc.check_in_datetime.split(" ")[0]
        },
        callback: function(rate_response) {
            if (rate_response.message && !rate_response.message.error) {
                frappe.model.set_value(cdt, cdn, 'rate_amount', rate_response.message);
                
                // Calculate total for this room
                if (frm.doc.number_of_nights) {
                    let room_total = flt(rate_response.message) * flt(frm.doc.number_of_nights);
                    frappe.model.set_value(cdt, cdn, 'total_amount', room_total);
                }
                
                frm.trigger('calculate_totals');
            } else {
                frappe.msgprint(__('Unable to fetch rate for this room type'));
                frappe.model.set_value(cdt, cdn, 'rate_amount', 0);
                frappe.model.set_value(cdt, cdn, 'total_amount', 0);
            }
        }
    });
}