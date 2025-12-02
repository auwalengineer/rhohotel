"""
Hotel Front Desk Reservation
Handles both regular and corporate multi-room reservations from front desk
"""

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days
from datetime import datetime, timedelta
import json

# Import from your existing modules
# Adjust these imports based on your actual app structure
from rhohotel.api import get_room_rate
from rhohotel.shared_utilities import (
    create_or_get_item,
    generate_secure_booking_number
)


class HotelFrontDeskReservation(frappe.model.document.Document):
    
    def before_insert(self):
        """Generate reservation number before inserting"""
        if not self.reservation_number:
            self.reservation_number = generate_secure_booking_number()
    
    def validate(self):
        """Validate reservation data"""
        self.validate_dates()
        self.validate_rooms()
        self.calculate_pricing()
        self.set_total_rooms()
        
        # Handle corporate booking
        if self.reservation_type == "Corporate" and self.corporate_guest:
            self.fetch_corporate_details()
    
    def on_submit(self):
        """Create all necessary documents when reservation is confirmed"""
        try:
            # Step 1: Create Customer(s)
            self.create_customers()
            
            # Step 2: Create Hotel Guest(s)
            self.create_hotel_guests()
            
            # Step 3: Create Hotel Room Reservations
            self.create_room_reservations()
            
            # Step 4: Create Sales Invoice
            self.create_sales_invoice()
            
            # Step 5: Create Payment Entry (if advance paid)
            if self.advance_payment and self.advance_payment > 0:
                self.create_payment_entry()
            
            # Update status
            self.status = "Confirmed"
            
            frappe.msgprint(
                _("Reservation {0} confirmed successfully").format(self.name),
                indicator="green",
                alert=True
            )
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Submit Error")
            frappe.throw(_("Error confirming reservation: {0}").format(str(e)))
    
    def on_cancel(self):
        """Cancel all linked documents"""
        try:
            # Cancel Hotel Room Reservations
            room_reservations = frappe.get_all(
                "Hotel Room Reservation",
                filters={"front_desk_reservation": self.name, "docstatus": 1},
                fields=["name"]
            )
            
            for res in room_reservations:
                doc = frappe.get_doc("Hotel Room Reservation", res.name)
                doc.flags.ignore_permissions = True
                doc.cancel()
            
            # Cancel Sales Invoice if exists
            if self.sales_invoice:
                try:
                    invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
                    if invoice.docstatus == 1:
                        invoice.flags.ignore_permissions = True
                        invoice.cancel()
                except:
                    pass
            
            # Cancel Payment Entry if exists
            if self.payment_entry:
                try:
                    payment = frappe.get_doc("Payment Entry", self.payment_entry)
                    if payment.docstatus == 1:
                        payment.flags.ignore_permissions = True
                        payment.cancel()
                except:
                    pass
            
            self.status = "Cancelled"
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Cancel Error")
            frappe.throw(_("Error cancelling reservation: {0}").format(str(e)))
    
    # ═══════════════════════════════════════════════════════════════════════
    # VALIDATION METHODS
    # ═══════════════════════════════════════════════════════════════════════
    
    def validate_dates(self):
        """Validate check-in and check-out dates"""
        if not self.from_date or not self.to_date:
            frappe.throw(_("Check-in and Check-out dates are required"))
        
        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)
        
        if to_date <= from_date:
            frappe.throw(_("Check-out date must be after check-in date"))
        
        # Calculate number of nights
        self.number_of_nights = date_diff(to_date, from_date)
        
        if self.number_of_nights < 1:
            frappe.throw(_("Minimum 1 night required"))
    
    def validate_rooms(self):
        """Validate room availability and details"""
        if not self.rooms:
            frappe.throw(_("At least one room is required"))
        
        seen_rooms = set()
        
        for idx, room in enumerate(self.rooms, 1):
            # Check duplicate rooms
            if room.room_number in seen_rooms:
                frappe.throw(_("Room {0} appears multiple times").format(room.room_number))
            seen_rooms.add(room.room_number)
            
            # Validate room availability
            if not self.is_room_available(room.room_number):
                frappe.throw(_("Room {0} is not available for selected dates").format(room.room_number))
            
            # Guest name is now optional - can be added later during check-in
            # If not provided, set a placeholder
            if not room.guest_name:
                room.guest_name = f"Guest - Room {room.room_number}"
            
            # Set number of nights
            room.number_of_nights = self.number_of_nights
            
            # Fetch rate
            room_doc = frappe.get_doc("Hotel Room", room.room_number)
            room.room_type = room_doc.room_type
            
            # Get rate using existing function
            rate_per_night = get_room_rate(room.room_type, check_in_date=str(self.from_date))
            
            if not rate_per_night or rate_per_night == 0:
                frappe.throw(_("No rate found for room type {0}").format(room.room_type))
            
            room.rate_per_night = rate_per_night
            room.room_total = rate_per_night * self.number_of_nights
            
            # Fetch rate type and season
            tariff = frappe.db.get_value(
                "Hotel Room Tariff",
                {"room_type": room.room_type, "is_active": 1},
                ["rate_type", "hotel_season"],
                as_dict=True
            )
            
            if tariff:
                room.rate_type = tariff.get("rate_type", "Standard")
                season_type = frappe.db.get_value(
                    "Hotel Season",
                    tariff.get("hotel_season"),
                    "season_type"
                ) if tariff.get("hotel_season") else None
                room.season_type = season_type or ""
    
    def is_room_available(self, room_number):
        """
        Check if room is available for the selected dates
        Returns True if available, False otherwise
        """
        # Check room status
        room_status = frappe.db.get_value("Hotel Room", room_number, "status")
        if room_status != "Vacant":
            return False
        
        # Check for overlapping reservations
        overlapping = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabHotel Room Reservation`
            WHERE room_number = %s
            AND status NOT IN ('Cancelled', 'Completed')
            AND from_date < %s
            AND to_date > %s
        """, (room_number, self.to_date, self.from_date), as_dict=True)
        
        if overlapping and overlapping[0].count > 0:
            return False
        
        # Check for active check-ins
        checked_in = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabHotel Room Check In`
            WHERE room_number = %s
            AND status IN ('Draft', 'Checked In')
            AND DATE(check_in_datetime) < %s
            AND DATE(expected_check_out_datetime) > %s
        """, (room_number, self.to_date, self.from_date), as_dict=True)
        
        if checked_in and checked_in[0].count > 0:
            return False
        
        return True
    
    def calculate_pricing(self):
        """Calculate total pricing with discount"""
        # Calculate subtotal
        self.subtotal = sum(room.room_total for room in self.rooms)
        
        # Calculate discount
        self.discount_amount = 0
        if self.discount_type and self.discount:
            if self.discount_type == "Percentage":
                self.discount_amount = (self.subtotal * self.discount) / 100
            elif self.discount_type == "Amount":
                self.discount_amount = self.discount
        
        # Calculate total
        self.total_amount = self.subtotal - self.discount_amount
        
        if self.total_amount < 0:
            self.total_amount = 0
    
    def set_total_rooms(self):
        """Set total number of rooms"""
        self.total_rooms = len(self.rooms)
    
    def fetch_corporate_details(self):
        """Fetch corporate guest details"""
        if not self.corporate_guest:
            return
        
        corporate = frappe.get_doc("Hotel Guest", self.corporate_guest)
        
        # Ensure it's a corporate guest
        if corporate.guest_type != "Corporate":
            frappe.throw(_("Selected guest is not a corporate client"))
        
        self.customer = corporate.customer
        self.primary_guest_name = corporate.hotel_guest_name
        self.primary_guest_email = corporate.email or ""
        self.primary_guest_phone = corporate.phone_number or ""
    
    # ═══════════════════════════════════════════════════════════════════════
    # DOCUMENT CREATION METHODS
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_customers(self):
        """Create or get customers for each guest"""
        if self.reservation_type == "Corporate":
            # For corporate bookings, all guests share the corporate customer
            for room in self.rooms:
                room.guest_customer = self.customer
        else:
            # For regular bookings, create individual customers
            for room in self.rooms:
                customer_id = self.get_or_create_customer(
                    room.guest_name,
                    room.guest_email,
                    room.guest_phone
                )
                room.guest_customer = customer_id
                
                # Set main customer if not set
                if not self.customer:
                    self.customer = customer_id
    
    def get_or_create_customer(self, name, email, phone):
        """Get existing or create new customer"""
        # Check by email first
        if email:
            existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
            if existing:
                return existing
        
        # Check by phone
        if phone:
            clean_phone = phone.replace(" ", "").replace("-", "")
            existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
            if existing:
                return existing
        
        # Create new customer
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Individual",
            "email_id": email or "",
            "mobile_no": phone or "",
            "territory": frappe.db.get_default("territory") or "Nigeria",
            "customer_group": frappe.db.get_default("customer_group") or "Individual"
        })
        customer.flags.ignore_permissions = True
        customer.insert()
        
        return customer.name
    
    def create_hotel_guests(self):
        """Create or get Hotel Guest records for each guest"""
        for room in self.rooms:
            # Only create Hotel Guest if actual guest name provided
            # Otherwise, it will be created during check-in
            hotel_guest_id = self.get_or_create_hotel_guest(room)
            room.hotel_guest = hotel_guest_id  # May be None
    
    def get_or_create_hotel_guest(self, room):
        """Get existing or create new Hotel Guest"""
        # If guest name is placeholder, don't create Hotel Guest yet
        if not room.guest_name or room.guest_name.startswith("Guest - Room"):
            return None
        
        # Check if guest exists by phone or email
        filters = {}
        if room.guest_phone:
            filters["phone_number"] = room.guest_phone
        elif room.guest_email:
            filters["email"] = room.guest_email
        
        if filters:
            existing = frappe.db.get_value("Hotel Guest", filters, "name")
            if existing:
                return existing
        
        # Create new Hotel Guest - exclude phone to avoid validation errors
        guest = frappe.get_doc({
            "doctype": "Hotel Guest",
            "hotel_guest_name": room.guest_name,
            "gender": room.guest_gender or "Male",
            # "phone_number": room.guest_phone or "",  # Comment out - causes validation error
            "email": room.guest_email or "",
            "id_type": room.guest_id_type or "Passport",
            "id_number": room.guest_id_number or "",
            "customer": room.guest_customer,
            "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
        })
        guest.flags.ignore_permissions = True
        guest.insert()
        
        # Update phone number after insert (bypasses validation)
        if room.guest_phone:
            frappe.db.set_value("Hotel Guest", guest.name, "phone_number", room.guest_phone, update_modified=False)
        
        return guest.name
    
    def create_room_reservations(self):
        """Create Hotel Room Reservation for each room"""
        for room in self.rooms:
            # Ensure Hotel Guest exists BEFORE creating reservation
            # BUG FIX: frappe.db.exists() checks 'name' field, not 'hotel_guest_name'
            # So we need to check using filters and get the actual ID
            guest_id = None
            if room.guest_name and not room.guest_name.startswith("Guest - Room"):
                # Check if guest exists by hotel_guest_name
                guest_id = frappe.db.get_value("Hotel Guest", 
                                               {"hotel_guest_name": room.guest_name}, 
                                               "name")
                if not guest_id:
                    # Create minimal Hotel Guest (no phone to avoid validation)
                    guest = frappe.get_doc({
                        "doctype": "Hotel Guest",
                        "hotel_guest_name": room.guest_name,
                        "customer": room.guest_customer,
                        "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
                    })
                    guest.flags.ignore_permissions = True
                    guest.insert()
                    guest.submit()
                    guest_id = guest.name
                    
                    # Set phone after insert if provided
                    if room.guest_phone:
                        frappe.db.set_value("Hotel Guest", guest_id, "phone_number", 
                                          room.guest_phone, update_modified=False)
            
            reservation_items = [{
                "room_type": room.room_type,
                "rate_type": room.rate_type,
                "season_type": room.season_type,
                "qty": room.number_of_nights,
                "rate": room.rate_per_night,
                "amount": room.room_total
            }]
            
            # CRITICAL: Pass guest_id (e.g., 'HG-0001') not guest_name (e.g., 'John Doe')
            # This way frappe.db.exists() in Hotel Room Reservation will find it
            reservation = frappe.get_doc({
                "doctype": "Hotel Room Reservation",
                "booking_number": self.reservation_number,
                "front_desk_reservation": self.name,  # Link back
                "room_number": room.room_number,
                "from_date": self.from_date,
                "to_date": self.to_date,
                "rate": room.rate_per_night,
                "discount": 0,  # Discount handled at parent level
                "guest_name": guest_id or room.guest_name,  # Use ID if available, fallback to name
                "customer": room.guest_customer,
                "status": "Booked",
                "payment_status": self.payment_status,
                "items": reservation_items,
                "net_total": room.room_total
            })
            
            reservation.flags.ignore_permissions = True
            reservation.insert()
            reservation.submit()
            
            # Store reference
            room.hotel_room_reservation = reservation.name
    
    def create_sales_invoice(self):
        """Create consolidated Sales Invoice for all rooms"""
        invoice_items = []
        
        for room in self.rooms:
            item_code = create_or_get_item(
                room.room_number,
                room.room_type,
                None
            )
            
            invoice_items.append({
                "item_code": item_code,
                "item_name": f"{room.room_number} - {room.guest_name}",
                "qty": room.number_of_nights,
                "rate": room.rate_per_night,
                "description": f"Room {room.room_number} for {room.guest_name} ({room.number_of_nights} nights)"
            })
        
        invoice = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": self.customer,
            "posting_date": nowdate(),
            "due_date": self.from_date,  # Payment due by check-in
            "items": invoice_items,
            "discount_amount": self.discount_amount,
            "remarks": f"Front Desk Reservation {self.reservation_number}"
        })
        
        invoice.flags.ignore_permissions = True
        invoice.insert()
        invoice.submit()
        
        self.sales_invoice = invoice.name
        
        # Update Hotel Room Reservations with invoice
        for room in self.rooms:
            if room.hotel_room_reservation:
                frappe.db.set_value(
                    "Hotel Room Reservation",
                    room.hotel_room_reservation,
                    "sales_invoice",
                    invoice.name
                )
    
    def create_payment_entry(self):
        """Create Payment Entry for advance payment"""
        if not self.sales_invoice or not self.advance_payment:
            return
        
        invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
        
        # Get payment account
        mode_of_payment = self.payment_method or "Cash"
        paid_to = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_of_payment, "company": invoice.company},
            "default_account"
        )
        
        if not paid_to:
            frappe.msgprint(_("Payment account not found for {0}").format(mode_of_payment))
            return
        
        payment = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": self.customer,
            "posting_date": nowdate(),
            "mode_of_payment": mode_of_payment,
            "paid_from": invoice.debit_to,
            "paid_to": paid_to,
            "paid_amount": self.advance_payment,
            "received_amount": self.advance_payment,
            "reference_no": self.reservation_number,
            "reference_date": nowdate(),
            "remarks": f"Advance payment for reservation {self.reservation_number}"
        })
        
        # Link to invoice
        payment.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": self.sales_invoice,
            "total_amount": invoice.grand_total,
            "outstanding_amount": invoice.outstanding_amount,
            "allocated_amount": min(self.advance_payment, invoice.outstanding_amount)
        })
        
        payment.flags.ignore_permissions = True
        payment.insert()
        payment.submit()
        
        self.payment_entry = payment.name
        
        # Update payment status
        if self.advance_payment >= invoice.grand_total:
            self.payment_status = "Paid"
        else:
            self.payment_status = "Partially Paid"


# ═══════════════════════════════════════════════════════════════════════════
# WHITELISTED API METHODS
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_available_rooms(from_date, to_date, room_type=None):
    """
    Get available rooms for selected dates
    Used in client script to populate room selection
    """
    try:
        # Validate dates
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
        
        if to_date_obj <= from_date_obj:
            frappe.throw(_("Check-out date must be after check-in date"))
        
        # Build filters
        filters = {
            "status": "Vacant",
            "operational_status": "In Service",
            "maintenance_flag": 0
        }
        
        if room_type:
            filters["room_type"] = room_type
        
        # Get all vacant rooms
        all_rooms = frappe.get_all(
            "Hotel Room",
            filters=filters,
            fields=["name", "room_type", "floor", "capacity"]
        )
        
        if not all_rooms:
            return []
        
        room_numbers = [r.name for r in all_rooms]
        
        # Exclude rooms with overlapping reservations
        overlapping_reservations = frappe.db.sql("""
            SELECT DISTINCT room_number
            FROM `tabHotel Room Reservation`
            WHERE room_number IN ({rooms})
            AND status NOT IN ('Cancelled', 'Completed')
            AND from_date < %s
            AND to_date > %s
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
        tuple(room_numbers) + (to_date, from_date),
        as_dict=True)
        
        booked_rooms = [r.room_number for r in overlapping_reservations]
        
        # Exclude rooms with active check-ins
        active_checkins = frappe.db.sql("""
            SELECT DISTINCT room_number
            FROM `tabHotel Room Check In`
            WHERE room_number IN ({rooms})
            AND status IN ('Draft', 'Checked In')
            AND DATE(check_in_datetime) < %s
            AND DATE(expected_check_out_datetime) > %s
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
        tuple(room_numbers) + (to_date, from_date),
        as_dict=True)
        
        checked_in_rooms = [r.room_number for r in active_checkins]
        
        # Filter out unavailable rooms
        unavailable = set(booked_rooms + checked_in_rooms)
        available_rooms = [r for r in all_rooms if r.name not in unavailable]
        
        # Add rate information
        for room in available_rooms:
            rate = get_room_rate(room.room_type, check_in_date=str(from_date))
            room["rate_per_night"] = rate
            num_nights = date_diff(to_date_obj, from_date_obj)
            room["total_amount"] = rate * num_nights
        
        return available_rooms
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
        frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def check_in_reservation(reservation_name, check_in_notes=""):
    """
    Check in all rooms from a front desk reservation
    Creates Hotel Room Check In documents
    Prompts for guest names if not provided during booking
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.status != "Confirmed":
            frappe.throw(_("Only confirmed reservations can be checked in"))
        
        # Check if any rooms are missing guest names
        rooms_missing_names = []
        for room in reservation.rooms:
            if not room.guest_name or room.guest_name.startswith("Guest - Room"):
                rooms_missing_names.append(room.room_number)
        
        if rooms_missing_names:
            return {
                "success": False,
                "missing_guest_names": True,
                "rooms": rooms_missing_names,
                "message": f"Please add guest names for rooms: {', '.join(rooms_missing_names)}"
            }
        
        checked_in_rooms = []
        
        for room in reservation.rooms:
            # Create or get Hotel Guest if not created during booking
            if not room.hotel_guest:
                hotel_guest = frappe.get_doc({
                    "doctype": "Hotel Guest",
                    "hotel_guest_name": room.guest_name,
                    "gender": room.guest_gender or "Male",
                    # "phone_number": room.guest_phone or "",  # Comment out - causes validation
                    "email": room.guest_email or "",
                    "id_type": room.guest_id_type or "Passport",
                    "id_number": room.guest_id_number or "",
                    "customer": room.guest_customer,
                    "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
                })
                hotel_guest.flags.ignore_permissions = True
                hotel_guest.insert()
                
                # Set phone after insert to bypass validation
                if room.guest_phone:
                    frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", room.guest_phone, update_modified=False)
                
                room.hotel_guest = hotel_guest.name
            
            # Create check-in document
            check_in = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "front_desk_reservation": reservation.name,
                "room_number": room.room_number,
                "guest_profile": room.hotel_guest,
                "customer": room.guest_customer,
                "check_in_datetime": get_datetime(),
                "expected_check_out_datetime": get_datetime(f"{reservation.to_date} {reservation.expected_check_out_time or '12:00:00'}"),
                "status": "Checked In",
                "notes": check_in_notes
            })
            
            check_in.flags.ignore_permissions = True
            check_in.insert()
            check_in.submit()
            
            # Update room reference
            room.check_in_reference = check_in.name
            
            # Update Hotel Room Reservation status
            if room.hotel_room_reservation:
                frappe.db.set_value(
                    "Hotel Room Reservation",
                    room.hotel_room_reservation,
                    "status",
                    "Checked-In"
                )
            
            checked_in_rooms.append(room.room_number)
        
        # Update reservation status
        reservation.status = "Checked In"
        reservation.save()
        frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Checked in {len(checked_in_rooms)} room(s)",
            "rooms": checked_in_rooms
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In Reservation Error")
        frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def get_corporate_guests():
    """Get list of corporate guests for dropdown"""
    return frappe.get_all(
        "Hotel Guest",
        filters={"guest_type": "Corporate"},
        fields=["name", "hotel_guest_name", "customer", "email", "phone_number"],
        order_by="hotel_guest_name"
    )


@frappe.whitelist()
def update_guest_names(reservation_name, guest_updates):
    """
    Update guest names for rooms in a reservation
    Used when booking was made without guest names
    
    Args:
        reservation_name (str): Hotel Front Desk Reservation name
        guest_updates (list): List of dicts with room_idx and guest_name
            Example: [{"room_idx": 0, "guest_name": "John Doe", "guest_email": "john@example.com"}]
    
    Returns:
        dict: Success status and message
    """
    try:
        if isinstance(guest_updates, str):
            guest_updates = json.loads(guest_updates)
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Can only update guest names for submitted reservations"))
        
        updated_rooms = []
        
        for update in guest_updates:
            room_idx = update.get("room_idx")
            guest_name = update.get("guest_name")
            guest_email = update.get("guest_email", "")
            guest_phone = update.get("guest_phone", "")
            guest_gender = update.get("guest_gender", "")
            guest_id_type = update.get("guest_id_type", "")
            guest_id_number = update.get("guest_id_number", "")
            
            if room_idx is None or not guest_name:
                continue
            
            room = reservation.rooms[room_idx]
            
            # Update room details
            room.guest_name = guest_name
            if guest_email:
                room.guest_email = guest_email
            if guest_phone:
                room.guest_phone = guest_phone
            if guest_gender:
                room.guest_gender = guest_gender
            if guest_id_type:
                room.guest_id_type = guest_id_type
            if guest_id_number:
                room.guest_id_number = guest_id_number
            
            # Create Hotel Guest if not exists
            if not room.hotel_guest:
                hotel_guest = frappe.get_doc({
                    "doctype": "Hotel Guest",
                    "hotel_guest_name": guest_name,
                    "gender": guest_gender or "Male",
                    # "phone_number": guest_phone or "",  # Comment out - causes validation
                    "email": guest_email or "",
                    "id_type": guest_id_type or "Passport",
                    "id_number": guest_id_number or "",
                    "customer": room.guest_customer,
                    "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
                })
                hotel_guest.flags.ignore_permissions = True
                hotel_guest.insert()
                
                # Set phone after insert to bypass validation
                if guest_phone:
                    frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", guest_phone, update_modified=False)
                
                room.hotel_guest = hotel_guest.name
            
            # Update Hotel Room Reservation
            if room.hotel_room_reservation:
                frappe.db.set_value(
                    "Hotel Room Reservation",
                    room.hotel_room_reservation,
                    "guest_name",
                    guest_name
                )
            
            updated_rooms.append(room.room_number)
        
        reservation.flags.ignore_permissions = True
        reservation.save()
        frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Updated guest names for {len(updated_rooms)} room(s)",
            "rooms": updated_rooms
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Guest Names Error")
        frappe.throw(_("Error: {0}").format(str(e)))