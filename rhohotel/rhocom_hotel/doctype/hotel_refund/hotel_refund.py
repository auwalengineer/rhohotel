import frappe
from frappe.model.document import Document

class HotelRefund(Document):

    def validate(self):
        # Ensure selected check-in belongs to selected guest
        check_in = None
        if self.check_in:
            check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
            if check_in.guest != self.guest:
                frappe.throw("Selected check-in does not belong to the selected guest.")

        # Auto-select sales invoice
        if not self.sales_invoice and check_in:
            customer = frappe.get_value("Hotel Guest", self.guest, "customer")
            invoices = frappe.get_all(
                "Sales Invoice",
                filters={
                    "custom_hotel_room_check_in": check_in.name,
                    "customer": customer
                },
                fields=["name"]
            )
            if invoices:
                self.sales_invoice = invoices[0].name

    def on_submit(self):
        # When refund is submitted, wait for approval
        self.db_set("status", "Pending Approval")

    @frappe.whitelist()
    def approve_refund(self):
        """Approve refund and create credit note on server."""
        refund = frappe.get_doc("Hotel Refund", self.name)

        if refund.docstatus != 1:
            frappe.throw("Only submitted refunds can be approved.")

        if refund.status == "Approved":
            frappe.throw("This refund is already approved.")

        # Create credit note
        credit_note = refund._create_credit_note()

        # Save credit note name into Refund Doc
        refund.db_set("credit_note", credit_note.name)
        refund.db_set("status", "Approved")

        frappe.msgprint("Refund approved and credit note created.")

        return {
            "credit_note": credit_note.name,
            "amount": refund.refund_amount,
            "customer": credit_note.customer
        }

    def _create_credit_note(self):
        if not self.sales_invoice:
            frappe.throw("Sales Invoice not found for this refund.")

        original = frappe.get_doc("Sales Invoice", self.sales_invoice)

        credit_note = frappe.new_doc("Sales Invoice")
        credit_note.is_return = 1
        credit_note.return_against = original.name
        credit_note.customer = original.customer
        credit_note.company = original.company
        credit_note.posting_date = frappe.utils.today()
        credit_note.update_outstanding_for_self = 1
        credit_note.custom_hotel_check_in = self.check_in

        # One refund line
        credit_note.append("items", {
            "item_code": original.items[0].item_code,
            "qty": -1,
            "rate": self.refund_amount,
            "description": f"Refund for {self.name}"
        })

        credit_note.set_taxes()
        credit_note.insert(ignore_permissions=True)
        credit_note.submit()

        return credit_note
    
@frappe.whitelist()
def create_payment_entry(refund_name):
    """
    Create a Payment Entry for the refund if not already created
    """
    
    # get refund record 
    refund = frappe.get_doc("Hotel Refund", refund_name)
    
    if refund.payment_entry:
        frappe.msgprint(f"Payment Entry already exists: {refund.payment_entry}")
        return refund.payment_entry

    if not refund.credit_note:
        frappe.throw("Credit Note not found. Approve refund first.")

    customer = frappe.get_value("Hotel Guest", refund.guest, "customer")
    refund_amount = refund.refund_amount
    
    credit_note = frappe.get_doc("Sales Invoice", refund.credit_note)
    
    # get default paid from account
    

    # Create Payment Entry
    payment_entry = frappe.new_doc("Payment Entry")
    payment_entry.payment_type = "Pay"
    payment_entry.party_type = "Customer"
    payment_entry.party = customer
    payment_entry.paid_from = "1310 - Debtors - WRH"  # You may adjust account
    payment_entry.paid_to = credit_note.debit_to
    payment_entry.paid_amount = refund_amount
    payment_entry.received_amount = refund_amount
    payment_entry.reference_no = refund.credit_note
    payment_entry.reference_date = frappe.utils.today()
    payment_entry.custom_hotel_room_check_in = refund.check_in

    payment_entry.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": refund.credit_note,
        "allocated_amount": credit_note.outstanding_amount
    })

    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()

    # Link Payment Entry to Refund Doc
    refund.db_set("payment_entry", payment_entry.name)

    return payment_entry.name


@frappe.whitelist()
def save_payment_entry(refund_name, payment_entry_name):
    """Save Payment Entry reference after approver creates it."""
    frappe.db.set_value("Hotel Refund", refund_name, "payment_entry", payment_entry_name)
    frappe.db.set_value("Hotel Refund", refund_name, "status", "Refunded")
    frappe.db.commit()
    return True
