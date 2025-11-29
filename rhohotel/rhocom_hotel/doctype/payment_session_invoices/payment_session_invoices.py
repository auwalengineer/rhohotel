# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


# class PaymentSessionInvoices(Document):
# 	pass


# Copyright (c) 2024, Rhocom Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class PaymentSessionInvoices(Document):
    def validate(self):
        # Validate that allocated amount doesn't exceed outstanding amount
        if self.allocated_amount and self.outstanding_amount:
            if self.allocated_amount > self.outstanding_amount:
                frappe.throw(
                    frappe._("Allocated amount (₦{0}) cannot exceed outstanding amount (₦{1}) for invoice {2}").format(
                        frappe.format_value(self.allocated_amount, {"fieldtype": "Currency"}),
                        frappe.format_value(self.outstanding_amount, {"fieldtype": "Currency"}),
                        self.invoice_number
                    )
                )
            
            if self.allocated_amount < 0:
                frappe.throw(
                    frappe._("Allocated amount cannot be negative for invoice {0}").format(
                        self.invoice_number
                    )
                )
    
    def before_insert(self):
        # Check if this combination already exists
        existing = frappe.db.exists(
            "Payment Session Invoices",
            {
                "payment_session": self.payment_session,
                "invoice_number": self.invoice_number
            }
        )
        
        if existing:
            frappe.throw(
                frappe._("Invoice {0} is already linked to Payment Session {1}").format(
                    self.invoice_number,
                    self.payment_session
                )
            )