# For license information, please see license.txt
import frappe
from frappe.model.document import Document

class PaymentSession(Document):
	def get_guest(self):
		if not self.hotel_room_check_in:
			return frappe.db.get_value("Hotel Room Check In", self.hotel_room_check_in, "guest")
		return guest_name

	def get_paid_invoices(self):
		invoices = frappe.get_all(
			"Payment Session Invoices",
			filters={"parent": self.name},
			fields=["invoice_number", "amount"]
		)
		return invoices