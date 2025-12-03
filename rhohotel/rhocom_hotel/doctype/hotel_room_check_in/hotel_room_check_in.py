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
		self.validate_room()
		self.set_checkout_time()
		self.validate_dates()
		self.calculate_total_charges()
		#self.validate_rate_and_session()
		#self.set_rate_amount()

	def set_checkout_time(self):
		"""Set the time part of expected_check_out_datetime from Hotel Settings."""
		if self.expected_check_out_datetime and not self.late_checkout:
			hotel_settings = frappe.get_single("Hotel Settings")
			if hotel_settings.default_check_out_time:
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

	def validate_reservation(self):

		    # Only run validation if reservation is selected
		if not self.reservation:
			return

		"""Check if reservation exists and is valid for check-in"""
		if self.reservation:
			
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
		if not frappe.db.exists("Hotel Room", self.room_number):
			frappe.throw(_("Room {0} does not exist").format(self.room_number))

		# Check if room matches reservation type
		room = frappe.get_doc("Hotel Room", self.room_number)
		# Convert string to datetime if needed
		if isinstance(self.check_in_datetime, str):
			self.check_in_datetime = datetime.strptime(self.check_in_datetime, "%Y-%m-%d %H:%M:%S")

		start_date = self.check_in_datetime.date()

		day_start = datetime.combine(start_date, time.min)
		day_end = datetime.combine(start_date, time.max)
		
		# Check if there is a reservation on the room on the check-in date
		reservation = frappe.get_all("Hotel Room Reservation",
			filters={
					"room_number": self.room_number,
        			"from_date": ["between", [day_start, day_end]],
					"guest_name": ["not in", [self.guest]],
					"status": ["in", ["booked", "Confirmed"]]
				}
			)

		if reservation: 
			frappe.throw(_("Room {0} is reserved for today").format(self.room_number))

		
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
  
		if self.reservation:
			frappe.db.set_value("Hotel Room Reservation", self.reservation, "status", "Checked-In")
   
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
		room.save(ignore_permissions=True)

	def make_sales_invoice(self):

		if self.reservation:
			reservation = frappe.get_doc("Hotel Room Reservation", self.reservation)
			if reservation.sales_invoice:
				# Sales Invoice already created from reservation
				# get the linked invoice and link to check-in
				invoice = frappe.get_doc("Sales Invoice", reservation.sales_invoice)
				invoice.db_set("custom_hotel_room_check_in", self.name)		

				# get payment entries linked to reservation invoice and link to check-in
				
				payments = frappe.db.get_all(
					"Payment Entry Reference",
					filters={
						"reference_doctype": "Sales Invoice",
						"reference_name": reservation.sales_invoice
					},
					fields=["parent"]
				)

				for payment in payments:
					payment_doc = frappe.get_doc("Payment Entry", payment.parent)
					payment_doc.db_set("custom_hotel_room_check_in", self.name)
					payment_doc.save(ignore_permissions=True)


				return

		# Get ERPNEXT item using selected room
		room_doc = frappe.get_doc("Hotel Room", self.room_number)


		customer = frappe.get_value("Hotel Guest", self.guest, "customer")
		si = frappe.new_doc("Sales Invoice")
		si.customer = customer
		si.custom_hotel_room_check_in = self.name
		si.due_date = get_datetime(self.expected_check_out_datetime).date()
		si.posting_date = get_datetime(self.check_in_datetime).date()		
		si.append("items", {
			"item_code": room_doc.erpnext_item,
			"rate": self.rate_amount,
			"qty": self.number_of_nights,
			"amount": self.total_charges,
			"description": _("Room charge for {0} from {1} to {2}").format(self.room_number, get_datetime(self.check_in_datetime).date(), get_datetime(self.expected_check_out_datetime).date())
		})
		si.set_taxes()
  
		# set discount
		if self.discount:
			si.discount_amount = self.discount
		
		si.insert(ignore_permissions=True)
		si.submit()


		# Link invoice back to check-in record
		#self.db_set("sales_invoice", si.name)

		#frappe.msgprint(_("Sales Invoice {0} created").format(si.name), alert=True)
	
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
def get_linked_documents(check_in):

    """Get linked invoices, payments, and sessions for a check-in."""
    
    check_in_doc = frappe.get_doc("Hotel Room Check In", check_in)

    # -----------------------------
    # Get POS Invoices
    # -----------------------------
    pos_invoices = frappe.get_all(
        "POS Invoice",
        filters={
            "custom_hotel_room_check_in": check_in_doc.name,
            "status": "Unpaid"
        },
        fields=[
            "name",
            "customer",
            "posting_date",
            "grand_total",
            "outstanding_amount",
            "pos_profile"
        ]
    )

    # Add invoice_type for frontend clarity
    for inv in pos_invoices:
        inv["invoice_type"] = "POS Invoice"

    # -----------------------------
    # Get Sales Invoices
    # -----------------------------
    sales_invoices = frappe.get_all(
        "Sales Invoice",
        filters={"custom_hotel_room_check_in": check_in_doc.name},
        fields=[
            "name",
            "customer",
            "posting_date",
            "grand_total",
            "outstanding_amount"
        ]
    )

    # Mark them as Sales Invoice
    for inv in sales_invoices:
        inv["invoice_type"] = "Sales Invoice"
        inv["pos_profile"] = None  # keep consistent keys

    # Merge lists
    invoices = sales_invoices + pos_invoices

    # -----------------------------
    # Get Payment Entries
    # -----------------------------
    payments = frappe.get_all(
        "Payment Entry",
        filters={"custom_hotel_room_check_in": check_in_doc.name},
        fields=["name", "party", "posting_date", "paid_amount"]
    )

    # -----------------------------
    # Get Payment Sessions (POS)
    # -----------------------------
    payment_sessions = frappe.get_all(
        "Payment Session",
        filters={"hotel_room_check_in": check_in_doc.name, "status": "Paid"},
        fields=["name", "posting_date", "total_amount"]
    )

    # -----------------------------
    # Compute Totals
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
        "payments": payments,
        "payment_sessions": payment_sessions,
        "total_outstanding_amount": total_outstanding_amount,
        "total_charges": total_charges,
        "guest_email": guest_email
    }

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
		check_out.insert(ignore_permissions=True)
		return check_out

	doc = get_mapped_doc()
	return doc

@frappe.whitelist()
def make_refund(source_name, target_doc=None):
	def get_mapped_doc():
		# Get total payments made against the check-in
		payments = frappe.get_all("Payment Entry", filters={"custom_hotel_room_check_in": source_name}, fields=["sum(paid_amount) as total_paid"])
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
		frappe.throw(_("Room {0} is not available for the selected extension period. It is occupied by another guest under Check In {1}.").format(check_in_doc.room_number, conflicting_check_in))

	# Create a new Sales Invoice for the extension
	extension_amount = number_of_nights * check_in_doc.rate_amount
	room_doc = frappe.get_doc("Hotel Room", check_in_doc.room_number)
	customer = frappe.get_value("Hotel Guest", check_in_doc.guest, "customer")

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.custom_hotel_room_check_in = check_in_doc.name
	si.due_date = new_checkout_dt.date()
	si.posting_date = now_datetime().date()
	si.append("items", {
		"item_code": room_doc.erpnext_item,
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

	# Add a record to the extensions child table
	check_in_doc.append("extensions", {
		"extension_date": now_datetime(),
		"previous_checkout_date": current_checkout_dt,
		"new_checkout_date": new_checkout_dt,
		"number_of_nights": number_of_nights,
		"extension_invoice": si.name,
		"amount": extension_amount
	})

	# Update the check-in document's checkout time and save it to persist the extension record
	check_in_doc.expected_check_out_datetime = new_expected_checkout
	check_in_doc.save(ignore_permissions=True)

	# Add a comment to the check-in document for history
	check_in_doc.add_comment(
		"Comment",
		text=_("Stay extended to {0}. New invoice {1} created for {2}.").format(new_expected_checkout, si.name, frappe.utils.fmt_money(extension_amount))
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
            f"New checkout must be earlier than current expected checkout: "
            f"{frappe.format_value(current_dt)}"
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
        credit_note = frappe.get_doc({
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
                    "amount": credit_amount
                }
            ],
            "posting_date": frappe.utils.today(),
            "remarks": f"Credit note for reduced stay ({diff_nights} nights)"
        })
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
        "credit_amount": credit_amount if diff_nights > 0 else 0
    }

@frappe.whitelist()
def adjust_stay(check_in_name, new_checkout):
    """
    Unified function for extending or reducing stay.
    Creates invoice (extension) or credit note (reduction) and logs adjustment in child table.
    """
    from frappe.utils import now_datetime, get_datetime, getdate, date_diff, flt
    
    doc = frappe.get_doc("Hotel Room Check In", check_in_name)
    
    # Convert to datetime objects
    new_dt = get_datetime(new_checkout)
    current_dt = get_datetime(doc.expected_check_out_datetime)
    checkin_dt = get_datetime(doc.check_in_datetime)
    now_dt = now_datetime()
    
    # VALIDATION 1: New checkout must be different from current
    if new_dt == current_dt:
        frappe.throw("New checkout is the same as current checkout. No adjustment needed.")
    
    # VALIDATION 2: New checkout must be after check-in
    if new_dt <= checkin_dt:
        frappe.throw("New checkout must be after check-in date/time.")
    
    # VALIDATION 3: Cannot be in the past
    if new_dt < now_dt:
        frappe.throw("New checkout cannot be in the past.")
    
    # Determine adjustment type
    adjustment_type = 'Extension' if new_dt > current_dt else 'Reduction'
    
    # VALIDATION 4: Special validation for reductions to "today"
    if adjustment_type == 'Reduction':
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
    new_nights = date_diff(getdate(new_dt), getdate(doc.check_in_datetime))
    if new_nights < 1:
        new_nights = 1
    
    # Calculate difference
    current_nights = doc.number_of_nights or 1
    diff_nights = abs(current_nights - new_nights)
    amount = flt(doc.rate_amount) * diff_nights
    
    # VALIDATION 5: Ensure there's actually a difference in nights
    if diff_nights == 0:
        frappe.throw("The new checkout results in the same number of nights. No adjustment needed.")
    
    adjustment_invoice_name = None
    
    try:
        if adjustment_type == 'Extension':
            # Create invoice for extra nights
            invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": doc.guest,
                "is_return": 0,
                "update_stock": 0,
                "check_in": doc.name,
                "custom_hotel_room_check_in": doc.name,
                "items": [{
                    "item_code": doc.room_type,
                    "qty": diff_nights,
                    "rate": doc.rate_amount,
                    "amount": amount
                }],
                "posting_date": frappe.utils.today(),
                "remarks": f"Invoice for stay extension: {diff_nights} additional night(s)"
            })
            invoice.insert()
            invoice.submit()
            adjustment_invoice_name = invoice.name
            
        else:  # Reduction
            # Create credit note
            credit_note = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": doc.guest,
                "is_return": 1,
                "update_stock": 0,
                "check_in": doc.name,
                "custom_hotel_room_check_in": doc.name,
                "items": [{
                    "item_code": doc.room_type,
                    "qty": -diff_nights,
                    "rate": doc.rate_amount,
                    "amount": amount
                }],
                "posting_date": frappe.utils.today(),
                "remarks": f"Credit note for stay reduction: {diff_nights} night(s) removed"
            })
            credit_note.insert()
            credit_note.submit()
            adjustment_invoice_name = credit_note.name
        
        # Add adjustment to child table
        doc.append('adjustments', {
            "adjustment_date": frappe.utils.now_datetime(),
            "adjustment_type": adjustment_type,
            "previous_checkout_datetime": doc.expected_check_out_datetime,
            "new_checkout_datetime": new_dt,
            "previous_number_of_nights": current_nights,
            "new_number_of_nights": new_nights,
            "nights_difference": diff_nights if adjustment_type == 'Extension' else -diff_nights,
            "adjustment_invoice": adjustment_invoice_name,
            "amount": amount
        })
        
        # Update parent doc
        doc.expected_check_out_datetime = new_dt
        doc.number_of_nights = new_nights
        doc.save()
        
        frappe.db.commit()
        
        return {
            "status": "success",
            "adjustment_type": adjustment_type,
            "new_checkout": str(new_dt),
            "previous_nights": current_nights,
            "new_nights": new_nights,
            "nights_difference": diff_nights if adjustment_type == 'Extension' else -diff_nights,
            "adjustment_invoice": adjustment_invoice_name,
            "amount": amount
        }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Stay Adjustment Error: {str(e)}", "adjust_stay")
        frappe.throw(f"Failed to process stay adjustment: {str(e)}")

def adjust_room_rate(check_in_doc, old_room_number, new_room_number):
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
		return

    # Calculate total difference for the remaining nights
	nightly_difference = new_rate - old_rate
	total_difference = nightly_difference * remaining_nights

	if total_difference == 0:
		frappe.logger().info(f"No rate change detected for transfer {check_in_doc.name}")
		return

	guest = check_in_doc.guest
	company = frappe.defaults.get_user_default("Company")
	posting_date = nowdate()
	default_income = frappe.db.get_value(
    	"Company",
    	company,
    	"default_income_account"
	)

	# Determine invoice type and direction
	
	if total_difference > 0:
		# Guest owes extra
		invoice_title = "Room Transfer Upgrade"
		is_refund = 0
		qty = 1
	else:
		# Refund guest
		# Create a refund request
		invoice_title = "Room Transfer Downgrade"
		is_refund = 1
		qty = -1

	
		# Create the invoice
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = guest
		invoice.company = company
		invoice.posting_date = posting_date
		invoice.is_return = bool(is_refund),
		invoice.remarks = _(
			"Room transfer from {0} to {1}. Rate adjusted for {2} remaining night(s)."
		).format(old_room_number, new_room_number, remaining_nights)
		invoice.custom_hotel_room_check_in = check_in_doc.name
		invoice.update_outstanding_for_self = bool(0)
		# Add line item
		invoice.append("items", {
			"item_name": invoice_title,
			"description": f"{invoice_title} for {remaining_nights} night(s)",
			"qty": qty,
			"rate": abs(total_difference),
			"income_account": default_income
		})

		invoice.save(ignore_permissions=True)
		invoice.submit()
  
		# create refund 
		
		refund = frappe.new_doc("Hotel Refund")
		refund.guest = guest
		refund.check_in = check_in_doc.name
		refund.refund_amount = abs(total_difference)
		refund.reason = f"Refund for Room Transfer from {old_room_number} to {new_room_number}"
		refund.credit_note = invoice.name,
		refund.status = "Approved",

		refund.insert(ignore_permissions=True)
		refund.submit()
  

	# Log comment on check-in
	check_in_doc.add_comment(
		"Comment",
		text=_(
			"Room rate adjusted due to transfer. Invoice {0} created for rate difference of {1} ({2} nights remaining)."
		).format(invoice.name, fmt_money(total_difference, 2), remaining_nights)
	)

	frappe.msgprint(
		_("Rate difference of {0} applied for {1} remaining night(s). Invoice {2} created.").format(
			fmt_money(total_difference, 2), remaining_nights, invoice.name
		),
		alert=True
	)

	frappe.db.commit()


@frappe.whitelist()
def transfer_room(check_in_name, new_room_number, note=None):
	check_in_doc = frappe.get_doc("Hotel Room Check In", check_in_name)

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
	old_room_doc.status = "Vacant"
	old_room_doc.current_guest = None
	old_room_doc.current_check_in = None
	old_room_doc.save(ignore_permissions=True)

	# Update the new room details
	new_room_doc.status = "Occupied"
	new_room_doc.current_guest = check_in_doc.guest
	new_room_doc.current_check_in = check_in_doc.name
	new_room_doc.save(ignore_permissions=True)

	# Update check-in document
	old_room_number = check_in_doc.room_number
	check_in_doc.room_number = new_room_number
	check_in_doc.db_set("room_number", new_room_number)
	check_in_doc.add_comment(
		"Comment",
		text=_("Guest transferred from Room {0} to Room {1}. {2}").format(
			old_room_number, new_room_number, note or ""
		)
	)

	# Log transfer history
	check_in_doc.append("transfer_history", {
		"transfer_datetime": now_datetime(),
		"from_room": old_room_number,
		"to_room": new_room_number,
		"reason": note,
		"user": frappe.session.user
	})
	check_in_doc.save(ignore_permissions=True)

	# Adjust rate if new room type has different tariff
	adjust_room_rate(check_in_doc, old_room_number, new_room_number)

	frappe.db.commit()
	frappe.publish_realtime('rhohotel_front_desk_update')

	return {
		"success": True,
		"message": _("Guest transferred successfully to Room {0}").format(new_room_number)
	}
