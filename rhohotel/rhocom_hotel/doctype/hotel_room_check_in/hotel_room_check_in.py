# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _, msgprint, utils
from frappe.model.document import Document
from datetime import datetime, time
from frappe.utils import get_datetime, now_datetime
from frappe.utils import nowdate, getdate, date_diff, fmt_money
from rhohotel.api import get_room_rate
from frappe.utils import flt
from datetime import datetime, time


class HotelRoomCheckIn(Document):
	def validate(self):
		self.validate_reservation()
		self.validate_rate_amount()
		self.validate_discount()
		self.validate_room()
		self.set_checkout_time()
		self.validate_dates()
		self.calculate_total_charges()
		self.validate_rate_and_session()

	def set_checkout_time(self):
		"""Set the time part of expected_check_out_datetime from Hotel Settings."""
		if self.expected_check_out_datetime and not self.late_checkout:
			hotel_settings = frappe.get_single("Hotel Settings")
			if hotel_settings.default_check_out_time:
				expected_checkout_date = get_datetime(self.expected_check_out_datetime).date()
				self.expected_check_out_datetime = get_datetime(
					f"{expected_checkout_date} {hotel_settings.default_check_out_time}"
				)

	def calculate_total_charges(self):
		"""Calculate total charges based on number of nights and rate amount."""
		if self.check_in_datetime and self.expected_check_out_datetime and self.rate_amount:
			check_in_dt = get_datetime(self.check_in_datetime)
			expected_checkout_dt = get_datetime(self.expected_check_out_datetime)
			number_of_nights = utils.date_diff(expected_checkout_dt.date(), check_in_dt.date())

			if self.discount:
				base_amount = number_of_nights * self.rate_amount

				if self.discount_type == "Percentage":
					self.total_charges = base_amount * (1 - (self.discount / 100))
				else:
					self.total_charges = base_amount - self.discount

				# Ensure total is not negative
				if self.total_charges < 0:
					self.total_charges = 0
			else:
				self.total_charges = number_of_nights * self.rate_amount

	def validate_rate_amount(self):
		if self.rate_amount <= 0:
			frappe.throw(_("Rate amount must be greater than zero"))

	def validate_rate_and_session(self):
		tariff = frappe.get_all("Hotel Room Tariff", filters={"room_type": self.room_type})
		if not tariff:
			frappe.throw(_("No valid tariff found for Room Type {0}").format(self.room_type))

	def set_rate_amount(self):
		tariff = frappe.get_all(
			"Hotel Room Tariff",
			filters={"room_type": self.room_type, "rate_type": self.rate_type, "is_active": 1},
			fields=["amount"],
			limit=1,
		)

		if not tariff:
			tariff = frappe.get_all(
				"Hotel Room Tariff",
				filters={"room_type": self.room_type, "is_active": 1},
				fields=["amount"],
				limit=1,
			)

		if tariff:
			self.rate_amount = tariff[0].amount

	def validate_reservation(self):
		if not self.reservation:
			return

		if not frappe.db.exists("Hotel Room Reservation", self.reservation):
			frappe.throw(_("Reservation {0} does not exist").format(self.reservation))

		reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)

		# ensure the room is vacant
		room = frappe.get_doc("Hotel Room", self.room_number)
		if room.status != "Vacant":
			frappe.throw(_("Room {0} is not vacant").format(self.room_number))

		check_in_date = get_datetime(self.check_in_datetime).date()
		if check_in_date < reservation.from_date:
			frappe.throw(_("Check-in date cannot be before reservation start date"))
		if check_in_date > reservation.to_date:
			frappe.throw(_("Check-in date cannot be after reservation end date"))

		existing = frappe.get_all(
			"Hotel Room Check In",
			filters={
				"reservation": self.reservation,
				"docstatus": 1,
				"status": ["in", ["Draft", "Checked In"]],
			},
		)

		if existing and self.is_new():
			frappe.throw(_("Reservation {0} is already checked in").format(self.reservation))

	def validate_room(self):
		if not frappe.db.exists("Hotel Room", self.room_number):
			frappe.throw(_("Room {0} does not exist").format(self.room_number))

		room = frappe.get_doc("Hotel Room", self.room_number)

		if room.status != "Vacant":
			frappe.throw(_("Room {0} is not vacant").format(self.room_number))

		# Skip for front desk override
		if self.front_desk_reservation:
			return

		# Normalize datetime
		if isinstance(self.check_in_datetime, str):
			self.check_in_datetime = datetime.strptime(
				self.check_in_datetime, "%Y-%m-%d %H:%M:%S"
			)

		check_in = self.check_in_datetime
		check_out = self.expected_check_out_datetime

		if not check_out:
			frappe.throw("Check-out date is required for reservation validation.")

		# 🔥 Correct overlap logic
		reservations = frappe.get_all(
			"Hotel Room Reservation",
			filters={
				"name": ["!=", self.reservation],
				"room_number": self.room_number,
				"guest_name": ["!=", self.name],
				"docstatus": ["!=", 2],
				"status": ["in", ["Booked", "Confirmed", "Pending Payment", "Checked-In", "Draft"]],
				"from_date": ["<=", check_out],
				"to_date": [">=", check_in],
			},
			fields=["name", "from_date", "to_date", "guest_name"],
		)

		for res in reservations:
			# ✅ Allow if SAME guest and SAME dates
			if (
				res.guest_name == self.guest and
				str(res.from_date) == str(check_in) and
				str(res.to_date) == str(check_out)
			):
				continue  # ✅ valid reservation → allow

			# ❌ Otherwise block
			frappe.log_error(
				title="Room Reservation Conflict Debug",
				message=(
					f"Room: {self.room_number}\n"
					f"Check-in: {check_in}\n"
					f"Check-out: {check_out}\n"
					f"Guest: {self.guest}\n"
					f"Conflicting Reservation:\n{frappe.as_json(res)}"
				),
			)

			frappe.throw(
				_("Room {0} is already reserved from {1} to {2} by {3}").format(
					self.room_number,
					res.from_date,
					res.to_date,
					res.guest_name
				)
			)

	def validate_dates(self):
		if get_datetime(self.check_in_datetime) > get_datetime(self.expected_check_out_datetime):
			frappe.throw(_("Check-in time cannot be after expected check-out time"))

	def on_submit(self):
		self.status = "Checked In"
		self.db_set("status", "Checked In")

		self.update_room_status("Occupied")
		self.update_room()
		self.make_sales_invoice()

		if self.reservation:
			frappe.db.set_value("Hotel Room Reservation", self.reservation, "status", "Completed")

		frappe.publish_realtime("rhohotel_front_desk_update")

	def on_cancel(self):
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")

		self.update_room_status("Vacant")
		frappe.publish_realtime("rhohotel_front_desk_update")

	def on_load(self):
		pass

	def update_room_status(self, status):
		frappe.db.set_value("Hotel Room", self.room_number, "status", status)

	def update_room(self):
		room = frappe.get_doc("Hotel Room", self.room_number)
		room.current_guest = self.guest
		room.current_check_in = self.name
		room.save(ignore_permissions=True)

	def validate_discount(self):
		if self.discount_type == "None" or not self.discount_type:
			# If discount_type is "None" or not set, ensure discount is 0
			self.discount = 0
			return

		# Handle None discount value
		if self.discount is None:
			self.discount = 0

		if self.discount_type == "Percentage":
			if not (0 <= self.discount <= 100):
				frappe.throw(_("Discount percentage must be between 0 and 100"))
		elif self.discount_type in ["Amount", "Fixed Amount"]:
			if self.discount < 0:
				frappe.throw(_("Discount amount cannot be negative"))

	def make_sales_invoice(self):
		if self.reservation:
			reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)

			if getattr(reservation, "reservation_type", None) == "Corporate":
				return

			if reservation.sales_invoice:
				invoice = frappe.get_doc("Sales Invoice", reservation.sales_invoice)
				invoice.db_set("custom_hotel_room_check_in", self.name)

				payments = frappe.db.get_all(
					"Payment Entry Reference",
					filters={
						"reference_doctype": "Sales Invoice",
						"reference_name": reservation.sales_invoice,
					},
					fields=["parent"],
				)

				for payment in payments:
					payment_doc = frappe.get_doc("Payment Entry", payment.parent)
					payment_doc.db_set("custom_hotel_room_check_in", self.name)
					payment_doc.save(ignore_permissions=True)

				return

		room_doc = frappe.get_doc("Hotel Room", self.room_number)
		customer = frappe.get_value("Hotel Guest", self.guest, "customer")

		si = frappe.new_doc("Sales Invoice")
		si.customer = customer
		si.custom_hotel_room_check_in = self.name
		si.due_date = get_datetime(self.expected_check_out_datetime).date()
		si.posting_date = get_datetime(self.check_in_datetime).date()

		si.append(
			"items",
			{
				"item_code": room_doc.erpnext_item,
				"rate": self.rate_amount,
				"qty": self.number_of_nights,
				"amount": self.total_charges,
				"description": _("Room charge for {0} from {1} to {2}").format(
					self.room_number,
					get_datetime(self.check_in_datetime).date(),
					get_datetime(self.expected_check_out_datetime).date(),
				),
			},
		)

		si.set_taxes()

		if self.discount:
			if self.discount_type == "Percentage":
				si.additional_discount_percentage = self.discount
			else:
				si.discount_amount = self.discount

		si.insert(ignore_permissions=True)
		si.submit()


@frappe.whitelist()
def set_checkin_invoice_list(self):
	"""Fetch all linked invoices for a given check-in"""
	invoices = []

	# Get Sales Invoices
	sales_invoices = frappe.get_all(
		"Sales Invoice",
		filters={"custom_hotel_room_check_in": self.name},
		fields=["name", "grand_total", "outstanding_amount"],
	)

	for inv in sales_invoices:
		invoices.append(
			{
				"invoice_type": "Sales Invoice",
				"invoice": inv.name,
				"amount": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount,
			}
		)

	# # Get POS Invoices
	pos_invoices = frappe.get_all(
		"POS Invoice",
		filters={"custom_hotel_room_check_in": self.name},
		fields=["name", "grand_total", "outstanding_amount"],
	)

	for inv in pos_invoices:
		invoices.append(
			{
				"invoice_type": "POS Invoice",
				"invoice": inv.name,
				"amount": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount,
			}
		)

	return invoices


@frappe.whitelist()
def get_linked_documents(check_in):
	"""Get linked invoices, payments, sessions, and journal entries for a check-in."""

	check_in_doc = frappe.get_doc("Hotel Room Check In", check_in)

	# -----------------------------
	# Get POS Invoices
	# -----------------------------
	pos_invoices = frappe.get_all(
		"POS Invoice",
		filters={"custom_hotel_room_check_in": check_in_doc.name, "status": "Unpaid"},
		fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount", "pos_profile"],
	)

	for inv in pos_invoices:
		inv["invoice_type"] = "POS Invoice"

	# -----------------------------
	# Get Sales Invoices
	# -----------------------------
	sales_invoices = frappe.get_all(
		"Sales Invoice",
		filters={"custom_hotel_room_check_in": check_in_doc.name, "status": ["!=", "Cancelled"]},
		fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount"],
	)

	for inv in sales_invoices:
		inv["invoice_type"] = "Room Invoice"
		inv["pos_profile"] = None  # keep consistent structure

	# Merge invoices
	invoices = sales_invoices + pos_invoices

	# -----------------------------
	# Get Journal Entries
	# -----------------------------
	journal_entries = frappe.get_all(
		"Journal Entry",
		filters={"custom_hotel_room_check_in": check_in_doc.name},
		fields=["name", "voucher_type", "posting_date", "remark as remarks"],
	)

	# For totals we need debit/credit → lookup child table
	for je in journal_entries:
		accounts = frappe.get_all(
			"Journal Entry Account", filters={"parent": je["name"]}, fields=["debit", "credit", "party"]
		)

		total_debit = sum(a.debit or 0 for a in accounts)
		total_credit = sum(a.credit or 0 for a in accounts)
		party = None
		for a in accounts:
			if a.party:
				party = a.party
				break

		je["total_debit"] = total_debit
		je["total_credit"] = total_credit
		je["party"] = party

	# -----------------------------
	# Get Payment Entries
	# -----------------------------
	payments = frappe.get_all(
		"Payment Entry",
		filters={"custom_hotel_room_check_in": check_in_doc.name, "payment_type": "Receive", "docstatus": 1},
		fields=["name", "party", "posting_date", "paid_amount"],
	)

	# -----------------------------
	# Get Payment Sessions
	# -----------------------------
	payment_sessions = frappe.get_all(
		"Payment Session",
		filters={"hotel_room_check_in": check_in_doc.name, "status": "Paid"},
		fields=["name", "posting_date", "total_amount"],
	)

	# -----------------------------
	# Totals
	# -----------------------------
	total_outstanding_amount = sum(inv.outstanding_amount or 0 for inv in invoices)
	total_charges = sum(inv.grand_total or 0 for inv in invoices)

	# -----------------------------
	# Guest Email
	# -----------------------------
	guest_doc = frappe.get_doc("Hotel Guest", check_in_doc.guest)
	guest_email = guest_doc.email

	# -----------------------------
	# Final Return
	# -----------------------------
	return {
		"invoices": invoices,
		"journal_entries": journal_entries,
		"payments": payments,
		"payment_sessions": payment_sessions,
		"total_outstanding_amount": total_outstanding_amount,
		"total_charges": total_charges,
		"guest_email": guest_email,
	}


@frappe.whitelist()
def get_outstanding_for_check_in(check_in):
	"""Return only the outstanding amount for faster UI checks."""
	data = get_linked_documents(check_in)
	return {"outstanding": data.get("total_outstanding_amount", 0)}


@frappe.whitelist()
def make_check_out(source_name, target_doc=None):
	# Block check-out for non-managers if outstanding invoices exist
	if "Hotel Manager" not in frappe.get_roles(frappe.session.user):
		data = get_linked_documents(source_name)
		outstanding = data.get("total_outstanding_amount", 0)

		if outstanding > 0:
			frappe.throw(
				_(
					"Cannot check out because there are outstanding invoices totaling {0}. Please settle them first."
				).format(frappe.format_value(outstanding))
			)

	def get_mapped_doc():
		check_in = frappe.get_doc("Hotel Room Check In", source_name)
		check_out = frappe.new_doc("Hotel Room Check Out")
		check_out.check_in = check_in.name
		check_out.guest = check_in.guest
		check_out.room_number = check_in.room_number
		check_out.check_in_datetime = check_in.check_in_datetime
		check_out.check_out_datetime = now_datetime()
		check_out.insert(ignore_permissions=True)
		return check_out

	doc = get_mapped_doc()
	return doc


@frappe.whitelist()
def apply_discount(check_in_name, discount_amount, reason=None):
	"""
	Apply a discount to the Hotel Room Check In document by creating a credit note.
	"""
	check_in_doc = frappe.get_doc("Hotel Room Check In", check_in_name)

	# Create credit note (Sales Invoice with is_return = 1)
	credit_note = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": check_in_doc.guest,
			"is_return": 1,
			"update_stock": 0,
			"custom_hotel_room_check_in": check_in_doc.name,
			"items": [{"item_code": "Room Discount", "qty": -1, "rate": discount_amount}],
			"posting_date": frappe.utils.today(),
			"remarks": reason or f"Discount applied to Check In {check_in_doc.name}",
		}
	)
	credit_note.insert()
	credit_note.submit()

	return {"status": "success", "credit_note": credit_note.name}


@frappe.whitelist()
def make_refund(source_name, target_doc=None):
	def get_mapped_doc():
		# Get total payments made against the check-in
		payments = frappe.get_all(
			"Payment Entry",
			filters={"custom_hotel_room_check_in": source_name},
			fields=["sum(paid_amount) as total_paid"],
		)
		total_paid = payments[0].total_paid if payments and payments[0].total_paid else 0

		check_in = frappe.get_doc("Hotel Room Check In", source_name)
		refund = frappe.new_doc("Hotel Refund")
		refund.guest = check_in.guest
		refund.check_in = check_in.name
		refund.refund_amount = total_paid
		refund.reason = f"Refund for Check In {check_in.name}"
		return refund

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
	new_expected_checkout = new_checkout_dt.strftime("%Y-%m-%d %H:%M:%S")

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
		frappe.throw(
			_(
				"Room {0} is not available for the selected extension period. It is reserved under {1}."
			).format(check_in_doc.room_number, conflicting_reservation)
		)

	# Check for conflicting check-ins during the extension period
	conflicting_check_in = frappe.db.exists(
		"Hotel Room Check In",
		{
			"room_number": check_in_doc.room_number,
			"status": ["in", ["Checked In", "Draft"]],
			"name": ["!=", check_in_doc.name],
			"check_in_datetime": ["<", new_checkout_dt],
			"expected_check_out_datetime": [">", current_checkout_dt],
		},
	)

	if conflicting_check_in:
		frappe.throw(
			_(
				"Room {0} is not available for the selected extension period. It is occupied by another guest under Check In {1}."
			).format(check_in_doc.room_number, conflicting_check_in)
		)

	# Create a new Sales Invoice for the extension
	extension_amount = number_of_nights * check_in_doc.rate_amount
	room_doc = frappe.get_doc("Hotel Room", check_in_doc.room_number)
	customer = frappe.get_value("Hotel Guest", check_in_doc.guest, "customer")

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.custom_hotel_room_check_in = check_in_doc.name
	si.due_date = new_checkout_dt.date()
	si.posting_date = now_datetime().date()
	si.append(
		"items",
		{
			"item_code": room_doc.erpnext_item,
			"rate": check_in_doc.rate_amount,
			"qty": number_of_nights,
			"amount": extension_amount,
			"description": _("Stay extension for {0} from {1} to {2}").format(
				check_in_doc.room_number,
				current_checkout_dt.strftime("%Y-%m-%d"),
				new_checkout_dt.strftime("%Y-%m-%d"),
			),
		},
	)
	si.set_taxes()
	si.insert(ignore_permissions=True)
	si.submit()

	# Add a record to the extensions child table
	check_in_doc.append(
		"extensions",
		{
			"extension_date": now_datetime(),
			"previous_checkout_date": current_checkout_dt,
			"new_checkout_date": new_checkout_dt,
			"number_of_nights": number_of_nights,
			"extension_invoice": si.name,
			"amount": extension_amount,
		},
	)

	# Update the check-in document's checkout time and save it to persist the extension record
	check_in_doc.expected_check_out_datetime = new_expected_checkout
	check_in_doc.save(ignore_permissions=True)

	# Add a comment to the check-in document for history
	check_in_doc.add_comment(
		"Comment",
		text=_("Stay extended to {0}. New invoice {1} created for {2}.").format(
			new_expected_checkout, si.name, frappe.utils.fmt_money(extension_amount)
		),
	)

	frappe.msgprint(_("Stay extended successfully. New invoice {0} created.").format(si.name))
	return {"sales_invoice": si.name}


@frappe.whitelist()
def reduce_stay(check_in_name, new_checkout):
	"""
	Reduce the expected check-out datetime for a guest.
	Rules:
	- New checkout must be earlier than current expected checkout.
	- New checkout cannot be in the past.
	- If new checkout is today, only allowed if current time <= default checkout time.
	"""

	from frappe.utils import now_datetime, get_datetime, getdate, date_diff, flt
	from datetime import datetime

	doc = frappe.get_doc("Hotel Room Check In", check_in_name)

	# Convert incoming datetime string
	new_dt = get_datetime(new_checkout)
	current_dt = get_datetime(doc.expected_check_out_datetime)
	now_dt = now_datetime()

	# --- 1. Must be earlier than current expected checkout ---
	if not (new_dt < current_dt):
		frappe.throw(
			f"New checkout must be earlier than current expected checkout: {frappe.format_value(current_dt)}"
		)

	# --- 2. Cannot be in the past ---
	if new_dt < now_dt:
		frappe.throw("New checkout cannot be in the past.")

	# --- 3. Special rule for reducing to today ---
	today = getdate(now_dt)
	new_date = getdate(new_dt)

	# Get default checkout time from Hotel Settings
	settings = frappe.get_doc("Hotel Settings")
	default_time = settings.default_check_out_time  # string "HH:mm:ss"

	# Build "today at default checkout time"
	today_default_dt = datetime.strptime(f"{today} {default_time}", "%Y-%m-%d %H:%M:%S")

	if new_date == today:
		if now_dt > today_default_dt:
			frappe.throw(
				f"Reducing stay to today is not allowed because default checkout time "
				f"({frappe.format_value(today_default_dt)}) has already passed."
			)
		if new_dt > today_default_dt:
			frappe.throw(
				f"For today, new checkout must not be later than the default checkout time "
				f"({frappe.format_value(today_default_dt)})."
			)

	# --- Everything ok → update document ---
	# Recalculate number of nights
	new_nights = date_diff(getdate(new_dt), getdate(doc.check_in_datetime))
	if new_nights < 1:
		new_nights = 1

	# --- Calculate difference and create credit note if reducing stay ---
	diff_nights = doc.number_of_nights - new_nights
	if diff_nights > 0:
		credit_amount = flt(doc.rate_amount) * diff_nights

		# Create credit note (Sales Invoice with is_return = 1)
		credit_note = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": doc.guest,
				"is_return": 1,
				"update_stock": 0,
				"check_in": doc.name,
				"custom_hotel_room_check_in": doc.name,
				"items": [
					{
						"item_code": doc.room_number,
						"qty": -diff_nights,
						"rate": doc.rate_amount,
						"amount": credit_amount,
					}
				],
				"posting_date": frappe.utils.today(),
				"remarks": f"Credit note for reduced stay ({diff_nights} nights)",
			}
		)
		credit_note.insert()
		credit_note.submit()

	# Update check-in document
	doc.expected_check_out_datetime = new_dt
	doc.number_of_nights = new_nights
	doc.save()
	frappe.db.commit()

	return {
		"status": "success",
		"new_checkout": new_dt,
		"new_nights": new_nights,
		"credit_nights": diff_nights if diff_nights > 0 else 0,
		"credit_amount": credit_amount if diff_nights > 0 else 0,
	}


@frappe.whitelist()
def adjust_stay(check_in_name, new_checkout, discount_type, new_discount=None):
	from frappe.utils import now_datetime, get_datetime, getdate, date_diff, flt

	# Safe-get doc (avoid missing permissions)
	doc = frappe.get_doc("Hotel Room Check In", check_in_name)

	# Convert datetime
	new_dt = get_datetime(new_checkout)
	current_dt = get_datetime(doc.expected_check_out_datetime)
	checkin_dt = get_datetime(doc.check_in_datetime)
	now_dt = now_datetime()

	# === VALIDATIONS ===
	if new_dt == current_dt:
		frappe.throw("New checkout is the same as current checkout. No adjustment needed.")
	if new_dt <= checkin_dt:
		frappe.throw("New checkout must be after check-in date.")
	if new_dt < now_dt:
		frappe.throw("New checkout cannot be in the past.")

	adjustment_type = "Extension" if new_dt > current_dt else "Reduction"

	# Special rule for reduction
	if adjustment_type == "Reduction":
		settings = frappe.get_cached_doc("Hotel Settings")
		default_time = settings.default_check_out_time

		today = getdate(now_dt)
		new_date = getdate(new_dt)
		today_default_dt = get_datetime(f"{today} {default_time}")

		if new_date == today:
			if now_dt > today_default_dt:
				frappe.throw(
					f"Cannot reduce stay to today; default checkout time ({default_time}) has passed."
				)
			if new_dt > today_default_dt:
				frappe.throw(f"New checkout must be on or before default checkout time ({default_time}).")

	# Night calculations
	new_nights = date_diff(getdate(new_dt), getdate(doc.check_in_datetime)) or 1
	current_nights = doc.number_of_nights or 1
	diff_nights = abs(current_nights - new_nights)
	if diff_nights == 0:
		frappe.throw("The new checkout results in the same number of nights.")

	# === Making sure no reservations or check-ins conflict with the new dates ===
	if adjustment_type == "Extension":
		conflicting_reservation = frappe.db.exists(
			"Hotel Room Reservation",
			{
				"room_number": doc.room_number,
				"status": ["not in", ["Cancelled", "No Show", "Completed"]],
				"docstatus": ["not in", [2, 1]],
				"from_date": ["<", new_dt.date()],
				"to_date": [">", current_dt.date()],
			},
		)

		if conflicting_reservation:
			reservation_guest = (
				frappe.db.get_value("Hotel Room Reservation", conflicting_reservation, "guest_name")
				if conflicting_reservation
				else ""
			)
			frappe.throw(
				_(
					"{0} is not available for the selected extension period. It is reserved for guest {1} under {2}."
				).format(doc.room_number, reservation_guest, conflicting_reservation)
			)

		conflicting_check_in = frappe.db.exists(
			"Hotel Room Check In",
			{
				"room_number": doc.room_number,
				"status": ["in", ["Checked In", "Draft"]],
				"name": ["!=", doc.name],
				"check_in_datetime": ["<", new_dt],
				"expected_check_out_datetime": [">", current_dt],
			},
		)

		if conflicting_check_in:
			reservation_guest = (
				frappe.db.get_value("Hotel Room Check In", conflicting_check_in, "guest_name")
				if conflicting_reservation
				else ""
			)
			frappe.throw(
				_(
					"{0} is not available for the selected extension period. It is occupied by another guest {1} under Check In {2} ."
				).format(doc.room_number, reservation_guest, conflicting_check_in)
			)

	amount = flt(doc.rate_amount) * diff_nights
	amount_with_discount = flt(amount) - flt(new_discount) if flt(new_discount) > 0 else 0
	frappe.log_error(amount_with_discount)
	adjustment_invoice_name = None

	try:
		# === EXTENSION INVOICE ===
		if adjustment_type == "Extension":
			invoice = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": doc.guest,
					"is_return": 0,
					"update_stock": 0,
					"custom_hotel_room_check_in": doc.name,
					"items": [
						{
							"item_code": doc.room_number,
							"qty": diff_nights,
							"rate": doc.rate_amount,
							"amount": diff_nights * doc.rate_amount,
						}
					],
					"posting_date": frappe.utils.today(),
				}
			)

			# Permission bypass
			invoice.flags.ignore_permissions = True
			invoice.flags.ignore_mandatory = True
			invoice.flags.ignore_links = True

			if new_discount and flt(new_discount) > 0:
				# check discount type
				if discount_type == "Percentage":
					invoice.additional_discount_percentage = flt(new_discount)
				elif discount_type == "Fixed Amount":
					invoice.discount_amount = flt(new_discount)

			# if invoice.discount_amount and invoice.discount_amount >= invoice.net_total:
			# 	frappe.throw(
			# 		"Discount cannot be greater than or equal to invoice amount."
			# 	)

			if invoice.additional_discount_percentage and invoice.additional_discount_percentage >= 100:
				frappe.throw("Discount percentage cannot be 100% or more.")
			invoice.insert(ignore_permissions=True)
			invoice.calculate_taxes_and_totals()
			invoice.submit()
			adjustment_invoice_name = invoice.name

		# === REDUCTION CREDIT NOTE ===
		else:
			credit_note = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": doc.guest,
					"is_return": 1,
					"update_stock": 0,
					"custom_hotel_room_check_in": doc.name,
					"items": [
						{
							"item_code": doc.room_number,
							"qty": -diff_nights,
							"rate": doc.rate_amount,
						}
					],
					"posting_date": frappe.utils.today(),
				}
			)

			# Permission bypass
			credit_note.flags.ignore_permissions = True
			credit_note.flags.ignore_mandatory = True
			credit_note.flags.ignore_links = True

			credit_note.insert()
			credit_note.calculate_taxes_and_totals()
			credit_note.submit()
			adjustment_invoice_name = credit_note.name

		# === Update Check-In Document ===
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True

		doc.append(
			"adjustments",
			{
				"adjustment_date": now_datetime(),
				"adjustment_type": adjustment_type,
				"previous_checkout_datetime": doc.expected_check_out_datetime,
				"new_checkout_datetime": new_dt,
				"previous_number_of_nights": current_nights,
				"new_number_of_nights": new_nights,
				"nights_difference": diff_nights if adjustment_type == "Extension" else -diff_nights,
				"adjustment_invoice": adjustment_invoice_name,
				"amount": amount,
			},
		)

		doc.expected_check_out_datetime = new_dt
		doc.number_of_nights = new_nights
		doc.save()

		frappe.db.commit()

		return {"status": "success", "adjustment_invoice": adjustment_invoice_name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(str(e), "adjust_stay")
		frappe.throw(f"Failed to process stay adjustment: {str(e)}")


@frappe.whitelist()
def transfer_room(check_in_name, new_room_number, note=None):
	check_in_doc = frappe.get_doc("Hotel Room Check In", check_in_name)

	# ensure new room is vacant
	if not frappe.db.exists("Hotel Room", new_room_number):
		frappe.throw(_("New room {0} does not exist.").format(new_room_number))

	new_room_doc = frappe.get_doc("Hotel Room", new_room_number)
	if new_room_doc.status != "Vacant":
		frappe.throw(_("New room {0} is not vacant.").format(new_room_number))

	# Ensure check-in is active
	if check_in_doc.status != "Checked In":
		frappe.throw(_("Only active check-ins can be transferred."))

	# Ensure target room exists and is vacant
	if not frappe.db.exists("Hotel Room", new_room_number):
		frappe.throw(_("Room {0} does not exist.").format(new_room_number))

	new_room_doc = frappe.get_doc("Hotel Room", new_room_number)
	if new_room_doc.status != "Vacant":
		frappe.throw(_("Room {0} is not vacant. Please select another room.").format(new_room_number))

	# Free the old room
	old_room_doc = frappe.get_doc("Hotel Room", check_in_doc.room_number)
	old_room_doc.db_set("current_check_in", None)
	old_room_doc.db_set("current_guest", None)
	old_room_doc.db_set("status", "Vacant")
	old_room_doc.add_comment(
		"Comment",
		text=_("Guest transferred out to {1}. {2}").format(
			check_in_doc.room_number, new_room_number, note or ""
		),
	)
	old_room_doc.save(ignore_permissions=True)

	# Update the new room details
	new_room_doc.status = "Occupied"
	new_room_doc.current_guest = check_in_doc.guest
	new_room_doc.current_check_in = check_in_doc.name
	new_room_doc.save(ignore_permissions=True)

	# get new room type rate
	new_rate_data = get_room_rate(new_room_doc.room_type, "", str(getdate(check_in_doc.check_in_datetime)))
	new_rate = flt(new_rate_data)
	if new_rate <= 0:
		frappe.throw(_("No valid rate found for Room Type {0}").format(new_room_doc.room_type))

	# Update check-in document (fixed: also update room_type)
	old_room_number = check_in_doc.room_number
	old_room_type = check_in_doc.room_type
	check_in_doc.room_number = new_room_number
	check_in_doc.room_type = new_room_doc.room_type  # Fixed: Update room type
	check_in_doc.db_set("room_number", new_room_number)
	check_in_doc.db_set("room_type", new_room_doc.room_type)  # Direct DB update
	check_in_doc.db_set("rate_amount", new_rate)
	check_in_doc.add_comment(
		"Comment",
		text=_("Guest transferred from {0} to {1}. {2}").format(old_room_number, new_room_number, note or ""),
	)

	# Log transfer history
	check_in_doc.append(
		"transfer_history",
		{
			"transfer_datetime": now_datetime(),
			"from_room": old_room_number,
			"to_room": new_room_number,
			"reason": note,
			"user": frappe.session.user,
		},
	)
	check_in_doc.save(ignore_permissions=True)

	# Adjust rate if new room type has different tariff
	adjust_room_rate(check_in_doc, old_room_number, new_room_number, note)

	frappe.db.commit()
	frappe.publish_realtime("rhohotel_front_desk_update")

	return {
		"success": True,
		"message": _("Guest transferred successfully to Room {0}").format(new_room_number),
	}


def adjust_room_rate(check_in_doc, old_room_number, new_room_number, note=None):
	"""Adjust room rate after transfer based on remaining nights, and auto-create rate difference invoice."""

	old_room = frappe.get_doc("Hotel Room", old_room_number)
	new_room = frappe.get_doc("Hotel Room", new_room_number)

	# Extract only the date (YYYY-MM-DD)
	check_in_date = str(getdate(check_in_doc.check_in_datetime))

	old_rate_data = get_room_rate(old_room.room_type, "", check_in_date)
	new_rate_data = get_room_rate(new_room.room_type, "", check_in_date)

	old_rate = flt(old_rate_data)
	new_rate = flt(new_rate_data)

	# Determine remaining nights
	today = getdate(nowdate())
	expected_checkout = getdate(check_in_doc.expected_check_out_datetime)
	remaining_nights = max(date_diff(expected_checkout, today), 0)

	if remaining_nights <= 0:
		frappe.logger().info(f"No remaining nights to adjust for {check_in_doc.name}")
		check_in_doc.add_comment(
			"Comment",
			text=_("No remaining nights to adjust for transfer {0}").format(new_room_number, note or ""),
		)
		return

	# Calculate total difference for remaining nights
	nightly_difference = new_rate - old_rate
	total_difference = nightly_difference * remaining_nights

	if total_difference == 0:
		frappe.logger().info(f"No rate change detected for transfer {check_in_doc.name}")
		return

	guest = check_in_doc.guest
	company = frappe.defaults.get_user_default("Company")

	if not company:
		frappe.throw(_("No default Company set for user. Cannot create invoice."))

	posting_date = nowdate()
	default_income = frappe.db.get_value("Company", company, "default_income_account")

	if not default_income:
		frappe.throw(_("No default_income_account set for Company {0}.").format(company))

	# Determine invoice type and direction
	if total_difference > 0:
		# Guest owes extra
		invoice_title = "Room Transfer Upgrade"
		is_refund = 0
		qty = 1
		difference_text = _("Charged extra")
	else:
		# Refund guest
		invoice_title = "Room Transfer Downgrade"
		is_refund = 1
		qty = -1
		difference_text = _("Refunded")

	# -----------------------------------------------------
	# Create Sales Invoice
	# -----------------------------------------------------
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = guest
	invoice.company = company
	invoice.posting_date = posting_date
	invoice.is_return = bool(is_refund)
	invoice.remarks = _("Room transfer from {0} to {1}. Rate adjusted for {2} remaining night(s).").format(
		old_room_number, new_room_number, remaining_nights
	)
	invoice.custom_hotel_room_check_in = check_in_doc.name
	invoice.update_outstanding_for_self = 0

	# Add line item
	invoice.append(
		"items",
		{
			"item_name": invoice_title,
			"description": f"{invoice_title} for {remaining_nights} night(s)",
			"qty": qty,
			"rate": abs(total_difference),
			"income_account": default_income,
		},
	)

	invoice.save(ignore_permissions=True)
	invoice.submit()

	# -----------------------------------------------------
	# Create Hotel Refund (only for downgrades)
	# -----------------------------------------------------
	if is_refund:
		refund = frappe.new_doc("Hotel Refund")
		refund.guest = guest
		refund.check_in = check_in_doc.name
		refund.refund_amount = abs(total_difference)
		refund.reason = f"Refund for Room Transfer from {old_room_number} to {new_room_number}"
		refund.credit_note = invoice.name
		refund.status = "Approved"

		refund.insert(ignore_permissions=True)
		refund.submit()

	# -----------------------------------------------------
	# Log comment on check-in document
	# -----------------------------------------------------
	check_in_doc.add_comment(
		"Comment",
		text=_(
			"Room rate adjusted due to transfer. {0} {1} for rate difference of {2} ({3} nights remaining)."
		).format(difference_text, invoice.name, fmt_money(total_difference, 2), remaining_nights),
	)

	# User alert
	frappe.msgprint(
		_("{0} rate difference of {1} applied for {2} remaining night(s). Invoice {3} created.").format(
			difference_text, fmt_money(total_difference, 2), remaining_nights, invoice.name
		),
		alert=True,
	)


@frappe.whitelist()
def apply_late_checkout_charge(check_in, item, charge_type, amount):
	from frappe.utils import flt

	"""
    Create Sales Invoice for late checkout charge
    """

	check_in_doc = frappe.get_doc("Hotel Room Check In", check_in)

	# --------------------------------
	# Safety: prevent duplicate charge
	# --------------------------------
	# existing = frappe.db.exists(
	#     "Sales Invoice Item",
	#     {
	#         "item_code": item,
	#         "custom_hotel_room_check_in": check_in
	#     }
	# )

	# if existing:
	#     frappe.throw("Late check-out charge has already been applied.")

	# ----------------------------
	# Customer validation using check-in guest
	# ----------------------------
	customer = frappe.get_value("Hotel Guest", check_in_doc.guest, "customer")
	if not customer:
		frappe.throw("No customer linked to this check-in.")

	# ----------------------------
	# Determine charge amount
	# ----------------------------
	rate = amount

	if charge_type == "Percentage":
		if not check_in_doc.rate_amount:
			frappe.throw("Room rate not found for percentage charge.")

		room_rate = flt(check_in_doc.rate_amount)
		percentage = flt(amount)

		rate = (room_rate * percentage) / 100

	# ----------------------------
	# Create Sales Invoice
	# ----------------------------
	company = frappe.defaults.get_user_default("Company")

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.posting_date = nowdate()
	si.company = company
	si.due_date = nowdate()
	si.custom_hotel_room_check_in = check_in

	# ----------------------------
	# Add item
	# ----------------------------
	si.append("items", {"item_code": item, "qty": 1, "rate": rate, "description": "Late Check-out Charge"})
	si.set_taxes()
	si.save(ignore_permissions=True)
	si.submit()

	return {"status": "success", "sales_invoice": si.name, "amount": rate}
