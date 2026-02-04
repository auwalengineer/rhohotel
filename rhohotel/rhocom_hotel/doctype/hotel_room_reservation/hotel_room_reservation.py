# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, date_diff, flt
from datetime import datetime
from frappe import _
from datetime import datetime
import json


class HotelRoomReservation(Document):
	def validate(self):
		self.validate_room_availability()

		self.number_of_nights = date_diff(getdate(self.to_date), getdate(self.from_date)) or 1

		discounted_amount = 0
		if self.discount:
			if self.discount_type == "Percentage":
				discounted_amount = self.number_of_nights * self.rate * (self.discount / 100)
			else:
				discounted_amount = self.discount

		self.net_total = (self.number_of_nights * self.rate) - discounted_amount

	def before_insert(self):
		self.apply_default_checkout_time()

		# 🔑 Always ensure customer
		self.customer = get_or_create_customer_for_guest(self.guest_name, self.guest_phone, self.guest_email)

	def apply_default_checkout_time(self):
		if not self.to_date:
			return

		settings = frappe.get_single("Hotel Settings")
		if not settings.default_check_out_time:
			return

		to_dt = get_datetime(self.to_date)
		default_time = datetime.strptime(settings.default_check_out_time, "%H:%M:%S").time()

		self.to_date = datetime.combine(to_dt.date(), default_time)

	def validate_room_availability(self):
		if self.docstatus == 2:
			return

		overlapping = frappe.db.sql(
			"""
            SELECT name FROM `tabHotel Room Reservation`
            WHERE room_number = %s
            AND docstatus = 1
            AND status NOT IN ('Cancelled', 'Completed')
            AND name != %s
            AND from_date < %s
            AND to_date > %s
        """,
			(self.room_number, self.name, self.to_date, self.from_date),
		)

		if overlapping:
			frappe.throw(
				_("Room {0} is already booked between {1} and {2}.").format(
					self.room_number, self.from_date, self.to_date
				)
			)

		# check Hotel Room Check In
		overlapping_checkin = frappe.db.sql(
			"""
            SELECT name
            FROM `tabHotel Room Check In`
            WHERE guest != %s
            AND room_number = %s
            AND status IN ('Draft', 'Checked In')
            AND name != %s
            AND DATE(check_in_datetime) < %s
            AND DATE(expected_check_out_datetime) > %s
        """,
			(self.guest_name, self.room_number, self.name or "", self.to_date, self.from_date),
		)

		if overlapping_checkin:
			frappe.throw(
				_("Room {0} is already checked in between {1} and {2}.").format(
					self.room_number, self.from_date, self.to_date
				)
			)

	def on_update(self):
		self.validate_room_availability()

	def on_save(self):
		self.validate_room_availability()

	def on_change(self):
		self.validate_room_availability()


@frappe.whitelist()
def make_invoice(name):
	doc = frappe.get_doc("Hotel Room Reservation", name)

	if not doc.customer:
		doc.customer = get_or_create_customer_for_guest(doc.guest_name, doc.guest_phone, doc.guest_email)

	room = frappe.get_doc("Hotel Room", doc.room_number)

	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": doc.customer,
			"posting_date": frappe.utils.today(),
			"due_date": get_datetime(doc.to_date).date(),
			"items": [
				{
					"item_code": room.erpnext_item,
					"qty": doc.number_of_nights,
					"rate": doc.rate,
					"description": _("Reservation charge for {0} from {1} to {2}").format(
						doc.room_number, getdate(doc.from_date), getdate(doc.to_date)
					),
				}
			],
		}
	)

	if doc.discount:
		if doc.discount_type == "Percentage":
			si.additional_discount_percentage = doc.discount
		else:
			si.discount_amount = doc.discount

	si.set_taxes()
	si.insert(ignore_permissions=True)
	si.submit()

	doc.db_set("sales_invoice", si.name)

	return si.name


@frappe.whitelist()
def adjust_reservation(reservation_name, new_checkout, new_check_in, new_discount=None):
	"""
	Unified function for extending or reducing stay.
	Creates invoice (extension) or credit note (reduction) and logs adjustment in child table.
	"""
	from frappe.utils import now_datetime, get_datetime, getdate, date_diff, flt

	doc = frappe.get_doc("Hotel Room Reservation", reservation_name)

	if not doc.customer:
		doc.customer = get_or_create_customer_for_guest(doc.guest_name, doc.guest_phone, doc.guest_email)

	# Convert to datetime objects
	new_dt = get_datetime(new_checkout)
	current_dt = get_datetime(doc.to_date)
	checkin_dt = get_datetime(doc.from_date)
	old_from_dt = get_datetime(doc.from_date)
	now_dt = now_datetime()

	# VALIDATION 1: New checkout must be different from current checkout and check-in must be different from current check-in
	if new_dt == current_dt and checkin_dt == new_check_in:
		frappe.throw("New checkout/checkin is the same as current checkout/checkin. No adjustment needed.")

	# VALIDATION 2: New checkout must be after check-in
	if new_dt <= checkin_dt:
		frappe.throw("New checkout must be after check-in date/time.")

	# VALIDATION 3: Cannot be in the past
	if new_dt < now_dt:
		frappe.throw("New checkout cannot be in the past.")

	# if new_check_in < now_dt:
	#     frappe.throw("New check-in cannot be in the past.")

	# Determine adjustment type
	adjustment_type = "Extension" if new_dt > current_dt else "Reduction"

	# VALIDATION 4: Special validation for reductions to "today"
	if adjustment_type == "Reduction":
		today = getdate(now_dt)
		new_date = getdate(new_dt)

		# Get hotel settings for default checkout time
		settings = frappe.get_doc("Hotel Settings")
		default_time = settings.default_check_out_time

		# Build today's default checkout datetime (timezone-aware)
		today_default_dt = get_datetime(f"{today} {default_time}")

		# If reducing to today, check special rules
		if new_date == today:
			# Rule 1: Can't reduce to today if default checkout time has passed
			if now_dt > today_default_dt:
				frappe.throw(
					f"Cannot reduce stay to today; default checkout time ({default_time}) has already passed."
				)

			# Rule 2: New checkout time for today must not exceed default checkout time
			if new_dt > today_default_dt:
				frappe.throw(
					f"New checkout for today must be on or before default checkout time ({default_time})."
				)

	# Calculate new number of nights
	new_nights = date_diff(getdate(new_dt), getdate(new_check_in))
	if new_nights < 1:
		new_nights = 1

	# Calculate difference
	current_nights = doc.number_of_nights or 1
	diff_nights = abs(current_nights - new_nights)
	amount = flt(doc.rate) * diff_nights

	# VALIDATION 5: Ensure there's actually a difference in nights
	if new_check_in == checkin_dt and old_from_dt == new_checkout:
		frappe.throw("No adjustment needed.")

	adjustment_invoice_name = None

	new_net_total = doc.net_total

	try:
		if new_nights > current_nights:  # Extension
			# Create invoice for extra nights
			invoice = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": doc.customer,
					"is_return": 0,
					"update_stock": 0,
					"check_in": doc.name,
					"items": [
						{
							"item_code": doc.room_number,
							"qty": diff_nights,
							"rate": doc.rate,
							"amount": amount,
							"description": f"Invoice for stay extension: {diff_nights} additional night(s)",
						}
					],
					"posting_date": frappe.utils.today(),
					"remarks": f"Invoice for stay extension: {diff_nights} additional night(s)",
				}
			)

			invoice.set_taxes()

			if new_discount and flt(new_discount) > 0:
				# check discount type
				if doc.discount_type == "Percentage":
					invoice.additional_discount_percentage = flt(new_discount)
				else:
					invoice.discount_amount = flt(new_discount)

			invoice.insert(ignore_permissions=True)
			invoice.submit()
			adjustment_invoice_name = invoice.name
			new_net_total = doc.net_total + invoice.grand_total

		else:  # Reduction
			# Create credit note
			credit_note = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": doc.customer,
					"is_return": 1,
					"update_stock": 0,
					"check_in": doc.name,
					"items": [
						{
							"item_code": doc.room_number,
							"qty": -diff_nights,
							"rate": doc.rate,
							"amount": amount,
						}
					],
					"posting_date": frappe.utils.today(),
					"remarks": f"Credit note for stay reduction: {diff_nights} night(s) removed",
				}
			)
			credit_note.insert(ignore_permissions=True)
			credit_note.submit()
			adjustment_invoice_name = credit_note.name
			new_net_total = doc.net_total + credit_note.grand_total

		if not adjustment_invoice_name:
			frappe.throw("Failed to create adjustment invoice.")

		# Add adjustment to child table
		doc.append(
			"adjustments",
			{
				"adjustment_date": frappe.utils.now_datetime(),
				"adjustment_type": adjustment_type,
				"previous_checkout_datetime": doc.to_date,
				"new_checkout_datetime": new_dt,
				"previous_number_of_nights": current_nights,
				"new_number_of_nights": new_nights,
				"nights_difference": diff_nights if adjustment_type == "Extension" else -diff_nights,
				"adjustment_nvoice": adjustment_invoice_name,
				"amount": amount,
			},
		)

		# Update parent doc
		doc.to_date = new_dt
		doc.from_date = new_check_in
		doc.number_of_nights = new_nights
		doc.net_total = new_net_total
		doc.save()

		frappe.db.commit()

		return {
			"status": "success",
			"adjustment_type": adjustment_type,
			"new_checkout": str(new_dt),
			"previous_nights": current_nights,
			"new_nights": new_nights,
			"nights_difference": diff_nights if adjustment_type == "Extension" else -diff_nights,
			"adjustment_invoice": adjustment_invoice_name,
			"amount": amount,
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"Stay Adjustment Error: {str(e)}", "adjust_stay")
		frappe.throw(f"Failed to process stay adjustment: {str(e)}")


def find_customer_by_contact(phone=None, email=None):
	"""Find existing Customer by phone or email"""

	if phone:
		customer = frappe.db.get_value("Customer", {"mobile_no": phone}, "name")
		if customer:
			return customer

	if email:
		customer = frappe.db.get_value("Customer", {"email_id": email}, "name")
		if customer:
			return customer

	return None


def get_or_create_customer_for_guest(guest_name, phone=None, email=None):
	"""
	Ensures:
	- Hotel Guest exists
	- Guest is linked to ONE Customer
	- Customer auto-merged by phone/email
	"""

	# ---------------------------
	# Get or Create Hotel Guest
	# ---------------------------
	guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")

	if guest:
		guest = frappe.get_doc("Hotel Guest", guest)
	else:
		guest = frappe.get_doc(
			{
				"doctype": "Hotel Guest",
				"hotel_guest_name": guest_name,
				"phone_number": phone or "",
				"email": email or "",
				"guest_type": "Individual",
			}
		)
		guest.insert(ignore_permissions=True)

	# ---------------------------
	# Already linked → done
	# ---------------------------
	if guest.customer:
		return guest.customer

	# ---------------------------
	# Try auto-merge by contact
	# ---------------------------
	existing_customer = find_customer_by_contact(phone, email)

	if existing_customer:
		guest.db_set("customer", existing_customer, update_modified=False)
		return existing_customer

	# ---------------------------
	# Create new Customer
	# ---------------------------
	selling_settings = frappe.get_cached_doc("Selling Settings")

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": guest.hotel_guest_name,
			"customer_type": "Individual",
			"customer_group": selling_settings.default_customer_group,
			"territory": selling_settings.default_territory,
			"mobile_number": phone or "",
			"email_id": email or "",
		}
	)

	customer.insert(ignore_permissions=True)

	guest.db_set("customer", customer.name, update_modified=False)

	return customer.name


@frappe.whitelist()
def get_available_rooms_for_reservation(doctype, txt, searchfield, start, page_len, filters):
	from rhohotel.api import get_available_rooms

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	room_number = filters.get("room_number")

	if not from_date or not to_date or not room_number:
		frappe.throw(_("Missing required filters: from_date, to_date, room_number"))

	room = frappe.get_doc("Hotel Room", {"room_number": room_number})
	available_rooms = get_available_rooms(from_date, to_date, room.room_type)

	return [[room.get("name")] for room in available_rooms]


@frappe.whitelist()
def change_reservation_room(reservation_name, new_room_number, reason=None):
	doc = frappe.get_doc("Hotel Room Reservation", reservation_name)

	if doc.docstatus != 1:
		frappe.throw(_("Reservation must be submitted to change the room."))

	if doc.status == "Checked In":
		frappe.throw(_("Cannot change room for a reservation that is already checked in."))

	if doc.room_number == new_room_number:
		frappe.throw(_("The new room is the same as the current room."))

	# Temporarily switch room for validation
	original_room = doc.room_number
	doc.room_number = new_room_number

	# Validate availability
	doc.validate_room_availability()

	# Restore original room before saving
	doc.room_number = original_room

	# Now apply the change
	old_room = doc.room_number
	doc.room_number = new_room_number
	doc.save(ignore_permissions=True)

	# Add audit comment
	comment_text = _("Room changed from {0} to {1}.").format(old_room, new_room_number)
	if reason:
		comment_text += f"\nReason: {reason}"

	doc.add_comment("Comment", text=comment_text)

	if doc.front_desk_reservation:
		_cascade_room_change_to_fdr(doc.front_desk_reservation, old_room, new_room_number)

	return {"status": "success", "message": _("Room changed successfully.")}


@frappe.whitelist()
def create_payment_entry(reservation, data):
	import json

	data = frappe._dict(json.loads(data))

	reservation_doc = frappe.get_doc("Hotel Room Reservation", reservation)

	if reservation_doc.docstatus != 1:
		frappe.throw("Only submitted reservations can receive payment.")

	if not reservation_doc.sales_invoice:
		frappe.throw("No invoice linked to this reservation.")

	invoice = frappe.get_doc("Sales Invoice", reservation_doc.sales_invoice)

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
	if data.reference_no:
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
					"allocated_amount": min(flt(data.paid_amount), flt(invoice.outstanding_amount)),
				}
			],
		}
	)

	pe.insert(ignore_permissions=True)
	pe.submit()

	# update reservation payment status
	invoice = frappe.get_doc("Sales Invoice", reservation_doc.sales_invoice)
	reservation_doc.payment_status = "Paid" if flt(invoice.outstanding_amount) <= 0 else "Partly Paid"
	reservation_doc.save()

	return pe.name


def _cascade_room_change_to_fdr(fdr_name, old_room, new_room):
	"""
	Updates the FDR child table row and recalculates FDR totals.
	Called automatically when a corporate HRR room is changed.
	"""
	from rhohotel.api import get_room_rate

	# Find the child row that holds old_room
	child_row = frappe.db.get_value(
		"Front Desk Reservation Room",
		{"parent": fdr_name, "room_number": old_room},
		["name", "rate_per_night"],
		as_dict=True,
	)

	if not child_row:
		# Edge case: child row doesn't exist, nothing to update
		return

	# Get new room's type and rate
	new_room_doc = frappe.get_doc("Hotel Room", new_room)
	fdr = frappe.get_doc("Hotel Front Desk Reservation", fdr_name)
	new_rate = get_room_rate(new_room_doc.room_type, check_in_date=str(fdr.from_date))

	if not new_rate:
		frappe.log_error(
			f"No rate found for {new_room_doc.room_type} when cascading room change to {fdr_name}",
			"FDR Cascade Error",
		)
		return

	new_room_total = new_rate * fdr.number_of_nights

	# Update the child row
	frappe.db.set_value(
		"Front Desk Reservation Room",
		child_row.name,
		{
			"room_number": new_room,
			"room_type": new_room_doc.room_type,
			"rate_per_night": new_rate,
			"room_total": new_room_total,
		},
		update_modified=False,
	)

	# Recalculate FDR subtotal & total
	fdr.reload()
	new_subtotal = sum(float(r.room_total or 0) for r in fdr.rooms)
	discount = float(fdr.discount_amount or 0)

	frappe.db.set_value(
		"Hotel Front Desk Reservation",
		fdr_name,
		{
			"subtotal": new_subtotal,
			"total_amount": new_subtotal - discount,
		},
		update_modified=False,
	)

	frappe.db.commit()
