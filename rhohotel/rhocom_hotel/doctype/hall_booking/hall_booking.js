// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hall Booking", {
    refresh(frm) {
        // Show only when document is submitted
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(
                __("Booking Adjustment"),
                () => open_datetime_adjustment_dialog(frm)
            );
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


frappe.ui.form.on("Hall Booking Additional Billing", {
    service: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);

        if (!row.service) {
            frm.refresh_field("additional_billings");
            return;
        }

        // Step 1: Call backend to get service rate
        frappe.call({
            method: "rhohotel.rhocom_hotel.doctype.hall_service.hall_service.get_service_rate",
            args: {
                hall_service: row.service
            },
            callback: function (r) {
                if (r.message) {
                    let rate = r.message;
                    frappe.model.set_value(cdt, cdn, "rate", rate);
                    frappe.model.set_value(cdt, cdn, "amount", rate * row.qty);
                }
            }
        });
        frm.refresh_field("additional_billings");
        calculate_net_total_amount(frm);
    },

    rate: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        frappe.model.set_value(cdt, cdn, "amount", row.rate * row.qty);
        frm.refresh_field("additional_billings");
        calculate_net_total_amount(frm);
    },

    qty: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        frappe.model.set_value(cdt, cdn, "amount", row.rate * row.qty);
        frm.refresh_field("additional_billings");
        calculate_net_total_amount(frm);
    }
});

function open_datetime_adjustment_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: "Adjust Booking Datetime",
        fields: [
            {
                fieldname: "new_start_datetime",
                label: "New Start Datetime",
                fieldtype: "Datetime",
                reqd: 1,
                default: frm.doc.start_datetime,
                onchange: function (e) {
                    const new_start = new Date(d.get_value("new_start_datetime"));
                    const current_end = new Date(d.get_value("new_end_datetime"));

                    if (new_start >= current_end) {
                        frappe.msgprint("New Start Datetime must be before New End Datetime.");
                        //d.set_value("new_start_datetime", frm.doc.start_datetime);
                        return;
                    }

                    // Calculate total hours
                    const diff_ms = current_end - new_start;
                    const hours = Math.floor(diff_ms / (1000 * 60 * 60));
                    d.set_value("new_total_hours", hours);
                }
            },
            {
                "fieldtype": "Int",
                "fieldname": "new_total_hours",
                "label": "Total Hours",
                "reqd": 1,
                "default": frm.doc.total_hours,
                "read_only": 1
            },
            {
                "fieldname": "column_break11",
                "fieldtype": "Column Break"
            },
            {
                fieldname: "new_end_datetime",
                label: "New End Datetime",
                fieldtype: "Datetime",
                reqd: 1,
                default: frm.doc.end_datetime,
                onchange: function (e) {
                    const new_end = new Date(d.get_value("new_end_datetime"));
                    const current_start = new Date(d.get_value("new_start_datetime"));

                    if (new_end <= current_start) {
                        frappe.msgprint("New End Datetime must be after New Start Datetime.");
                        d.set_value("new_end_datetime", frm.doc.end_datetime);
                        return;
                    }

                    // Calculate total hours
                    const diff_ms = new_end - current_start;
                    const hours = Math.floor(diff_ms / (1000 * 60 * 60));
                    d.set_value("new_total_hours", hours);
                }
            },

            {
                "fieldtype": "Section Break",
                "fieldname": "section_break11"
            },
            {
                "fieldname": "old_discount",
                "label": "Current Discount Amount",
                "fieldtype": "Currency",
                "read_only": 1,
                "default": frm.doc.discount
            },
            {
                "fieldname": "column_break12",
                "fieldtype": "Column Break"
            },
            {
                "fieldname": "new_discount",
                "label": "New Discount Amount",
                "fieldtype": "Currency",
                "default": frm.doc.discount
            },

            {
                "fieldtype": "Section Break",
                "fieldname": "section_break144"
            },

            {
                fieldname: "reason",
                label: "Adjustment Reason",
                fieldtype: "Small Text",
                reqd: 1
            }
        ],
        primary_action_label: "Apply Adjustment",
        primary_action(values) {
            frappe.call({
                method: "rhohotel.rhocom_hotel.doctype.hall_booking.hall_booking.adjust_booking_datetime",
                args: {
                    booking_name: frm.doc.name,
                    start_datetime: parse_date(values.new_start_datetime),
                    end_datetime: parse_date(values.new_end_datetime),
                    reason: values.reason,
                    new_discount: values.new_discount
                },
                freeze: true,
                callback() {
                    d.hide();
                    frm.reload_doc();
                }
            });
        }
    });

    d.show();
}


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

    let additional_billings_total = 0;
    if (frm.doc.additional_billings && frm.doc.additional_billings.length > 0) {
        frm.doc.additional_billings.forEach(function (row) {
            additional_billings_total += row.amount || 0;
        });
    }

    let net_total = frm.doc.total_amount || 0;
    let discount = frm.doc.discount_amount || 0;

    net_total += additional_billings_total;

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