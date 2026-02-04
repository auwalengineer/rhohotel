import frappe
from frappe.utils import getdate


def validate_sales_invoice(doc, method):
	# Check if this invoice is from a Hall Booking
	# by looking at the items for hall items
	is_hall_booking_invoice = False

	if doc.items:
		for item in doc.items:
			# Check if item is a Hall
			if frappe.db.exists("Hall", item.item_code):
				is_hall_booking_invoice = True
				break

	# Also check if it's an adjustment invoice
	if hasattr(doc, "custom_hall_booking") and doc.custom_hall_booking:
		is_hall_booking_invoice = True

	# Skip the due date validation for hall booking invoices
	if is_hall_booking_invoice:
		# If set_posting_time is enabled, allow any due date
		if doc.get("set_posting_time"):
			# Bypass the standard validation by setting a flag
			doc.flags.ignore_validate_due_date = True
