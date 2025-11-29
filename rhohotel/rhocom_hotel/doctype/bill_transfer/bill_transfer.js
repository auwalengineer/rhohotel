// Copyright (c) 2025, Rhocom Technology Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bill Transfer", {
    refresh(frm) {
        if (frm.doc.docstatus === 0 && frm.doc.status === "Pending Approval") {
            frm.add_custom_button("Approve", () => {
                frappe.call({
                    method: "frappe.hotel.doctype.bill_transfer.bill_transfer.approve_transfer",
                    args: { docname: frm.doc.name },
                    callback: () => frm.reload_doc()
                });
            });
        }
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
