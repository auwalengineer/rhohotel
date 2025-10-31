# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


class HotelRoomCheckIn(Document):
	def validate(self):
		self.validate_reservation()
		self.validate_room()
		self.validate_dates()
		self.validate_rate_and_session()
		self.set_rate_amount()

	def validate_rate_and_session(self):
		# Validate rate type exists for room type
		tariff = frappe.get_all(
			"Hotel Room Tariff",
			filters={
				"room_type": self.room_type,
				"rate_type": self.rate_type,
				"session_type": self.session_type,
				"docstatus": 1
			}
		)
        
		if not tariff:
			frappe.throw(_(
				"No valid tariff found for Room Type {0} with Rate Type {1} and Session Type {2}"
			).format(self.room_type, self.rate_type, self.session_type))

       def set_rate_amount(self):
	       # Get rate amount from tariff using session period/duration
	       tariff = frappe.get_all(
		       "Hotel Room Tariff",
		       filters={
			       "room_type": self.room_type,
			       "rate_type": self.rate_type,
			       "session_type": self.session_type,
			       "is_active": 1
		       },
		       fields=["amount"],
		       limit=1
	       )
	       if tariff:
		       self.rate_amount = tariff[0].amount
	def validate_reservation(self):
		"""Check if reservation exists and is valid for check-in"""
		if not frappe.db.exists("Hotel Room Reservation", self.reservation):
			frappe.throw(_("Reservation {0} does not exist").format(self.reservation))

		reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)
		
		# Check reservation dates
		check_in_date = get_datetime(self.check_in_datetime).date()
		if check_in_date < reservation.from_date:
			frappe.throw(_("Check-in date cannot be before reservation start date"))
		if check_in_date > reservation.to_date:
			frappe.throw(_("Check-in date cannot be after reservation end date"))

		# Check if already checked in
		existing = frappe.get_all("Hotel Room Check In",
			filters={
				"reservation": self.reservation,
				"docstatus": 1,
				"status": ["in", ["Draft", "Checked In"]]
			})
		if existing and self.is_new():
			frappe.throw(_("Reservation {0} is already checked in").format(self.reservation))

	def validate_room(self):
		"""Validate room assignment and availability"""
		if not frappe.db.exists("Hotel Room", self.room):
			frappe.throw(_("Room {0} does not exist").format(self.room))

		# Check if room matches reservation type
		room = frappe.get_doc("Hotel Room", self.room)
		reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)
		
		if not any(item.room_type == room.hotel_room_type for item in reservation.items):
			frappe.throw(_("Room {0} type does not match any room type in reservation").format(self.room))

		# Check if room is available
		existing = frappe.get_all("Hotel Room Check In",
			filters={
				"room": self.room,
				"docstatus": 1,
				"status": "Checked In",
				"name": ["!=", self.name]
			})
		if existing:
			frappe.throw(_("Room {0} is currently occupied").format(self.room))

	def validate_dates(self):
		"""Validate check-in/out dates"""
		if get_datetime(self.check_in_datetime) > get_datetime(self.expected_check_out_datetime):
			frappe.throw(_("Check-in time cannot be after expected check-out time"))

	def on_submit(self):
		"""Update status on submit"""
		self.status = "Checked In"
		self.db_set("status", "Checked In")

	def on_cancel(self):
		"""Update status on cancel"""
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")