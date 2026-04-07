frappe.ui.form.on("Hotel Refund", {
    refresh(frm) {

        // Check if the current user has "Manager" role
        const is_manager = frappe.user_roles.includes("Hotel Manager");

        if (!is_manager) return; // exit if not a Manager

        // Approve Refund button
        if (frm.doc.docstatus === 1 && frm.doc.status === "Pending Approval") {

            frm.add_custom_button("Approve Refund", () => {
                frappe.confirm(
                    "Do you want to approve this refund?",
                    () => {
                        frappe.call({
                            method: "run_doc_method",
                            args: {
                                docs: frm.doc,
                                method: "approve_refund"
                            },
                            freeze: true,
                            freeze_message: "Approving refund...",
                            callback: function (r) {

                                if (!r.message) {
                                    frappe.msgprint("Approval completed.");
                                    frm.reload_doc();
                                    return;
                                }

                                let credit_note = r.message.credit_note;
                                let refund_amount = r.message.amount;
                                let customer = r.message.customer;

                                frappe.confirm(
                                    `Refund approved.<br><br>Do you want to issue Refund Payment Entry now?`,
                                    () => {

                                        frappe.call({
                                            method: "rhohotel.rhocom_hotel.doctype.hotel_refund.hotel_refund.create_payment_entry",
                                            args: {
                                                refund_name: frm.doc.name
                                            },
                                            freeze: true,
                                            freeze_message: "Creating Payment Entry...",
                                            callback: function (res) {
                                                if (!res.message) {
                                                    frappe.msgprint("Payment Entry could not be created.");
                                                    return;
                                                }
                                                frappe.msgprint(
                                                    `Payment Entry <b>${res.message}</b> created.`
                                                );
                                                frm.reload_doc();
                                            }
                                        });

                                    },
                                    () => {
                                        frappe.msgprint("Refund approved. Payment Entry not created.");
                                        frm.reload_doc();
                                    }
                                );
                            }
                        });
                    }
                );
            }).addClass("btn-primary");
        }

        // Refund Money button
        if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && !frm.doc.payment_entry) {
            frm.add_custom_button("Refund Money", () => {
                frappe.confirm(
                    `Do you want to create the Refund Payment Entry now?`,
                    () => {
                        frappe.call({
                            method: "rhohotel.rhocom_hotel.doctype.hotel_refund.hotel_refund.create_payment_entry",
                            args: {
                                refund_name: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: "Creating Payment Entry...",
                            callback: function (res) {
                                if (!res.message) {
                                    frappe.msgprint("Payment Entry could not be created.");
                                    return;
                                }
                                frappe.msgprint(`Payment Entry <b>${res.message}</b> created.`);
                                frm.reload_doc();
                            }
                        });
                    }
                );
            }).addClass("btn-success");
        }
    },

    setup(frm) {
        frm.set_query("check_in", function () {
            if (!frm.doc.guest) return {};

            return {
                filters: { guest: frm.doc.guest }
            };
        });

        frm.set_query("sales_invoice", function () {
            if (!frm.doc.check_in) return {};

            return {
                filters: { custom_hotel_room_check_in: frm.doc.check_in }
            };
        });
    }
});
