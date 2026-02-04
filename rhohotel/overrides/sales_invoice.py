import frappe


def validate_sales_invoice(doc, method):
	# Skip due date validation for hall booking invoices
	if hasattr(doc, "custom_hall_booking") and doc.custom_hall_booking:
		# Allow due date to be before posting date for hall bookings
		pass
	# Otherwise let normal validation run
