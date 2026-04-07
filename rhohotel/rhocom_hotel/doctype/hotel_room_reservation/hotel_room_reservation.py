# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, date_diff, flt
from frappe import _
from datetime import datetime, time
import json


class HotelRoomReservation(Document):
	def validate(self):
		if self.status == "Cancelled" and self.docstatus != 2:
			frappe.throw("Use the Cancel button to cancel this reservation.")
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
		if not self.from_date or not self.to_date:
			return

		# -----------------------------------
		# Build TIME-AWARE boundaries
		# -----------------------------------
		CHECK_IN_TIME = time(12, 0)
		CHECK_OUT_TIME = time(12, 0)
		from_date = getdate(self.from_date)
		to_date = getdate(self.to_date)

		new_start = datetime.combine(from_date, CHECK_IN_TIME)
		new_end = datetime.combine(to_date, CHECK_OUT_TIME)

		# -----------------------------
		# Reservation Overlap Check
		# -----------------------------
		overlapping_reservation = frappe.db.sql(
			"""
			SELECT name
			FROM `tabHotel Room Reservation`
			WHERE room_number = %s
				AND docstatus = 1
				AND status NOT IN ('Cancelled', 'Completed')
				AND name != %s
				AND NOT (
					TIMESTAMP(to_date, '12:00:00') <= %s
					OR TIMESTAMP(from_date, '12:00:00') >= %s
				)
			""",
			(
				self.room_number,
				self.name or "",
				new_start,   # compare with datetime
				new_end
			),
		)

		if overlapping_reservation:
			frappe.throw(
				_("{0} is already booked between {1} and {2}.").format(
					self.room_number, self.from_date, self.to_date
				)
			)

		# -----------------------------
		# Check-In Overlap Check
		# -----------------------------
		overlapping_checkin = frappe.db.sql(
			"""
			SELECT name
			FROM `tabHotel Room Check In`
			WHERE room_number = %s
				AND status IN ('Draft', 'Checked In')
				AND name != %s
				AND NOT (
					expected_check_out_datetime <= %s
					OR check_in_datetime >= %s
				)
			""",
			(
				self.room_number,
				self.name or "",
				new_start,
				new_end
			),
		)

		if overlapping_checkin:
			frappe.throw(
				_("{0} is already checked in between {1} and {2}.").format(
					self.room_number, self.from_date, self.to_date
				)
			)
	# def validate_room_availability(self):
	# 	if self.docstatus == 2:
	# 		return

	# 	# -----------------------------
	# 	# Reservation Overlap Check
	# 	# -----------------------------
	# 	overlapping_reservation = frappe.db.sql(
	# 		"""
	# 		SELECT name 
	# 		FROM `tabHotel Room Reservation`
	# 		WHERE room_number = %s
	# 			AND docstatus = 1
	# 			AND status NOT IN ('Cancelled', 'Completed')
	# 			AND name != %s
	# 			AND NOT (
	# 				DATE(to_date) <= DATE(%s)
	# 				OR DATE(from_date) >= DATE(%s)
	# 			)
	# 		""",
	# 		(
	# 			self.room_number,
	# 			self.name or "",
	# 			self.from_date,
	# 			self.to_date
	# 		),
	# 	)

	# 	if overlapping_reservation:
	# 		frappe.throw(
	# 			_("{0} is already booked between {1} and {2}.").format(
	# 				self.room_number, self.from_date, self.to_date
	# 			)
	# 		)

	# 	# -----------------------------
	# 	# Check-In Overlap Check
	# 	# -----------------------------
	# 	overlapping_checkin = frappe.db.sql(
	# 		"""
	# 		SELECT name
	# 		FROM `tabHotel Room Check In`
	# 		WHERE room_number = %s
	# 			AND status IN ('Draft', 'Checked In')
	# 			AND name != %s
	# 			AND NOT (
	# 				expected_check_out_datetime <= %s
	# 				OR check_in_datetime >= %s
	# 			)
	# 		""",
	# 		(
	# 			self.room_number,
	# 			self.name or "",
	# 			self.from_date,
	# 			self.to_date
	# 		),
	# 	)

	# 	if overlapping_checkin:
	# 		frappe.throw(
	# 			_("{0} is already checked in between {1} and {2}.").format(
	# 				self.room_number, self.from_date, self.to_date
	# 			)
	# 		)


	def on_update(self):
		if self.status == "Cancelled":
			frappe.throw("Use the Cancel button instead of setting status manually.")

		self.validate_room_availability()

	def on_save(self):
		frappe.throw(self.status)
		if self.status == "Cancelled":
			frappe.throw("Use the Cancel button instead of setting status manually.")

		self.validate_room_availability()

	def on_change(self):
		if self.status == "Cancelled" and self.docstatus != 2:
			frappe.throw("Use the Cancel button to cancel this reservation.")
		self.validate_room_availability()
	def on_cancel(self):
		self.status = "Cancelled"


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


def _get_reservation_item_code(reservation_doc, invoice=None):
	if invoice and invoice.items:
		return invoice.items[0].item_code

	room_item = frappe.db.get_value("Hotel Room", reservation_doc.room_number, "erpnext_item")
	return room_item or reservation_doc.room_number


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


def _build_reservation_invoice(
	reservation_doc,
	nights,
	discount_value,
	from_date,
	to_date,
	item_code,
	is_return=False,
	return_against=None,
	amount_override=None,
	remarks=None,
):
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": reservation_doc.customer,
			"posting_date": frappe.utils.today(),
			"due_date": get_datetime(to_date).date(),
			"is_return": 1 if is_return else 0,
			"return_against": return_against,
			"update_stock": 0,
			"items": [
				{
					"item_code": item_code,
					"qty": -nights if is_return else nights,
					"rate": (abs(amount_override) / nights) if amount_override is not None and nights else reservation_doc.rate,
					"description": _("Reservation charge for {0} from {1} to {2}").format(
						reservation_doc.room_number, getdate(from_date), getdate(to_date)
					),
				}
			],
			"remarks": remarks,
		}
	)

	if not is_return and amount_override is None and discount_value:
		if reservation_doc.discount_type == "Percentage":
			invoice.additional_discount_percentage = discount_value
		else:
			invoice.discount_amount = discount_value

	invoice.set_taxes()
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice

@frappe.whitelist()
def adjust_reservation(reservation_name, new_checkout, new_check_in, new_discount=None):
	"""
	Unified function for extending or reducing stay.
	Creates invoice (extension) or credit note (reduction) and logs adjustment in child table.
	"""
	from frappe.utils import now_datetime, get_datetime, getdate, date_diff, flt

	doc = frappe.get_doc("Hotel Room Reservation", reservation_name)

	# VALIDATION: Check if sales invoice exists

	if not doc.customer:
		doc.customer = get_or_create_customer_for_guest(doc.guest_name, doc.guest_phone, doc.guest_email)


	# Convert to datetime objects
	new_dt = get_datetime(new_checkout)
	current_dt = get_datetime(doc.to_date)
	checkin_dt = get_datetime(doc.from_date)
	old_from_dt = get_datetime(doc.from_date)
	now_dt = now_datetime()

	# VALIDATION 1
	if new_dt == current_dt and checkin_dt == new_check_in:
		frappe.throw("New checkout/checkin is the same as current checkout/checkin. No adjustment needed.")

	# Determine adjustment type
	adjustment_type = "Extension" if new_dt > current_dt else "Reduction"

	# VALIDATION 4: Special validation for reductions to "today"
	if adjustment_type == "Reduction":
		today = getdate(now_dt)
		new_date = getdate(new_dt)
		settings = frappe.get_doc("Hotel Settings")
		default_time = settings.default_check_out_time
		today_default_dt = get_datetime(f"{today} {default_time}")

		if new_date == today:
			if now_dt > today_default_dt:
				frappe.throw(
					f"Cannot reduce stay to today; default checkout time ({default_time}) has already passed."
				)
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

	# VALIDATION 5
	if new_check_in == checkin_dt and new_dt == current_dt:
		frappe.throw("No adjustment needed.")

	# Handle discount - use new_discount if provided (even if 0)
	if new_discount is not None:
		discount_to_use = flt(new_discount)
	else:
		discount_to_use = flt(doc.discount)

	discount_type = doc.discount_type

	# 🔧 SIMPLIFIED: Calculate what the NEW total should be
	new_gross_total = flt(doc.rate) * new_nights
	new_discount_amount = 0

	if discount_to_use > 0:
		if discount_type == "Percentage":
			new_discount_amount = new_gross_total * (discount_to_use / 100)
		else:  # Amount
			new_discount_amount = discount_to_use

	new_net_total = new_gross_total - new_discount_amount

	# Calculate the adjustment amount (what the invoice should be)
	adjustment_amount = new_net_total - flt(doc.net_total)
	if abs(adjustment_amount) < 0.01:
		doc.flags.ignore_validate_update_after_submit = True
		doc.to_date = new_dt
		doc.from_date = new_check_in
		doc.number_of_nights = new_nights
		doc.net_total = new_net_total

		if new_discount is not None:
			doc.discount = discount_to_use

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		return {
			"status": "success",
			"adjustment_type": "Date Change Only",
			"new_checkout": str(new_dt),
			"new_checkin": str(new_check_in),
			"previous_nights": current_nights,
			"new_nights": new_nights,
			"nights_difference": new_nights - current_nights,
			"adjustment_invoice": None,
			"amount": 0,
			"new_net_total": new_net_total,
		}

	adjustment_invoice_name = None

	try:
		original_invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice) if doc.sales_invoice else None
		item_code = _get_reservation_item_code(doc, original_invoice)
		has_payment_activity = _invoice_has_payment_activity(original_invoice)

		if original_invoice and not has_payment_activity:
			if original_invoice.docstatus == 1:
				original_invoice.flags.ignore_permissions = True
				original_invoice.cancel()

			replacement_invoice = _build_reservation_invoice(
				doc,
				nights=new_nights,
				discount_value=discount_to_use,
				from_date=new_check_in,
				to_date=new_dt,
				item_code=item_code,
				remarks=_("Recreated after reservation adjustment from {0} nights to {1} nights.").format(
					current_nights, new_nights
				),
			)
			adjustment_invoice_name = replacement_invoice.name
			doc.sales_invoice = replacement_invoice.name
			doc.payment_status = "Pending"
		elif adjustment_amount > 0:
			adjustment_invoice = _build_reservation_invoice(
				doc,
				nights=diff_nights or 1,
				discount_value=0,
				from_date=current_dt,
				to_date=new_dt,
				item_code=item_code,
				amount_override=adjustment_amount,
				remarks=_("Adjustment invoice for reservation change from {0} nights to {1} nights.").format(
					current_nights, new_nights
				),
			)
			adjustment_invoice_name = adjustment_invoice.name
		else:
			credit_note = _build_reservation_invoice(
				doc,
				nights=diff_nights or 1,
				discount_value=0,
				from_date=new_check_in,
				to_date=current_dt,
				item_code=item_code,
				is_return=True,
				return_against=original_invoice.name if original_invoice and original_invoice.docstatus == 1 else None,
				amount_override=abs(adjustment_amount),
				remarks=_("Credit note for reservation change from {0} nights to {1} nights.").format(
					current_nights, new_nights
				),
			)
			adjustment_invoice_name = credit_note.name

		if adjustment_invoice_name:
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
					"amount": abs(adjustment_amount),
				},
			)

		# Update parent doc
		doc.flags.ignore_validate_update_after_submit = True

		doc.to_date = new_dt
		doc.from_date = new_check_in
		doc.number_of_nights = new_nights
		doc.net_total = new_net_total
		if new_discount is not None:
			doc.discount = discount_to_use

		doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"adjustment_type": adjustment_type,
			"new_checkout": str(new_dt),
			"previous_nights": current_nights,
			"new_nights": new_nights,
			"nights_difference": new_nights - current_nights,
			"adjustment_invoice": adjustment_invoice_name,
			"amount": abs(adjustment_amount),
			"new_net_total": new_net_total,
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
