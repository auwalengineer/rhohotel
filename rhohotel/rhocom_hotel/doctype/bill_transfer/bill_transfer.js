// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bill Transfer", {
    refresh(frm) {
        // if (frm.doc.docstatus === 0 && frm.doc.status === "Pending Approval") {
        //     frm.add_custom_button("Approve", () => {
        //         frappe.call({
        //             method: "frappe.hotel.doctype.bill_transfer.bill_transfer.approve_transfer",
        //             args: { docname: frm.doc.name },
        //             callback: () => frm.reload_doc()
        //         });
        //     });
        // }
    },
    setup(frm) {
        // filter check from for the selected guest
        frm.set_query("from_check_in", function () {
            if (!frm.doc.from_guest) return {};

            return {
                filters: { guest: frm.doc.from_guest, status: "Checked In" }
            };
        });

        frm.set_query("source_invoice", function () {
            if (!frm.doc.from_check_in) return {};

            return {
                filters: { custom_hotel_room_check_in: frm.doc.from_check_in, outstanding_amount: [">", 0] }
            };
        });

        // exclude the selected "from_guest" from "to_guest"
        frm.set_query("to_guest", function () {
            return {
                filters: {
                    name: ["!=", frm.doc.from_guest]
                }
            };
        });

        frm.set_query("to_check_in", function () {
            if (!frm.doc.to_guest) return {};

            return {
                filters: { guest: frm.doc.to_guest, status: "Checked In" }
            };
        });

    }
});

frappe.ui.form.on("Bill Transfer Item", {
    amount(frm) {
        let total = 0;
        frm.doc.items.forEach(d => {
            total += d.amount || 0;
        });
        frm.set_value("total_amount", total);
        frm.refresh_field("total_amount");
    }
});


