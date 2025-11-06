// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hotel Room Check In", {
    refresh(frm) {
        // Add custom buttons based on status
        if (frm.doc.docstatus === 1 && frm.doc.status === "Checked In") {
            frm.add_custom_button(__("Check Out"), () => {
                frappe.model.open_mapped_doc({
                    method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
                    frm: frm
                });
            });

            frm.add_custom_button(__('Pay with Moniepoint'), function () {
                frappe.call({
                    method: 'rhohotel.api.initiate_payment',
                    args: {
                        invoice_names: [frm.doc.sales_invoice]
                    },
                    callback: function (r) {
                        if (r.message && r.message.name) {
                            //frappe.msgprint(__('Payment session created: {0}', [r.message.name]));

                            const d = new frappe.ui.Dialog({
                                title: 'Complete Payment',
                                fields: [
                                    {
                                        label: 'Payment Reference',
                                        fieldname: 'payment_reference',
                                        fieldtype: 'Data',
                                        default: r.message.payment_reference,
                                        read_only: 1
                                    },
                                    {
                                        label: 'Total Amount',
                                        fieldname: 'total_amount',
                                        fieldtype: 'Currency',
                                        default: r.message.total_amount,
                                        read_only: 1
                                    }
                                ],
                                primary_action_label: 'Mark as Paid',
                                primary_action(values) {
                                    frappe.call({
                                        method: 'rhohotel.api.complete_payment',
                                        args: {
                                            payment_session: r.message.name
                                        },
                                        callback: function (res) {
                                            frappe.msgprint(__('Payment completed successfully.'));
                                            d.hide();
                                            frm.reload_doc();
                                        }
                                    });
                                }
                            });

                            d.show();
                        }
                    }
                });
            });
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
                    "status": "Confirmed"
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
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Hotel Room Reservation",
                    name: frm.doc.reservation
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("expected_check_out_datetime",
                            frappe.datetime.get_datetime_str(r.message.to_date));
                    }
                }
            });
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
        if (frm.doc.room_type && frm.doc.rate_type && frm.doc.check_in_datetime) {
            frappe.call({
                method: 'rhohotel.api.get_room_rate',
                args: {
                    room_type: frm.doc.room_type,
                    rate_type: frm.doc.rate_type,
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
    }
});