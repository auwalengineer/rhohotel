# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


class HotelRoomCheckIn(Document):
	def validate(self):
		#self.validate_reservation()
		self.validate_rate_amount()
		self.validate_room()
		self.validate_dates()
		self.handle_late_checkout()
		#self.validate_rate_and_session()
		#self.set_rate_amount()

	def handle_late_checkout(self):
		if self.late_checkout:
			hotel_settings = frappe.get_single("Hotel Settings")
			if hotel_settings.enable_late_check_out:
				expected_checkout_date = get_datetime(self.expected_check_out_datetime).date()
				self.expected_check_out_datetime = get_datetime(str(expected_checkout_date) + " " + str(hotel_settings.default_check_out_time))

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
				"hotel_season": self.hotel_season,
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
		self.make_sales_invoice()
		frappe.publish_realtime('rhohotel_front_desk_update')

	def on_cancel(self):
		"""Update status on cancel"""
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")
		self.update_room_status("Vacant")
		frappe.publish_realtime('rhohotel_front_desk_update')

	def update_room_status(self, status):
		frappe.db.set_value("Hotel Room", self.room_number, "status", status)

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
		"""Publish update to front desk"""
		frappe.publish_realtime('rhohotel_front_desk_update')

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