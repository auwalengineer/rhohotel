// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hall Booking", {
    refresh(frm) {
        // add booking adjustment button 
        if (!frm.doc.sales_invoice) {
            frm.add_custom_button("Adjust Booking", function () {
                frappe.call({
                    method: "rhohotel.rhocom_hotel.doctype.hall_booking.hall_booking.create_sales_invoice",
                    args: {
                        hall_booking_name: frm.doc.name
                    },
                    callback: function (r) {
                        if (r.message) {
                            frm.reload_doc();
                            frappe.set_route("Form", "Sales Invoice", r.message);
                        }
                    }
                });
            });
        }
    },

    start_datetime: function (frm) {
        calculate_total_hours(frm);
        calculate_total_amount(frm);
    },

    end_datetime: function (frm) {
        calculate_total_hours(frm);
        calculate_total_amount(frm);
    },

    discount_type: function (frm) {
        calculate_net_total_amount(frm);
    },

    discount_amount: function (frm) {
        calculate_net_total_amount(frm);
    },

    hall: function (frm) {
        frappe.call({
            method: "rhohotel.rhocom_hotel.doctype.hall_booking.hall_booking.get_hall_rate",
            args: {
                hall_name: frm.doc.hall
            },
            callback: function (r) {


                if (r.message) {
                    frm.set_value("rate", r.message);
                } else {
                    frm.set_value("rate", 0);
                }
                calculate_total_amount(frm);
            }
        });
    }

});


function calculate_total_hours(frm) {
    if (frm.doc.start_datetime && frm.doc.end_datetime) {

        // Convert strings to JS Date objects
        const start = new Date(frm.doc.start_datetime);
        const end = new Date(frm.doc.end_datetime);

        // Calculate difference in milliseconds
        const diff_ms = end - start;

        // Convert to hours (whole hours only)
        const hours = Math.floor(diff_ms / (1000 * 60 * 60));

        frm.set_value("total_hours", hours);
    }
}

function calculate_total_amount(frm) {
    if (frm.doc.rate && frm.doc.total_hours) {
        let total_amount = frm.doc.rate * frm.doc.total_hours;
        frm.set_value("total_amount", total_amount);
    } else {
        frm.set_value("total_amount", 0);

    }

    calculate_net_total_amount(frm);
}

function calculate_net_total_amount(frm) {
    let net_total = frm.doc.total_amount || 0;
    let discount = frm.doc.discount_amount || 0;

    if (discount > 0) {
        if (frm.doc.discount_type === "Percentage") {
            discount = (discount / 100) * net_total;
        }
        net_total -= discount;
    } else {
        frm.set_value("net_total", net_total);
    }

    frm.set_value("net_total", net_total);
}

function parse_date(dt) {
    // convert DD-MM-YYYY HH:mm:ss → YYYY-MM-DD HH:mm:ss
    if (!dt) return dt;

    let parts = dt.split(" ");
    let date = parts[0].split("-");
    let time = parts[1];

    // date[0]=DD, date[1]=MM, date[2]=YYYY
    return `${date[2]}-${date[1]}-${date[0]} ${time}`;
}