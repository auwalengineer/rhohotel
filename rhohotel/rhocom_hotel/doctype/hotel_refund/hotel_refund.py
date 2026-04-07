import frappe
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.accounts.party import get_party_account

class HotelRefund(Document):

    def validate(self):
        # Ensure selected check-in belongs to selected guest
        check_in = None
        if self.check_in:
            check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
            if check_in.guest != self.guest:
                frappe.throw("Selected check-in does not belong to the selected guest.")

        if flt(self.refund_amount) <= 0:
            frappe.throw("Refund amount must be greater than zero.")

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

        credit_note = None
        if refund.sales_invoice:
            credit_note = refund._create_credit_note()
            refund.db_set("credit_note", credit_note.name)

        refund.db_set("status", "Approved")

        if credit_note:
            frappe.msgprint("Refund approved and credit note created.")
        else:
            refund.db_set("credit_note", None)
            frappe.msgprint("Refund approved without credit note.")

        return {
            "credit_note": credit_note.name if credit_note else None,
            "amount": refund.refund_amount,
            "customer": credit_note.customer if credit_note else _get_guest_customer(refund.guest)
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
        credit_note.custom_hotel_room_check_in = self.check_in

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

    refund = frappe.get_doc("Hotel Refund", refund_name)

    # جلوگیری duplicate from same document
    if refund.payment_entry:
        frappe.msgprint(f"Payment Entry already exists: {refund.payment_entry}")
        return refund.payment_entry

    refund_amount = flt(refund.refund_amount)
    if refund_amount <= 0:
        frappe.throw("Refund amount must be greater than zero.")

    company, customer, party_account, credit_note = _get_refund_context(refund)

    if not customer:
        frappe.throw("Customer not found for this refund.")

    refund_account, mode_of_payment = _get_refund_payment_account(company)

    existing_filters = {
        "party": customer,
        "paid_amount": refund_amount,
        "docstatus": 1,
    }
    if refund.credit_note:
        existing_filters["reference_no"] = refund.credit_note
    else:
        existing_filters["custom_hotel_room_check_in"] = refund.check_in
    existing_pe = frappe.db.exists("Payment Entry", existing_filters)
    if existing_pe:
        return existing_pe

    # 🧾 Create Payment Entry
    payment_entry = frappe.new_doc("Payment Entry")
    payment_entry.payment_type = "Pay"
    payment_entry.company = company

    payment_entry.party_type = "Customer"
    payment_entry.party = customer

    payment_entry.mode_of_payment = mode_of_payment

    # 💰 Accounts
    payment_entry.paid_from = refund_account
    payment_entry.paid_to = party_account

    # 💵 Payment Entry values must ALWAYS be positive
    payment_entry.paid_amount = refund_amount
    payment_entry.received_amount = refund_amount

    payment_entry.posting_date = frappe.utils.today()
    if refund.credit_note:
        payment_entry.reference_no = refund.credit_note
        payment_entry.reference_date = frappe.utils.today()

    payment_entry.custom_hotel_room_check_in = refund.check_in

    # ⚙️ Let ERPNext compute defaults
    payment_entry.setup_party_account_field()
    payment_entry.set_missing_values()
    payment_entry.set_amounts()

    # 🚨 CRITICAL FIX: Remove ERPNext auto-added references
    payment_entry.set("references", [])

    # Optional: stop auto allocation entirely
    payment_entry.allocate_payment_amount = 0

    if credit_note:
        latest_outstanding = frappe.db.get_value(
            "Sales Invoice",
            refund.credit_note,
            "outstanding_amount"
        )

        if latest_outstanding is None:
            frappe.throw("Unable to determine outstanding amount.")

        if flt(latest_outstanding) < 0:
            allocated_amount = -min(refund_amount, abs(flt(latest_outstanding)))
        else:
            allocated_amount = min(refund_amount, flt(latest_outstanding))

        if allocated_amount == 0:
            frappe.throw("Nothing to refund. Outstanding already cleared.")

        payment_entry.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": refund.credit_note,
            "total_amount": credit_note.grand_total,
            "allocated_amount": allocated_amount
        })

    # 💾 Save & submit
    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()

    # 🔗 Update refund doc
    refund.db_set("payment_entry", payment_entry.name)
    refund.db_set("status", "Refunded")

    return payment_entry.name


def _get_refund_context(refund):
    if refund.credit_note:
        credit_note = frappe.get_doc("Sales Invoice", refund.credit_note)
        return credit_note.company, credit_note.customer, credit_note.debit_to, credit_note

    customer = _get_guest_customer(refund.guest)
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        frappe.throw("Default company is not configured.")

    party_account = get_party_account("Customer", customer, company)
    if not party_account:
        frappe.throw(f"Receivable account not found for customer {customer}.")

    return company, customer, party_account, None


def _get_guest_customer(guest):
    customer = frappe.get_value("Hotel Guest", guest, "customer")
    if not customer:
        frappe.throw("Customer not found for the selected guest.")
    return customer


def _get_refund_payment_account(company):
    """Resolve a usable outgoing account for refund payments."""
    preferred_modes = ("Cash", "Bank")

    for mode_name in preferred_modes:
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_name, "company": company},
            "default_account",
        )
        if account:
            return account, mode_name

    company_doc = frappe.get_cached_doc("Company", company)
    for account_field in ("default_cash_account", "default_bank_account"):
        account = company_doc.get(account_field)
        if account:
            return account, "Cash" if account_field == "default_cash_account" else "Bank"

    frappe.throw(
        f"No refund payment account is configured for company {company}. "
        "Set up a Cash or Bank Mode of Payment account, or define a default company cash/bank account."
    )


@frappe.whitelist()
def save_payment_entry(refund_name, payment_entry_name):
    """Save Payment Entry reference after approver creates it."""
    frappe.db.set_value("Hotel Refund", refund_name, "payment_entry", payment_entry_name)
    frappe.db.set_value("Hotel Refund", refund_name, "status", "Refunded")
    frappe.db.commit()
    return True
