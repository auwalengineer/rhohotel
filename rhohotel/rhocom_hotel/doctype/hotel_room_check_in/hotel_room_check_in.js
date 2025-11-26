// Copyright (c) 2024, Rhocom Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hotel Room Check In", {
    refresh(frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__("Refund"), () => {
                frappe.model.open_mapped_doc({
                    method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_refund',
                    frm: frm
                });
            });
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
                        frm.fields_dict.payments_html.html(render_payments(r.message.payments));
                        //frm.set_value('total_outstanding_amount', r.message.total_outstanding_amount);
                        //frm.set_value('total_charges', r.message.total_outstanding_amount);


                        if (r.message.total_outstanding_amount > 0) {
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
                                        // Dropdown for multiple terminals - clean Frappe way, no manual DOM
                                        frm.add_custom_button(button_label, null, button_label);

                                        terminals.forEach(terminal => {
                                            frm.add_custom_button(
                                                terminal.terminal_name || terminal.name,
                                                function () {
                                                    initiate_payment(frm, terminal.name);
                                                },
                                                button_label
                                            );
                                        });
                                    } else if (terminals.length === 1) {
                                        // Single terminal - normal button
                                        frm.add_custom_button(button_label, function () {
                                            initiate_payment(frm, terminals[0].name);
                                        });
                                    }
                                }
                            });
                        }

                        function initiate_payment(frm, terminal_id) {
                            frappe.call({
                                method: 'rhohotel.api.initiate_payment',
                                args: {
                                    check_in: frm.doc.name,
                                    terminal_id: terminal_id
                                },
                                callback: function (r) {
                                    if (r.message && r.message.name) {
                                        const d = new frappe.ui.Dialog({
                                            title: `Payment request was successfully sent to pos terminal: ${r.message.terminal_id}, \nComplete the transaction and select Confirm payment`,
                                            fields: [
                                                { label: 'Payment Reference', fieldname: 'payment_reference', fieldtype: 'Data', default: r.message.payment_reference, read_only: 1 },
                                                { label: 'Total Amount', fieldname: 'total_amount', fieldtype: 'Currency', default: r.message.total_amount, read_only: 1 }
                                            ],
                                            primary_action_label: 'Confirm Payment',
                                            primary_action(values) {
                                                frappe.call({
                                                    method: 'rhohotel.api.complete_payment',
                                                    args: { payment_session: r.message.name },
                                                    callback: function (res) {
                                                        if (res.message.success === false) {
                                                            frappe.msgprint(__('Payment is still pending. Please try again later.'));
                                                            return;
                                                        } else {
                                                            frappe.msgprint(__('Payment Verified successfully.'));
                                                            d.hide();
                                                            frm.reload_doc();

                                                            frappe.confirm(
                                                                __('Do you want to print the payment receipt?'),
                                                                () => {
                                                                    frappe.open_route_options({ "doctype": "Payment Session", "name": r.message.name, "print_format": "Payment Receipt" });
                                                                }
                                                            );
                                                        }
                                                    }
                                                });
                                            }
                                        });
                                        d.show();
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
            frm.add_custom_button(__("Check Out"), () => {
                frappe.model.open_mapped_doc({
                    method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
                    frm: frm
                });
            });

            frm.add_custom_button(__("Extend Stay"), () => {
                let d = new frappe.ui.Dialog({
                    title: __('Extend Stay'),
                    fields: [
                        {
                            label: __('Current Expected Check-out'),
                            fieldname: 'current_checkout',
                            fieldtype: 'Datetime',
                            default: frm.doc.expected_check_out_datetime,
                            read_only: 1
                        },
                        {
                            label: __('Number of Nights'),
                            fieldname: 'number_of_nights',
                            fieldtype: 'Int',
                            reqd: 1,
                            default: 1,
                            onchange: () => {
                                let nights = d.get_value('number_of_nights');
                                if (nights > 0) {
                                    let current_checkout = frm.doc.expected_check_out_datetime;
                                    let new_checkout = frappe.datetime.add_days(current_checkout, nights);

                                    // set time part from default check-out time from Hotel Settings
                                    frappe.call({
                                        method: "rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time",
                                        callback: function (r) {
                                            if (!r.exc) {
                                                let default_check_out_time = r.message;
                                                if (default_check_out_time) {
                                                    let datePart = new_checkout.split(" ")[0];
                                                    new_checkout = datePart + " " + default_check_out_time;
                                                    d.set_value('new_checkout', new_checkout);
                                                } else {
                                                    d.set_value('new_checkout', new_checkout);
                                                }
                                            } else {
                                                d.set_value('new_checkout', '');

                                            }
                                        }
                                    });


                                } else {
                                    d.set_value('new_checkout', '');
                                }
                            }
                        },
                        {
                            label: __('New Expected Check-out'),
                            fieldname: 'new_checkout',
                            fieldtype: 'Datetime',
                            read_only: 1
                        }
                    ],
                    on_page_show: () => { d.fields_dict.number_of_nights.df.onchange(); },
                    primary_action_label: __('Confirm Extension'),
                    primary_action: (values) => {
                        frappe.call({
                            method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.extend_stay',
                            args: {
                                check_in_name: frm.doc.name,
                                number_of_nights: values.number_of_nights
                            },
                            callback: (r) => {
                                if (!r.exc) {
                                    frm.reload_doc();
                                    d.hide();
                                }
                            }
                        });
                    }
                });
                d.show();
            });

            if (frm.doc.docstatus === 1 && frm.doc.status === "Checked In") {
                frm.add_custom_button(__('Transfer Room'), function () {
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
                            frappe.call({
                                method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.transfer_room',
                                args: {
                                    check_in_name: frm.doc.name,
                                    new_room_number: values.new_room_number,
                                    note: values.transfer_note
                                },
                                callback: function (r) {
                                    if (!r.exc) {
                                        frappe.msgprint(__('Guest transferred successfully to Room {0}').format(values.new_room_number));
                                        frm.reload_doc();
                                    }
                                    frm.reload_doc();
                                },
                                error: function (r) {
                                    frappe.msgprint(__('Room transfer failed'));
                                }
                            });
                            dialog.hide();
                        }
                    });
                    dialog.show();
                });
            }

            // frm.add_custom_button(__("Transfer Room"), () => {
            //     let d = new frappe.ui.Dialog({
            //         title: __('Transfer Room'),
            //         fields: [
            //             {
            //                 label: __('New Room'),
            //                 fieldname: 'new_room',
            //                 fieldtype: 'Link',
            //                 options: 'Hotel Room',
            //                 reqd: 1,
            //                 get_query: function () {
            //                     return {
            //                         filters: {
            //                             'status': 'Vacant'
            //                         }
            //                     };
            //                 }
            //             },
            //             {
            //                 label: __('Reason'),
            //                 fieldname: 'reason',
            //                 fieldtype: 'Text'
            //             }
            //         ],
            //         primary_action_label: __('Confirm Transfer'),
            //         primary_action: (values) => {
            //             frappe.call({
            //                 method: 'frappe.client.insert',
            //                 args: {
            //                     doc: {
            //                         doctype: 'Hotel Room Transfer',
            //                         check_in: frm.doc.name,
            //                         from_room: frm.doc.room_number,
            //                         to_room: values.new_room,
            //                         reason: values.reason,
            //                         docstatus: 1
            //                     }
            //                 },
            //                 callback: (r) => {
            //                     if (!r.exc) {
            //                         frm.reload_doc();
            //                         d.hide();
            //                     }
            //                 }
            //             });
            //         }
            //     });
            //     d.show();
            // });



        }

        // Set dynamic filter for Business Source
        frm.set_query("business_source", function () {
            return {
                filters: {
                    reservation_source: frm.doc.market_source || ""

                }
            };
        })
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
    },


    setup(frm) {
        // Fetch check-out date from reservation when reservation is set
        frm.set_query("room", function () {
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
        // Clear old value when market source changes
        frm.set_value('business_source', null);

        // Trigger the query update
        frm.fields_dict.business_source.get_query();
    },
    reservation(frm) {
        if (frm.doc.reservation) {
            frm.set_df_property('room_number', 'read_only', 1);
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Hotel Room Reservation",
                    name: frm.doc.reservation
                },
                callback: function (r) {
                    if (r.message) { // r.message contains the reservation document
                        frm.set_value('room_number', r.message.room_number);
                        frm.set_value('room_type', r.message.room_type);
                        frm.set_value('number_of_nights', r.message.number_of_nights);
                    }
                },
            });
        } else {
            frm.set_df_property('room_number', 'read_only', 0);
            // Clear fields if reservation is cleared
            frm.set_value('room_number', null);
            frm.set_value('room_type', null);
            frm.set_value('number_of_nights', null);

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
            //let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
            //let check_out = frappe.datetime.str_to_obj(frm.doc.expected_check_out_datetime);
            let nights = frm.doc.number_of_nights;
            frm.set_value('total_charges', nights * frm.doc.rate_amount);
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
        // Do not fetch rate if a reservation is already linked
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
                    check_in_date: frm.doc.check_in_datetime.split(" ")[0] // Pass only the date part
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
        if (frm.doc.check_in_datetime && frm.doc.number_of_nights) {
            let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
            let new_checkout = frappe.datetime.add_days(check_in, frm.doc.number_of_nights);

            // set time part from default check-out time from Hotel Settings
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
            //
            frm.set_value('expected_check_out_datetime', new_checkout);
        }
    }
});

function render_invoices(invoices) {

    let html = `<table class="table table-bordered">
        <thead>
            <tr>
                <th>Sales Invoice</th>
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
            html += `<tr>
                <td><a href="/app/sales-invoice/${invoice.name}">${invoice.name}</a></td>
                <td>${invoice.customer}</td>
                <td>${frappe.datetime.str_to_user(invoice.posting_date)}</td>
                <td>${format_currency(invoice.grand_total)}</td>
                <td>${format_currency(invoice.outstanding_amount)}</td>
            </tr>`;
        });
    } else {
        html += '<tr><td colspan="5" class="text-center">No Invoices Found</td></tr>';
    }
    html += '</tbody>';
    if (invoices.length > 0) {
        html += `<tfoot>
            <tr style="font-weight: bold; background-color: #f8f9fa;">
                <td colspan="3">Total</td>
                <td>${format_currency(total_grand_total)}</td>
                <td>${format_currency(total_outstanding_amount)}</td>
            </tr>
        </tfoot>`;
    }
    html += '</table>';

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