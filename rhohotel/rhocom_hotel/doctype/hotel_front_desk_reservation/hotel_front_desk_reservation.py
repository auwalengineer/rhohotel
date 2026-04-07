import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, date_diff, nowdate, now_datetime, format_datetime, flt
from datetime import datetime
import json

from rhohotel.api import get_room_rate
from rhohotel.shared_utilities import create_or_get_item, generate_secure_booking_number


class HotelFrontDeskReservation(frappe.model.document.Document):
	def before_insert(self):
		"""Generate reservation number"""
		if not self.reservation_number:
			self.reservation_number = generate_secure_booking_number()

	def validate(self):
		"""Validate and calculate"""
		self.validate_dates()
		self.validate_rooms()
		self.calculate_pricing()
		self.set_total_rooms()

		if self.corporate_guest:
			self.fetch_corporate_details()

	def on_submit(self):
		"""Create customers, guests, and reservations"""
		try:
			self.create_customers_and_guests()
			self.create_room_reservations()
			self.status = "Confirmed"
			self.db_set("status", "Confirmed")

			frappe.msgprint(_("Reservation {0} confirmed").format(self.name), indicator="green", alert=True)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Reservation Submit Error")
			frappe.throw(_("Error: {0}").format(str(e)))

	# def on_cancel(self):
	# 	"""Cancel linked reservations"""
	# 	try:
	# 		reservations = frappe.get_all(
	# 			"Hotel Room Reservation",
	# 			filters={"front_desk_reservation": self.name, "docstatus": 1},
	# 			fields=["name"],
	# 		)

	# 		for res in reservations:
	# 			doc = frappe.get_doc("Hotel Room Reservation", res.name)
	# 			doc.flags.ignore_permissions = True
	# 			doc.cancel()

	# 		self.status = "Cancelled"
	# 	except Exception as e:
	# 		frappe.log_error(frappe.get_traceback(), "Reservation Cancel Error")
	# 		frappe.throw(_("Error: {0}").format(str(e)))

	# ═══════════════════════════════════════════════════════════════════════
	# hotel_front_desk_reservation.py  →  on_cancel()
	# ═══════════════════════════════════════════════════════════════════════

	def on_cancel(self):
		try:
			cancelled_rooms = []

			# ───────────────────────────────────────────
			# 1. CANCEL ALL LINKED HOTEL ROOM RESERVATIONS
			#    + RELEASE EACH ROOM BACK TO AVAILABLE
			# ───────────────────────────────────────────
			room_reservations = frappe.get_all(
				"Hotel Room Reservation",
				filters={
					"front_desk_reservation": self.name,
					"docstatus": 1,  # Only submitted docs can be cancelled
				},
				fields=["name", "room_number"],
			)

			for res in room_reservations:
				# Cancel the reservation
				res_doc = frappe.get_doc("Hotel Room Reservation", res["name"])
				res_doc.flags.ignore_permissions = True
				res_doc.cancel()
				frappe.delete_doc("Hotel Room Reservation", res["name"], force=True)

				# # Release the room → set back to Available
				# if res["room_number"]:
				# 	try:
				# 		room_doc = frappe.get_doc("Hotel Room", res["room_number"])
				# 		room_doc.booking_status = "Available"
				# 		room_doc.current_booking_number = None
				# 		room_doc.hold_expires_at = None
				# 		# Only set Vacant if room is currently Occupied due to THIS reservation
				# 		if room_doc.status == "Occupied":
				# 			room_doc.status = "Vacant"
				# 		room_doc.save(ignore_permissions=True)
				# 		cancelled_rooms.append(res["room_number"])
				# 	except Exception as room_err:
				# 		frappe.log_error(
				# 			frappe.get_traceback(),
				# 			f"Room release failed for {res['room_number']} on FDR {self.name}",
				# 		)

			# ───────────────────────────────────────────
			# 2. UPDATE GUEST PROFILES → mark as Failed
			# ───────────────────────────────────────────
			for res in room_reservations:
				guest_profiles = frappe.get_all(
					"Hotel Reservation Guest Profile",
					filters={"hotel_reservation": res["name"]},
					fields=["name"],
				)
				for gp in guest_profiles:
					try:
						gp_doc = frappe.get_doc("Hotel Reservation Guest Profile", gp["name"])
						gp_doc.payment_status = "Failed"
						gp_doc.save(ignore_permissions=True)
					except Exception:
						pass  # Non-critical — log if needed

			# ───────────────────────────────────────────
			# 3. CANCEL SALES INVOICE (if exists + submitted)
			# ───────────────────────────────────────────
			if self.sales_invoice:
				try:
					invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
					if invoice.docstatus == 1:
						invoice.flags.ignore_permissions = True
						invoice.cancel()
						frappe.delete_doc("Sales Invoice", self.sales_invoice, force=True)
				except Exception as inv_err:
					frappe.log_error(
						frappe.get_traceback(),
						f"Invoice cancel failed for {self.sales_invoice} on FDR {self.name}",
					)

			# ───────────────────────────────────────────
			# 4. CANCEL PAYMENT ENTRY (if exists + submitted)
			# ───────────────────────────────────────────
			if self.payment_entry:
				try:
					payment = frappe.get_doc("Payment Entry", self.payment_entry)
					if payment.docstatus == 1:
						payment.flags.ignore_permissions = True
						payment.cancel()
				except Exception as pay_err:
					frappe.log_error(
						frappe.get_traceback(),
						f"Payment cancel failed for {self.payment_entry} on FDR {self.name}",
					)

			# ───────────────────────────────────────────
			# 5. UPDATE FDR STATUS + CONFIRM TO USER
			# ───────────────────────────────────────────
			self.status = "Cancelled"

			rooms_msg = ", ".join(cancelled_rooms) if cancelled_rooms else "None"
			frappe.msgprint(
				_(
					"FDR {0} cancelled.<br><b>Rooms released:</b> {1}<br><b>Reservations cancelled:</b> {2}"
				).format(self.name, rooms_msg, len(room_reservations)),
				indicator="red",
				alert=True,
			)

		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Cancel Error")
			frappe.throw(_("Error cancelling reservation: {0}").format(str(e)))

	# ═══════════════════════════════════════════════════════════════════════
	# VALIDATION
	# ═══════════════════════════════════════════════════════════════════════

	def validate_dates(self):
		"""Validate dates and calculate nights"""
		if not self.from_date or not self.to_date:
			frappe.throw(_("Check-in and check-out dates required"))

		if getdate(self.to_date) <= getdate(self.from_date):
			frappe.throw(_("Check-out must be after check-in"))

		self.number_of_nights = date_diff(self.to_date, self.from_date)

		if self.number_of_nights < 1:
			frappe.throw(_("Minimum 1 night required"))

	def validate_rooms(self):
		"""Validate rooms"""
		if not self.rooms:
			frappe.throw(_("At least one room required"))

		seen_rooms = set()

		for room in self.rooms:
			# Check duplicates
			if room.room_number in seen_rooms:
				frappe.throw(_("Room {0} appears multiple times").format(room.room_number))
			seen_rooms.add(room.room_number)

			# Check availability
			if not self.is_room_available(room.room_number):
				frappe.throw(_("Room {0} not available").format(room.room_number))

			# Set defaults from primary guest
			room.guest_name = room.guest_name or self.primary_guest_name or ""
			room.guest_email = room.guest_email or self.primary_guest_email or ""
			room.guest_phone = room.guest_phone or self.primary_guest_phone or ""
			room.number_of_nights = self.number_of_nights

			# Get room type and rate
			room_doc = frappe.get_doc("Hotel Room", room.room_number)
			room.room_type = room_doc.room_type

			rate = get_room_rate(room.room_type, check_in_date=str(self.from_date))
			if not rate:
				frappe.throw(_("No rate found for {0}").format(room.room_type))

			room.rate_per_night = rate
			room.room_total = rate * self.number_of_nights

			# Get tariff info
			tariff = frappe.db.get_value(
				"Hotel Room Tariff",
				{"room_type": room.room_type, "is_active": 1},
				["rate_type", "hotel_season"],
				as_dict=True,
			)

			if tariff:
				room.rate_type = tariff.get("rate_type", "Standard")
				if tariff.get("hotel_season"):
					season_type = frappe.db.get_value(
						"Hotel Season", tariff.get("hotel_season"), "season_type"
					)
					room.season_type = season_type or ""

	def is_room_available(self, room_number):
		"""Check room availability"""
		# Check overlapping reservations
		overlapping = frappe.db.sql(
			"""
            SELECT COUNT(*) as count
            FROM `tabHotel Room Reservation`
            WHERE room_number = %s
            AND status NOT IN ('Cancelled', 'Completed')
            AND from_date < %s
            AND to_date > %s
        """,
			(room_number, self.to_date, self.from_date),
			as_dict=True,
		)

		if overlapping and overlapping[0].count > 0:
			return False

		# Check active check-ins
		checked_in = frappe.db.sql(
			"""
            SELECT COUNT(*) as count
            FROM `tabHotel Room Check In`
            WHERE room_number = %s
            AND status IN ('Draft', 'Checked In')
            AND DATE(check_in_datetime) < %s
            AND DATE(expected_check_out_datetime) > %s
        """,
			(room_number, self.to_date, self.from_date),
			as_dict=True,
		)

		return not (checked_in and checked_in[0].count > 0)

	def calculate_pricing(self):
		"""Calculate totals"""
		self.subtotal = sum(room.room_total for room in self.rooms)

		self.discount_amount = 0
		if self.discount_type and self.discount:
			if self.discount_type == "Percentage":
				self.discount_amount = (self.subtotal * self.discount) / 100
			elif self.discount_type == "Fixed Amount":
				self.discount_amount = self.discount

		self.total_amount = max(0, self.subtotal - self.discount_amount)

	def set_total_rooms(self):
		"""Set total rooms"""
		self.total_rooms = len(self.rooms)

	def fetch_corporate_details(self):
		"""Fetch from corporate guest"""
		if not self.corporate_guest:
			return

		corporate = frappe.get_doc("Hotel Guest", self.corporate_guest)

		if corporate.guest_type != "Corporate":
			frappe.throw(_("Selected guest is not corporate"))

		self.customer = corporate.customer
		self.primary_guest_name = self.primary_guest_name or corporate.hotel_guest_name
		self.primary_guest_email = self.primary_guest_email or corporate.email or ""
		self.primary_guest_phone = self.primary_guest_phone or corporate.phone_number or ""

	# ═══════════════════════════════════════════════════════════════════════
	# DOCUMENT CREATION
	# ═══════════════════════════════════════════════════════════════════════

	def create_customers_and_guests(self):
		"""Link existing corporate customer/guest or create new ones for edited rooms"""
		for room in self.rooms:
			# If room details match primary guest (not edited), just link to corporate customer/guest
			if (
				room.guest_name == self.primary_guest_name
				and room.guest_email == (self.primary_guest_email or "")
				and room.guest_phone == (self.primary_guest_phone or "")
			):
				# Use the corporate customer and corporate guest directly
				room.guest_customer = self.customer
				room.hotel_guest = self.corporate_guest
				frappe.db.set_value(
					"Front Desk Reservation Room",
					room.name,
					{"guest_customer": self.customer, "hotel_guest": self.corporate_guest},
					update_modified=False,
				)
				continue

			# Room has been edited with different guest details - create new customer/guest
			customer = self.get_or_create_customer(room.guest_name, room.guest_email, room.guest_phone)
			room.guest_customer = customer

			hotel_guest = self.get_or_create_hotel_guest(room, customer)
			room.hotel_guest = hotel_guest

			frappe.db.set_value(
				"Front Desk Reservation Room",
				room.name,
				{"guest_customer": customer, "hotel_guest": hotel_guest},
				update_modified=False,
			)

	def get_or_create_customer(self, name, email, phone):
		"""Get or create customer (uses native Email and Phone fields for validation)"""
		# Check by email
		if email:
			existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
			if existing:
				return existing

		# Check by phone (last 10 digits)
		if phone:
			search_phone = phone.replace(" ", "").replace("-", "").replace("+", "")[-10:]
			existing = frappe.db.sql(
				"""
                SELECT name FROM `tabCustomer`
                WHERE REPLACE(REPLACE(REPLACE(mobile_no, ' ', ''), '-', ''), '+', '') LIKE %s
                LIMIT 1
            """,
				(f"%{search_phone}",),
				as_dict=True,
			)

			if existing:
				return existing[0].name

		# Create new
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name or "Guest",
				"customer_type": "Individual",
				"email_id": email or "",
				"mobile_no": phone or "",
				"territory": frappe.db.get_default("territory") or "Nigeria",
				"customer_group": frappe.db.get_default("customer_group") or "Individual",
			}
		)
		customer.flags.ignore_permissions = True
		customer.insert()

		return customer.name

	def get_or_create_hotel_guest(self, room, customer):
		"""Get or create hotel guest (uses native Email and Phone fields)"""
		# Check by name
		existing = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": room.guest_name}, "name")
		if existing:
			return existing

		# Check by email
		if room.guest_email:
			existing = frappe.db.get_value("Hotel Guest", {"email": room.guest_email}, "name")
			if existing:
				return existing

		# Check by phone
		if room.guest_phone:
			search_phone = room.guest_phone.replace(" ", "").replace("-", "").replace("+", "")[-10:]
			existing = frappe.db.sql(
				"""
                SELECT name FROM `tabHotel Guest`
                WHERE REPLACE(REPLACE(REPLACE(phone_number, ' ', ''), '-', ''), '+', '') LIKE %s
                LIMIT 1
            """,
				(f"%{search_phone}",),
				as_dict=True,
			)

			if existing:
				return existing[0].name

		# Create new
		try:
			guest = frappe.get_doc(
				{
					"doctype": "Hotel Guest",
					"hotel_guest_name": room.guest_name,
					"phone_number": room.guest_phone or "",
					"email": room.guest_email or "",
					"gender": room.guest_gender or "Male",
					"id_type": room.guest_id_type or "Passport",
					"id_number": room.guest_id_number or "",
					"customer": customer,
					"guest_type": "Corporate",
				}
			)
			guest.flags.ignore_permissions = True
			guest.insert()
			return guest.name
		except frappe.exceptions.DuplicateEntryError:
			existing = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": room.guest_name}, "name")
			if existing:
				return existing
			raise

	def create_room_reservations(self):
		"""Create Hotel Room Reservations"""
		for room in self.rooms:
			reservation_items = [
				{
					"room_type": room.room_type,
					"rate_type": getattr(room, "rate_type", "Standard"),
					"season_type": getattr(room, "season_type", ""),
					"qty": room.number_of_nights,
					"rate": room.rate_per_night,
					"amount": room.room_total,
				}
			]

			reservation = frappe.get_doc(
				{
					"doctype": "Hotel Room Reservation",
					"booking_number": self.reservation_number,
					"front_desk_reservation": self.name,
					"room_number": room.room_number,
					"from_date": self.from_date,
					"to_date": self.to_date,
					"rate": room.rate_per_night,
					"discount_type": self.discount_type or "Percentage",
					"discount": self.discount or 0,
					"guest_name": room.guest_name,
					"customer": room.guest_customer,
					"status": "Booked",
					"payment_status": "Pending",
					"items": reservation_items,
					"net_total": room.room_total,
					"reservation_type": "Corporate",
					"number_of_nights": self.number_of_nights,
				}
			)

			reservation.flags.ignore_permissions = True
			reservation.insert()
			reservation.submit()


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_available_rooms(from_date, to_date, room_type=None):
	"""Get available rooms"""
	try:
		from_date_obj = getdate(from_date)
		to_date_obj = getdate(to_date)

		if to_date_obj <= from_date_obj:
			frappe.throw(_("Check-out must be after check-in"))

		filters = {"room_type": room_type} if room_type else {}
		all_rooms = frappe.get_all(
			"Hotel Room", filters=filters, fields=["name", "room_type", "floor", "capacity"]
		)

		if not all_rooms:
			return []

		room_numbers = [r.name for r in all_rooms]
		current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

		# Exclude held rooms
		held_rooms = frappe.db.sql(
			"""
            SELECT DISTINCT tbr.room_number
            FROM `tabTemporary Booking` tb
            INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
            WHERE tbr.room_number IN ({rooms})
            AND tb.status IN ('Hold', 'Payment Link Generated')
            AND tb.payment_status = 'Pending'
            AND tb.booking_status = 'Held'
            AND tb.hold_expires_at > %s
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
			tuple(room_numbers) + (current_time,),
			as_dict=True,
		)

		# Exclude reserved rooms
		overlapping = frappe.db.sql(
			"""
            SELECT DISTINCT room_number
            FROM `tabHotel Room Reservation`
            WHERE room_number IN ({rooms})
            AND status NOT IN ('Cancelled', 'Completed')
            AND from_date < %s AND to_date > %s
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
			tuple(room_numbers) + (to_date, from_date),
			as_dict=True,
		)

		# Exclude checked-in rooms
		checked_in = frappe.db.sql(
			"""
            SELECT DISTINCT room_number
            FROM `tabHotel Room Check In`
            WHERE room_number IN ({rooms})
            AND status IN ('Draft', 'Checked In')
            AND DATE(check_in_datetime) < %s
            AND DATE(expected_check_out_datetime) > %s
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
			tuple(room_numbers) + (to_date, from_date),
			as_dict=True,
		)

		unavailable = set(
			[r.room_number for r in held_rooms]
			+ [r.room_number for r in overlapping]
			+ [r.room_number for r in checked_in]
		)

		available_rooms = [r for r in all_rooms if r.name not in unavailable]

		# Add pricing
		for room in available_rooms:
			rate = get_room_rate(room.room_type, check_in_date=str(from_date))
			room["rate_per_night"] = rate
			room["total_amount"] = rate * date_diff(to_date_obj, from_date_obj)

		return available_rooms

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
		frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def get_rooms_in_bulk_invoice(reservation_name):
	"""Get rooms in bulk invoice for check-in"""
	try:
		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			return {"success": False, "message": "Reservation not submitted"}

		if not reservation.sales_invoice:
			return {"success": False, "message": "No bulk invoice found", "has_bulk_invoice": False}

		all_rooms = []
		for room in reservation.rooms:
			existing_checkin = frappe.db.get_value(
				"Hotel Room Check In",
				{
					"front_desk_reservation": reservation_name,
					"room_number": room.room_number,
					"status": ["in", ["Draft", "Checked In"]],
				},
				["name", "status"],
				as_dict=True,
			)

			all_rooms.append(
				{
					"idx": room.idx,
					"room_number": room.room_number,
					"room_type": room.room_type,
					"guest_name": room.guest_name,
					"guest_email": room.guest_email,
					"guest_phone": room.guest_phone,
					"rate_per_night": room.rate_per_night,
					"room_total": room.room_total,
					"has_checkin": bool(existing_checkin),
					"checkin_status": existing_checkin.get("status") if existing_checkin else None,
					"checkin_name": existing_checkin.get("name") if existing_checkin else None,
				}
			)

		return {
			"success": True,
			"has_bulk_invoice": True,
			"bulk_invoice": reservation.sales_invoice,
			"rooms": all_rooms,
			"total_rooms": len(all_rooms),
			"rooms_checked_in": len([r for r in all_rooms if r["has_checkin"]]),
			"rooms_pending": len([r for r in all_rooms if not r["has_checkin"]]),
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Rooms in Bulk Invoice Error")
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def check_in_rooms_in_bulk_invoice(reservation_name, room_indices, check_in_notes=""):
	"""Check in rooms from bulk invoice (no new invoice created)"""
	try:
		if isinstance(room_indices, str):
			room_indices = json.loads(room_indices)

		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		if not reservation.sales_invoice:
			frappe.throw(_("No bulk invoice found"))

		settings = frappe.get_single("Hotel Settings")
		check_in_time = now_datetime().strftime("%H:%M:%S")
		check_out_time = settings.default_check_out_time or "11:00:00"

		checked_in_rooms = []
		skipped_rooms = []

		for idx in room_indices:
			idx = int(idx)
			room = None

			for r in reservation.rooms:
				if r.idx == idx + 1:
					room = r
					break

			if not room:
				skipped_rooms.append({"idx": idx, "reason": "Room not found"})
				continue

			# Check if already checked in
			existing = frappe.db.get_value(
				"Hotel Room Check In",
				{
					"front_desk_reservation": reservation_name,
					"room_number": room.room_number,
					"status": ["in", ["Draft", "Checked In"]],
				},
				"name",
			)

			if existing:
				skipped_rooms.append({"room_number": room.room_number, "reason": "Already checked in"})
				continue

			if not room.guest_name or room.guest_name.startswith("Guest - Room"):
				skipped_rooms.append({"room_number": room.room_number, "reason": "Guest name required"})
				continue

			# Get Hotel Room Reservation
			hrr = frappe.db.get_value(
				"Hotel Room Reservation",
				{"front_desk_reservation": reservation_name, "room_number": room.room_number, "docstatus": 1},
				"name",
			)

			if not hrr:
				skipped_rooms.append({"room_number": room.room_number, "reason": "No reservation found"})
				continue

			check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
			expected_checkout_datetime = get_datetime(f"{reservation.to_date} {check_out_time}")

			# Create check-in (no invoice - uses bulk invoice)
			checkin = frappe.get_doc(
				{
					"doctype": "Hotel Room Check In",
					"front_desk_reservation": reservation_name,
					"reservation": hrr,
					"room_number": room.room_number,
					"room_type": room.room_type,
					"rate_type": getattr(room, "rate_type", None),
					"guest": room.hotel_guest,
					"guest_name": room.guest_name,
					"guest_email": room.guest_email or reservation.primary_guest_email,
					"guest_phone": room.guest_phone or reservation.primary_guest_phone,
					"customer": room.guest_customer or reservation.customer,
					"hotel_guest": room.hotel_guest,
					"check_in_datetime": check_in_datetime,
					"expected_check_out_datetime": expected_checkout_datetime,
					"number_of_nights": reservation.number_of_nights,
					"rate_per_night": room.rate_per_night,
					"rate_amount": room.rate_per_night,
					"total_amount": room.room_total,
					"status": "Checked In",
					"payment_status": "Paid",
					"check_in_notes": check_in_notes,
					"sales_invoice": reservation.sales_invoice,
					"is_bulk_invoice_room": 1,
					"discount": reservation.discount or 0,
					"discount_type": reservation.discount_type or "None",
					"total_charges": room.room_total,
				}
			)

			checkin.flags.ignore_permissions = True
			checkin.insert()
			checkin.submit()

			frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")

			checked_in_rooms.append(
				{"room_number": room.room_number, "guest_name": room.guest_name, "checkin_name": checkin.name}
			)

		# Update reservation status
		if checked_in_rooms:
			total_checkins = frappe.db.count(
				"Hotel Room Check In",
				{"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
			)

			if total_checkins >= len(reservation.rooms):
				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")
			elif total_checkins > 0 and reservation.status == "Confirmed":
				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")

		frappe.db.commit()

		message = _("{0} room(s) checked in (bulk invoice)").format(len(checked_in_rooms))
		if skipped_rooms:
			message += _(" | {0} skipped").format(len(skipped_rooms))

		return {
			"success": True,
			"message": message,
			"checked_in_rooms": checked_in_rooms,
			"skipped_rooms": skipped_rooms,
			"bulk_invoice": reservation.sales_invoice,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Check In Bulk Invoice Rooms Error")
		frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def create_sales_invoice_for_reservation(reservation_name):
# 	"""Create bulk sales invoice for unchecked rooms"""
# 	try:
# 		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

# 		if reservation.docstatus != 1:
# 			frappe.throw(_("Reservation must be submitted"))

# 		if reservation.sales_invoice:
# 			frappe.throw(_("Invoice exists: {0}").format(reservation.sales_invoice))

# 		if not reservation.customer:
# 			frappe.throw(_("Customer required"))

# 		# Get checked-in rooms
# 		checked_in = frappe.get_all(
# 			"Hotel Room Check In",
# 			filters={"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
# 			pluck="room_number",
# 		)

# 		# Filter unchecked rooms
# 		unchecked_rooms = [r for r in reservation.rooms if r.room_number not in checked_in]

# 		if not unchecked_rooms:
# 			frappe.throw(_("All rooms already checked in"))

# 		# Create invoice
# 		si = frappe.new_doc("Sales Invoice")
# 		si.customer = reservation.customer
# 		si.posting_date = nowdate()
# 		si.due_date = reservation.to_date
# 		si.po_no = reservation.reservation_number
# 		si.remarks = _("Bulk invoice for {0}").format(reservation.reservation_number)

# 		total = 0
# 		for room in unchecked_rooms:
# 			# try:
# 			#     item_name = create_or_get_item(room.room_type)
# 			# except:
# 			#     item_name = room.room_type

# 			try:
# 				item_code = create_or_get_item(
# 					room_number=room.room_number, room_type=room.room_type, erpnext_item=None
# 				)
# 			except Exception as item_error:
# 				frappe.log_error(f"Item creation failed: {str(item_error)}", "Bulk Invoice Item Error")
# 				# Fallback to room type
# 				item_code = room.room_type

# 			si.append(
# 				"items",
# 				{
# 					"item_code": item_code,
# 					"item_name": f"{room.room_number} - {room.guest_name}",
# 					"description": _("Room {0} ({1}) - {2} night(s) @ {3}/night for {4}").format(
# 						room.room_number,
# 						room.room_type,
# 						reservation.number_of_nights,
# 						room.rate_per_night,
# 						room.guest_name,
# 					),
# 					"qty": reservation.number_of_nights,
# 					"rate": room.rate_per_night,
# 					"amount": room.room_total,
# 				},
# 			)
# 			total += room.room_total

# 		if reservation.discount_amount:
# 			si.discount_amount = reservation.discount_amount

# 		si.flags.ignore_permissions = True
# 		si.insert()
# 		si.submit()

# 		frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "sales_invoice", si.name)
# 		frappe.db.commit()

# 		message = _("Invoice {0} created for {1} room(s)").format(si.name, len(unchecked_rooms))
# 		if checked_in:
# 			message += _(" | {0} checked-in rooms excluded").format(len(checked_in))

# 		return {
# 			"success": True,
# 			"message": message,
# 			"invoice": si.name,
# 			"total_rooms": len(reservation.rooms),
# 			"unchecked_rooms": len(unchecked_rooms),
# 			"excluded_rooms": len(checked_in),
# 		}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Create Invoice Error")
# 		frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def create_sales_invoice_for_reservation(reservation_name):
	"""Create bulk sales invoice for unchecked rooms"""
	try:
		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		if reservation.sales_invoice:
			frappe.throw(
				_("A bulk invoice ({0}) already exists for this reservation.").format(
					reservation.sales_invoice
				)
			)

		# ── GUARD: block if individual invoices already exist ────────────────────
		existing_individual_invoices = [r for r in reservation.sales_invoices if r.sales_invoice]
		if existing_individual_invoices:
			invoiced_rooms = ", ".join([r.room_number for r in existing_individual_invoices])
			frappe.throw(
				_(
					"Individual invoices already exist for {0} room(s): {1}.<br>"
					"Cannot create a bulk invoice when individual invoices have already been issued.<br>"
				).format(len(existing_individual_invoices), invoiced_rooms)
			)

		if not reservation.customer:
			frappe.throw(_("Customer required"))

		# ── GET CHECKED-IN ROOMS ─────────────────────────────────────────────────
		checked_in_room_numbers = frappe.get_all(
			"Hotel Room Check In",
			filters={
				"front_desk_reservation": reservation_name,
				"status": ["in", ["Draft", "Checked In"]],
			},
			pluck="room_number",
		)

		# ── FILTER TO UNCHECKED ROOMS ONLY ───────────────────────────────────────
		unchecked_rooms = [r for r in reservation.rooms if r.room_number not in checked_in_room_numbers]

		if not unchecked_rooms:
			frappe.throw(_("All rooms are already checked in. No bulk invoice needed."))

		# ── BUILD INVOICE ────────────────────────────────────────────────────────
		si = frappe.new_doc("Sales Invoice")
		si.customer = reservation.customer
		si.posting_date = nowdate()
		si.due_date = reservation.to_date
		si.po_no = reservation.reservation_number
		si.remarks = _("Bulk invoice for reservation {0}").format(reservation.reservation_number)

		unchecked_subtotal = sum(flt(r.room_total) for r in unchecked_rooms)

		for room in unchecked_rooms:
			try:
				item_code = create_or_get_item(
					room_number=room.room_number, room_type=room.room_type, erpnext_item=None
				)
			except Exception as item_error:
				frappe.log_error(f"Item creation failed: {str(item_error)}", "Bulk Invoice Item Error")
				item_code = room.room_type

			si.append(
				"items",
				{
					"item_code": item_code,
					"item_name": f"{room.room_number} - {room.guest_name}",
					"description": _("Room {0} ({1}) - {2} night(s) @ {3}/night for {4}").format(
						room.room_number,
						room.room_type,
						reservation.number_of_nights,
						room.rate_per_night,
						room.guest_name,
					),
					"qty": reservation.number_of_nights,
					"rate": room.rate_per_night,
					"amount": room.room_total,
				},
			)

		# ── DISCOUNT ─────────────────────────────────────────────────────────────
		# If some rooms were already checked in with individual invoices,
		# only apply the remaining discount (what hasn't been applied yet).
		# If no prior individual invoices exist (guarded above), apply full discount.
		if reservation.discount_amount and reservation.subtotal:
			total_discount = flt(reservation.discount_amount, 2)

			already_applied = flt(
				frappe.db.sql(
					"""
					SELECT IFNULL(SUM(si.discount_amount), 0)
					FROM `tabSales Invoice` si
					INNER JOIN `tabHotel Front Desk Reservation Invoice` fdri
						ON fdri.sales_invoice = si.name
					WHERE fdri.parent = %s
					AND si.docstatus = 1
					""",
					(reservation_name,),
				)[0][0],
				2,
			)

			remaining_discount = flt(total_discount - already_applied, 2)

			if remaining_discount > 0 and unchecked_subtotal > 0:
				# Prorate remaining discount against unchecked rooms only
				bulk_share = unchecked_subtotal / flt(reservation.subtotal)
				bulk_discount = flt(remaining_discount * bulk_share, 2)

				if bulk_discount > 0:
					si.discount_amount = bulk_discount
					si.apply_discount_on = "Grand Total"

		si.flags.ignore_permissions = True
		si.insert()
		si.submit()

		# ── SAVE INVOICE REFERENCE ON FDR ────────────────────────────────────────
		frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "sales_invoice", si.name)
		frappe.db.commit()

		# ── BUILD RESPONSE MESSAGE ───────────────────────────────────────────────
		message = _("Bulk invoice {0} created for {1} room(s)").format(si.name, len(unchecked_rooms))
		if checked_in_room_numbers:
			message += _(" | {0} already checked-in room(s) excluded").format(len(checked_in_room_numbers))

		return {
			"success": True,
			"message": message,
			"invoice": si.name,
			"total_rooms": len(reservation.rooms),
			"unchecked_rooms": len(unchecked_rooms),
			"excluded_rooms": len(checked_in_room_numbers),
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Create Invoice Error")
		frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
# 	"""Check in selected rooms (creates individual invoices if no bulk invoice)"""
# 	try:
# 		if isinstance(room_indices, str):
# 			room_indices = json.loads(room_indices)

# 		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

# 		if reservation.docstatus != 1:
# 			frappe.throw(_("Reservation must be submitted"))

# 		if reservation.sales_invoice:
# 			frappe.throw(
# 				_(
# 					"You have a bulk invoice for this reservation already.\n"
# 					"Use Check In Rooms (Bulk Invoice) to check in this reservation.\n"
# 					"Use bulk invoice check-in for this reservation"
# 				)
# 			)

# 		settings = frappe.get_single("Hotel Settings")
# 		check_in_time = now_datetime().strftime("%H:%M:%S")
# 		check_out_time = settings.default_check_out_time or "11:00:00"

# 		checked_in_rooms = []
# 		skipped_rooms = []

# 		for idx in room_indices:
# 			idx = int(idx)
# 			room = None

# 			for r in reservation.rooms:
# 				if r.idx == idx + 1:
# 					room = r
# 					break

# 			if not room:
# 				skipped_rooms.append({"idx": idx, "reason": "Not found"})
# 				continue

# 			# Check existing
# 			existing = frappe.db.get_value(
# 				"Hotel Room Check In",
# 				{
# 					"front_desk_reservation": reservation_name,
# 					"room_number": room.room_number,
# 					"status": ["in", ["Draft", "Checked In"]],
# 				},
# 				"name",
# 			)

# 			if existing:
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "Already checked in"})
# 				continue

# 			if not room.guest_name or room.guest_name.startswith("Guest - Room"):
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "Guest name required"})
# 				continue

# 			# Get reservation
# 			hrr = frappe.db.get_value(
# 				"Hotel Room Reservation",
# 				{"front_desk_reservation": reservation_name, "room_number": room.room_number, "docstatus": 1},
# 				"name",
# 			)

# 			if not hrr:
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "No reservation"})
# 				continue

# 			# Create individual invoice
# 			try:
# 				si = frappe.new_doc("Sales Invoice")
# 				si.customer = reservation.customer
# 				si.posting_date = nowdate()
# 				si.due_date = reservation.to_date
# 				si.po_no = f"{reservation.reservation_number} - {room.room_number}"

# 				# try:
# 				#     item_name = create_or_get_item(room.room_type)
# 				# except:
# 				#     item_name = room.room_type

# 				try:
# 					item_code = create_or_get_item(
# 						room_number=room.room_number, room_type=room.room_type, erpnext_item=None
# 					)
# 				except Exception as item_error:
# 					frappe.log_error(f"Item creation failed: {str(item_error)}", "Invoice Item Error")
# 					# Fallback to room type
# 					item_code = room.room_type

# 				si.append(
# 					"items",
# 					{
# 						"item_code": item_code,
# 						"item_name": f"{room.room_number} - {room.guest_name}",
# 						"description": _("Room {0} - {1} night(s) @ {2}/night").format(
# 							room.room_number, reservation.number_of_nights, room.rate_per_night
# 						),
# 						"qty": reservation.number_of_nights,
# 						"rate": room.rate_per_night,
# 						"amount": room.room_total,
# 					},
# 				)

# 				if reservation.discount_amount and reservation.subtotal:
# 					room_share = room.room_total / reservation.subtotal
# 					room_discount = reservation.discount_amount * room_share
# 					si.discount_amount = flt(room_discount, 2)
# 					si.apply_discount_on = "Grand Total"

# 				si.flags.ignore_permissions = True
# 				si.insert()
# 				si.submit()
# 				room_invoice = si.name

# 				# Add to child table
# 				reservation.append(
# 					"sales_invoices",
# 					{
# 						"room_number": room.room_number,
# 						"guest_name": room.guest_name,
# 						"sales_invoice": si.name,
# 						"amount": room.room_total,
# 						"created_at": now_datetime(),
# 					},
# 				)
# 				reservation.flags.ignore_permissions = True
# 				reservation.flags.ignore_validate_update_after_submit = True
# 				reservation.save()

# 			except Exception as e:
# 				frappe.log_error(f"Invoice error for {room.room_number}: {str(e)}", "Check In Invoice Error")
# 				room_invoice = None

# 			check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
# 			expected_checkout = get_datetime(f"{reservation.to_date} {check_out_time}")

# 			# Create check-in
# 			checkin = frappe.get_doc(
# 				{
# 					"doctype": "Hotel Room Check In",
# 					"front_desk_reservation": reservation_name,
# 					"hotel_room_reservation": hrr,
# 					"reservation": hrr,
# 					"room_number": room.room_number,
# 					"room_type": room.room_type,
# 					"rate_type": getattr(room, "rate_type", None),
# 					"guest": room.hotel_guest,
# 					"guest_name": room.guest_name,
# 					"guest_email": room.guest_email or reservation.primary_guest_email,
# 					"guest_phone": room.guest_phone or reservation.primary_guest_phone,
# 					"customer": room.guest_customer or reservation.customer,
# 					"hotel_guest": room.hotel_guest,
# 					"check_in_datetime": check_in_datetime,
# 					"expected_check_out_datetime": expected_checkout,
# 					"number_of_nights": reservation.number_of_nights,
# 					"rate_per_night": room.rate_per_night,
# 					"rate_amount": room.rate_per_night,
# 					"total_amount": room.room_total,
# 					"status": "Checked In",
# 					"payment_status": "Pending",
# 					"check_in_notes": check_in_notes,
# 					"sales_invoice": room_invoice,
# 					"discount": reservation.discount_amount or 0,
# 					"discount_type": reservation.discount_type or "None",
# 					"total_charges": room.room_total,
# 				}
# 			)

# 			checkin.flags.ignore_permissions = True
# 			checkin.insert()
# 			checkin.submit()

# 			frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")

# 			checked_in_rooms.append(
# 				{
# 					"room_number": room.room_number,
# 					"guest_name": room.guest_name,
# 					"checkin_name": checkin.name,
# 					"invoice": room_invoice,
# 				}
# 			)

# 		# Update status
# 		if checked_in_rooms:
# 			total_checkins = frappe.db.count(
# 				"Hotel Room Check In",
# 				{"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
# 			)

# 			if total_checkins >= len(reservation.rooms):
# 				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")
# 			elif total_checkins > 0 and reservation.status == "Confirmed":
# 				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")

# 		frappe.db.commit()

# 		message = _("{0} room(s) checked in").format(len(checked_in_rooms))
# 		if skipped_rooms:
# 			message += _(" | {0} skipped").format(len(skipped_rooms))

# 		return {
# 			"success": True,
# 			"message": message,
# 			"checked_in_rooms": checked_in_rooms,
# 			"skipped_rooms": skipped_rooms,
# 		}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Check In Selected Error")
# 		frappe.throw(_("Error: {0}").format(str(e)))


# share by percentage
# @frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
# 	"""Check in selected rooms (creates individual invoices if no bulk invoice)"""
# 	try:
# 		if isinstance(room_indices, str):
# 			room_indices = json.loads(room_indices)

# 		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

# 		if reservation.docstatus != 1:
# 			frappe.throw(_("Reservation must be submitted"))

# 		if reservation.sales_invoice:
# 			frappe.throw(
# 				_(
# 					"A bulk invoice ({0}) already exists for this reservation. "
# 					"Use 'Check In Rooms (Bulk Invoice)' instead to avoid duplicate invoicing."
# 				).format(reservation.sales_invoice)
# 			)

# 		# ── GUARD: block if all rooms already have individual invoices ──────────
# 		invoiced_room_numbers = {r.room_number for r in reservation.sales_invoices if r.sales_invoice}
# 		all_room_numbers = {r.room_number for r in reservation.rooms}
# 		if invoiced_room_numbers >= all_room_numbers:
# 			frappe.throw(
# 				_(
# 					"All rooms already have individual invoices. "
# 					"No further invoicing is needed for this reservation."
# 				)
# 			)

# 		settings = frappe.get_single("Hotel Settings")
# 		check_in_time = now_datetime().strftime("%H:%M:%S")
# 		check_out_time = settings.default_check_out_time or "11:00:00"

# 		checked_in_rooms = []
# 		skipped_rooms = []

# 		for idx in room_indices:
# 			idx = int(idx)
# 			room = None

# 			for r in reservation.rooms:
# 				if r.idx == idx + 1:
# 					room = r
# 					break

# 			if not room:
# 				skipped_rooms.append({"idx": idx, "reason": "Not found"})
# 				continue

# 			# Check existing check-in
# 			existing = frappe.db.get_value(
# 				"Hotel Room Check In",
# 				{
# 					"front_desk_reservation": reservation_name,
# 					"room_number": room.room_number,
# 					"status": ["in", ["Draft", "Checked In"]],
# 				},
# 				"name",
# 			)

# 			if existing:
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "Already checked in"})
# 				continue

# 			if not room.guest_name or room.guest_name.startswith("Guest - Room"):
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "Guest name required"})
# 				continue

# 			# Get Hotel Room Reservation
# 			hrr = frappe.db.get_value(
# 				"Hotel Room Reservation",
# 				{"front_desk_reservation": reservation_name, "room_number": room.room_number, "docstatus": 1},
# 				"name",
# 			)

# 			if not hrr:
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "No reservation"})
# 				continue

# 			# ── CREATE INDIVIDUAL INVOICE ────────────────────────────────────────
# 			room_invoice = None
# 			try:
# 				si = frappe.new_doc("Sales Invoice")
# 				si.customer = reservation.customer
# 				si.posting_date = nowdate()
# 				si.due_date = reservation.to_date
# 				si.po_no = f"{reservation.reservation_number} - {room.room_number}"

# 				try:
# 					item_code = create_or_get_item(
# 						room_number=room.room_number, room_type=room.room_type, erpnext_item=None
# 					)
# 				except Exception as item_error:
# 					frappe.log_error(f"Item creation failed: {str(item_error)}", "Invoice Item Error")
# 					item_code = room.room_type

# 				si.append(
# 					"items",
# 					{
# 						"item_code": item_code,
# 						"item_name": f"{room.room_number} - {room.guest_name}",
# 						"description": _("Room {0} - {1} night(s) @ {2}/night").format(
# 							room.room_number, reservation.number_of_nights, room.rate_per_night
# 						),
# 						"qty": reservation.number_of_nights,
# 						"rate": room.rate_per_night,
# 						"amount": room.room_total,
# 					},
# 				)

# 				# ── DISCOUNT: remaining-balance proration ────────────────────────
# 				if reservation.discount_amount and reservation.subtotal:
# 					total_discount = flt(reservation.discount_amount, 2)

# 					# How much discount has already been applied across prior invoices
# 					already_applied = flt(
# 						frappe.db.sql(
# 							"""
# 							SELECT IFNULL(SUM(si.discount_amount), 0)
# 							FROM `tabSales Invoice` si
# 							INNER JOIN `tabHotel Front Desk Reservation Invoice` fdri
# 								ON fdri.sales_invoice = si.name
# 							WHERE fdri.parent = %s
# 							AND si.docstatus = 1
# 							""",
# 							(reservation_name,),
# 						)[0][0],
# 						2,
# 					)

# 					remaining_discount = flt(total_discount - already_applied, 2)

# 					if remaining_discount > 0:
# 						# Prorate remaining discount over rooms not yet invoiced
# 						# (current room is not yet in sales_invoices so it's included here)
# 						already_invoiced_rooms = {
# 							r.room_number for r in reservation.sales_invoices if r.sales_invoice
# 						}
# 						uninvoiced_rooms = [
# 							r for r in reservation.rooms if r.room_number not in already_invoiced_rooms
# 						]
# 						uninvoiced_subtotal = sum(flt(r.room_total) for r in uninvoiced_rooms)

# 						if uninvoiced_subtotal > 0:
# 							room_share = flt(room.room_total) / uninvoiced_subtotal
# 							room_discount = flt(remaining_discount * room_share, 2)

# 							if room_discount > 0:
# 								si.discount_amount = room_discount
# 								si.apply_discount_on = "Grand Total"

# 				si.flags.ignore_permissions = True
# 				si.insert()
# 				si.submit()
# 				room_invoice = si.name

# 				# Add invoice to child table immediately so next room in loop
# 				# sees this room as already invoiced when calculating its share
# 				reservation.reload()
# 				reservation.append(
# 					"sales_invoices",
# 					{
# 						# "room_number": room.room_number,
# 						# "guest_name": room.guest_name,
# 						# "sales_invoice": si.name,
# 						# "amount": room.room_total,
# 						# "created_at": now_datetime(),
# 						"room_number": room.room_number,
# 						"guest_name": room.guest_name,
# 						"sales_invoice": si.name,
# 						"room_total": flt(room.room_total, 2),  # gross before discount
# 						"discount_amount": flt(si.discount_amount, 2),  # discount applied to this room
# 						"amount": flt(si.grand_total, 2),  # actual amount charged
# 						"created_at": now_datetime(),
# 					},
# 				)
# 				reservation.flags.ignore_permissions = True
# 				reservation.flags.ignore_validate_update_after_submit = True
# 				reservation.save()

# 			except Exception as e:
# 				frappe.log_error(f"Invoice error for {room.room_number}: {str(e)}", "Check In Invoice Error")
# 				room_invoice = None

# 			# ── CREATE CHECK-IN ──────────────────────────────────────────────────
# 			check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
# 			expected_checkout = get_datetime(f"{reservation.to_date} {check_out_time}")

# 			checkin = frappe.get_doc(
# 				{
# 					"doctype": "Hotel Room Check In",
# 					"front_desk_reservation": reservation_name,
# 					"hotel_room_reservation": hrr,
# 					"reservation": hrr,
# 					"room_number": room.room_number,
# 					"room_type": room.room_type,
# 					"rate_type": getattr(room, "rate_type", None),
# 					"guest": room.hotel_guest,
# 					"guest_name": room.guest_name,
# 					"guest_email": room.guest_email or reservation.primary_guest_email,
# 					"guest_phone": room.guest_phone or reservation.primary_guest_phone,
# 					"customer": room.guest_customer or reservation.customer,
# 					"hotel_guest": room.hotel_guest,
# 					"check_in_datetime": check_in_datetime,
# 					"expected_check_out_datetime": expected_checkout,
# 					"number_of_nights": reservation.number_of_nights,
# 					"rate_per_night": room.rate_per_night,
# 					"rate_amount": room.rate_per_night,
# 					"total_amount": room.room_total,
# 					"status": "Checked In",
# 					"payment_status": "Pending",
# 					"check_in_notes": check_in_notes,
# 					"sales_invoice": room_invoice,
# 					"discount": reservation.discount_amount or 0,
# 					"discount_type": reservation.discount_type or "None",
# 					"total_charges": room.room_total,
# 				}
# 			)

# 			checkin.flags.ignore_permissions = True
# 			checkin.insert()
# 			checkin.submit()

# 			frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")

# 			checked_in_rooms.append(
# 				{
# 					"room_number": room.room_number,
# 					"guest_name": room.guest_name,
# 					"checkin_name": checkin.name,
# 					"invoice": room_invoice,
# 				}
# 			)

# 		# ── UPDATE FDR STATUS ────────────────────────────────────────────────────
# 		if checked_in_rooms:
# 			total_checkins = frappe.db.count(
# 				"Hotel Room Check In",
# 				{"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
# 			)

# 			if total_checkins >= len(reservation.rooms):
# 				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")
# 			elif total_checkins > 0 and reservation.status == "Confirmed":
# 				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")

# 		frappe.db.commit()

# 		message = _("{0} room(s) checked in").format(len(checked_in_rooms))
# 		if skipped_rooms:
# 			message += _(" | {0} skipped").format(len(skipped_rooms))

# 		return {
# 			"success": True,
# 			"message": message,
# 			"checked_in_rooms": checked_in_rooms,
# 			"skipped_rooms": skipped_rooms,
# 		}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Check In Selected Error")
# 		frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes="", discount_type="", discount=0):
# 	"""Check in selected rooms (creates individual invoices if no bulk invoice)"""
# 	try:
# 		if isinstance(room_indices, str):
# 			room_indices = json.loads(room_indices)

# 		discount = flt(discount)

# 		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

# 		if reservation.docstatus != 1:
# 			frappe.throw(_("Reservation must be submitted"))

# 		if reservation.sales_invoice:
# 			frappe.throw(
# 				_(
# 					"A bulk invoice ({0}) already exists for this reservation. "
# 					"Use 'Check In Rooms (Bulk Invoice)' instead to avoid duplicate invoicing."
# 				).format(reservation.sales_invoice)
# 			)

# 		# ── GUARD: block if all rooms already have individual invoices ────────
# 		invoiced_room_numbers = {r.room_number for r in reservation.sales_invoices if r.sales_invoice}
# 		all_room_numbers = {r.room_number for r in reservation.rooms}
# 		if invoiced_room_numbers >= all_room_numbers:
# 			frappe.throw(
# 				_(
# 					"All rooms already have individual invoices. "
# 					"No further invoicing is needed for this reservation."
# 				)
# 			)

# 		# ── CALCULATE TOTAL DISCOUNT AMOUNT FOR SELECTED ROOMS ────────────────
# 		# We need this upfront to prorate across selected rooms
# 		selected_rooms = []
# 		for idx in room_indices:
# 			idx = int(idx)
# 			for r in reservation.rooms:
# 				if r.idx == idx + 1:
# 					selected_rooms.append(r)
# 					break

# 		selected_subtotal = sum(flt(r.room_total) for r in selected_rooms)

# 		# Resolve discount amount from type
# 		if discount_type == "Percentage":
# 			total_discount_for_batch = flt((selected_subtotal * discount) / 100, 2)
# 		elif discount_type == "Fixed Amount":
# 			total_discount_for_batch = flt(discount, 2)
# 		else:
# 			total_discount_for_batch = 0

# 		# Validate fixed discount doesn't exceed selected rooms subtotal
# 		if total_discount_for_batch > selected_subtotal:
# 			frappe.throw(
# 				_("Discount amount ({0}) cannot exceed the total for selected rooms ({1})").format(
# 					total_discount_for_batch, selected_subtotal
# 				)
# 			)

# 		settings = frappe.get_single("Hotel Settings")
# 		check_in_time = now_datetime().strftime("%H:%M:%S")
# 		check_out_time = settings.default_check_out_time or "11:00:00"

# 		checked_in_rooms = []
# 		skipped_rooms = []

# 		for idx in room_indices:
# 			idx = int(idx)
# 			room = None

# 			for r in reservation.rooms:
# 				if r.idx == idx + 1:
# 					room = r
# 					break

# 			if not room:
# 				skipped_rooms.append({"idx": idx, "reason": "Not found"})
# 				continue

# 			# Check existing check-in
# 			existing = frappe.db.get_value(
# 				"Hotel Room Check In",
# 				{
# 					"front_desk_reservation": reservation_name,
# 					"room_number": room.room_number,
# 					"status": ["in", ["Draft", "Checked In"]],
# 				},
# 				"name",
# 			)

# 			if existing:
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "Already checked in"})
# 				continue

# 			if not room.guest_name or room.guest_name.startswith("Guest - Room"):
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "Guest name required"})
# 				continue

# 			# Get Hotel Room Reservation
# 			hrr = frappe.db.get_value(
# 				"Hotel Room Reservation",
# 				{"front_desk_reservation": reservation_name, "room_number": room.room_number, "docstatus": 1},
# 				"name",
# 			)

# 			if not hrr:
# 				skipped_rooms.append({"room_number": room.room_number, "reason": "No reservation"})
# 				continue

# 			# ── CREATE INDIVIDUAL INVOICE ─────────────────────────────────────
# 			room_invoice = None
# 			try:
# 				si = frappe.new_doc("Sales Invoice")
# 				si.customer = reservation.customer
# 				si.posting_date = nowdate()
# 				si.due_date = reservation.to_date
# 				si.po_no = f"{reservation.reservation_number} - {room.room_number}"

# 				try:
# 					item_code = create_or_get_item(
# 						room_number=room.room_number, room_type=room.room_type, erpnext_item=None
# 					)
# 				except Exception as item_error:
# 					frappe.log_error(f"Item creation failed: {str(item_error)}", "Invoice Item Error")
# 					item_code = room.room_type

# 				si.append(
# 					"items",
# 					{
# 						"item_code": item_code,
# 						"item_name": f"{room.room_number} - {room.guest_name}",
# 						"description": _("Room {0} - {1} night(s) @ {2}/night").format(
# 							room.room_number, reservation.number_of_nights, room.rate_per_night
# 						),
# 						"qty": reservation.number_of_nights,
# 						"rate": room.rate_per_night,
# 						"amount": room.room_total,
# 					},
# 				)

# 				# ── DISCOUNT: prorate batch discount across selected rooms ─────
# 				if total_discount_for_batch > 0 and selected_subtotal > 0:
# 					room_share = flt(room.room_total) / selected_subtotal
# 					room_discount = flt(total_discount_for_batch * room_share, 2)
# 					if room_discount > 0:
# 						si.discount_amount = room_discount
# 						si.apply_discount_on = "Grand Total"

# 				si.flags.ignore_permissions = True
# 				si.insert()
# 				si.submit()
# 				room_invoice = si.name

# 				# Reload so next room sees updated sales_invoices
# 				reservation.reload()
# 				reservation.append(
# 					"sales_invoices",
# 					{
# 						"room_number": room.room_number,
# 						"guest_name": room.guest_name,
# 						"sales_invoice": si.name,
# 						"room_total": flt(room.room_total, 2),
# 						"discount_amount": flt(si.discount_amount, 2),
# 						"amount": flt(si.grand_total, 2),
# 						"created_at": now_datetime(),
# 					},
# 				)
# 				reservation.flags.ignore_permissions = True
# 				reservation.flags.ignore_validate_update_after_submit = True
# 				reservation.save()

# 			except Exception as e:
# 				frappe.log_error(f"Invoice error for {room.room_number}: {str(e)}", "Check In Invoice Error")
# 				room_invoice = None

# 			# ── CREATE CHECK-IN ───────────────────────────────────────────────
# 			check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
# 			expected_checkout = get_datetime(f"{reservation.to_date} {check_out_time}")

# 			checkin = frappe.get_doc(
# 				{
# 					"doctype": "Hotel Room Check In",
# 					"front_desk_reservation": reservation_name,
# 					"hotel_room_reservation": hrr,
# 					"reservation": hrr,
# 					"room_number": room.room_number,
# 					"room_type": room.room_type,
# 					"rate_type": getattr(room, "rate_type", None),
# 					"guest": room.hotel_guest,
# 					"guest_name": room.guest_name,
# 					"guest_email": room.guest_email or reservation.primary_guest_email,
# 					"guest_phone": room.guest_phone or reservation.primary_guest_phone,
# 					"customer": room.guest_customer or reservation.customer,
# 					"hotel_guest": room.hotel_guest,
# 					"check_in_datetime": check_in_datetime,
# 					"expected_check_out_datetime": expected_checkout,
# 					"number_of_nights": reservation.number_of_nights,
# 					"rate_per_night": room.rate_per_night,
# 					"rate_amount": room.rate_per_night,
# 					"total_amount": room.room_total,
# 					"status": "Checked In",
# 					"payment_status": "Pending",
# 					"check_in_notes": check_in_notes,
# 					"sales_invoice": room_invoice,
# 					"discount": flt(si.discount_amount, 2) if room_invoice else 0,
# 					"discount_type": discount_type or "None",
# 					"total_charges": flt(si.grand_total, 2) if room_invoice else room.room_total,
# 				}
# 			)

# 			checkin.flags.ignore_permissions = True
# 			checkin.insert()
# 			checkin.submit()

# 			frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")

# 			checked_in_rooms.append(
# 				{
# 					"room_number": room.room_number,
# 					"guest_name": room.guest_name,
# 					"checkin_name": checkin.name,
# 					"invoice": room_invoice,
# 				}
# 			)

# 		# ── UPDATE FDR STATUS ─────────────────────────────────────────────────
# 		if checked_in_rooms:
# 			total_checkins = frappe.db.count(
# 				"Hotel Room Check In",
# 				{"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
# 			)

# 			if total_checkins >= len(reservation.rooms):
# 				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")
# 			elif total_checkins > 0 and reservation.status == "Confirmed":
# 				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")

# 		frappe.db.commit()

# 		message = _("{0} room(s) checked in").format(len(checked_in_rooms))
# 		if skipped_rooms:
# 			message += _(" | {0} skipped").format(len(skipped_rooms))

# 		return {
# 			"success": True,
# 			"message": message,
# 			"checked_in_rooms": checked_in_rooms,
# 			"skipped_rooms": skipped_rooms,
# 		}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Check In Selected Error")
# 		frappe.throw(_("Error: {0}").format(str(e)))

@frappe.whitelist()
def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
	"""Check in selected rooms (creates individual invoices if no bulk invoice)"""
	try:
		if isinstance(room_indices, str):
			room_indices = json.loads(room_indices)

		# room_indices is now a list of dicts:
		# [{"room_idx": 0, "discount_type": "Percentage", "discount": 10}, ...]

		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		if reservation.sales_invoice:
			frappe.throw(
				_(
					"A bulk invoice ({0}) already exists for this reservation. "
					"Use 'Check In Rooms (Bulk Invoice)' instead to avoid duplicate invoicing."
				).format(reservation.sales_invoice)
			)

		# ── GUARD: block if all rooms already have individual invoices ─────────
		invoiced_room_numbers = {r.room_number for r in reservation.sales_invoices if r.sales_invoice}
		all_room_numbers = {r.room_number for r in reservation.rooms}
		if invoiced_room_numbers >= all_room_numbers:
			frappe.throw(
				_(
					"All rooms already have individual invoices. "
					"No further invoicing is needed for this reservation."
				)
			)

		settings = frappe.get_single("Hotel Settings")
		check_in_time = now_datetime().strftime("%H:%M:%S")
		check_out_time = settings.default_check_out_time or "11:00:00"

		checked_in_rooms = []
		skipped_rooms = []

		for item in room_indices:
			idx = int(item["room_idx"])
			discount_type = item.get("discount_type", "") or ""
			discount = flt(item.get("discount", 0))

			# ── FIND ROOM ─────────────────────────────────────────────────────
			room = None
			for r in reservation.rooms:
				if r.idx == idx + 1:
					room = r
					break

			if not room:
				skipped_rooms.append({"idx": idx, "reason": "Not found"})
				continue

			# ── CHECK EXISTING CHECK-IN ───────────────────────────────────────
			existing = frappe.db.get_value(
				"Hotel Room Check In",
				{
					"front_desk_reservation": reservation_name,
					"room_number": room.room_number,
					"status": ["in", ["Draft", "Checked In"]],
				},
				"name",
			)

			if existing:
				skipped_rooms.append({"room_number": room.room_number, "reason": "Already checked in"})
				continue

			if not room.guest_name or room.guest_name.startswith("Guest - Room"):
				skipped_rooms.append({"room_number": room.room_number, "reason": "Guest name required"})
				continue

			# ── GET HOTEL ROOM RESERVATION ────────────────────────────────────
			hrr = frappe.db.get_value(
				"Hotel Room Reservation",
				{"front_desk_reservation": reservation_name, "room_number": room.room_number, "docstatus": 1},
				"name",
			)

			if not hrr:
				skipped_rooms.append({"room_number": room.room_number, "reason": "No reservation"})
				continue

			# ── CALCULATE THIS ROOM'S DISCOUNT ───────────────────────────────
			if discount_type == "Percentage":
				room_discount_amount = flt((flt(room.room_total) * discount) / 100, 2)
			elif discount_type == "Fixed Amount":
				room_discount_amount = flt(discount, 2)
			else:
				room_discount_amount = 0

			# Safety check — discount cannot exceed room total
			if room_discount_amount > flt(room.room_total):
				skipped_rooms.append(
					{
						"room_number": room.room_number,
						"reason": f"Discount ({room_discount_amount}) exceeds room total ({room.room_total})",
					}
				)
				continue

			# ── CREATE INDIVIDUAL INVOICE ─────────────────────────────────────
			room_invoice = None
			si = None
			try:
				si = frappe.new_doc("Sales Invoice")
				si.customer = reservation.customer
				si.posting_date = nowdate()
				si.due_date = reservation.to_date
				si.po_no = f"{reservation.reservation_number} - {room.room_number}"

				try:
					item_code = create_or_get_item(
						room_number=room.room_number, room_type=room.room_type, erpnext_item=None
					)
				except Exception as item_error:
					frappe.log_error(f"Item creation failed: {str(item_error)}", "Invoice Item Error")
					item_code = room.room_type

				si.append(
					"items",
					{
						"item_code": item_code,
						"item_name": f"{room.room_number} - {room.guest_name}",
						"description": _("Room {0} - {1} night(s) @ {2}/night").format(
							room.room_number, reservation.number_of_nights, room.rate_per_night
						),
						"qty": reservation.number_of_nights,
						"rate": room.rate_per_night,
						"amount": room.room_total,
					},
				)

				# ── APPLY DISCOUNT DIRECTLY — NO PRORATION ───────────────────
				if room_discount_amount > 0:
					si.discount_amount = room_discount_amount
					si.apply_discount_on = "Grand Total"

				si.flags.ignore_permissions = True
				si.insert()
				si.submit()
				room_invoice = si.name

				# ── UPDATE SALES INVOICES CHILD TABLE ────────────────────────
				# Reload first so next iteration sees fresh sales_invoices
				reservation.reload()
				reservation.append(
					"sales_invoices",
					{
						"room_number": room.room_number,
						"guest_name": room.guest_name,
						"sales_invoice": si.name,
						"room_total": flt(room.room_total, 2),
						"discount_type": discount_type or "",
						"discount_amount": flt(si.discount_amount, 2),
						"amount": flt(si.grand_total, 2),
						"created_at": now_datetime(),
					},
				)
				reservation.flags.ignore_permissions = True
				reservation.flags.ignore_validate_update_after_submit = True
				reservation.save()

			except Exception as e:
				frappe.log_error(f"Invoice error for {room.room_number}: {str(e)}", "Check In Invoice Error")
				room_invoice = None

			# ── CREATE CHECK-IN ───────────────────────────────────────────────
			check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
			expected_checkout = get_datetime(f"{reservation.to_date} {check_out_time}")

			checkin = frappe.get_doc(
				{
					"doctype": "Hotel Room Check In",
					"front_desk_reservation": reservation_name,
					"hotel_room_reservation": hrr,
					"reservation": hrr,
					"room_number": room.room_number,
					"room_type": room.room_type,
					"rate_type": getattr(room, "rate_type", None),
					"guest": room.hotel_guest,
					"guest_name": room.guest_name,
					"guest_email": room.guest_email or reservation.primary_guest_email,
					"guest_phone": room.guest_phone or reservation.primary_guest_phone,
					"customer": room.guest_customer or reservation.customer,
					"hotel_guest": room.hotel_guest,
					"check_in_datetime": check_in_datetime,
					"expected_check_out_datetime": expected_checkout,
					"number_of_nights": reservation.number_of_nights,
					"rate_per_night": room.rate_per_night,
					"rate_amount": room.rate_per_night,
					"total_amount": room.room_total,
					"status": "Checked In",
					"payment_status": "Pending",
					"check_in_notes": check_in_notes,
					"sales_invoice": room_invoice,
					"discount": discount
					if discount_type == "Percentage"
					else flt(si.discount_amount, 2)
					if si
					else 0,
					"discount_type": discount_type or "None",
					"total_charges": flt(si.grand_total, 2) if si else flt(room.room_total, 2),
				}
			)

			checkin.flags.ignore_permissions = True
			checkin.insert()
			checkin.submit()

			frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")

			checked_in_rooms.append(
				{
					"room_number": room.room_number,
					"guest_name": room.guest_name,
					"checkin_name": checkin.name,
					"invoice": room_invoice,
				}
			)

		# ── UPDATE FDR STATUS ─────────────────────────────────────────────────
		if checked_in_rooms:
			total_checkins = frappe.db.count(
				"Hotel Room Check In",
				{"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
			)

			if total_checkins >= len(reservation.rooms):
				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")
			elif total_checkins > 0 and reservation.status == "Confirmed":
				frappe.db.set_value("Hotel Front Desk Reservation", reservation_name, "status", "Checked In")

		frappe.db.commit()

		message = _("{0} room(s) checked in").format(len(checked_in_rooms))
		if skipped_rooms:
			message += _(" | {0} skipped").format(len(skipped_rooms))

		return {
			"success": True,
			"message": message,
			"checked_in_rooms": checked_in_rooms,
			"skipped_rooms": skipped_rooms,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Check In Selected Error")
		frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def check_in_all_rooms(reservation_name, check_in_notes=""):
	"""Check in all rooms (requires bulk invoice)"""
	try:
		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		if not reservation.sales_invoice:
			frappe.throw(_("Create bulk invoice first"))

		# Get all room indices
		room_indices = [r.idx - 1 for r in reservation.rooms]

		return check_in_rooms_in_bulk_invoice(reservation_name, room_indices, check_in_notes)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Check In All Error")
		frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def check_in_reservation(reservation_name, check_in_notes="", create_reservations=False):
	"""Alias for check_in_all_rooms"""
	return check_in_all_rooms(reservation_name, check_in_notes)


@frappe.whitelist()
def update_guest_names(reservation_name, guest_updates):
	"""Update guest names"""
	try:
		if isinstance(guest_updates, str):
			guest_updates = json.loads(guest_updates)

		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		updated = 0

		for update in guest_updates:
			room_idx = update.get("room_idx")
			guest_name = update.get("guest_name")

			if room_idx is None or not guest_name:
				continue

			room = reservation.rooms[room_idx]

			frappe.db.set_value(
				"Front Desk Reservation Room",
				{"parent": reservation_name, "room_number": room.room_number},
				{
					"guest_name": guest_name,
					"guest_email": update.get("guest_email", ""),
					"guest_phone": update.get("guest_phone", ""),
				},
				update_modified=False,
			)
			updated += 1

			# Update HRR if exists
			hrr = frappe.db.get_value(
				"Hotel Room Reservation",
				{"front_desk_reservation": reservation_name, "room_number": room.room_number},
				"name",
			)
			if hrr:
				frappe.db.set_value("Hotel Room Reservation", hrr, "guest_name", guest_name)

		frappe.db.commit()

		return {"success": True, "message": _("{0} guest name(s) updated").format(updated)}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Update Guest Names Error")
		frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def edit_guest_details(reservation_name, room_idx, guest_name, guest_email, guest_phone, room_number):
	"""Edit guest details (no editing after check-in)"""
	try:
		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		# Check if checked in
		existing = frappe.db.get_value(
			"Hotel Room Check In",
			{
				"front_desk_reservation": reservation_name,
				"room_number": room_number,
				"status": ["in", ["Draft", "Checked In"]],
			},
			"name",
		)

		if existing:
			frappe.throw(_("Cannot edit after check-in"))

		# Get/create customer
		customer = reservation.get_or_create_customer(guest_name, guest_email, guest_phone)

		# Get/create hotel guest
		room_idx = int(room_idx)
		room = reservation.rooms[room_idx]
		room.guest_name = guest_name
		room.guest_email = guest_email
		room.guest_phone = guest_phone
		hotel_guest = reservation.get_or_create_hotel_guest(room, customer)

		# Update room
		frappe.db.set_value(
			"Front Desk Reservation Room",
			{"parent": reservation_name, "room_number": room_number},
			{
				"guest_name": guest_name,
				"guest_email": guest_email,
				"guest_phone": guest_phone,
				"guest_customer": customer,
				"hotel_guest": hotel_guest,
			},
			update_modified=False,
		)

		# Update HRR
		hrr = frappe.db.get_value(
			"Hotel Room Reservation",
			{"front_desk_reservation": reservation_name, "room_number": room_number},
			"name",
		)
		if hrr:
			frappe.db.set_value(
				"Hotel Room Reservation", hrr, {"guest_name": guest_name, "customer": customer}
			)

		frappe.db.commit()

		return {
			"success": True,
			"message": _("Guest details updated for {0}").format(room_number),
			"customer": customer,
			"hotel_guest": hotel_guest,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Edit Guest Error")
		frappe.throw(_("Error: {0}").format(str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# STAY ADJUSTMENT
# ═══════════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_default_check_out_time():
	"""Get default checkout time"""
	try:
		settings = frappe.get_single("Hotel Settings")
		return settings.default_check_out_time or "12:00:00"
	except:
		return "12:00:00"


@frappe.whitelist()
def get_reservation_status_info(reservation_name):
	"""Get status info for adjustment"""
	try:
		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			return {"valid": False, "message": "Not submitted"}

		checkins = frappe.get_all(
			"Hotel Room Check In",
			filters={"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
			fields=["name", "room_number", "status"],
		)

		return {
			"valid": True,
			"is_checked_in": len(checkins) > 0,
			"checked_in_count": len(checkins),
			"total_rooms": len(reservation.rooms),
			"current_checkin": reservation.from_date,
			"current_checkout": reservation.to_date,
			"current_nights": reservation.number_of_nights,
			"has_invoice": bool(reservation.sales_invoice),
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Status Error")
		return {"valid": False, "message": str(e)}


def _invoice_has_payment_activity(invoice):
	if not invoice:
		return False

	if flt(invoice.outstanding_amount) < flt(invoice.grand_total):
		return True

	return bool(
		frappe.db.sql(
			"""
			SELECT per.name
			FROM `tabPayment Entry Reference` per
			INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
			WHERE per.reference_doctype = 'Sales Invoice'
				AND per.reference_name = %s
				AND pe.docstatus = 1
			LIMIT 1
			""",
			(invoice.name,),
		)
	)


def _append_adjustment_row(
	reservation,
	adjustment_type,
	invoice_name,
	amount,
	night_diff,
	old_checkout,
	new_checkout,
	old_nights,
	new_nights,
	reason,
):
	reservation.append(
		"adjustment_invoices",
		{
			"adjustment_type": adjustment_type,
			"adjustment_nvoice": invoice_name,
			"amount": abs(amount),
			"previous_checkout_datetime": str(old_checkout),
			"new_checkout_datetime": str(new_checkout),
			"previous_number_of_nights": old_nights,
			"new_number_of_nights": new_nights,
			"adjustment_date": now_datetime(),
			"reason": reason,
		},
	)


@frappe.whitelist()
def adjust_front_desk_reservation(reservation_name, new_checkout_date, new_checkout_time, new_discount=0):
	"""Adjust stay (extension or reduction)"""
	try:
		new_discount = float(new_discount) if new_discount else 0

		reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)

		if reservation.docstatus != 1:
			frappe.throw(_("Reservation must be submitted"))

		# Get active check-ins
		checkins = frappe.get_all(
			"Hotel Room Check In",
			filters={"front_desk_reservation": reservation_name, "status": ["in", ["Draft", "Checked In"]]},
			fields=["name", "room_number"],
		)

		is_checked_in = len(checkins) > 0

		# Parse dates
		new_checkout_dt = get_datetime(f"{new_checkout_date} {new_checkout_time}")
		current_checkout_dt = get_datetime(f"{reservation.to_date} 12:00:00")
		checkin_dt = get_datetime(f"{reservation.from_date} 00:00:00")
		now_dt = get_datetime(now_datetime())

		# Validate
		if new_checkout_dt <= checkin_dt:
			frappe.throw(_("Checkout must be after check-in"))

		if is_checked_in and new_checkout_dt < now_dt:
			frappe.throw(_("Checkout cannot be in past"))

		if new_checkout_dt == current_checkout_dt:
			frappe.throw(_("No change"))

		is_extension = new_checkout_dt > current_checkout_dt

		# Calculate
		old_checkout = getdate(reservation.to_date)
		new_checkout = getdate(new_checkout_date)
		checkin_date = getdate(reservation.from_date)

		old_nights = date_diff(old_checkout, checkin_date)
		new_nights = date_diff(new_checkout, checkin_date)
		night_diff = new_nights - old_nights

		if new_nights < 1:
			frappe.throw(_("Minimum 1 night"))

		old_subtotal = float(reservation.subtotal or 0)
		new_subtotal = 0
		room_changes = []

		for room in reservation.rooms:
			rate = float(room.rate_per_night or 0)
			new_total = rate * new_nights
			old_total = float(room.room_total or 0)

			room_changes.append(
				{
					"room_number": room.room_number,
					"room_type": room.room_type,
					"rate_per_night": rate,
					"old_total": old_total,
					"new_total": new_total,
					"change": new_total - old_total,
				}
			)

			new_subtotal += new_total

		amount_change = new_subtotal - old_subtotal
		new_total = new_subtotal - new_discount

		original_invoice = (
			frappe.get_doc("Sales Invoice", reservation.sales_invoice) if reservation.sales_invoice else None
		)
		has_payment_activity = _invoice_has_payment_activity(original_invoice)

		# Handle invoicing
		invoice_name = None
		credit_note = None
		recreated_invoice = None

		if reservation.sales_invoice and not has_payment_activity and reservation.customer:
			if original_invoice and original_invoice.docstatus == 1:
				original_invoice.flags.ignore_permissions = True
				original_invoice.cancel()

			si = frappe.new_doc("Sales Invoice")
			si.customer = reservation.customer
			si.posting_date = nowdate()
			si.due_date = new_checkout_date
			si.po_no = reservation.reservation_number
			si.remarks = _("Recreated after reservation adjustment from {0} to {1} night(s)").format(
				old_nights, new_nights
			)

			for rc in room_changes:
				try:
					item_code = create_or_get_item(
						room_number=rc["room_number"],
						room_type=rc["room_type"],
						erpnext_item=None,
					)
				except Exception as item_error:
					frappe.log_error(
						f"Item creation failed: {str(item_error)}", "Adjustment Invoice Item Error"
					)
					item_code = rc["room_number"]

				si.append(
					"items",
					{
						"item_code": item_code,
						"item_name": f"{rc['room_number']} - Adjusted Stay",
						"description": _("Room {0} ({1}) - {2} night(s) @ {3}/night").format(
							rc["room_number"], rc["room_type"], new_nights, rc["rate_per_night"]
						),
						"qty": new_nights,
						"rate": rc["rate_per_night"],
						"amount": rc["new_total"],
					},
				)

			if new_discount:
				si.discount_amount = new_discount

			si.flags.ignore_permissions = True
			si.insert()
			si.submit()
			recreated_invoice = si.name
			invoice_name = si.name

		elif is_extension and amount_change > 0 and reservation.customer:
			# Extension invoice
			si = frappe.new_doc("Sales Invoice")
			si.customer = reservation.customer
			si.posting_date = nowdate()
			si.due_date = new_checkout_date
			si.po_no = f"{reservation.reservation_number} - Extension"
			si.remarks = _("Extension for {0} night(s)").format(abs(night_diff))

			for rc in room_changes:
				if rc["change"] > 0:
					try:
						item_code = create_or_get_item(
							room_number=rc["room_number"],
							room_type=rc["room_type"],
							erpnext_item=None,
						)
					except Exception as item_error:
						frappe.log_error(
							f"Item creation failed: {str(item_error)}", "Adjustment Invoice Item Error"
						)
						# Fallback to room number
						item_code = rc["room_number"]

					si.append(
						"items",
						{
							"item_code": item_code,
							"item_name": f"{rc['room_number']} - Extension",
							"description": _("{0} - {1} nights @ {2}").format(
								rc["room_number"], abs(night_diff), rc["rate_per_night"]
							),
							"qty": abs(night_diff),
							"rate": rc["rate_per_night"],
							"amount": abs(rc["change"]),
						},
					)

			if si.items:
				si.flags.ignore_permissions = True
				si.insert()
				si.submit()
				invoice_name = si.name

		elif not is_extension and amount_change < 0 and reservation.customer:
			# Credit note
			cn = frappe.new_doc("Sales Invoice")
			cn.customer = reservation.customer
			cn.posting_date = nowdate()
			cn.due_date = nowdate()
			cn.is_return = 1
			if reservation.sales_invoice:
				cn.return_against = reservation.sales_invoice
			cn.po_no = f"{reservation.reservation_number} - Early Checkout"
			cn.remarks = _("Reduction by {0} night(s)").format(abs(night_diff))

			for rc in room_changes:
				try:
					item_code = create_or_get_item(
						room_number=rc["room_number"],
						room_type=rc["room_type"],
						erpnext_item=None,
					)
				except Exception as item_error:
					frappe.log_error(
						f"Item creation failed: {str(item_error)}", "Adjustment Invoice Item Error"
					)
					# Fallback to room number
					item_code = rc["room_number"]

				cn.append(
					"items",
					{
						"item_code": item_code,
						"item_name": f"{rc['room_number']} - Refund",
						"description": _("{0} - {1} nights refund").format(
							rc["room_number"], abs(night_diff)
						),
						"qty": -abs(night_diff),
						"rate": rc["rate_per_night"],
					},
				)

			if cn.items:
				cn.flags.ignore_permissions = True
				cn.insert()
				cn.submit()
				credit_note = cn.name

		# Update reservation
		update_values = {
			"to_date": new_checkout_date,
			"number_of_nights": new_nights,
			"subtotal": new_subtotal,
			"discount_amount": new_discount,
			"total_amount": new_total,
		}
		if recreated_invoice:
			update_values["sales_invoice"] = recreated_invoice

		frappe.db.set_value(
			"Hotel Front Desk Reservation",
			reservation_name,
			update_values,
			update_modified=False,
		)

		# Update rooms
		for idx, room in enumerate(reservation.rooms):
			frappe.db.set_value(
				"Front Desk Reservation Room",
				{"parent": reservation_name, "room_number": room.room_number},
				{"room_total": room_changes[idx]["new_total"], "number_of_nights": new_nights},
				update_modified=False,
			)

		# Update HRRs
		hrrs = frappe.get_all(
			"Hotel Room Reservation",
			filters={"front_desk_reservation": reservation_name, "docstatus": 1},
			pluck="name",
		)

		for hrr in hrrs:
			hrr_values = {"to_date": new_checkout_date, "number_of_nights": new_nights}
			if recreated_invoice:
				hrr_values["sales_invoice"] = recreated_invoice
			frappe.db.set_value(
				"Hotel Room Reservation",
				hrr,
				hrr_values,
				update_modified=False,
			)

		# Update check-ins
		new_checkout_str = f"{new_checkout_date} {new_checkout_time}"
		for checkin in checkins:
			ci = frappe.get_doc("Hotel Room Check In", checkin.name)
			ci.expected_check_out_datetime = get_datetime(new_checkout_str)
			ci.number_of_nights = new_nights
			ci.flags.ignore_permissions = True
			ci.save()

		# Persist parent doc rows after db_set updates
		reservation.reload()
		if recreated_invoice:
			reservation.sales_invoice = recreated_invoice
			reservation.set("sales_invoices", [])
			for room in reservation.rooms:
				reservation.append(
					"sales_invoices",
					{
						"room_number": room.room_number,
						"guest_name": room.guest_name,
						"sales_invoice": recreated_invoice,
						"amount": room.room_total,
						"created_at": now_datetime(),
					},
				)
			_append_adjustment_row(
				reservation,
				"Extension" if is_extension else "Reduction",
				recreated_invoice,
				amount_change,
				night_diff,
				old_checkout,
				new_checkout,
				old_nights,
				new_nights,
				f"Invoice recreated after reservation adjustment from {old_nights} to {new_nights} night(s)",
			)
		elif invoice_name:
			_append_adjustment_row(
				reservation,
				"Extension",
				invoice_name,
				amount_change,
				night_diff,
				old_checkout,
				new_checkout,
				old_nights,
				new_nights,
				f"Extension for {abs(night_diff)} night(s)",
			)
		elif credit_note:
			_append_adjustment_row(
				reservation,
				"Reduction",
				credit_note,
				amount_change,
				night_diff,
				old_checkout,
				new_checkout,
				old_nights,
				new_nights,
				f"Reduction by {abs(night_diff)} night(s)",
			)

		reservation.flags.ignore_permissions = True
		reservation.flags.ignore_validate_update_after_submit = True
		reservation.save()

		frappe.db.commit()

		adjustment_type = "Extension" if is_extension else "Reduction"

		return {
			"success": True,
			"message": _("{0} completed").format(adjustment_type),
			"adjustment_type": adjustment_type,
			"is_extension": is_extension,
			"old_checkout": format_datetime(current_checkout_dt),
			"new_checkout": format_datetime(new_checkout_dt),
			"old_nights": old_nights,
			"new_nights": new_nights,
			"night_difference": night_diff,
			"amount_change": float(amount_change),
			"recreated_invoice": recreated_invoice,
			"additional_invoice": invoice_name,
			"credit_note": credit_note,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Adjust Reservation Error")
		frappe.throw(_("Error: {0}").format(str(e)))
