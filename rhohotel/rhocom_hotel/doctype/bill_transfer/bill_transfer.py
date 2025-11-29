# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class BillTransfer(Document):

    def validate(self):
        if self.from_guest == self.to_guest:
            frappe.throw("You cannot transfer bill to the same guest.")

        if self.total_amount <= 0:
            frappe.throw("Total amount must be greater than zero.")

    def on_submit(self):
        # Submit only when already approved
        if self.status != "Approved":
            frappe.throw("Bill Transfer must be approved before submission.")

        self.create_source_invoice()
        self.create_destination_invoice()


    def on_cancel(self):
        frappe.throw("Cancelling Bill Transfer is not allowed automatically. Reverse both invoices manually.")


    # --------------------
    #   CORE OPERATIONS
    # --------------------

    def create_source_invoice(self):
        """Creates negative invoice for the source folio."""
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.from_guest
        inv.debit_to = self.get_default_receivable(self.from_guest)
        inv.is_pos = 0
        inv.update_stock = 0
        inv.set_posting_time = 1
        inv.posting_date = frappe.utils.nowdate()
        inv.posting_time = frappe.utils.nowtime()

        inv.append("items", {
            "item_name": "Bill Transfer",
            "description": f"Bill transferred to {self.to_guest}",
            "qty": -1,
            "rate": self.total_amount,
            "income_account": self.get_income_account()
        })

        inv.insert()
        inv.submit()

        self.db_set("source_invoice", inv.name)


    def create_destination_invoice(self):
        """Creates positive invoice for the receiving folio."""
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.to_guest
        inv.debit_to = self.get_default_receivable(self.to_guest)
        inv.is_pos = 0
        inv.update_stock = 0
        inv.set_posting_time = 1
        inv.posting_date = frappe.utils.nowdate()
        inv.posting_time = frappe.utils.nowtime()

        inv.append("items", {
            "item_name": "Bill Transfer",
            "description": f"Bill transferred from {self.from_guest}",
            "qty": 1,
            "rate": self.total_amount,
            "income_account": self.get_income_account()
        })

        inv.insert()
        inv.submit()

        self.db_set("destination_invoice", inv.name)


    # --------------------
    #  Utility Functions
    # --------------------

    def get_default_receivable(self, customer):
        """Fetches default company receivable account."""
        company = frappe.db.get_value("Customer", customer, "default_company")
        acc = frappe.db.get_value("Company", company, "default_receivable_account")
        if not acc:
            frappe.throw("Default Receivable Account not set in Company.")
        return acc


    def get_income_account(self):
        """Get default income account from Company."""
        company = frappe.defaults.get_user_default("Company")
        acc = frappe.db.get_value("Company", company, "default_income_account")
        if not acc:
            frappe.throw("Default Income Account not set in Company.")
        return acc


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
