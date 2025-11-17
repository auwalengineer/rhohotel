# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

# import frappe

import frappe
from frappe.model.document import Document

class HotelRefund(Document):
    def validate(self):
        # Ensure the selected check-in belongs to the selected guest
        check_in = None
        if self.check_in:
            check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
            if getattr(check_in, "guest", None) != getattr(self, "guest", None):
                frappe.throw("Selected check-in does not belong to the selected guest.")

        # If sales invoice not supplied, try to pick one linked to the check-in
        # but restrict to invoices for the selected guest's customer only.
        if not self.sales_invoice and check_in:
            customer = frappe.get_value("Hotel Guest", self.guest, "customer")
            invoices = frappe.get_all(
                "Sales Invoice",
                filters={"custom_hotel_room_check_in": check_in.name, "customer": customer},
                fields=["name"],
            )
            if invoices:
                self.sales_invoice = invoices[0].name

    def on_submit(self):
        if self.status == "Approved":
            self.create_credit_note()

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")

    def create_credit_note(self):
        if not self.sales_invoice:
            frappe.throw("Sales Invoice not found for this refund.")

        sales_invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)

        # Create Credit Note
        credit_note = frappe.new_doc("Sales Invoice")
        credit_note.is_return = bool(1)
        credit_note.return_against = self.sales_invoice
        credit_note.customer = sales_invoice.customer
        credit_note.posting_date = frappe.utils.today()
        credit_note.update_outstanding_for_self = bool(1)

        # Append items (use original rate)
        for item in sales_invoice.items:
            credit_note.append("items", {
                "item_code": item.item_code,
                "qty": -item.qty, 
                "rate": self.refund_amount,
                "description": item.description
            })

        credit_note.set_taxes()
        credit_note.insert(ignore_permissions=True)
        credit_note.submit()

        # Issue the Refund Payment
        payment_entry = frappe.new_doc("Payment Entry")
        payment_entry.payment_type = "Pay"
        payment_entry.posting_date = frappe.utils.today()
        payment_entry.party_type = "Customer"
        payment_entry.party = sales_invoice.customer
        payment_entry.paid_from = "Cash - P"  # must be set!
        payment_entry.paid_to = sales_invoice.debit_to
        refund_amount = self.refund_amount or credit_note.outstanding_amount
        if refund_amount <= 0:
            frappe.throw("Refund amount must be greater than zero.")

        payment_entry.paid_amount = refund_amount
        payment_entry.received_amount = refund_amount
        payment_entry.reference_no = credit_note.name
        payment_entry.reference_date = credit_note.posting_date
        payment_entry.custom_hotel_check_in = self.check_in

        # Currency fields
        company_currency = frappe.db.get_value("Company", sales_invoice.company, "default_currency")
        payment_entry.paid_from_account_currency = company_currency
        payment_entry.paid_to_account_currency = company_currency
        payment_entry.source_exchange_rate = 1
        payment_entry.target_exchange_rate = 1

        # Reference Credit Note
        payment_entry.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": credit_note.name,
            "allocated_amount": credit_note.outstanding_amount
        })

        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()

        # Update Check-in status
        self.db_set("status", "Refunded")
        frappe.msgprint("Credit Note created successfully and refund issued.")

