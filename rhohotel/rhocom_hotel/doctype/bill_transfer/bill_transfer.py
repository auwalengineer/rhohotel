# Copyright (c) 2025
# Rhocom Technology Ltd

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class BillTransfer(Document):

    # --------------------------------------
    # VALIDATION
    # --------------------------------------
    def validate(self):
        if self.from_guest == self.to_guest:
            frappe.throw("You cannot transfer a bill to the same guest.")

        if self.total_amount <= 0:
            frappe.throw("Total amount must be greater than zero.")

        if not self.source_invoice:
            frappe.throw("Source Invoice is required to process bill transfer.")

    # --------------------------------------
    # SUBMISSION LOGIC
    # --------------------------------------
    def on_submit(self):
        if self.status != "Approved":
            frappe.throw("Bill Transfer must be approved before submission.")

        self.create_journal_entry()

    # --------------------------------------
    #   CREATE ONE JOURNAL ENTRY
    # --------------------------------------
    def create_journal_entry(self):

        # Get the company from the source invoice
        company = frappe.db.get_value("Sales Invoice", self.source_invoice, "company")
        
        # Load the source invoice
        inv = frappe.get_doc("Sales Invoice", self.source_invoice)

        # The customer on the invoice
        invoice_customer = inv.customer

        # The receivable account used on invoice
        receivable_account = inv.debit_to

        # Fetch the receivable account
        receivable_account = frappe.db.get_value(
            "Company",
            company,
            "default_receivable_account"
        )

        if not receivable_account:
            frappe.throw("Default Receivable Account is not set in Company master.")

        # ---------------------------------
        # Create JE document
        # ---------------------------------
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = nowdate()
        je.company = company
        je.custom_hotel_room_check_in = self.to_check_in
        je.user_remark = f"Bill Transfer from {self.from_guest} to {self.to_guest} ({self.name})"

        # ----------------------------
        # Line 1 — CREDIT Guest A
        # ----------------------------
        je.append("accounts", {
            "account": receivable_account,
            "party_type": "Customer",
            "party": invoice_customer,
            "credit_in_account_currency": self.total_amount,
            "debit_in_account_currency": 0,
            "reference_type": "Sales Invoice",
            "reference_name": self.source_invoice
        })

        # ----------------------------
        # Line 2 — DEBIT Guest B
        # ----------------------------
        je.append("accounts", {
            "account": receivable_account,
            "party_type": "Customer",
            "party": self.to_guest,
            "debit_in_account_currency": self.total_amount,
            "credit_in_account_currency": 0
        })

        # Save & Submit JE
        je.insert(ignore_permissions=True)
        je.submit()

        # Store link
        self.journal_entry = je.name
        self.db_set("journal_entry", je.name)

        frappe.msgprint(f"Journal Entry <b>{je.name}</b> created successfully.")


# --------------------
#   APPROVAL METHOD
# --------------------
@frappe.whitelist()
def approve_transfer(docname):
    doc = frappe.get_doc("Bill Transfer", docname)

    if "Manager" not in frappe.get_roles():
        frappe.throw("Only users with Manager role can approve Bill Transfers.")

    if doc.status != "Pending Approval":
        frappe.throw("Bill Transfer is not in Pending Approval state.")

    doc.status = "Approved"
    doc.authorized_by = frappe.session.user
    doc.save()

    frappe.msgprint("Bill Transfer approved. You can now Submit the document.")
