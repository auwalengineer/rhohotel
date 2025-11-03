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

    room: function (frm) {
        if (frm.doc.room) {
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
                        // Clear dependent fields when room changes
                        frm.set_value('rate_type', '');
                        frm.set_value('hotel_session', '');
                        frm.set_value('rate_amount', '');
                    }
                }
            });
        }
    },

    rate_type: function (frm) {
        frm.trigger('fetch_rate_amount');
    },

    hotel_session: function (frm) {
        frm.trigger('fetch_rate_amount');
    },

    fetch_rate_amount: function (frm) {

        if (frm.doc.room_type && frm.doc.rate_type && frm.doc.hotel_session) {

            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Hotel Room Tariff',
                    filters: {
                        room_type: frm.doc.room_type,
                        rate_type: frm.doc.rate_type,
                        hotel_session: frm.doc.hotel_session

                    },
                    fieldname: 'rate_amount'
                },
                callback: function (response) {
                    if (response.message && response.message.rate_amount) {
                        frm.set_value('rate_amount', response.message.rate_amount);
                    } else {
                        frappe.show_alert({
                            message: __('No valid tariff found for the selected combination'),
                            indicator: 'red'
                        });
                        frm.set_value('rate_amount', '');
                    }
                }
            });
        }
    }
});