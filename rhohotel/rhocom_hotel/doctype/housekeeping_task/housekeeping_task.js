









// /**
//  * Housekeeping Task - Client-side Script
//  * Handles room inventory, validation, completion lock, and UX enhancements
//  * 
//  * File location: apps/rhohotel/rhohotel/rhocom_hotel/doctype/housekeeping_task/housekeeping_task.js
//  */

// frappe.ui.form.on('Housekeeping Task', {

//     setup: function(frm) {
//         // Make initial inventory read-only
//         frm.set_df_property('room_inventory_before', 'read_only', 1);
//     },

//     refresh: function(frm) {
//         // --- Lock document if completed ---
//         if (frm.doc.docstatus === 1 && frm.doc.status === "Completed") {
//             frappe.show_alert({
//                 message: `✅ Housekeeping Task ${frm.doc.name} for Room ${frm.doc.room} is now completed.`,
//                 indicator: 'green'
//             }, 10);

//             // Lock all fields
//             frm.fields.forEach(field => {
//                 frm.set_df_property(field.df.fieldname, 'read_only', 1);
//             });

//             // Disable save and hide primary button
//             frm.disable_save();
//             if(frm.page && frm.page.btn_primary) frm.page.btn_primary.hide();

//             // Hide child table controls
//             if (frm.fields_dict.room_inventory_changes) {
//                 frm.fields_dict.room_inventory_changes.grid.wrapper.find('.grid-add-row').hide();
//                 frm.fields_dict.room_inventory_changes.grid.wrapper.find('.grid-remove-rows').hide();
//             }

//             frm.refresh_fields();
//             return;  // stop other refresh logic
//         }

//         // --- Draft documents (docstatus 0) ---
//         if (frm.doc.docstatus === 0) {
//             frm.add_custom_button('Load Current Inventory', function() {
//                 frm.trigger('room');
//             }, __('Inventory'));

//             frm.add_custom_button('Clear Inventory Changes', function() {
//                 if (confirm('Are you sure you want to clear all inventory changes?')) {
//                     frm.clear_table('room_inventory_changes');
//                     frm.refresh_field('room_inventory_changes');
//                     frm.dirty();
//                 }
//             }, __('Inventory'));
//         }

//         // --- Show stock entry link ---
//         if (frm.doc.stock_entry && frm.doc.docstatus === 1) {
//             frm.add_custom_button('View Stock Entry', function() {
//                 frappe.set_route('Form', 'Stock Entry', frm.doc.stock_entry);
//             }, __('Stock'));
//         }
//     },

//     // --- Field triggers ---
//     room: function(frm) {
//         if (!frm.doc.room) {
//             frm.clear_table('room_inventory_before');
//             frm.refresh_field('room_inventory_before');
//             return;
//         }

//         frappe.call({
//             method: 'rhohotel.rhocom_hotel.doctype.housekeeping_task.housekeeping_task.load_room_inventory',
//             args: { room: frm.doc.room },
//             callback: function(r) {
//                 if (r.message) {
//                     frm.clear_table('room_inventory_before');
//                     r.message.forEach(item => {
//                         frm.add_child('room_inventory_before', item);
//                     });
//                     frm.refresh_field('room_inventory_before');
//                     frm.dirty();
//                 } else if (r.exc) {
//                     frappe.msgprint({
//                         title: __('Error Loading Inventory'),
//                         message: r.exc || 'Could not load room inventory',
//                         indicator: 'red'
//                     });
//                 }
//             },
//             error: function(err) {
//                 frappe.msgprint({
//                     title: __('Error'),
//                     message: 'Failed to load inventory: ' + err,
//                     indicator: 'red'
//                 });
//             }
//         });
//     },

//     task_type: function(frm) {
//         let hints = {
//             'Daily Cleaning': 'Routine cleaning - minimal inventory changes expected',
//             'Checkout Cleaning': 'Room checkout - may require item replacement/restocking',
//             'Deep Cleaning': 'Intensive cleaning - may need cleaning supplies refreshed',
//             'Turndown Service': 'Evening service - may add amenities or towels',
//             'Guest Request': 'Special cleaning request - depends on guest needs',
//             'Emergency Cleaning': 'Urgent cleaning - may require additional supplies'
//         };
//         if (hints[frm.doc.task_type]) {
//             frappe.msgprint({
//                 title: __('Task Type Hint'),
//                 message: hints[frm.doc.task_type],
//                 indicator: 'blue'
//             });
//         }
//     },

//     status: function(frm) {
//         // Instant feedback if user tries to mark Completed without assignment
//         if (frm.doc.status === "Completed" && !frm.doc.assigned_to) {
//             frappe.msgprint({
//                 title: __('Assignment Required'),
//                 message: 'You must assign an employee before marking the task as Completed.',
//                 indicator: 'red'
//             });
//             frm.set_value('status', 'In Progress'); // optional: revert immediately
//         }
//     },

//     validate: function(frm) {
//         // --- Validate inventory changes ---
//         if (frm.doc.room_inventory_changes && frm.doc.room_inventory_changes.length > 0) {
//             frm.doc.room_inventory_changes.forEach(function(row, idx) {
//                 if (!row.item) {
//                     frappe.throw({
//                         title: __('Missing Item'),
//                         message: `Row ${idx + 1}: Please select an item`
//                     });
//                 }
//                 if (!row.change_type) {
//                     frappe.throw({
//                         title: __('Missing Change Type'),
//                         message: `Row ${idx + 1}: Please select a change type`
//                     });
//                 }
//                 if (!row.quantity_changed || row.quantity_changed <= 0) {
//                     frappe.throw({
//                         title: __('Invalid Quantity'),
//                         message: `Row ${idx + 1}: Quantity must be positive`
//                     });
//                 }
//             });
//         }

//         // --- Ensure assignment when Completed ---
//         if (frm.doc.status === "Completed" && !frm.doc.assigned_to) {
//             frappe.throw({
//                 title: __('Assignment Required'),
//                 message: 'You must assign an employee before marking the task as Completed.'
//             });
//         }
//     }
// });


// /**
//  * Housekeeping Task Inventory Change Row Events
//  */
// frappe.ui.form.on('Housekeeping Task Inventory Change', {

//     room_inventory_changes_add: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         row.change_type = 'Added';
//         row.quantity_changed = 1;
//     },

//     item: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         if (!row.item) return;

//         frappe.call({
//             method: 'rhohotel.rhocom_hotel.doctype.housekeeping_task.housekeeping_task.get_item_details',
//             args: { item_code: row.item },
//             callback: function(r) {
//                 if (r.message) {
//                     row.uom = r.message.uom;
//                     frm.refresh_field('room_inventory_changes');

//                     if (!r.message.is_stock_item) {
//                         frappe.msgprint({
//                             title: __('Non-Stock Item'),
//                             message: `${row.item} is not marked as a stock item. Stock tracking may not work.`,
//                             indicator: 'yellow'
//                         });
//                     }
//                 }
//             },
//             error: function(err) {
//                 frappe.msgprint({
//                     title: __('Error'),
//                     message: 'Could not fetch item details: ' + err,
//                     indicator: 'red'
//                 });
//             }
//         });
//     },

//     change_type: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         let reasons = {
//             'Added': 'Restocking room',
//             'Replaced': 'Item worn/broken/soiled',
//             'Removed': 'Excess inventory'
//         };
//         if (!row.reason && reasons[row.change_type]) {
//             row.reason = reasons[row.change_type];
//         }
//     },

//     quantity_changed: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         if (row.quantity_changed && row.quantity_changed < 0) {
//             frappe.msgprint({
//                 title: __('Invalid Quantity'),
//                 message: 'Quantity must be positive (> 0)',
//                 indicator: 'red'
//             });
//             row.quantity_changed = 1;
//             frm.refresh_field('room_inventory_changes');
//         }
//     }
// });

































frappe.ui.form.on('Housekeeping Task', {

    setup: function(frm) {
        // Make initial inventory read-only
        frm.set_df_property('room_inventory_before', 'read_only', 1);
    },

    refresh: function(frm) {
        // --- Lock document if completed ---
        if (frm.doc.docstatus === 1 && frm.doc.status === "Completed") {
            frappe.show_alert({
                message: `✅ Housekeeping Task ${frm.doc.name} for Room ${frm.doc.room} is now completed.`,
                indicator: 'green'
            }, 10);

            // Lock all fields
            frm.fields.forEach(field => {
                frm.set_df_property(field.df.fieldname, 'read_only', 1);
            });

            // Disable save and hide primary button
            frm.disable_save();
            if(frm.page && frm.page.btn_primary) frm.page.btn_primary.hide();

            // Hide child table controls
            if (frm.fields_dict.room_inventory_changes) {
                frm.fields_dict.room_inventory_changes.grid.wrapper.find('.grid-add-row').hide();
                frm.fields_dict.room_inventory_changes.grid.wrapper.find('.grid-remove-rows').hide();
            }

            frm.refresh_fields();
            return;  // stop other refresh logic
        }

        // --- Draft documents (docstatus 0) ---
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button('Load Current Inventory', function() {
                frm.trigger('room');
            }, __('Inventory'));

            frm.add_custom_button('Clear Inventory Changes', function() {
                if (confirm('Are you sure you want to clear all inventory changes?')) {
                    frm.clear_table('room_inventory_changes');
                    frm.refresh_field('room_inventory_changes');
                    frm.dirty();
                }
            }, __('Inventory'));

            // ✅ ADDED: Button to reload checklist
            if (frm.doc.checklist_template) {
                frm.add_custom_button(__('Reload Checklist from Template'), function() {
                    load_checklist_items(frm);
                }, __('Checklist'));
            }
        }

        // --- Show stock entry link ---
        if (frm.doc.stock_entry && frm.doc.docstatus === 1) {
            frm.add_custom_button('View Stock Entry', function() {
                frappe.set_route('Form', 'Stock Entry', frm.doc.stock_entry);
            }, __('Stock'));
        }
    },

    // --- Field triggers ---
    room: function(frm) {
        if (!frm.doc.room) {
            frm.clear_table('room_inventory_before');
            frm.refresh_field('room_inventory_before');
            return;
        }

        // ✅ ADDED: Auto-suggest template when room is selected
        if (frm.doc.room && frm.doc.task_type) {
            suggest_template(frm);
        }

        frappe.call({
            method: 'rhohotel.rhocom_hotel.doctype.housekeeping_task.housekeeping_task.load_room_inventory',
            args: { room: frm.doc.room },
            callback: function(r) {
                if (r.message) {
                    frm.clear_table('room_inventory_before');
                    r.message.forEach(item => {
                        frm.add_child('room_inventory_before', item);
                    });
                    frm.refresh_field('room_inventory_before');
                    frm.dirty();
                } else if (r.exc) {
                    frappe.msgprint({
                        title: __('Error Loading Inventory'),
                        message: r.exc || 'Could not load room inventory',
                        indicator: 'red'
                    });
                }
            },
            error: function(err) {
                frappe.msgprint({
                    title: __('Error'),
                    message: 'Failed to load inventory: ' + err,
                    indicator: 'red'
                });
            }
        });
    },

    task_type: function(frm) {
        let hints = {
            'Daily Cleaning': 'Routine cleaning - minimal inventory changes expected',
            'Checkout Cleaning': 'Room checkout - may require item replacement/restocking',
            'Deep Cleaning': 'Intensive cleaning - may need cleaning supplies refreshed',
            'Turndown Service': 'Evening service - may add amenities or towels',
            'Guest Request': 'Special cleaning request - depends on guest needs',
            'Emergency Cleaning': 'Urgent cleaning - may require additional supplies'
        };
        if (hints[frm.doc.task_type]) {
            frappe.msgprint({
                title: __('Task Type Hint'),
                message: hints[frm.doc.task_type],
                indicator: 'blue'
            });
        }

        // ✅ ADDED: Auto-suggest template when task type changes
        if (frm.doc.room && frm.doc.task_type) {
            suggest_template(frm);
        }
    },

    // ✅ COMPLETELY NEW FUNCTION ADDED:
    checklist_template: function(frm) {
        if (frm.doc.checklist_template) {
            load_checklist_items(frm);
        }
    },

    status: function(frm) {
        // Instant feedback if user tries to mark Completed without assignment
        if (frm.doc.status === "Completed" && !frm.doc.employee) {  // ✅ CHANGED: assigned_to → employee
            frappe.msgprint({
                title: __('Assignment Required'),
                message: 'You must assign an employee before marking the task as Completed.',
                indicator: 'red'
            });
            frm.set_value('status', 'In Progress'); // optional: revert immediately
        }

        // ✅ ADDED: Auto-fill start/end times
        if (frm.doc.status === 'In Progress' && !frm.doc.start_time) {
            frm.set_value('start_time', frappe.datetime.now_datetime());
        }
        
        if (frm.doc.status === 'Completed' && !frm.doc.end_time) {
            frm.set_value('end_time', frappe.datetime.now_datetime());
        }
    },

    validate: function(frm) {
        // --- Validate inventory changes ---
        if (frm.doc.room_inventory_changes && frm.doc.room_inventory_changes.length > 0) {
            frm.doc.room_inventory_changes.forEach(function(row, idx) {
                if (!row.item) {
                    frappe.throw({
                        title: __('Missing Item'),
                        message: `Row ${idx + 1}: Please select an item`
                    });
                }
                if (!row.change_type) {
                    frappe.throw({
                        title: __('Missing Change Type'),
                        message: `Row ${idx + 1}: Please select a change type`
                    });
                }
                if (!row.quantity_changed || row.quantity_changed <= 0) {
                    frappe.throw({
                        title: __('Invalid Quantity'),
                        message: `Row ${idx + 1}: Quantity must be positive`
                    });
                }
            });
        }

        // --- Ensure assignment when Completed ---
        if (frm.doc.status === "Completed" && !frm.doc.employee) {  // ✅ CHANGED: assigned_to → employee
            frappe.throw({
                title: __('Assignment Required'),
                message: 'You must assign an employee before marking the task as Completed.'
            });
        }
    }
});


// ✅ COMPLETELY NEW SECTION ADDED:
/**
 * Task Checklist Item Events
 */
frappe.ui.form.on('Task Checklist Item', {
    is_completed: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        if (row.is_completed) {
            // Auto-fill completed_by with current user
            if (!row.completed_by) {
                frappe.model.set_value(cdt, cdn, 'completed_by', frappe.session.user);
            }
            // Auto-fill completed_at with current datetime
            if (!row.completed_at) {
                frappe.model.set_value(cdt, cdn, 'completed_at', frappe.datetime.now_datetime());
            }
        } else {
            // Clear completion data if unchecked
            frappe.model.set_value(cdt, cdn, 'completed_by', '');
            frappe.model.set_value(cdt, cdn, 'completed_at', '');
        }
    }
});


/**
 * Housekeeping Task Inventory Change Row Events
 */
frappe.ui.form.on('Housekeeping Task Inventory Change', {

    room_inventory_changes_add: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        row.change_type = 'Added';
        row.quantity_changed = 1;
    },

    item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.item) return;

        frappe.call({
            method: 'rhohotel.rhocom_hotel.doctype.housekeeping_task.housekeeping_task.get_item_details',
            args: { item_code: row.item },
            callback: function(r) {
                if (r.message) {
                    row.uom = r.message.uom;
                    frm.refresh_field('room_inventory_changes');

                    if (!r.message.is_stock_item) {
                        frappe.msgprint({
                            title: __('Non-Stock Item'),
                            message: `${row.item} is not marked as a stock item. Stock tracking may not work.`,
                            indicator: 'yellow'
                        });
                    }
                }
            },
            error: function(err) {
                frappe.msgprint({
                    title: __('Error'),
                    message: 'Could not fetch item details: ' + err,
                    indicator: 'red'
                });
            }
        });
    },

    change_type: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let reasons = {
            'Added': 'Restocking room',
            'Replaced': 'Item worn/broken/soiled',
            'Removed': 'Excess inventory'
        };
        if (!row.reason && reasons[row.change_type]) {
            row.reason = reasons[row.change_type];
        }
    },

    quantity_changed: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.quantity_changed && row.quantity_changed < 0) {
            frappe.msgprint({
                title: __('Invalid Quantity'),
                message: 'Quantity must be positive (> 0)',
                indicator: 'red'
            });
            row.quantity_changed = 1;
            frm.refresh_field('room_inventory_changes');
        }
    }
});


// ✅ COMPLETELY NEW HELPER FUNCTIONS ADDED AT THE END:

/**
 * Load checklist items from template
 */
function load_checklist_items(frm) {
    if (!frm.doc.checklist_template) {
        frappe.msgprint(__('Please select a Checklist Template first'));
        return;
    }
    
    // Show loading indicator
    frappe.show_alert({
        message: __('Loading checklist items...'),
        indicator: 'blue'
    }, 3);
    
    // Call server method to get template items
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.housekeeping_task.housekeeping_task.get_template_items',
        args: {
            template: frm.doc.checklist_template
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                // Clear existing checklist items
                frm.clear_table('checklist_items');
                
                // Add each item from template to the task
                r.message.forEach(function(item) {
                    let child = frm.add_child('checklist_items');
                    child.item_description = item.item_description;
                    child.is_mandatory = item.is_mandatory;
                    child.sequence = item.sequence;
                    child.is_completed = 0;
                });
                
                // Refresh the checklist items table
                frm.refresh_field('checklist_items');
                
                // Show success message
                frappe.show_alert({
                    message: __('{0} checklist items loaded successfully', [r.message.length]),
                    indicator: 'green'
                }, 5);
            } else {
                frappe.msgprint(__('No checklist items found in the selected template'));
            }
        },
        error: function(r) {
            frappe.msgprint(__('Error loading checklist items. Please try again.'));
        }
    });
}

/**
 * Suggest template based on room type and task type
 */
function suggest_template(frm) {
    if (!frm.doc.room || !frm.doc.task_type) {
        return;
    }
    
    frappe.call({
        method: 'rhohotel.rhocom_hotel.doctype.housekeeping_task.housekeeping_task.get_suggested_template',
        args: {
            room: frm.doc.room,
            task_type: frm.doc.task_type
        },
        callback: function(r) {
            if (r.message) {
                // Only set template if it's not already set or different
                if (!frm.doc.checklist_template || frm.doc.checklist_template !== r.message) {
                    frm.set_value('checklist_template', r.message);
                    frappe.show_alert({
                        message: __('Template auto-selected based on room type'),
                        indicator: 'blue'
                    }, 3);
                }
            }
        }
    });
}