# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, nowdate, getdate, now_datetime
from frappe import _


class HallBooking(Document):
	pass

	def validate(self):
		self.validate_booking_overlap()
		if self.total_hours <= 0:
			frappe.throw("End DateTime must be after Start DateTime.")

		# prevent invalid discount
		for row in self.additional_billings:
			if row.discount_amount and row.discount_amount > (row.qty * row.rate):
				frappe.throw(f"Discount cannot be greater than amount for service {row.service}")

	def on_submit(self):
		# Create Customer if not exists
		self.create_customer_if_not_exists()
		# Create Sales Invoice
		self.create_invoice()

	def validate_booking_overlap(self):
		# Conditions for time overlap:
		# new.start < existing.end AND new.end > existing.start

		overlapping_bookings = frappe.db.sql(
			"""
			SELECT name
			FROM `tabHall Booking`
			WHERE hall = %(hall)s
			AND docstatus = 1
			AND name != %(name)s
			AND (
				%(start)s < end_datetime
				AND %(end)s > start_datetime
			)
		""",
			{
				"hall": self.hall,
				"name": self.name or "",
				"start": self.start_datetime,
				"end": self.end_datetime,
			},
			as_dict=True,
		)

		if overlapping_bookings:
			frappe.throw(
				f"Hall '{self.hall}' is already booked between {self.start_datetime} and {self.end_datetime}."
			)

	def create_invoice(self):
		hall = frappe.get_doc("Hall", self.hall)

		total_amount = hall.rate_per_hour * self.total_hours

		# Get default company
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		company_doc = frappe.get_doc("Company", company)

		default_income = frappe.db.get_value("Company", company, "default_income_account")

		if not default_income:
			frappe.throw(_("No default income account set for Company {0}.").format(company))

		cost_center = company_doc.cost_center

		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer_name,
				# "posting_date": nowdate(),
				"posting_date": getdate(self.end_datetime),
				"due_date": getdate(self.end_datetime),
				"set_posting_time": 1,
				"company": company,
				"items": [
					{
						"item_code": self.hall,
						"rate": hall.rate_per_hour,
						"qty": self.total_hours,
						"amount": total_amount,
						"income_account": default_income,
						"cost_center": cost_center,
						"discount_amount": 0.0,
					}
				],
			}
		)

		# Add additional billings (optional)
		additional_billings = self.get("additional_billings")
		if additional_billings:
			for billing in additional_billings:
				invoice.append(
					"items",
					{
						"item_code": billing.service,
						"rate": billing.rate,
						"qty": billing.qty,
						"amount": billing.amount,
						"income_account": default_income,
						"cost_center": cost_center,
						"discount_amount": billing.discount_amount or 0.0,
					},
				)
		invoice.set_taxes()

		# Apply discount correctly
		if self.discount_amount and self.discount_amount > 0:
			if self.discount_type == "Percentage":
				invoice.additional_discount_percentage = self.discount_amount
			else:
				invoice.discount_amount = self.discount_amount

		invoice.insert(ignore_permissions=True)
		invoice.submit()

		self.sales_invoice = invoice.name
		self.save(ignore_permissions=True)

	def create_customer_if_not_exists(self):
		if not frappe.db.exists("Customer", self.customer_name):
			customer = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": self.customer_name,
					"customer_type": "Individual",
					"customer_group": "All Customer Groups",
					"territory": "All Territories",
				}
			)
			customer.insert(ignore_permissions=True)


@frappe.whitelist()
def get_hall_rate(hall_name):
	hall = frappe.get_doc("Hall", hall_name)
	return hall.rate_per_hour


@frappe.whitelist()
def adjust_booking_datetime(booking_name, start_datetime, end_datetime, reason=None):
	import math

	booking = frappe.get_doc("Hall Booking", booking_name)

	if booking.docstatus != 1:
		frappe.throw("Only submitted bookings can be adjusted.")

	start_dt = get_datetime(start_datetime)
	end_dt = get_datetime(end_datetime)

	if end_dt <= start_dt:
		frappe.throw("End datetime must be after start datetime.")

	# ----------------------------------
	# Calculate hours (round up)
	# ----------------------------------
	new_total_hours = math.ceil((end_dt - start_dt).total_seconds() / 3600)

	previous_total_hours = booking.total_hours or 0

	# ----------------------------------
	# Revalidate overlap
	# ----------------------------------
	overlapping_bookings = frappe.db.sql(
		"""
		SELECT name
		FROM `tabHall Booking`
		WHERE hall = %(hall)s
		AND docstatus = 1
		AND name != %(name)s
		AND (
			%(start)s < end_datetime
			AND %(end)s > start_datetime
		)
	""",
		{
			"hall": booking.hall,
			"name": booking.name or "",
			"start": start_dt,
			"end": end_dt,
		},
		as_dict=True,
	)

	if overlapping_bookings:
		frappe.throw(f"Hall '{booking.hall}' is already booked between {start_dt} and {end_dt}.")
	new_net_total = booking.net_total
	# ----------------------------------
	# Financial adjustment
	# ----------------------------------
	if new_total_hours != previous_total_hours:
		hall = frappe.get_doc("Hall", booking.hall)
		company = frappe.db.get_single_value("Global Defaults", "default_company")

		income_account = frappe.db.get_value("Company", company, "default_income_account")
		cost_center = frappe.db.get_value("Company", company, "cost_center")

		diff_hours = abs(new_total_hours - previous_total_hours)

		if new_total_hours < previous_total_hours:
			# Return invoice
			qty = -diff_hours
		else:
			# Additional invoice
			qty = diff_hours

		invoice_data = {
			"doctype": "Sales Invoice",
			"customer": booking.customer_name,
			"posting_date": nowdate(),
			"company": company,
			"items": [
				{
					"item_code": booking.hall,
					"rate": hall.rate_per_hour,
					"qty": qty,
					"income_account": income_account,
					"cost_center": cost_center,
				}
			],
			"custom_hall_booking": booking.name,
		}

		if new_total_hours < previous_total_hours:
			invoice_data["is_return"] = 1

		invoice = frappe.get_doc(invoice_data)
		invoice.insert(ignore_permissions=True)
		invoice.submit()

		new_net_total = booking.net_total + invoice.grand_total

	# ----------------------------------
	# Adjustment history
	# ----------------------------------
	booking.append(
		"adjustment_history",
		{
			"previous_start": booking.start_datetime,
			"previous_end": booking.end_datetime,
			"previous_hours": previous_total_hours,
			"new_start": start_dt,
			"new_end": end_dt,
			"new_hours": new_total_hours,
			"adjustment_reason": reason,
			"adjusted_by": frappe.session.user,
			"adjusted_on": nowdate(),
			"adjustment_invoice": invoice.name if new_total_hours != previous_total_hours else None,
		},
	)

	# ----------------------------------
	# Final save
	# ----------------------------------
	total_amount = hall.rate_per_hour * new_total_hours

	booking.start_datetime = start_dt
	booking.end_datetime = end_dt
	booking.total_hours = new_total_hours
	booking.net_total = new_net_total
	booking.total_amount = total_amount
	# booking.db_set("start_datetime", booking.start_datetime)
	# booking.db_set("end_datetime", booking.end_datetime)
	# booking.db_set("total_hours", new_total_hours)
	booking.save()
	frappe.db.commit()

	return {"previous_hours": previous_total_hours, "new_hours": new_total_hours}


@frappe.whitelist()
def get_payment_status(booking_name):
	booking = frappe.get_doc("Hall Booking", booking_name)
	if not booking.sales_invoice:
		return "No Invoice"
	invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
	if invoice.outstanding_amount <= 0:
		return "Paid"
	elif invoice.outstanding_amount < invoice.grand_total:
		return "Partially Paid"
	else:
		return "Unpaid"


@frappe.whitelist()
def create_payment_entry(booking, data):
	import json

	data = frappe._dict(json.loads(data))

	booking = frappe.get_doc("Hall Booking", booking)

	if booking.docstatus != 1:
		frappe.throw("Only submitted bookings can receive payment.")

	if not booking.sales_invoice:
		frappe.throw("No invoice linked to this booking.")

	invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)

	if invoice.outstanding_amount <= 0:
		frappe.throw("Invoice is already fully paid.")

	company = frappe.db.get_single_value("Global Defaults", "default_company")

	# --------------------------------------------------
	# Get accounts from Mode of Payment
	# --------------------------------------------------
	mop = frappe.get_doc("Mode of Payment", data.payment_mode)

	if not mop.accounts:
		frappe.throw("Mode of Payment has no accounts configured.")

	mop_account = next((a.default_account for a in mop.accounts if a.company == company), None)

	if not mop_account:
		frappe.throw(f"No account found for Mode of Payment in {company}")

	# avoid duplicate reference numbers
	existing_pe = frappe.db.get_value("Payment Entry", {"reference_no": data.reference_no})
	if existing_pe:
		frappe.throw("A Payment Entry with this reference number already exists.")

	# --------------------------------------------------
	# Create Payment Entry
	# --------------------------------------------------
	pe = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"company": company,
			"posting_date": data.payment_date,
			"party_type": "Customer",
			"party": invoice.customer,
			"mode_of_payment": data.payment_mode,
			"paid_to": mop_account,
			"paid_amount": data.paid_amount,
			"received_amount": data.paid_amount,
			"reference_no": data.reference_no,
			"reference_date": data.reference_date,
			"remarks": data.remarks,
			"references": [
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": invoice.name,
					"allocated_amount": min(data.paid_amount, invoice.outstanding_amount),
				}
			],
		}
	)

	pe.insert(ignore_permissions=True)
	pe.submit()

	return pe.name
