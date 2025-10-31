# Copyright (c) 2025, Rhocom Technology Ltd and Contributors
# See license.txt

import unittest
import frappe
from frappe.utils import add_days, now_datetime
from rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in import HotelRoomCheckIn

class TestHotelRoomCheckIn(unittest.TestCase):
	def setUp(self):
		# Create test reservation and room
		self.room_type = frappe.get_doc({
			"doctype": "Hotel Room Type",
			"room_type": "Test Type",
			"capacity": 2
		}).insert()

		self.room = frappe.get_doc({
			"doctype": "Hotel Room",
			"room_number": "TEST-101",
			"hotel_room_type": self.room_type.name,
			"capacity": 2
		}).insert()

		self.reservation = frappe.get_doc({
			"doctype": "Hotel Room Reservation",
			"guest_name": "Test Guest",
			"from_date": now_datetime().date(),
			"to_date": add_days(now_datetime().date(), 2),
			"items": [
				{
					"room_type": self.room_type.name,
					"qty": 1
				}
			]
		}).insert()
		self.reservation.submit()

	def test_check_in_creation(self):
		"""Test basic check-in creation"""
		check_in = frappe.get_doc({
			"doctype": "Hotel Room Check In",
			"reservation": self.reservation.name,
			"guest_name": "Test Guest",
			"guest_count": 1,
			"id_type": "Passport",
			"id_number": "TEST123",
			"contact_number": "1234567890",
			"check_in_datetime": now_datetime(),
			"expected_check_out_datetime": add_days(now_datetime(), 1),
			"room": self.room.name
		})
		check_in.insert()
		check_in.submit()

		self.assertEqual(check_in.status, "Checked In")
		self.assertEqual(check_in.guest_name, "Test Guest")

	def test_invalid_room(self):
		"""Test check-in with invalid room"""
		with self.assertRaises(frappe.ValidationError):
			check_in = frappe.get_doc({
				"doctype": "Hotel Room Check In",
				"reservation": self.reservation.name,
				"guest_name": "Test Guest",
				"guest_count": 1,
				"id_type": "Passport",
				"id_number": "TEST123",
				"contact_number": "1234567890",
				"check_in_datetime": now_datetime(),
				"expected_check_out_datetime": add_days(now_datetime(), 1),
				"room": "INVALID-ROOM"
			}).insert()

	def test_duplicate_check_in(self):
		"""Test preventing duplicate check-ins for same reservation"""
		check_in1 = frappe.get_doc({
			"doctype": "Hotel Room Check In",
			"reservation": self.reservation.name,
			"guest_name": "Test Guest",
			"guest_count": 1,
			"id_type": "Passport",
			"id_number": "TEST123",
			"contact_number": "1234567890",
			"check_in_datetime": now_datetime(),
			"expected_check_out_datetime": add_days(now_datetime(), 1),
			"room": self.room.name
		})
		check_in1.insert()
		check_in1.submit()

		with self.assertRaises(frappe.ValidationError):
			check_in2 = frappe.get_doc({
				"doctype": "Hotel Room Check In",
				"reservation": self.reservation.name,
				"guest_name": "Test Guest",
				"guest_count": 1,
				"id_type": "Passport",
				"id_number": "TEST123",
				"contact_number": "1234567890",
				"check_in_datetime": now_datetime(),
				"expected_check_out_datetime": add_days(now_datetime(), 1),
				"room": self.room.name
			}).insert()

	def tearDown(self):
		# Clean up created test records
		for doctype in ["Hotel Room Check In", "Hotel Room Reservation", "Hotel Room", "Hotel Room Type"]:
			frappe.db.sql(f"delete from `tab{doctype}` where creation > '2025-10-29'")