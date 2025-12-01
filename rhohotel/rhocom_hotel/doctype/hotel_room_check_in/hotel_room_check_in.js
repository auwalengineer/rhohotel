// // Copyright (c) 2024, Rhocom Technologies and contributors
// // For license information, please see license.txt

// frappe.ui.form.on("Hotel Room Check In", {
//     refresh(frm) {
//         if (frm.doc.docstatus === 1) {
//             frm.add_custom_button(__("Refund"), () => {
//                 frappe.model.open_mapped_doc({
//                     method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_refund',
//                     frm: frm
//                 });
//             });
//         }
//         if (frm.doc.docstatus === 1) {
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.get_linked_documents',
//                 args: {
//                     check_in: frm.doc.name
//                 },
//                 callback: function (r) {

//                     if (r.message) {

//                         frm.fields_dict.invoices_html.html(render_invoices(r.message.invoices));
//                         frm.fields_dict.payments_html.html(render_payments(r.message.payments));
//                         //frm.set_value('total_outstanding_amount', r.message.total_outstanding_amount);
//                         //frm.set_value('total_charges', r.message.total_outstanding_amount);


//                         if (r.message.total_outstanding_amount > 0) {
//                             // Fetch terminals and create payment buttons
//                             frappe.call({
//                                 method: 'frappe.client.get_list',
//                                 args: {
//                                     doctype: 'Moniepoint Terminal',
//                                     parent: 'Moniepoint Settings',
//                                     fields: ['name', 'terminal_name'],
//                                     filters: {
//                                         parenttype: 'Moniepoint Settings',
//                                         parentfield: 'terminals'
//                                     }
//                                 },
//                                 callback: function (res) {
//                                     const terminals = res.message || [];
//                                     const button_label = __('Pay with Moniepoint');
//                                     if (terminals.length > 1) {
//                                         // Dropdown for multiple terminals - clean Frappe way, no manual DOM
//                                         frm.add_custom_button(button_label, null, button_label);

//                                         terminals.forEach(terminal => {
//                                             frm.add_custom_button(
//                                                 terminal.terminal_name || terminal.name,
//                                                 function () {
//                                                     initiate_payment(frm, terminal.name);
//                                                 },
//                                                 button_label
//                                             );
//                                         });
//                                     } else if (terminals.length === 1) {
//                                         // Single terminal - normal button
//                                         frm.add_custom_button(button_label, function () {
//                                             initiate_payment(frm, terminals[0].name);
//                                         });
//                                     }
//                                 }
//                             });
//                         }

//                         function initiate_payment(frm, terminal_id) {
//                             frappe.call({
//                                 method: 'rhohotel.api.initiate_payment',
//                                 args: {
//                                     check_in: frm.doc.name,
//                                     terminal_id: terminal_id
//                                 },
//                                 callback: function (r) {
//                                     if (r.message && r.message.name) {
//                                         const d = new frappe.ui.Dialog({
//                                             title: `Payment request was successfully sent to pos terminal: ${r.message.terminal_id}, \nComplete the transaction and select Confirm payment`,
//                                             fields: [
//                                                 { label: 'Payment Reference', fieldname: 'payment_reference', fieldtype: 'Data', default: r.message.payment_reference, read_only: 1 },
//                                                 { label: 'Total Amount', fieldname: 'total_amount', fieldtype: 'Currency', default: r.message.total_amount, read_only: 1 }
//                                             ],
//                                             secondary_action_label: 'Resend Request',
//                                             secondary_action() {
//                                                 frappe.call({
//                                                     method: 'rhohotel.api.resend_payment_request',
//                                                     args: { payment_session_name: r.message.name },
//                                                     callback: function (res) {
//                                                         if (res.message && res.message.success) {
//                                                             frappe.show_alert({ message: __('Payment request resent successfully.'), indicator: 'green' });
//                                                         } else {
//                                                             frappe.msgprint(__('Failed to resend payment request.'));
//                                                         }
//                                                     }
//                                                 });
//                                             },
//                                             primary_action_label: 'Confirm Payment',
//                                             primary_action(values) {
//                                                 frappe.call({
//                                                     method: 'rhohotel.api.complete_payment',
//                                                     args: { payment_session: r.message.name },
//                                                     callback: function (res) {
//                                                         if (res.message.success === false) {
//                                                             frappe.msgprint(__('Payment is still pending. Please try again later.'));
//                                                             return;
//                                                         } else {
//                                                             frappe.msgprint(__('Payment Verified successfully.'));
//                                                             d.hide();
//                                                             frm.reload_doc();

//                                                             frappe.confirm(
//                                                                 __('Do you want to print the payment receipt?'),
//                                                                 () => {
//                                                                     frappe.open_route_options({ "doctype": "Payment Session", "name": r.message.name, "print_format": "Payment Receipt" });
//                                                                 }
//                                                             );
//                                                         }
//                                                     }
//                                                 });
//                                             }
//                                         });
//                                         d.show();
//                                     }
//                                 }
//                             });
//                         }

//                         // Add Print Receipt button if there are paid sessions
//                         if (r.message.payment_sessions && r.message.payment_sessions.length > 0) {
//                             frm.add_custom_button(__('Print Receipt'), function () {
//                                 let dialog = new frappe.ui.Dialog({
//                                     title: __('Select a Payment to Print'),
//                                     fields: [
//                                         {
//                                             label: __('Payment Session'),
//                                             fieldname: 'payment_session',
//                                             fieldtype: 'Link',
//                                             options: 'Payment Session',
//                                             reqd: 1,
//                                             get_query: function () {
//                                                 return {
//                                                     filters: {
//                                                         'hotel_room_check_in': frm.doc.name,
//                                                         'status': 'Paid'
//                                                     }
//                                                 };
//                                             }
//                                         }
//                                     ],
//                                     primary_action_label: __('Print'),
//                                     primary_action: (values) => {
//                                         window.open(
//                                             `/printview?doctype=Payment%20Session&name=${values.payment_session}&format=Payment%20Receipt&no_letterhead=0`,
//                                             '_blank'
//                                         );
//                                         dialog.hide();
//                                     }
//                                 });
//                                 dialog.show();
//                             });

//                         }
//                     }
//                 }
//             });
//         }


//         // Add custom buttons based on status
//         if (frm.doc.docstatus === 1 && frm.doc.status === "Checked In") {
//             frm.add_custom_button(__("Check Out"), () => {
//                 frappe.model.open_mapped_doc({
//                     method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
//                     frm: frm
//                 });
//             });

//             frm.add_custom_button(__("Extend Stay"), () => {
//                 let d = new frappe.ui.Dialog({
//                     title: __('Extend Stay'),
//                     fields: [
//                         {
//                             label: __('Current Expected Check-out'),
//                             fieldname: 'current_checkout',
//                             fieldtype: 'Datetime',
//                             default: frm.doc.expected_check_out_datetime,
//                             read_only: 1
//                         },
//                         {
//                             label: __('Number of Nights'),
//                             fieldname: 'number_of_nights',
//                             fieldtype: 'Int',
//                             reqd: 1,
//                             default: 1,
//                             onchange: () => {
//                                 let nights = d.get_value('number_of_nights');
//                                 if (nights > 0) {
//                                     let current_checkout = frm.doc.expected_check_out_datetime;
//                                     let new_checkout = frappe.datetime.add_days(current_checkout, nights);

//                                     // set time part from default check-out time from Hotel Settings
//                                     frappe.call({
//                                         method: "rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time",
//                                         callback: function (r) {
//                                             if (!r.exc) {
//                                                 let default_check_out_time = r.message;
//                                                 if (default_check_out_time) {
//                                                     let datePart = new_checkout.split(" ")[0];
//                                                     new_checkout = datePart + " " + default_check_out_time;
//                                                     d.set_value('new_checkout', new_checkout);
//                                                 } else {
//                                                     d.set_value('new_checkout', new_checkout);
//                                                 }
//                                             } else {
//                                                 d.set_value('new_checkout', '');

//                                             }
//                                         }
//                                     });


//                                 } else {
//                                     d.set_value('new_checkout', '');
//                                 }
//                             }
//                         },
//                         {
//                             label: __('New Expected Check-out'),
//                             fieldname: 'new_checkout',
//                             fieldtype: 'Datetime',
//                             read_only: 1
//                         }
//                     ],
//                     on_page_show: () => { d.fields_dict.number_of_nights.df.onchange(); },
//                     primary_action_label: __('Confirm Extension'),
//                     primary_action: (values) => {
//                         frappe.call({
//                             method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.extend_stay',
//                             args: {
//                                 check_in_name: frm.doc.name,
//                                 number_of_nights: values.number_of_nights
//                             },
//                             callback: (r) => {
//                                 if (!r.exc) {
//                                     frm.reload_doc();
//                                     d.hide();
//                                 }
//                             }
//                         });
//                     }
//                 });
//                 d.show();
//             });

//             if (frm.doc.docstatus === 1 && frm.doc.status === "Checked In") {
//                 frm.add_custom_button(__('Transfer Room'), function () {
//                     const dialog = new frappe.ui.Dialog({
//                         title: __('Transfer Guest to Another Room'),
//                         fields: [
//                             {
//                                 label: 'New Room',
//                                 fieldname: 'new_room_number',
//                                 fieldtype: 'Link',
//                                 options: 'Hotel Room',
//                                 reqd: 1,
//                                 get_query: () => ({
//                                     filters: { status: 'Vacant', housekeeping_status: 'Clean' }
//                                 })
//                             },
//                             {
//                                 label: 'Transfer Reason / Note',
//                                 fieldname: 'transfer_note',
//                                 fieldtype: 'Small Text'
//                             }
//                         ],
//                         primary_action_label: 'Transfer',
//                         primary_action(values) {
//                             frappe.call({
//                                 method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.transfer_room',
//                                 args: {
//                                     check_in_name: frm.doc.name,
//                                     new_room_number: values.new_room_number,
//                                     note: values.transfer_note
//                                 },
//                                 callback: function (r) {
//                                     if (!r.exc) {
//                                         frappe.msgprint(__('Guest transferred successfully to Room {0}').format(values.new_room_number));
//                                         frm.reload_doc();
//                                     }
//                                     frm.reload_doc();
//                                 },
//                                 error: function (r) {
//                                     frappe.msgprint(__('Room transfer failed'));
//                                 }
//                             });
//                             dialog.hide();
//                         }
//                     });
//                     dialog.show();
//                 });
//             }

//             // frm.add_custom_button(__("Transfer Room"), () => {
//             //     let d = new frappe.ui.Dialog({
//             //         title: __('Transfer Room'),
//             //         fields: [
//             //             {
//             //                 label: __('New Room'),
//             //                 fieldname: 'new_room',
//             //                 fieldtype: 'Link',
//             //                 options: 'Hotel Room',
//             //                 reqd: 1,
//             //                 get_query: function () {
//             //                     return {
//             //                         filters: {
//             //                             'status': 'Vacant'
//             //                         }
//             //                     };
//             //                 }
//             //             },
//             //             {
//             //                 label: __('Reason'),
//             //                 fieldname: 'reason',
//             //                 fieldtype: 'Text'
//             //             }
//             //         ],
//             //         primary_action_label: __('Confirm Transfer'),
//             //         primary_action: (values) => {
//             //             frappe.call({
//             //                 method: 'frappe.client.insert',
//             //                 args: {
//             //                     doc: {
//             //                         doctype: 'Hotel Room Transfer',
//             //                         check_in: frm.doc.name,
//             //                         from_room: frm.doc.room_number,
//             //                         to_room: values.new_room,
//             //                         reason: values.reason,
//             //                         docstatus: 1
//             //                     }
//             //                 },
//             //                 callback: (r) => {
//             //                     if (!r.exc) {
//             //                         frm.reload_doc();
//             //                         d.hide();
//             //                     }
//             //                 }
//             //             });
//             //         }
//             //     });
//             //     d.show();
//             // });



//         }

//         // Set dynamic filter for Business Source
//         frm.set_query("business_source", function () {
//             return {
//                 filters: {
//                     reservation_source: frm.doc.market_source || ""

//                 }
//             };
//         })
//     },

//     on_submit: function (frm) {
//         frappe.confirm(
//             __('Do you want to issue a key card for this guest?'),
//             () => {
//                 const guestName = frm.doc.guest_name;
//                 const checkInName = frm.doc.name;
//                 const roomNumber = frm.doc.room_number;
//                 const checkInDateTime = frm.doc.check_in_datetime;
//                 const checkOutDateTime = frm.doc.expected_check_out_datetime;

//                 const url = `hotel-key-card-issuer://issue?guestName=${encodeURIComponent(guestName)}&checkInName=${encodeURIComponent(checkInName)}&roomNumber=${encodeURIComponent(roomNumber)}&checkInDateTime=${encodeURIComponent(checkInDateTime)}&checkOutDateTime=${encodeURIComponent(checkOutDateTime)}`;
//                 window.open(url, '_self');
//             },
//             () => { }
//         );
//     },

//     onload: function (frm) {
//         if (!frm.is_new() && frm.doc.guest) {
//             frm.add_custom_button(__('Ledger'), function () {
//                 frappe.call({
//                     method: 'frappe.client.get_value',
//                     args: {
//                         doctype: 'Hotel Guest',
//                         filters: { name: frm.doc.guest },
//                         fieldname: 'customer'
//                     },
//                     callback: function (r) {
//                         if (r.message && r.message.customer) {
//                             frappe.set_route('query-report', 'General Ledger', {
//                                 party_type: 'Customer',
//                                 party: r.message.customer
//                             });
//                         }
//                     }
//                 });
//             });
//         }
//     },


//     setup(frm) {
//         // Fetch check-out date from reservation when reservation is set
//         frm.set_query("room", function () {
//             return {
//                 filters: {
//                     "status": "Vacant"
//                 }
//             };
//         });

//         frm.set_query("reservation", function () {
//             return {
//                 filters: {
//                     "docstatus": 1,
//                     "status": ["in", ["Confirmed", "Booked"]]
//                 }
//             };
//         });
//     },


//     market_source: function (frm) {
//         // Clear old value when market source changes
//         frm.set_value('business_source', null);

//         // Trigger the query update
//         frm.fields_dict.business_source.get_query();
//     },
//     reservation(frm) {
//         if (frm.doc.reservation) {
//             frm.set_df_property('room_number', 'read_only', 1);
//             frappe.call({
//                 method: "frappe.client.get",
//                 args: {
//                     doctype: "Hotel Room Reservation",
//                     name: frm.doc.reservation
//                 },
//                 callback: function (r) {
//                     if (r.message) { // r.message contains the reservation document
//                         frm.set_value('room_number', r.message.room_number);
//                         frm.set_value('room_type', r.message.room_type);
//                         frm.set_value('number_of_nights', r.message.number_of_nights);
//                     }
//                 },
//             });
//         } else {
//             frm.set_df_property('room_number', 'read_only', 0);
//             // Clear fields if reservation is cleared
//             frm.set_value('room_number', null);
//             frm.set_value('room_type', null);
//             frm.set_value('number_of_nights', null);

//         }
//     },

//     expected_check_out_datetime: function (frm) {
//         frm.trigger('calculate_total_charges');
//     },

//     number_of_nights: function (frm) {
//         frm.trigger('calculate_total_charges');
//     },

//     rate_amount: function (frm) {
//         frm.trigger('calculate_total_charges');
//     },

//     calculate_total_charges: function (frm) {
//         if (frm.doc.check_in_datetime && frm.doc.expected_check_out_datetime && frm.doc.rate_amount) {
//             //let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
//             //let check_out = frappe.datetime.str_to_obj(frm.doc.expected_check_out_datetime);
//             let nights = frm.doc.number_of_nights;
//             frm.set_value('total_charges', nights * frm.doc.rate_amount);
//         }
//     },

//     room_number: function (frm) {
//         if (frm.doc.room_number) {
//             frappe.call({
//                 method: 'frappe.client.get_value',
//                 args: {
//                     doctype: 'Hotel Room',
//                     filters: { name: frm.doc.room_number },
//                     fieldname: 'room_type'
//                 },
//                 callback: function (response) {
//                     if (response.message) {
//                         frm.set_value('room_type', response.message.room_type);
//                         frm.trigger('fetch_rate');
//                     }
//                 }
//             });
//         }
//     },

//     rate_type: function (frm) {
//         frm.trigger('fetch_rate');
//     },

//     check_in_datetime: function (frm) {
//         frm.trigger('fetch_rate');
//     },

//     fetch_rate: function (frm) {
//         // Do not fetch rate if a reservation is already linked
//         if (frm.doc.reservation) {
//             frappe.show_alert({ message: __("Rate is based on the linked reservation."), indicator: "info" });
//             return;
//         }

//         if (frm.doc.room_type && frm.doc.check_in_datetime) {
//             frappe.call({
//                 method: 'rhohotel.api.get_room_rate',
//                 args: {
//                     room_type: frm.doc.room_type,
//                     rate_type: "",
//                     check_in_date: frm.doc.check_in_datetime.split(" ")[0] // Pass only the date part
//                 },
//                 callback: function (response) {
//                     if (response.message && !response.message.error) {
//                         frm.set_value('rate_amount', response.message);
//                     } else {
//                         if (response.message.error) {
//                             frappe.show_alert({
//                                 message: __(response.message.error),
//                                 indicator: 'red'
//                             });
//                         }
//                         frm.set_value('rate_amount', 0);
//                     }
//                 }
//             });
//         }
//     },

//     number_of_nights: function (frm) {
//         if (frm.doc.check_in_datetime && frm.doc.number_of_nights) {
//             let check_in = frappe.datetime.str_to_obj(frm.doc.check_in_datetime);
//             let new_checkout = frappe.datetime.add_days(check_in, frm.doc.number_of_nights);

//             // set time part from default check-out time from Hotel Settings
//             frappe.call({
//                 method: 'rhohotel.rhocom_hotel.doctype.hotel_settings.hotel_settings.get_default_check_out_time',
//                 callback: function (r) {

//                     if (r.message) {
//                         let time_part = r.message;
//                         let date_str = frappe.datetime.obj_to_str(new_checkout);
//                         new_checkout = date_str + " " + time_part;

//                         frm.set_value('expected_check_out_datetime', new_checkout);
//                     } else {
//                         frm.set_value('expected_check_out_datetime', new_checkout);
//                     }
//                 }
//             });
//             //
//             frm.set_value('expected_check_out_datetime', new_checkout);
//         }
//     }
// });

// function render_invoices(invoices) {

//     let html = `<table class="table table-bordered">
//         <thead>
//             <tr>
//                 <th>Sales Invoice</th>
//                 <th>Customer</th>
//                 <th>Posting Date</th>
//                 <th>Grand Total</th>
//                 <th>Balance</th>
//             </tr>
//         </thead>
//         <tbody>`;
//     let total_grand_total = 0;
//     let total_outstanding_amount = 0;
//     if (invoices.length > 0) {
//         invoices.forEach(invoice => {
//             total_grand_total += invoice.grand_total || 0;
//             total_outstanding_amount += invoice.outstanding_amount || 0;
//             html += `<tr>
//                 <td><a href="/app/sales-invoice/${invoice.name}">${invoice.name}</a></td>
//                 <td>${invoice.customer}</td>
//                 <td>${frappe.datetime.str_to_user(invoice.posting_date)}</td>
//                 <td>${format_currency(invoice.grand_total)}</td>
//                 <td>${format_currency(invoice.outstanding_amount)}</td>
//             </tr>`;
//         });
//     } else {
//         html += '<tr><td colspan="5" class="text-center">No Invoices Found</td></tr>';
//     }
//     html += '</tbody>';
//     if (invoices.length > 0) {
//         html += `<tfoot>
//             <tr style="font-weight: bold; background-color: #f8f9fa;">
//                 <td colspan="3">Total</td>
//                 <td>${format_currency(total_grand_total)}</td>
//                 <td>${format_currency(total_outstanding_amount)}</td>
//             </tr>
//         </tfoot>`;
//     }
//     html += '</table>';

//     return html;
// }

// function render_payments(payments) {
//     let html = `<table class="table table-bordered">
//         <thead>
//             <tr>
//                 <th>Payment Entry</th>
//                 <th>Party</th>
//                 <th>Posting Date</th>
//                 <th>Paid Amount</th>
//             </tr>
//         </thead>
//         <tbody>`;
//     let total_paid_amount = 0;
//     if (payments.length > 0) {
//         payments.forEach(payment => {
//             total_paid_amount += payment.paid_amount || 0;
//             html += `<tr>
//                 <td><a href="/app/payment-entry/${payment.name}">${payment.name}</a></td>
//                 <td>${payment.party}</td>
//                 <td>${frappe.datetime.str_to_user(payment.posting_date)}</td>
//                 <td>${format_currency(payment.paid_amount)}</td>
//             </tr>`;
//         });
//     } else {
//         html += '<tr><td colspan="4" class="text-center">No Payments Found</td></tr>';
//     }
//     html += '</tbody>';
//     if (payments.length > 0) {
//         html += `<tfoot>
//             <tr style="font-weight: bold; background-color: #f8f9fa;">
//                 <td colspan="3">Total</td>
//                 <td>${format_currency(total_paid_amount)}</td>
//             </tr>
//         </tfoot>`;
//     }
//     html += '</table>';
//     return html;
// }






































// Copyright (c) 2024, Rhocom Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hotel Room Check In", {
    refresh(frm) {

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

        // Set dynamic filter for Business Source
        frm.set_query("business_source", function () {
            return {
                filters: {
                    reservation_source: frm.doc.market_source || ""
                }
            };
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
        console.log(frappe.route_options);

        if (frm.is_new() && frappe.route_options) {
            frm.set_value("reservation", frappe.route_options.reservation);
            frm.set_value("guest", frappe.route_options.guest);
            frm.set_value("room_number", frappe.route_options.room_number);
            frm.set_value("rate_amount", frappe.route_options.rate_amount);
            // frm.set_value("check_in_datetime", frappe.route_options.check_in_datetime);
            frm.set_value("expected_check_out_datetime", frappe.route_options.expected_check_out_datetime);

            // Clear route options after using them
            frappe.route_options = null;
        }
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
        frm.set_value('business_source', null);
        frm.fields_dict.business_source.get_query();
    },

    reservation(frm) {
        if (frm.doc.reservation) {

            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Hotel Room Reservation",
                    name: frm.doc.reservation
                },
                callback: function (r) {
                    console.log(r);
                    if (r.message) {
                        //frm.set_value('check_in_datetime', r.message.from_date);
                        frm.set_value('expected_check_out_datetime', r.message.to_date);
                        frm.set_value('room_number', r.message.room_number);
                        frm.set_value('rate_amount', r.message.rate);
                        frm.set_value('guest', r.message.guest_name);
                        //frm.set_value('room_type', r.message.room_type);

                        //frm.set_value('number_of_nights', frm.calculate_number_of_nights());

                        frm.set_value('discount', r.message.discount);

                        let from = frappe.datetime.str_to_obj(r.message.from_date);
                        let to = frappe.datetime.str_to_obj(r.message.to_date);
                        let nights = frappe.datetime.get_day_diff(to, from);
                        frm.set_value('number_of_nights', nights);

                        frm.set_df_property('room_number', 'read_only', 1);
                        frm.set_df_property('number_of_nights', 'read_only', 1);
                        frm.set_df_property('discount', 'read_only', 1);
                        frm.set_df_property('rate_amount', 'read_only', 1);
                        frm.set_df_property('room_type', 'read_only', 1);


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
            frm.set_value('total_charges', (nights * frm.doc.rate_amount) - frm.doc.discount);
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
        if (frm.doc.check_in_datetime && frm.doc.number_of_nights) {
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
