// Copyright (c) 2024, Rhocom Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hotel Room Check In", {
    refresh(frm) {
        frm.add_custom_button(__('Front Desk'), () => {
            frappe.set_route('front-desk');
        });

        // set fields as read-onlyr
        if (frm.doc.docstatus === 1) {
            // set fields as read-only
            frm.set_df_property("guest", "read_only", 1);
            frm.set_df_property("room", "read_only", 1);
            frm.set_df_property("check_in_datetime", "read_only", 1);
            frm.set_df_property("expected_check_out_datetime", "read_only", 1);
            frm.set_df_property("number_of_nights", "read_only", 1);
            frm.set_df_property("rate_amount", "read_only", 1);
            frm.set_df_property("total_amount", "read_only", 1);
            frm.set_df_property("discount", "read_only", 1);
            frm.set_df_property("net_total", "read_only", 1);
            frm.set_df_property("status", "read_only", 1);
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__('Payment'), () => {

                frappe.route_options = {
                    party_type: "Customer",
                    party: frm.doc.guest,
                    custom_hotel_room_check_in: frm.doc.name
                };

                frappe.new_doc("Payment Entry");
            }, __("Create"));
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__("Refund"), () => {
                frappe.model.open_mapped_doc({
                    method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_refund',
                    frm: frm
                });
            }, __("Create"));

            // Discount dialog (credit note)
            frm.add_custom_button(__("Discount"), () => {
                let dialog = new frappe.ui.Dialog({
                    title: __('Apply Discount'),
                    fields: [

                        {
                            label: __('Discount Amount'),
                            fieldname: 'discount_amount',
                            fieldtype: 'Currency',
                            reqd: 1,
                            description: __('Enter the discount amount to apply to this check-in.')
                        },
                        {
                            label: __('Reason for Discount'),
                            fieldname: 'discount_reason',
                            fieldtype: 'Small Text',
                            reqd: 1,
                            description: __('Provide a reason for the discount.')
                        }
                    ],
                    primary_action_label: __('Apply Discount'),
                    primary_action: (values) => {
                        frappe.call({
                            method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.apply_discount',
                            args: {
                                check_in_name: frm.doc.name,
                                discount_amount: values.discount_amount,
                                discount_reason: values.discount_reason
                            },
                            callback: (r) => {
                                if (!r.exc) {
                                    frappe.show_alert({
                                        message: __('Discount of {0} applied successfully!', [values.discount_amount]),
                                        indicator: 'green'
                                    }, 5);
                                    frm.reload_doc();
                                    dialog.hide();
                                }
                            },
                            error: (r) => {
                                frappe.msgprint({
                                    title: __("Error"),
                                    message: __("Failed to apply discount. Please try again."),
                                    indicator: "red"
                                });
                            }
                        });
                    }
                });

                dialog.show();
            }, __("Create"));

        }



        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Transfer Bill In'), () => {
                frappe.route_options = {
                    to_guest: frm.doc.guest,
                    to_check_in: frm.doc.name
                };

                frappe.new_doc("Bill Transfer");
            }, __("Bill Transfer"));

            frm.add_custom_button(__('Transfer Bill Out'), () => {
                frappe.route_options = {
                    from_guest: frm.doc.guest,
                    from_check_in: frm.doc.name
                };
                frappe.new_doc("Bill Transfer");
            }, __("Bill Transfer"))
        }

        if (frm.doc.docstatus === 1) {
            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.get_linked_documents',
                args: {
                    check_in: frm.doc.name
                },
                callback: function (r) {
                    if (r.message) {
                        frm.fields_dict.invoices_html.html(render_invoices(r.message.invoices));
                        frm.fields_dict.journal_entries_html.html(render_journal_entries(r.message.journal_entries));
                        frm.fields_dict.payments_html.html(render_payments(r.message.payments));

                        if (r.message.total_outstanding_amount > 0) {
                            frm.add_custom_button(__("Receive Payment"), () => {
                                open_checkin_payment_dialog(frm);
                            });

                            // Fetch terminals and create payment buttons
                            frappe.call({
                                method: 'frappe.client.get_list',
                                args: {
                                    doctype: 'Moniepoint Terminal',
                                    parent: 'Moniepoint Settings',
                                    fields: ['name', 'terminal_name'],
                                    filters: {
                                        parenttype: 'Moniepoint Settings',
                                        parentfield: 'terminals'
                                    }
                                },
                                callback: function (res) {
                                    const terminals = res.message || [];
                                    const button_label = __('Pay with Moniepoint');

                                    if (terminals.length > 1) {
                                        frm.add_custom_button(button_label, null, button_label);
                                        terminals.forEach(terminal => {
                                            frm.add_custom_button(
                                                terminal.terminal_name || terminal.name,
                                                function () {
                                                    show_invoice_selection_dialog(frm, terminal.name);
                                                },
                                                button_label
                                            );
                                        });
                                    } else if (terminals.length === 1) {
                                        frm.add_custom_button(button_label, function () {
                                            show_invoice_selection_dialog(frm, terminals[0].name);
                                        });
                                    }
                                }
                            });
                        }

                        // Add Print Receipt button if there are paid sessions
                        if (r.message.payment_sessions && r.message.payment_sessions.length > 0) {
                            frm.add_custom_button(__('Print Receipt'), function () {
                                let dialog = new frappe.ui.Dialog({
                                    title: __('Select a Payment to Print'),
                                    fields: [
                                        {
                                            label: __('Payment Session'),
                                            fieldname: 'payment_session',
                                            fieldtype: 'Link',
                                            options: 'Payment Session',
                                            reqd: 1,
                                            get_query: function () {
                                                return {
                                                    filters: {
                                                        'hotel_room_check_in': frm.doc.name,
                                                        'status': 'Paid'
                                                    }
                                                };
                                            }
                                        }
                                    ],
                                    primary_action_label: __('Print'),
                                    primary_action: (values) => {
                                        window.open(
                                            `/printview?doctype=Payment%20Session&name=${values.payment_session}&format=Payment%20Receipt&no_letterhead=0`,
                                            '_blank'
                                        );
                                        dialog.hide();
                                    }
                                });
                                dialog.show();
                            });
                        }
                    }
                }
            });
        }



        // Add custom buttons based on status
        if (frm.doc.docstatus === 1 && frm.doc.status === "Checked In") {


            // Check out button should only be visible only there is no outstanding or user has manager role
            // Fetch outstanding from backend
            frappe.call({
                method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.get_outstanding_for_check_in",
                args: { check_in: frm.doc.name },
                callback(r) {
                    let outstanding = r.message.outstanding || 0;

                    // Check manager role override
                    let is_manager =
                        frappe.user_roles.includes("Hotel Manager") ||
                        frappe.user_roles.includes("System Manager");

                    // Show button if no outstanding OR user is manager
                    if (outstanding === 0 || is_manager) {


                        frm.add_custom_button(__("Check Out"), () => {

                            frm.trigger("handle_late_checkout");

                            // frappe.model.open_mapped_doc({
                            //     method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
                            //     frm: frm
                            // });
                        }).addClass("btn-primary");
                    }
                }
            });


            if (frm.doc.docstatus === 1 && !frm.doc.actual_check_out_datetime) {
                frm.add_custom_button(__('Adjust Stay'), () => {
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
                                title: __('Adjust Stay'),
                                fields: [
                                    {
                                        label: __('Current Check-in'),
                                        fieldname: 'current_checkin',
                                        fieldtype: 'Datetime',
                                        default: frm.doc.check_in_datetime,
                                        read_only: 1
                                    },
                                    {
                                        label: __('Current Expected Check-out'),
                                        fieldname: 'current_checkout',
                                        fieldtype: 'Datetime',
                                        default: frm.doc.expected_check_out_datetime,
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
                                        fieldname: 'room_rate',
                                        fieldtype: 'Currency',
                                        default: frm.doc.rate_amount || 0,
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

                                            let current_checkout = frm.doc.expected_check_out_datetime;
                                            let current_dt = frappe.datetime.str_to_obj(current_checkout);
                                            let selected_dt = frappe.datetime.str_to_obj(new_datetime_with_default_time);
                                            let checkin_dt = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);

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
                                            let from = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);

                                            from.setHours(0, 0, 0, 0);
                                            // Calculate difference in nights
                                            let diff_days = frappe.datetime.get_day_diff(
                                                new_datetime_with_default_time,
                                                from
                                            );
                                            if (diff_days < 1) diff_days = 1;
                                            d.set_value('new_nights', diff_days);

                                            // Calculate night difference
                                            let current_nights = frm.doc.number_of_nights || 1;
                                            let nights_diff = diff_days - current_nights;
                                            d.set_value('nights_difference', nights_diff);

                                            // Calculate amount
                                            let room_rate = frm.doc.rate_amount || 0;
                                            let amount_change = nights_diff * room_rate;
                                            d.set_value('amount_change', amount_change);

                                            // Show total new amount
                                            let new_total = diff_days * room_rate;
                                            //d.set_value('new_total_amount', new_total);

                                            let new_discount = d.get_value('new_discount') || 0;
                                            let final_amount = new_total - new_discount;
                                            d.set_value('new_total_amount', final_amount);
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
                                        label: __('Discount Type'),
                                        fieldname: 'discount_type',
                                        fieldtype: 'Select',
                                        options: 'None\nPercentage\nFixed Amount',
                                        default: frm.doc.discount_type || 'None'
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
                                    const current_dt = frappe.datetime.str_to_obj(frm.doc.expected_check_out_datetime);
                                    const checkin_dt = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);

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
                                                [frappe.datetime.str_to_user(checkin_dt)])
                                        });
                                        return;
                                    }

                                    // VALIDATION 2: Cannot be in the past
                                    if (new_dt < now_dt) {
                                        frappe.msgprint({
                                            title: __("Invalid Date"),
                                            indicator: "red",
                                            message: __("New checkout cannot be in the past. Current time is: {0}",
                                                [frappe.datetime.str_to_user(now_dt)])
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
                                                        [frappe.datetime.str_to_user(default_dt)])
                                                });
                                                return;
                                            }

                                            // If reducing to today, time must be on or before default checkout
                                            if (new_dt > default_dt) {
                                                frappe.msgprint({
                                                    title: __("Invalid Time"),
                                                    indicator: "red",
                                                    message: __("For today, new checkout must be on or before the hotel's default checkout time: {0}",
                                                        [frappe.datetime.str_to_user(default_dt)])
                                                });
                                                return;
                                            }
                                        }
                                    }

                                    if (values.new_discount > 0 && values.discount_type === "None") {
                                        frappe.msgprint({
                                            title: __("Invalid Discount"),
                                            indicator: "red",
                                            message: __("Please select a discount type.")
                                        });
                                        return;
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
                                        method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.adjust_stay',
                                        args: {
                                            check_in_name: frm.doc.name,
                                            new_checkout: values.new_checkout,
                                            new_discount: values.new_discount,
                                            discount_type: values.discount_type
                                        },
                                        freeze: true,
                                        freeze_message: __("Processing stay adjustment..."),
                                        callback: (r) => {
                                            if (!r.exc) {
                                                const adjustment_type = r.message?.adjustment_type || values.adjustment_type;
                                                frappe.show_alert({
                                                    message: __('Stay {0} completed successfully!', [adjustment_type]),
                                                    indicator: 'green'
                                                }, 5);
                                                frm.reload_doc();
                                                d.hide();
                                            }
                                        },
                                        error: (r) => {
                                            frappe.msgprint({
                                                title: __("Error"),
                                                message: __("Failed to adjust stay. Please try again or contact support."),
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

            frm.add_custom_button(__('Transfer Room'), function () {
                const transfer_button = frm.page.add_inner_button(__('Transfer'), function () { }, 'Actions');  // Optional: Loading button
                const dialog = new frappe.ui.Dialog({
                    title: __('Transfer Guest to Another Room'),
                    fields: [
                        {
                            label: 'New Room',
                            fieldname: 'new_room_number',
                            fieldtype: 'Link',
                            options: 'Hotel Room',
                            reqd: 1,
                            get_query: () => ({
                                filters: { status: 'Vacant', housekeeping_status: 'Clean' }
                            })
                        },
                        {
                            label: 'Transfer Reason / Note',
                            fieldname: 'transfer_note',
                            fieldtype: 'Small Text'
                        }
                    ],
                    primary_action_label: 'Transfer',
                    primary_action(values) {
                        // Optional: Show loading
                        frappe.dom.freeze();
                        frappe.call({
                            method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.transfer_room',
                            args: {
                                check_in_name: frm.doc.name,
                                new_room_number: values.new_room_number,
                                note: values.transfer_note
                            },
                            callback: function (r) {
                                frappe.dom.unfreeze();
                                if (!r.exc && r.message) {
                                    frappe.msgprint(r.message);  // Use Python message (includes rate details if adjusted)
                                    frm.reload_doc();
                                } else if (!r.exc) {
                                    frappe.msgprint(__('Guest transferred successfully to Room {0}').format(values.new_room_number));  // Fallback
                                    frm.reload_doc();
                                }
                            },
                            error: function (r) {
                                frappe.dom.unfreeze();
                                frappe.msgprint(__('Room transfer failed'));
                                console.log(r);
                            }
                        });
                        dialog.hide();
                    }
                });
                dialog.show();
            });
        }

        // Set dynamic filter for Business Source
        frm.set_query("business_source", function () {
            return {
                filters: {
                    reservation_source: frm.doc.market_source || ""
                }
            };
        });
    },
    handle_late_checkout(frm) {
        frappe.call({
            method: "rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.check_late_checkout",
            args: {
                check_in_name: frm.doc.name
            },
            freeze: true,
            freeze_message: __("Checking late checkout policy..."),
            callback: function (r) {
                if (!r.message || !r.message.late) {
                    frappe.model.open_mapped_doc({
                        method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
                        frm: frm
                    });
                    return;
                }

                const hours_late = r.message.hours_late;
                const policy = r.message.policy;

                const message = `
                    <b>Late Check-out Detected</b><br><br>
                    Guest is checking out <b>${hours_late} hour(s) late</b>.<br>
                    Do you want to apply a late check-out charge?
                `;

                frappe.confirm(
                    message,
                    () => {
                        frappe.call({
                            method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.apply_late_checkout_charge",
                            args: {
                                check_in: frm.doc.name,
                                item: policy.item,
                                charge_type: policy.charge_type,
                                amount: policy.amount
                            },
                            freeze: true,
                            freeze_message: __("Applying late checkout charge..."),
                            callback: function () {
                                frappe.show_alert({
                                    message: __("Late check-out charge applied, proceeding to check-out."),
                                    indicator: "green"
                                });

                            }
                        });

                        // reload the page to reflect new charge
                        frm.doc.reload_doc();
                    },
                    () => {
                        frappe.model.open_mapped_doc({
                            method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
                            frm: frm
                        });
                    }
                );
            }
        });
    },
    apply_late_checkout_charge(frm, policy) {

        frappe.show_alert({
            message: __(`Applying late check-out charge... ${policy.item} - ${policy.charge_type} - ${policy.amount}`),
            indicator: "blue"
        });

        frappe.call({
            method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.apply_late_checkout_charge",
            args: {
                check_in: frm.doc.name,
                item: policy.item,
                charge_type: policy.charge_type,
                amount: policy.amount
            },
            freeze: true,
            freeze_message: __("Applying late checkout charge..."),
            callback: function () {
                frappe.show_alert({
                    message: __("Late check-out charge applied, proceeding to check-out."),
                    indicator: "green"
                });

                frm.doc.reload_doc();
            }
        });
    },

    on_submit: function (frm) {
        frappe.confirm(
            __('Do you want to issue a key card for this guest?'),
            () => {
                const guestName = frm.doc.guest_name;
                const checkInName = frm.doc.name;
                const roomNumber = frm.doc.room_number;
                const checkInDateTime = frm.doc.check_in_datetime;
                const checkOutDateTime = frm.doc.expected_check_out_datetime;

                const url = `hotel-key-card-issuer://issue?guestName=${encodeURIComponent(guestName)}&checkInName=${encodeURIComponent(checkInName)}&roomNumber=${encodeURIComponent(roomNumber)}&checkInDateTime=${encodeURIComponent(checkInDateTime)}&checkOutDateTime=${encodeURIComponent(checkOutDateTime)}`;
                window.open(url, '_self');
            },
            () => { }
        );
    },

    onload: function (frm) {
        if (!frm.is_new() && frm.doc.guest) {
            frm.add_custom_button(__('Ledger'), function () {
                frappe.call({
                    method: 'frappe.client.get_value',
                    args: {
                        doctype: 'Hotel Guest',
                        filters: { name: frm.doc.guest },
                        fieldname: 'customer'
                    },
                    callback: function (r) {
                        if (r.message && r.message.customer) {
                            frappe.set_route('query-report', 'General Ledger', {
                                party_type: 'Customer',
                                party: r.message.customer
                            });
                        }
                    }
                });
            });
        }

        // Load route options only when creating a new doc

        // if (frm.is_new() && frappe.route_options) {

        //     // let nights = frappe.datetime.get_day_diff(
        //     //     frappe.route_options
        //     // );

        //     console.log("data from route options", frappe.route_options)



        //     frm.set_value("reservation", frappe.route_options.reservation);
        //     frm.set_value("guest", frappe.route_options.guest);
        //     frm.set_value("room_number", frappe.route_options.room_number);
        //     frm.set_value("rate_amount", frappe.route_options.rate_amount);
        //     // frm.set_value("check_in_datetime", frappe.route_options.check_in_datetime);
        //     //frm.set_value("expected_check_out_datetime", frappe.route_options.to_date);

        //     // Clear route options after using them
        //     frappe.route_options = null;
        // }
    },

    discount: function (frm) {
        frm.trigger('calculate_total_charges');
    },

    discount_type: function (frm) {
        if (frm.doc.discount_type === "None") {
            // hide discount
            frm.set_df_property("discount", "hidden", 1);
        }
        else {
            frm.set_df_property("discount", "hidden", 0);
        }
        frm.trigger('calculate_total_charges');
    },

    // get number of nights from two dates
    calculate_number_of_nights(frm) {
        if (frm.doc.check_in_datetime && frm.doc.expected_check_out_datetime) {
            const checkInDate = new Date(frm.doc.check_in_datetime);
            const checkOutDate = new Date(frm.doc.expected_check_out_datetime);
            const timeDiff = checkOutDate - checkInDate;
            const nights = Math.ceil(timeDiff / (1000 * 3600 * 24));
            frm.set_value('number_of_nights', nights);
        }
    },

    setup(frm) {
        frm.set_query("room_number", function () {
            return {
                filters: {
                    "status": "Vacant"
                }
            };
        });

        frm.set_query("reservation", function () {
            return {
                filters: {
                    "docstatus": 1,
                    "status": ["in", ["Confirmed", "Booked"]]
                }
            };
        });
    },

    market_source: function (frm) {
        frm.set_value('business_source', null);
        frm.fields_dict.business_source.get_query();
    },

    reservation(frm) {
        if (frm.doc.reservation) {

            frm.set_df_property("check_in_datetime", "read_only", 1);

            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Hotel Room Reservation",
                    name: frm.doc.reservation
                },
                callback: function (r) {
                    if (r.message) {

                        frappe.call({
                            method: 'rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time',
                            callback: function (res) {
                                if (res.message) {
                                    let time_part = res.message;

                                    let expected_check_out_datetime = r.message.to_date + " " + time_part;
                                    let formatted_checkout = frappe.datetime.str_to_obj(expected_check_out_datetime);
                                    // new_checkout = date_str + " " + time_part;

                                    ////////
                                    let check_in_datetime = r.message.from_date;

                                    // If append current time if not time on check_in_datetime
                                    if (!check_in_datetime.includes(" ")) {
                                        check_in_datetime += " " + frappe.datetime.now_datetime().split(" ")[1];
                                    }


                                    //frm.set_value('check_in_datetime', check_in_datetime);


                                    let from = frappe.datetime.str_to_obj(check_in_datetime);
                                    let to = frappe.datetime.str_to_obj(formatted_checkout);

                                    from.setHours(0, 0, 0, 0);
                                    to.setHours(0, 0, 0, 0);

                                    let nights = frappe.datetime.get_day_diff(to, from);

                                    //format expected_check_out_datetime and attach default check out time to the time part
                                    frm.set_value('check_in_datetime', check_in_datetime)
                                    frm.set_value('expected_check_out_datetime', formatted_checkout);
                                    frm.set_value('room_number', r.message.room_number);
                                    frm.set_value('rate_amount', r.message.rate);
                                    frm.set_value('guest', r.message.guest_name);
                                    frm.set_value('number_of_nights', nights);
                                    frm.set_value('discount', r.message.discount);

                                    frm.set_df_property('room_number', 'read_only', 1);
                                    frm.set_df_property('number_of_nights', 'read_only', 1);
                                    frm.set_df_property('discount', 'read_only', 1);
                                    frm.set_df_property('rate_amount', 'read_only', 1);
                                    frm.set_df_property('room_type', 'read_only', 1);

                                }
                            }
                        });
                    }
                },
            });
        } else {
            frm.set_df_property('room_number', 'read_only', 0);
            frm.set_value('room_number', null);
            frm.set_value('room_type', null);
            frm.set_value('number_of_nights', null);
            frm.set_value('discount', null);
        }
    },

    expected_check_out_datetime: function (frm) {
        frm.trigger('calculate_total_charges');
    },

    number_of_nights: function (frm) {
        frm.trigger('calculate_total_charges');
    },

    rate_amount: function (frm) {
        frm.trigger('calculate_total_charges');
    },

    calculate_total_charges: function (frm) {
        if (frm.doc.check_in_datetime && frm.doc.expected_check_out_datetime && frm.doc.rate_amount) {
            let nights = frm.doc.number_of_nights;
            const total = nights * frm.doc.rate_amount;
            if (discount) {


                if (frm.doc.discount_type === "Percentage") {
                    const discounted_amount = (total * discount) / 100;
                    const discounted_total = total - discounted_amount;

                    frm.set_value('total_charges', discounted_total);
                    //frm.set_value('discount_amount', discounted_amount);   // optional if you track it
                }
                else {
                    // Amount discount
                    const discounted_total = total - discount;
                    frm.set_value('total_charges', discounted_total);
                }
            } else {
                frm.set_value('total_charges', total);
            }
        }
    },

    room_number: function (frm) {
        if (frm.doc.room_number) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Hotel Room',
                    filters: { name: frm.doc.room_number },
                    fieldname: 'room_type'
                },
                callback: function (response) {
                    if (response.message) {
                        frm.set_value('room_type', response.message.room_type);
                        frm.trigger('fetch_rate');
                    }
                }
            });
        }
    },

    rate_type: function (frm) {
        frm.trigger('fetch_rate');
    },

    check_in_datetime: function (frm) {
        frm.trigger('fetch_rate');
    },

    fetch_rate: function (frm) {
        if (frm.doc.reservation) {
            frappe.show_alert({ message: __("Rate is based on the linked reservation."), indicator: "info" });
            return;
        }

        if (frm.doc.room_type && frm.doc.check_in_datetime) {
            frappe.call({
                method: 'rhohotel.api.get_room_rate',
                args: {
                    room_type: frm.doc.room_type,
                    rate_type: "",
                    check_in_date: frm.doc.check_in_datetime.split(" ")[0]
                },
                callback: function (response) {
                    if (response.message && !response.message.error) {
                        frm.set_value('rate_amount', response.message);
                    } else {
                        if (response.message.error) {
                            frappe.show_alert({
                                message: __(response.message.error),
                                indicator: 'red'
                            });
                        }
                        frm.set_value('rate_amount', 0);
                    }
                }
            });
        }
    },

    number_of_nights: function (frm) {
        if (frm.doc.check_in_datetime && frm.doc.number_of_nights && !frm.doc.reservation) {
            let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
            let new_checkout = frappe.datetime.add_days(check_in, frm.doc.number_of_nights);

            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time',
                callback: function (r) {
                    if (r.message) {
                        let time_part = r.message;
                        let date_str = frappe.datetime.obj_to_str(new_checkout);
                        new_checkout = date_str + " " + time_part;
                        frm.set_value('expected_check_out_datetime', new_checkout);
                    } else {
                        frm.set_value('expected_check_out_datetime', new_checkout);
                    }
                }
            });
        }
    }
});

function open_checkin_payment_dialog(frm) {
    frappe.call({
        method: 'rhohotel.api.get_outstanding_invoices',
        args: {
            check_in: frm.doc.name
        },
        callback: function (r) {
            const invoices = r.message || [];

            if (!invoices.length) {
                frappe.msgprint(__('No outstanding invoices found.'));
                return;
            }

            const invoice_map = {};
            const total_outstanding = invoices.reduce((sum, inv) => sum + (inv.outstanding_amount || 0), 0);
            let dialog;
            let is_syncing_totals = false;

            const parse_amount = (value) => {
                if (value === null || value === undefined) return 0;
                if (typeof value === 'number') return value;
                const normalized = String(value).replace(/,/g, '').trim();
                return parseFloat(normalized) || 0;
            };

            const format_amount = (value) => {
                const amount = parse_amount(value);
                return frappe.format(amount, { fieldtype: 'Currency' }, { inline: true });
            };

            const format_amount_input = (value) => {
                const amount = parse_amount(value);
                return new Intl.NumberFormat('en-US', {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 2
                }).format(amount);
            };

            let html = `
                <div class="invoice-selection-container">
                    <style>
                        .invoice-selection-container {
                            max-height: 400px;
                            overflow-y: auto;
                        }
                        .invoice-item {
                            border: 1px solid #d1d8dd;
                            border-radius: 4px;
                            padding: 12px;
                            margin-bottom: 10px;
                            background: #f8f9fa;
                        }
                        .invoice-item:hover {
                            background: #e9ecef;
                        }
                        .invoice-header {
                            display: flex;
                            align-items: center;
                            margin-bottom: 8px;
                        }
                        .invoice-details {
                            flex: 1;
                        }
                        .invoice-number {
                            font-weight: bold;
                            color: #2490ef;
                        }
                        .invoice-amount {
                            color: #6c757d;
                            font-size: 0.9em;
                        }
                        .invoice-allocation {
                            margin-top: 8px;
                            padding-left: 28px;
                        }
                        .manual-allocation-input[readonly] {
                            background: #fff;
                            cursor: default;
                        }
                        .total-section {
                            margin-top: 20px;
                            padding: 15px;
                            background: #fff3cd;
                            border: 1px solid #ffc107;
                            border-radius: 4px;
                            text-align: center;
                        }
                        .total-label {
                            font-weight: bold;
                            font-size: 1.1em;
                            color: #333;
                        }
                        .total-amount {
                            font-size: 1.5em;
                            font-weight: bold;
                            color: #28a745;
                            margin-top: 5px;
                        }
                        .payment-summary {
                            margin-top: 10px;
                            color: #6c757d;
                            font-size: 0.95em;
                        }
                    </style>
                    <div id="manual-payment-invoice-list">
            `;

            invoices.forEach((invoice, index) => {
                invoice_map[invoice.name] = invoice;
                html += `
                    <div class="invoice-item" data-invoice="${invoice.name}">
                        <div class="invoice-header">
                            <input type="checkbox"
                                   class="manual-payment-checkbox"
                                   id="manual_chk_${index}"
                                   data-invoice="${invoice.name}"
                                   checked>
                            <div class="invoice-details">
                                <div class="invoice-number">${invoice.name}</div>
                                <div class="invoice-amount">
                                    Outstanding: ${format_currency(invoice.outstanding_amount)}
                                    | Posted: ${frappe.datetime.str_to_user(invoice.posting_date)}
                                </div>
                            </div>
                        </div>
                        <div class="invoice-allocation">
                            <label style="display:block; margin-bottom:4px; font-size:0.9em;">
                                Amount to Pay:
                            </label>
                            <input type="text"
                                   class="manual-allocation-input"
                                   id="manual_amt_${index}"
                                   data-invoice="${invoice.name}"
                                   value="${format_amount_input(invoice.outstanding_amount)}"
                                   inputmode="decimal"
                                   readonly>
                        </div>
                    </div>
                `;
            });

            html += `
                    </div>
                    <div class="total-section">
                        <div class="total-label">${__("Distributed Amount")}</div>
                        <div class="total-amount" id="manual-total-payment-amount">
                            ${format_amount(total_outstanding)}
                        </div>
                        <div class="payment-summary">
                            ${__("Selected invoices outstanding: {0}", [format_amount(total_outstanding)])}
                        </div>
                        <div class="payment-summary" id="manual-unallocated-payment-amount">
                            ${__("Unallocated Amount: {0}", [format_amount(0)])}
                        </div>
                    </div>
                </div>
            `;

            dialog = new frappe.ui.Dialog({
                title: __('Receive Payment'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'invoice_html',
                        options: html
                    },
                    {
                        fieldname: 'amount_to_collect',
                        label: __('Total Amount to Collect'),
                        fieldtype: 'Currency',
                        reqd: 1,
                        default: total_outstanding,
                        description: __('Enter the full amount received. It will be distributed across selected invoices, and any balance will remain unallocated.')
                    },
                    {
                        fieldname: 'payment_mode',
                        label: __('Mode of Payment'),
                        fieldtype: 'Link',
                        options: 'Mode of Payment',
                        reqd: 1,
                        default: 'Moniepoint - Front Desk'
                    },
                    {
                        fieldname: 'payment_date',
                        label: __('Payment Date'),
                        fieldtype: 'Date',
                        default: frappe.datetime.nowdate(),
                        reqd: 1
                    },
                    {
                        fieldname: 'reference_no',
                        label: __('Reference No'),
                        fieldtype: 'Data'
                    },
                    {
                        fieldname: 'reference_date',
                        label: __('Reference Date'),
                        fieldtype: 'Date'
                    },
                    {
                        fieldname: 'remarks',
                        label: __('Remarks'),
                        fieldtype: 'Small Text'
                    }
                ],
                primary_action_label: __('Submit Payment'),
                primary_action(values) {
                    const allocations = [];
                    let distributed_total = 0;
                    const total_collected = parse_amount(values.amount_to_collect);

                    invoices.forEach((invoice, index) => {
                        const checkbox = document.getElementById(`manual_chk_${index}`);
                        const amount_input = document.getElementById(`manual_amt_${index}`);

                        if (!checkbox || !amount_input || !checkbox.checked) {
                            return;
                        }

                        const allocated_amount = parse_amount(amount_input.value);
                        if (allocated_amount <= 0) {
                            return;
                        }

                        allocations.push({
                            invoice: invoice.name,
                            amount: allocated_amount
                        });
                        distributed_total += allocated_amount;
                    });

                    if (total_collected <= 0) {
                        frappe.msgprint(__('Please enter a total amount greater than zero.'));
                        return;
                    }

                    if (!allocations.length && total_collected <= 0) {
                        frappe.msgprint(__('Please select at least one invoice with an amount greater than zero.'));
                        return;
                    }

                    frappe.call({
                        method: 'rhohotel.rhocom_hotel.api.front_desk.collect_payment_for_checkin',
                        args: {
                            check_in: frm.doc.name,
                            allocations: JSON.stringify(allocations),
                            payment_info: JSON.stringify({
                                mode_of_payment: values.payment_mode,
                                paid_amount: total_collected,
                                payment_date: values.payment_date,
                                reference_no: values.reference_no,
                                reference_date: values.reference_date || values.payment_date,
                                remarks: values.remarks,
                                source_exchange_rate: 1,
                                exchange_rate: 1,
                            })
                        },
                        freeze: true,
                        freeze_message: __('Recording payment...'),
                        callback: function (res) {
                            const payment_entry = res.message && res.message.payment_entry;
                            if (!payment_entry) {
                                frappe.msgprint(__('Payment could not be recorded.'));
                                return;
                            }

                            frappe.msgprint({
                                title: __('Payment Successful'),
                                message: __('Payment Entry {0} created.', [payment_entry]),
                                indicator: 'green'
                            });
                            dialog.hide();
                            frm.reload_doc();
                        }
                    });
                }
            });

            dialog.show();

            setTimeout(() => {
                const update_summary = () => {
                    let distributed_total = 0;
                    let selected_outstanding_total = 0;

                    document.querySelectorAll('.manual-allocation-input').forEach(input => {
                        const invoice_name = input.getAttribute('data-invoice');
                        const checkbox = document.querySelector(`input.manual-payment-checkbox[data-invoice="${invoice_name}"]`);

                        if (checkbox && checkbox.checked) {
                            distributed_total += parse_amount(input.value);
                            selected_outstanding_total += parse_amount(invoice_map[invoice_name].outstanding_amount);
                        }
                    });

                    const total_collected = parse_amount(dialog.get_value('amount_to_collect'));
                    const unallocated_amount = Math.max(total_collected - distributed_total, 0);

                    const totalWrapper = document.getElementById('manual-total-payment-amount');
                    if (totalWrapper) {
                        totalWrapper.textContent = format_amount(distributed_total);
                    }

                    const unallocatedWrapper = document.getElementById('manual-unallocated-payment-amount');
                    if (unallocatedWrapper) {
                        unallocatedWrapper.textContent = __('Selected invoices outstanding: {0}. Unallocated Amount: {1}', [
                            format_amount(selected_outstanding_total),
                            format_amount(unallocated_amount)
                        ]);
                    }
                };

                const get_selected_outstanding_total = () => {
                    let selected_total = 0;

                    invoices.forEach((invoice, index) => {
                        const checkbox = document.getElementById(`manual_chk_${index}`);
                        if (checkbox && checkbox.checked) {
                            selected_total += parse_amount(invoice.outstanding_amount);
                        }
                    });

                    return selected_total;
                };

                const sync_checkbox_visual_state = (checkbox, amount_input) => {
                    if (!checkbox || !amount_input) return;

                    amount_input.disabled = !checkbox.checked;
                    amount_input.style.opacity = checkbox.checked ? '1' : '0.55';
                    amount_input.style.backgroundColor = checkbox.checked ? '' : '#f1f3f5';
                };

                const distribute_total = ({ sync_total_to_selection = false } = {}) => {
                    if (is_syncing_totals) return;

                    const selected_outstanding_total = get_selected_outstanding_total();
                    let total_to_collect = parse_amount(dialog.get_value('amount_to_collect'));

                    if (sync_total_to_selection) {
                        total_to_collect = selected_outstanding_total;
                        is_syncing_totals = true;
                        dialog.set_value('amount_to_collect', total_to_collect);
                        is_syncing_totals = false;
                    }

                    let remaining = Math.max(total_to_collect, 0);

                    is_syncing_totals = true;
                    invoices.forEach((invoice, index) => {
                        const checkbox = document.getElementById(`manual_chk_${index}`);
                        const amount_input = document.getElementById(`manual_amt_${index}`);
                        if (!checkbox || !amount_input) return;

                        sync_checkbox_visual_state(checkbox, amount_input);

                        if (!checkbox.checked) {
                            amount_input.value = format_amount_input(0);
                            return;
                        }

                        const outstanding = parse_amount(invoice.outstanding_amount);
                        const allocated = Math.min(remaining, outstanding);
                        amount_input.value = format_amount_input(allocated);
                        remaining = Math.max(remaining - allocated, 0);
                    });
                    is_syncing_totals = false;
                    update_summary();
                };

                document.querySelectorAll('.manual-payment-checkbox').forEach(checkbox => {
                    checkbox.addEventListener('change', function () {
                        const invoice_name = this.getAttribute('data-invoice');
                        const amount_input = document.querySelector(`input.manual-allocation-input[data-invoice="${invoice_name}"]`);

                        if (!amount_input) return;

                        sync_checkbox_visual_state(this, amount_input);
                        distribute_total({ sync_total_to_selection: true });
                    });
                });

                const totalField = dialog.get_field('amount_to_collect');
                if (totalField && totalField.$input) {
                    totalField.$input.on('input', function () {
                        if (is_syncing_totals) return;
                        distribute_total();
                    });
                }

                distribute_total({ sync_total_to_selection: true });
            }, 100);
        }
    });
}

// NEW FUNCTION: Show invoice selection dialog with partial payment support
function show_invoice_selection_dialog(frm, terminal_id) {
    // Fetch outstanding invoices
    frappe.call({
        method: 'rhohotel.api.get_outstanding_invoices',
        args: {
            check_in: frm.doc.name
        },
        callback: function (r) {
            if (!r.message || r.message.length === 0) {
                frappe.msgprint(__('No outstanding invoices found.'));
                return;
            }

            const invoices = r.message;
            let invoice_fields = [];
            let invoice_map = {};

            // Create HTML for invoice selection
            let html = `
                <div class="invoice-selection-container">
                    <style>
                        .invoice-selection-container {
                            max-height: 400px;
                            overflow-y: auto;
                        }
                        .invoice-item {
                            border: 1px solid #d1d8dd;
                            border-radius: 4px;
                            padding: 12px;
                            margin-bottom: 10px;
                            background: #f8f9fa;
                        }
                        .invoice-item:hover {
                            background: #e9ecef;
                        }
                        .invoice-header {
                            display: flex;
                            align-items: center;
                            margin-bottom: 8px;
                        }
                        .invoice-checkbox {
                            margin-right: 10px;
                            width: 18px;
                            height: 18px;
                        }
                        .invoice-details {
                            flex: 1;
                        }
                        .invoice-number {
                            font-weight: bold;
                            color: #2490ef;
                        }
                        .invoice-amount {
                            color: #6c757d;
                            font-size: 0.9em;
                        }
                        .invoice-allocation {
                            margin-top: 8px;
                            padding-left: 28px;
                        }
                        .allocation-input {
                            width: 100%;
                            padding: 6px;
                            border: 1px solid #d1d8dd;
                            border-radius: 4px;
                        }
                        .total-section {
                            margin-top: 20px;
                            padding: 15px;
                            background: #fff3cd;
                            border: 1px solid #ffc107;
                            border-radius: 4px;
                            text-align: center;
                        }
                        .total-label {
                            font-weight: bold;
                            font-size: 1.1em;
                            color: #333;
                        }
                        .total-amount {
                            font-size: 1.5em;
                            font-weight: bold;
                            color: #28a745;
                            margin-top: 5px;
                        }
                    </style>
                    <div id="invoice-list">
            `;

            invoices.forEach((invoice, index) => {
                invoice_map[invoice.name] = invoice;
                html += `
                    <div class="invoice-item" data-invoice="${invoice.name}">
                        <div class="invoice-header">
                            <input type="checkbox" 
                                   class="invoice-checkbox" 
                                   id="chk_${index}" 
                                   data-invoice="${invoice.name}"
                                   checked>
                            <div class="invoice-details">
                                <div class="invoice-number">${invoice.name}</div>
                                <div class="invoice-amount">
                                    Outstanding: ${format_currency(invoice.outstanding_amount, 'NGN')}
                                    | Posted: ${frappe.datetime.str_to_user(invoice.posting_date)}
                                </div>
                            </div>
                        </div>
                        <div class="invoice-allocation">
                            <label style="display: block; margin-bottom: 4px; font-size: 0.9em;">
                                Amount to Pay:
                            </label>
                            <input type="number" 
                                   class="allocation-input" 
                                   id="amt_${index}"
                                   data-invoice="${invoice.name}"
                                   value="${invoice.outstanding_amount}"
                                   min="0"
                                   max="${invoice.outstanding_amount}"
                                   step="0.01">
                        </div>
                    </div>
                `;
            });

            html += `
                    </div>
                    <div class="total-section">
                        <div class="total-label">Total Payment Amount</div>
                        <div class="total-amount" id="total-payment-amount">
                            ${format_currency(invoices.reduce((sum, inv) => sum + inv.outstanding_amount, 0), 'NGN')}
                        </div>
                    </div>
                </div>
            `;

            // Create dialog
            const d = new frappe.ui.Dialog({
                title: __('Select Invoices to Pay'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'invoice_html',
                        options: html
                    }
                ],
                primary_action_label: __('Proceed to Payment'),
                primary_action: function () {
                    // Collect selected invoices and allocations
                    let invoice_allocations = [];
                    let total = 0;

                    invoices.forEach((invoice, index) => {
                        const checkbox = document.getElementById(`chk_${index}`);
                        const amount_input = document.getElementById(`amt_${index}`);

                        if (checkbox && checkbox.checked && amount_input) {
                            const allocated_amount = parseFloat(amount_input.value) || 0;

                            if (allocated_amount > 0) {
                                invoice_allocations.push({
                                    invoice_number: invoice.name,
                                    allocated_amount: allocated_amount
                                });
                                total += allocated_amount;
                            }
                        }
                    });

                    if (invoice_allocations.length === 0) {
                        frappe.msgprint(__('Please select at least one invoice to pay.'));
                        return;
                    }

                    if (total <= 0) {
                        frappe.msgprint(__('Total payment amount must be greater than zero.'));
                        return;
                    }

                    // Proceed with payment
                    d.hide();
                    initiate_payment_with_allocations(frm, terminal_id, invoice_allocations);
                }
            });

            d.show();

            // Add event listeners after dialog is shown
            setTimeout(() => {
                // Update total when checkbox changes
                document.querySelectorAll('.invoice-checkbox').forEach(checkbox => {
                    checkbox.addEventListener('change', function () {
                        const invoice_name = this.getAttribute('data-invoice');
                        const amount_input = document.querySelector(`input.allocation-input[data-invoice="${invoice_name}"]`);

                        if (!this.checked) {
                            amount_input.value = 0;
                        } else {
                            const invoice = invoice_map[invoice_name];
                            amount_input.value = invoice.outstanding_amount;
                        }

                        update_total();
                    });
                });

                // Update total when amount changes
                document.querySelectorAll('.allocation-input').forEach(input => {
                    input.addEventListener('input', function () {
                        const invoice_name = this.getAttribute('data-invoice');
                        const checkbox = document.querySelector(`input.invoice-checkbox[data-invoice="${invoice_name}"]`);
                        const invoice = invoice_map[invoice_name];

                        let value = parseFloat(this.value) || 0;

                        // Validate amount
                        if (value > invoice.outstanding_amount) {
                            value = invoice.outstanding_amount;
                            this.value = value;
                            frappe.show_alert({
                                message: __('Amount cannot exceed outstanding amount'),
                                indicator: 'orange'
                            });
                        }

                        if (value < 0) {
                            value = 0;
                            this.value = 0;
                        }

                        // Auto-check/uncheck checkbox based on amount
                        checkbox.checked = value > 0;

                        update_total();
                    });
                });

                function update_total() {
                    let total = 0;
                    document.querySelectorAll('.allocation-input').forEach(input => {
                        const checkbox = document.querySelector(`input.invoice-checkbox[data-invoice="${input.getAttribute('data-invoice')}"]`);
                        if (checkbox && checkbox.checked) {
                            total += parseFloat(input.value) || 0;
                        }
                    });

                    document.getElementById('total-payment-amount').textContent = format_currency(total, 'NGN');
                }
            }, 100);
        }
    });
}

// NEW FUNCTION: Initiate payment with allocations
function initiate_payment_with_allocations(frm, terminal_id, invoice_allocations) {
    frappe.call({
        method: 'rhohotel.api.initiate_payment',
        args: {
            check_in: frm.doc.name,
            terminal_id: terminal_id,
            invoice_allocations: JSON.stringify(invoice_allocations)
        },
        callback: function (r) {
            if (r.message && r.message.name) {
                show_payment_dialog(frm, r.message);
            } else {
                frappe.msgprint(__('Failed to initiate payment. Please try again.'));
            }
        },
        error: function (r) {
            frappe.msgprint(__('Error initiating payment: {0}', [r.message || 'Unknown error']));
        }
    });
}

// UPDATED FUNCTION: Show payment confirmation dialog
function show_payment_dialog(frm, payment_session) {
    const d = new frappe.ui.Dialog({
        title: __('Complete Payment on POS Terminal'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'instructions',
                options: `<div class="alert alert-info">
                    <strong>Payment request sent to terminal: ${payment_session.terminal_id}</strong><br>
                    Please complete the transaction on the POS terminal, then click "Confirm Payment" below.
                </div>`
            },
            {
                label: 'Payment Reference',
                fieldname: 'payment_reference',
                fieldtype: 'Data',
                default: payment_session.payment_reference,
                read_only: 1
            },
            {
                label: 'Total Amount',
                fieldname: 'total_amount',
                fieldtype: 'Currency',
                default: payment_session.total_amount,
                read_only: 1
            }
        ],
        secondary_action_label: 'Resend Request',
        secondary_action() {
            frappe.call({
                method: 'rhohotel.api.resend_payment_request',
                args: { payment_session_name: payment_session.name },
                callback: function (res) {
                    if (res.message && res.message.success) {
                        frappe.show_alert({
                            message: __('Payment request resent successfully.'),
                            indicator: 'green'
                        });
                        // Update the payment reference in the dialog
                        frappe.call({
                            method: 'frappe.client.get_value',
                            args: {
                                doctype: 'Payment Session',
                                filters: { name: payment_session.name },
                                fieldname: 'payment_reference'
                            },
                            callback: function (r) {
                                if (r.message) {
                                    d.set_value('payment_reference', r.message.payment_reference);
                                }
                            }
                        });
                    } else {
                        frappe.msgprint({
                            title: __('Resend Failed'),
                            message: res.message?.message || __('Failed to resend payment request.'),
                            indicator: 'red'
                        });
                    }
                }
            });
        },
        primary_action_label: 'Confirm Payment',
        primary_action(values) {
            // Disable the button to prevent multiple clicks
            d.get_primary_btn().prop('disabled', true);

            frappe.call({
                method: 'rhohotel.api.complete_payment',
                args: { payment_session: payment_session.name },
                callback: function (res) {
                    // Re-enable the button
                    d.get_primary_btn().prop('disabled', false);

                    if (res.message && res.message.success === true) {
                        frappe.show_alert({
                            message: __('Payment verified successfully!'),
                            indicator: 'green'
                        });
                        d.hide();
                        frm.reload_doc();

                        // Ask if they want to print receipt
                        frappe.confirm(
                            __('Do you want to print the payment receipt?'),
                            () => {
                                window.open(
                                    `/printview?doctype=Payment%20Session&name=${res.message.name}&format=Payment%20Receipt&no_letterhead=0`,
                                    '_blank'
                                );
                            }
                        );
                    } else {
                        // Payment is still pending or failed
                        const error_msg = res.message?.message || 'Payment is still pending. Please try again later.';
                        frappe.msgprint({
                            title: __('Payment Not Complete'),
                            message: __(error_msg),
                            indicator: 'orange',
                            primary_action: {
                                label: __('Check Again'),
                                action() {
                                    // Re-trigger the payment check
                                    d.get_primary_btn().trigger('click');
                                }
                            }
                        });
                    }
                },
                error: function (r) {
                    d.get_primary_btn().prop('disabled', false);
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('Error verifying payment: {0}', [r.message || 'Unknown error']),
                        indicator: 'red'
                    });
                }
            });
        }
    });
    d.show();
}

function render_invoices(invoices) {
    let html = `<table class="table table-bordered">
        <thead>
            <tr>
                <th>Invoice</th>
                <th>Type / Profile</th>
                <th>Customer</th>
                <th>Posting Date</th>
                <th>Grand Total</th>
                <th>Balance</th>
            </tr>
        </thead>
        <tbody>`;

    let total_grand_total = 0;
    let total_outstanding_amount = 0;

    if (invoices.length > 0) {
        invoices.forEach(invoice => {
            total_grand_total += invoice.grand_total || 0;
            total_outstanding_amount += invoice.outstanding_amount || 0;

            const doctype_route = invoice.invoice_type === "POS Invoice"
                ? "pos-invoice"
                : "sales-invoice";

            // POS Invoice → show POS Profile
            // Sales Invoice → show "Sales Invoice"
            const type_or_profile =
                invoice.invoice_type === "POS Invoice"
                    ? (invoice.pos_profile || "POS Invoice")
                    : "Sales Invoice";

            html += `<tr>
                <td><a href="/app/${doctype_route}/${invoice.name}">${invoice.name}</a></td>
                <td>${type_or_profile}</td>
                <td>${invoice.customer}</td>
                <td>${frappe.datetime.str_to_user(invoice.posting_date)}</td>
                <td>${format_currency(invoice.grand_total)}</td>
                <td>${format_currency(invoice.outstanding_amount)}</td>
            </tr>`;
        });
    } else {
        html += `<tr>
            <td colspan="6" class="text-center">No Invoices Found</td>
        </tr>`;
    }

    html += `</tbody>`;

    // ✅ Add total row (same as your original implementation)
    if (invoices.length > 0) {
        html += `<tfoot>
            <tr style="font-weight: bold; background-color: #f8f9fa;">
                <td colspan="4">Total</td>
                <td>${format_currency(total_grand_total)}</td>
                <td>${format_currency(total_outstanding_amount)}</td>
            </tr>
        </tfoot>`;
    }

    html += `</table>`;
    return html;
}

function render_journal_entries(entries) {
    let html = `<table class="table table-bordered">
        <thead>
            <tr>
                <th>Journal Entry</th>
                <th>Type</th>
                <th>Posting Date</th>
                <th>Party</th>
                <th>Total Debit</th>
                <th>Remarks</th>
            </tr>
        </thead>
        <tbody>`;

    let total_debit = 0;
    let total_credit = 0;

    if (entries && entries.length > 0) {
        entries.forEach(je => {
            total_debit += je.total_debit || 0;

            html += `<tr>
                <td><a href="/app/journal-entry/${je.name}">${je.name}</a></td>
                <td>${je.voucher_type || ""}</td>
                <td>${frappe.datetime.str_to_user(je.posting_date)}</td>
                <td>${je.party || ""}</td>
                <td>${format_currency(je.total_debit)}</td>
                <td>${je.remarks || ""}</td>
            </tr>`;
        });
    } else {
        html += `<tr>
            <td colspan="7" class="text-center">No Journal Entries Found</td>
        </tr>`;
    }

    html += `</tbody>`;

    // Add totals row if there are entries
    if (entries && entries.length > 0) {
        html += `
        <tfoot>
            <tr style="font-weight:bold; background-color:#f8f9fa;">
                <td colspan="4">Total</td>
                <td>${format_currency(total_debit)}</td>
                <td>${format_currency(total_credit)}</td>
                <td></td>
            </tr>
        </tfoot>`;
    }

    html += `</table>`;

    return html;
}





function render_payments(payments) {
    let html = `<table class="table table-bordered">
        <thead>
            <tr>
                <th>Payment Entry</th>
                <th>Party</th>
                <th>Posting Date</th>
                <th>Paid Amount</th>
            </tr>
        </thead>
        <tbody>`;
    let total_paid_amount = 0;
    if (payments.length > 0) {
        payments.forEach(payment => {
            total_paid_amount += payment.paid_amount || 0;
            html += `<tr>
                <td><a href="/app/payment-entry/${payment.name}">${payment.name}</a></td>
                <td>${payment.party}</td>
                <td>${frappe.datetime.str_to_user(payment.posting_date)}</td>
                <td>${format_currency(payment.paid_amount)}</td>
            </tr>`;
        });
    } else {
        html += '<tr><td colspan="4" class="text-center">No Payments Found</td></tr>';
    }
    html += '</tbody>';
    if (payments.length > 0) {
        html += `<tfoot>
            <tr style="font-weight: bold; background-color: #f8f9fa;">
                <td colspan="3">Total</td>
                <td>${format_currency(total_paid_amount)}</td>
            </tr>
        </tfoot>`;
    }
    html += '</table>';
    return html;
}
