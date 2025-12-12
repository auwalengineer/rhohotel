# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class HallBooking(Document):
	pass

	def validate(self):
		self.validate_booking_overlap()
		if self.total_hours <= 0:
			frappe.throw("End DateTime must be after Start DateTime.")

	def on_submit(self):
		# Create Customer if not exists
		self.create_customer_if_not_exists()
		# Create Sales Invoice
		self.create_invoice()

	def validate_booking_overlap(self):
    # Conditions for time overlap:
    # new.start < existing.end AND new.end > existing.start

		overlapping_bookings = frappe.db.sql("""
			SELECT name
			FROM `tabHall Booking`
			WHERE hall = %(hall)s
			AND docstatus = 1
			AND name != %(name)s
			AND (
				%(start)s < end_datetime
				AND %(end)s > start_datetime
			)
		""", {
			"hall": self.hall,
			"name": self.name or "",
			"start": self.start_datetime,
			"end": self.end_datetime,
		}, as_dict=True)

		if overlapping_bookings:
			frappe.throw(
				f"Hall '{self.hall}' is already booked between "
				f"{self.start_datetime} and {self.end_datetime}."
			)


	def create_invoice(self):
		hall = frappe.get_doc("Hall", self.hall)
		total_amount = hall.rate_per_hour * self.total_hours
		# get default company income account and cost center
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		company_doc = frappe.get_doc("Company", company)
		default_income = frappe.db.get_value("Company", company, "default_income_account")

		if not default_income:
			frappe.throw(_("No default_income_account set for Company {0}.").format(company))
		cost_center = company_doc.cost_center

		invoice = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer_name,
			"posting_date": frappe.utils.nowdate(),
			"due_date": self.end_datetime,
			"company": company,
			
			"cost_center": cost_center,
			"items": [{
				"item_name": hall.item_name,
				"rate": hall.rate_per_hour,
				"qty": self.total_hours,
				"amount": total_amount,
				"income_account": default_income,
			}]
		})
		invoice.set_taxes()
		if self.discount_amount > 0:
			if self.discount_type == "Percentage":
				discount_amount = (self.discount_amount / 100) * invoice.grand_total
				invoice.additional_discount_percentage = discount_amount
			else:
				invoice.discount_amount = self.discount_amount
    
		invoice.insert(ignore_permissions=True)
		invoice.submit()
		self.sales_invoice = invoice.name
		self.save()

	def create_customer_if_not_exists(self):
		if not frappe.db.exists("Customer", self.customer_name):
			customer = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": self.customer_name,
				"customer_type": "Individual",
				"customer_group": "All Customer Groups",
				"territory": "All Territories"
			})
			customer.insert(ignore_permissions=True)
			
@frappe.whitelist()
def get_hall_rate(hall_name):
	hall = frappe.get_doc("Hall", hall_name)
	return hall.rate_per_hour
