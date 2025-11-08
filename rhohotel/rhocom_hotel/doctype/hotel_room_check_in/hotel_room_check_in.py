# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _, msgprint, utils
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


class HotelRoomCheckIn(Document):
	def validate(self):
		#self.validate_reservation()
		self.validate_rate_amount()
		self.validate_room()
		self.validate_dates()
		self.handle_late_checkout()
		self.calculate_total_charges()
		#self.validate_rate_and_session()
		#self.set_rate_amount()

	def handle_late_checkout(self):
		if self.late_checkout:
			hotel_settings = frappe.get_single("Hotel Settings")
			if hotel_settings.enable_late_check_out:
				expected_checkout_date = get_datetime(self.expected_check_out_datetime).date()
				self.expected_check_out_datetime = get_datetime(str(expected_checkout_date) + " " + str(hotel_settings.default_check_out_time))

	def calculate_total_charges(self):
		"""Calculate total charges based on number of nights and rate amount."""
		if self.check_in_datetime and self.expected_check_out_datetime and self.rate_amount:
			check_in_dt = get_datetime(self.check_in_datetime)
			expected_checkout_dt = get_datetime(self.expected_check_out_datetime)
			
			number_of_nights = utils.date_diff(expected_checkout_dt.date(), check_in_dt.date())
			self.total_charges = number_of_nights * self.rate_amount

	# validate rate amount
	def validate_rate_amount(self):
		if self.rate_amount <= 0:
			frappe.throw(_("Rate amount must be greater than zero"))

	def validate_rate_and_session(self):
		# Validate rate type exists for room type
		tariff = frappe.get_all(
			"Hotel Room Tariff",
			filters={"room_type": self.room_type}
		)

		if not tariff:
			frappe.throw(_("No valid tariff found for Room Type {0}").format(self.room_type))

	def set_rate_amount(self):
		# Get rate amount from tariff using session period/duration
		tariff = frappe.get_all(
			"Hotel Room Tariff",
			filters={
				"room_type": self.room_type,
				"rate_type": self.rate_type,
				"is_active": 1
			},
			fields=["amount"],
			limit=1
		)

		if not tariff:
			tariff = frappe.get_all(
				"Hotel Room Tariff",
				filters={"room_type": self.room_type, "is_active": 1},
				fields=["amount"],
				limit=1
			)

		if tariff:
			self.rate_amount = tariff[0].amount
	# def validate_reservation(self):

	# 	    # Only run validation if reservation is selected
	# 	if not self.reservation:
	# 		return

	# 	"""Check if reservation exists and is valid for check-in"""
	# 	if self.reservation:
			
	# 		if not frappe.db.exists("Hotel Room Reservation", self.reservation):
	# 			frappe.throw(_("Reservation {0} does not exist").format(self.reservation))

	# 		reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)
			
	# 		# Check reservation dates
	# 		check_in_date = get_datetime(self.check_in_datetime).date()
	# 		if check_in_date < reservation.from_date:
	# 			frappe.throw(_("Check-in date cannot be before reservation start date"))
	# 		if check_in_date > reservation.to_date:
	# 			frappe.throw(_("Check-in date cannot be after reservation end date"))

	# 		# Check if already checked in
	# 		existing = frappe.get_all("Hotel Room Check In",
	# 			filters={
	# 				"reservation": self.reservation,
	# 				"docstatus": 1,
	# 				"status": ["in", ["Draft", "Checked In"]]
	# 			})
	# 		if existing and self.is_new():
	# 			frappe.throw(_("Reservation {0} is already checked in").format(self.reservation))

	def validate_room(self):
		"""Validate room assignment and availability"""
		if not frappe.db.exists("Hotel Room", self.room_number):
			frappe.throw(_("Room {0} does not exist").format(self.room_number))

		# Check if room matches reservation type
		room = frappe.get_doc("Hotel Room", self.room_number)
		#reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)
		
		#if not any(item.room_type == room.hotel_room_type for item in reservation.items):
		#	frappe.throw(_("Room {0} type does not match any room type in reservation").format(self.room))

		# Check if room is available
		existing = frappe.get_all("Hotel Room Check In",
			filters={
				"room_number": self.room_number,
				"docstatus": 1,
				"status": "Checked In",
				"name": ["!=", self.name]
			})
		if existing:
			frappe.throw(_("Room {0} is currently occupied").format(self.room_number))

	def validate_dates(self):
		"""Validate check-in/out dates"""
		if get_datetime(self.check_in_datetime) > get_datetime(self.expected_check_out_datetime):
			frappe.throw(_("Check-in time cannot be after expected check-out time"))

	def on_submit(self):
		"""Update status on submit"""
		self.status = "Checked In"
		self.db_set("status", "Checked In")
		self.update_room_status("Occupied")
		self.update_room()
		self.make_sales_invoice()
		frappe.publish_realtime('rhohotel_front_desk_update')

	def on_cancel(self):
		"""Update status on cancel"""
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")
		self.update_room_status("Vacant")
		frappe.publish_realtime('rhohotel_front_desk_update')

	def	on_load(self):
		"""Fetch linked invoices on load"""
		#self.fetch_invoices()
		"""Update total charges on with outstanding amount of the loaded invoices"""
		#total_charges = sum(inv.outstanding_amount for inv in invoices)
		#self.set("total_charges", total_charges)

	def update_room_status(self, status):
		frappe.db.set_value("Hotel Room", self.room_number, "status", status)

	def update_room(self):
		room = frappe.get_doc("Hotel Room", self.room_number)
		room.current_guest = self.guest
		room.current_check_in = self.name
		room.save()

	def make_sales_invoice(self):

		# Get ERPNEXT item using selected room type
		room_type_doc = frappe.get_doc("Hotel Room Type", self.room_type)


		customer = frappe.get_value("Hotel Guest", self.guest, "customer")
		si = frappe.new_doc("Sales Invoice")
		si.customer = customer
		si.custom_hotel_room_check_in = self.name
		si.due_date = get_datetime(self.expected_check_out_datetime).date()
		si.posting_date = get_datetime(self.check_in_datetime).date()		
		si.append("items", {
			"item_code": room_type_doc.erpnext_item,
			"rate": self.rate_amount,
			"qty": 1,
			"amount": self.rate_amount,
			"description": _("Room charge for {0}").format(self.room_number)
		})
		si.set_taxes()
		si.insert(ignore_permissions=True)
		si.submit()


		# Link invoice back to check-in record
		#self.db_set("sales_invoice", si.name)

		#frappe.msgprint(_("Sales Invoice {0} created").format(si.name), alert=True)
	
	def on_update(self):
		"""Fetch linked invoices on update"""
		self.update_checkin_status()

	# def fetch_invoices(self):
	# 	"""Fetch all Sales and POS Invoices linked to this Check In"""

	# 	# Clear table first
	# 	self.set("invoices", [])

	# 	# Get Sales Invoices
	# 	sales_invoices = frappe.get_all(
	# 		"Sales Invoice",
	# 		filters={"hotel_room_check_in": self.name},
	# 		fields=["name", "grand_total", "outstanding_amount"]
	# 	)

	# 	for inv in sales_invoices:
	# 		self.append("invoices", {
	# 			"invoice_type": "Sales Invoice",
	# 			"invoice": inv.name,
	# 			"amount": inv.grand_total,
	# 			"outstanding_amount": inv.outstanding_amount
	# 		})

	# 	# Get POS Invoices
	# 	pos_invoices = frappe.get_all(
	# 		"POS Invoice",
	# 		filters={"hotel_room_check_in": self.name},
	# 		fields=["name", "grand_total", "outstanding_amount"]
	# 	)

	# 	for inv in pos_invoices:
	# 		self.append("invoices", {
	# 			"invoice_type": "POS Invoice",
	# 			"invoice": inv.name,
	# 			"amount": inv.grand_total,
	# 			"outstanding_amount": inv.outstanding_amount
	# 		})

	@frappe.whitelist()
	def set_checkin_invoice_list(self):
		"""Fetch all linked invoices for a given check-in"""
		invoices = []

		# Get Sales Invoices
		sales_invoices = frappe.get_all(
			"Sales Invoice",
			filters={"custom_hotel_room_check_in": self.name},
			fields=["name", "grand_total", "outstanding_amount"]
		)

		for inv in sales_invoices:
			invoices.append({
				"invoice_type": "Sales Invoice",
				"invoice": inv.name,
				"amount": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount
			})

		# # Get POS Invoices
		pos_invoices = frappe.get_all(
			"POS Invoice",
			filters={"custom_hotel_room_check_in": self.name},
			fields=["name", "grand_total", "outstanding_amount"]
		)

		for inv in pos_invoices:
			invoices.append({
				"invoice_type": "POS Invoice",
				"invoice": inv.name,
				"amount": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount
			})

		return invoices

@frappe.whitelist()
def make_check_out(source_name, target_doc=None):
	def get_mapped_doc():
		check_in = frappe.get_doc("Hotel Room Check In", source_name)
		check_out = frappe.new_doc("Hotel Room Check Out")
		check_out.check_in = check_in.name
		check_out.guest = check_in.guest
		check_out.room_number = check_in.room_number
		check_out.check_in_datetime = check_in.check_in_datetime
		check_out.check_out_datetime = now_datetime()
		check_out.insert()
		return check_out

	doc = get_mapped_doc()
	return doc

@frappe.whitelist()
def extend_stay(check_in_name, number_of_nights):
	"""
	Extends a guest's stay by updating the expected_check_out_datetime
	and creating a new Sales Invoice for the extension period.
	"""
	number_of_nights = int(number_of_nights)
	if number_of_nights <= 0:
		frappe.throw(_("Number of nights must be a positive number."))

	check_in_doc = frappe.get_doc("Hotel Room Check In", check_in_name)
	current_checkout_dt = get_datetime(check_in_doc.expected_check_out_datetime)
	new_checkout_dt = utils.add_to_date(current_checkout_dt, days=number_of_nights)
	new_expected_checkout = new_checkout_dt.strftime('%Y-%m-%d %H:%M:%S')

	# Check for room availability during the extension period
	conflicting_reservation = frappe.db.exists(
		"Hotel Room Reservation",
		{
			"room_number": check_in_doc.room_number,
			"status": ["not in", ["Cancelled", "No Show"]],
			"from_date": ["<", new_checkout_dt.date()],
			"to_date": [">", current_checkout_dt.date()],
		},
	)

	if conflicting_reservation:
		frappe.throw(_("Room {0} is not available for the selected extension period. It is reserved under {1}.").format(check_in_doc.room_number, conflicting_reservation))


	# Create a new Sales Invoice for the extension
	extension_amount = number_of_nights * check_in_doc.rate_amount
	room_type_doc = frappe.get_doc("Hotel Room Type", check_in_doc.room_type)
	customer = frappe.get_value("Hotel Guest", check_in_doc.guest, "customer")

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.custom_hotel_room_check_in = check_in_doc.name
	si.due_date = new_checkout_dt.date()
	si.posting_date = now_datetime().date()
	si.append("items", {
		"item_code": room_type_doc.erpnext_item,
		"rate": check_in_doc.rate_amount,
		"qty": number_of_nights,
		"amount": extension_amount,
		"description": _("Stay extension for {0} from {1} to {2}").format(
			check_in_doc.room_number,
			current_checkout_dt.strftime('%Y-%m-%d'),
			new_checkout_dt.strftime('%Y-%m-%d')
		)
	})
	si.set_taxes()
	si.insert(ignore_permissions=True)
	si.submit()

	# Update the check-in document
	check_in_doc.db_set("expected_check_out_datetime", new_expected_checkout)

	# Add a comment to the check-in document for history
	check_in_doc.add_comment(
		"Comment",
		text=_("Stay extended to {0}. New invoice {1} created for {2}.").format(new_expected_checkout, si.name, frappe.utils.fmt_money(extension_amount))
	)

	msgprint(_("Stay extended successfully. New invoice {0} created.").format(si.name))
	return {"sales_invoice": si.name}