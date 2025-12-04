# # # REFACTORED Hotel Front Desk Reservation v2
# # # KEY CHANGE: Corporate bookings do NOT create Hotel Room Reservations on submit
# # # Instead: Create them during check-in (one at a time or all at once)
# # # Non-corporate: Still create reservations on submit (original behavior)

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days, now_datetime
from datetime import datetime, timedelta
import json

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
        
        if self.reservation_type == "Corporate" and self.corporate_guest:
            self.fetch_corporate_details()
    
    def on_submit(self):
        """
        REFACTORED v2:
        - Corporate: Create customers + guests ONLY (no room reservations)
        - Non-corporate: Create customers + guests + room reservations (original)
        """
        try:
            self.create_customers()
            self.create_hotel_guests_with_names()
            
            self.create_room_reservations()
        
            self.status = "Confirmed"
            self.db_set("status", "Confirmed")
            
            frappe.msgprint(
                _("Reservation {0} confirmed. Hotel room reservations created.").format(self.name),
                indicator="green",
                alert=True
            )
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Submit Error")
            frappe.throw(_("Error confirming reservation: {0}").format(str(e)))
    
    def on_cancel(self):
        """Cancel all linked Hotel Room Reservations (only applies to non-corporate)"""
        try:
            room_reservations = frappe.get_all(
                "Hotel Room Reservation",
                filters={"front_desk_reservation": self.name, "docstatus": 1},
                fields=["name"]
            )
            
            for res in room_reservations:
                doc = frappe.get_doc("Hotel Room Reservation", res.name)
                doc.flags.ignore_permissions = True
                doc.cancel()
            
            self.status = "Cancelled"
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Cancel Error")
            frappe.throw(_("Error cancelling reservation: {0}").format(str(e)))
    
    # ═══════════════════════════════════════════════════════════════════════
    # VALIDATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def validate_dates(self):
        """Validate check-in and check-out dates"""
        if not self.from_date or not self.to_date:
            frappe.throw(_("Check-in and Check-out dates are required"))
        
        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)
        
        if to_date <= from_date:
            frappe.throw(_("Check-out date must be after check-in date"))
        
        self.number_of_nights = date_diff(to_date, from_date)
        
        if self.number_of_nights < 1:
            frappe.throw(_("Minimum 1 night required"))
    
    def validate_rooms(self):
        """Validate room availability and details"""
        if not self.rooms:
            frappe.throw(_("At least one room is required"))
        
        seen_rooms = set()
        
        for idx, room in enumerate(self.rooms, 1):
            if room.room_number in seen_rooms:
                frappe.throw(_("Room {0} appears multiple times").format(room.room_number))
            seen_rooms.add(room.room_number)
            
            if not self.is_room_available(room.room_number):
                frappe.throw(_("Room {0} is not available for selected dates").format(room.room_number))
            
            if not room.guest_name:
                # room.guest_name = f"Guest - Room {room.room_number}"
                room.guest_name = self.primary_guest_name or f"Guest - Room {room.room_number}"
            
            room.number_of_nights = self.number_of_nights
            
            room_doc = frappe.get_doc("Hotel Room", room.room_number)
            room.room_type = room_doc.room_type
            
            rate_per_night = get_room_rate(room.room_type, check_in_date=str(self.from_date))
            
            if not rate_per_night or rate_per_night == 0:
                frappe.throw(_("No rate found for room type {0}").format(room.room_type))
            
            room.rate_per_night = rate_per_night
            room.room_total = rate_per_night * self.number_of_nights
            
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
        """Check if room is available for the selected dates"""
        # room_status = frappe.db.get_value("Hotel Room", room_number, "status")
        # if room_status != "Vacant":
        #     return False
        
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
        self.subtotal = sum(room.room_total for room in self.rooms)
        
        self.discount_amount = 0
        if self.discount_type and self.discount:
            if self.discount_type == "Percentage":
                self.discount_amount = (self.subtotal * self.discount) / 100
            elif self.discount_type == "Amount":
                self.discount_amount = self.discount
        
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
        
        if corporate.guest_type != "Corporate":
            frappe.throw(_("Selected guest is not a corporate client"))
        
        self.customer = corporate.customer
        self.primary_guest_name = corporate.hotel_guest_name
        self.primary_guest_email = corporate.email or ""
        self.primary_guest_phone = corporate.phone_number or ""
    
    # ═══════════════════════════════════════════════════════════════════════
    # DOCUMENT CREATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_customers(self):
        """Create or get customers for each guest"""
        if self.reservation_type == "Corporate":
            for room in self.rooms:
                room.guest_customer = self.customer
        else:
            for room in self.rooms:
                customer_id = self.get_or_create_customer(
                    room.guest_name,
                    room.guest_email,
                    room.guest_phone
                )
                room.guest_customer = customer_id
                
                if not self.customer:
                    self.customer = customer_id
    
    def get_or_create_customer(self, name, email, phone):
        """Get existing or create new customer"""
        if email:
            existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
            if existing:
                return existing
        
        if phone:
            clean_phone = phone.replace(" ", "").replace("-", "")
            existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
            if existing:
                return existing
        
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
    
    def create_hotel_guests_with_names(self):
        """
        Create Hotel Guests with smart name handling:
        - If room has guest_name: use it
        - Else if corporate: use corporate_guest name
        - Else: use primary_guest_name
        - If still none: mark as missing (will need to add during check-in)
        """
        rooms_missing_names = []
        
        for room in self.rooms:
            guest_name = room.guest_name
            
            # Try to derive name if missing
            if not guest_name or guest_name.startswith("Guest - Room"):
                if self.reservation_type == "Corporate" and self.primary_guest_name:
                    guest_name = self.primary_guest_name
                elif self.primary_guest_name:
                    guest_name = self.primary_guest_name
                
                # Still no name?
                if not guest_name or guest_name.startswith("Guest - Room"):
                    rooms_missing_names.append(room.room_number)
                    continue
                else:
                    room.guest_name = guest_name
            
            # Create guest
            self.get_or_create_hotel_guest(room)
        
        # Notify if any rooms missing names (for corporate, this is expected)
        if rooms_missing_names and self.reservation_type != "Corporate":
            frappe.msgprint({
                'title': _('Guest Names Required'),
                'message': _('The following rooms do not have guest names: {0}').format(', '.join(rooms_missing_names)),
                'indicator': 'orange'
            })
    
    def get_or_create_hotel_guest(self, room):
        """Create Hotel Guest if not exists"""
        guest_name = room.guest_name
        
        if not guest_name or guest_name.startswith("Guest - Room"):
            return None
        
        if frappe.db.exists("Hotel Guest", {'hotel_guest_name': guest_name}):
            room.hotel_guest = guest_name
            return guest_name
        
        try:
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": room.guest_phone or "",
                "email": room.guest_email or "",
                "gender": room.guest_gender or "Male",
                "id_type": room.guest_id_type or "Passport",
                "id_number": room.guest_id_number or "",
                "customer": room.guest_customer,
                "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
            })
            guest.flags.ignore_permissions = True
            guest.insert()
            room.hotel_guest = guest.name
            return guest.name
            
        except frappe.exceptions.InvalidPhoneNumberError:
            # Retry without phone
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": "",
                "email": room.guest_email or "",
                "gender": room.guest_gender or "Male",
                "id_type": room.guest_id_type or "Passport",
                "id_number": room.guest_id_number or "",
                "customer": room.guest_customer,
                "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
            })
            guest.flags.ignore_permissions = True
            guest.insert()
            
            if room.guest_phone:
                frappe.db.set_value(
                    "Hotel Guest",
                    guest.name,
                    "phone_number",
                    room.guest_phone,
                    update_modified=False
                )
            
            room.hotel_guest = guest.name
            return guest.name
    
    def create_room_reservations(self):
        """Create Hotel Room Reservations (NON-CORPORATE ONLY)"""
        for room in self.rooms:
            reservation_items = [{
                "room_type": room.room_type,
                "rate_type": room.rate_type,
                "season_type": room.season_type,
                "qty": room.number_of_nights,
                "rate": room.rate_per_night,
                "amount": room.room_total
            }]
            
            reservation = frappe.get_doc({
                "doctype": "Hotel Room Reservation",
                "booking_number": self.reservation_number,
                "front_desk_reservation": self.name,
                "room_number": room.room_number,
                "from_date": self.from_date,
                "to_date": self.to_date,
                "rate": room.rate_per_night,
                "discount": 0,
                "guest_name": room.guest_name,
                "customer": room.guest_customer,
                "status": "Booked",
                "payment_status": "Pending",
                "items": reservation_items,
                "net_total": room.room_total,
                "reservation_type": 'Corporate' if self.reservation_type == 'Corporate' else 'Individual'
            })
            
            reservation.flags.ignore_permissions = True
            reservation.insert()
            reservation.submit()


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def create_room_reservation_for_checkin(reservation_name, room_idx):
    """
    NEW: Create Hotel Room Reservation for a specific room during check-in
    Called from check-in dialog (corporate bookings)
    
    Args:
        reservation_name: Front Desk Reservation name
        room_idx: Index of room in rooms table (0-based)
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        # Get the specific room
        if room_idx >= len(reservation.rooms):
            frappe.throw(_("Invalid room index"))
        
        room = reservation.rooms[room_idx]
        
        # Check if already created
        if room.hotel_room_reservation:
            return {
                "success": False,
                "message": _("Reservation already exists for room {0}").format(room.room_number)
            }
        
        # Create the reservation
        reservation_items = [{
            "room_type": room.room_type,
            "rate_type": room.rate_type,
            "season_type": room.season_type,
            "qty": room.number_of_nights,
            "rate": room.rate_per_night,
            "amount": room.room_total
        }]
        
        hrr = frappe.get_doc({
            "doctype": "Hotel Room Reservation",
            "booking_number": reservation.reservation_number,
            "front_desk_reservation": reservation.name,
            "room_number": room.room_number,
            "from_date": reservation.from_date,
            "to_date": reservation.to_date,
            "rate": room.rate_per_night,
            "discount": 0,
            "guest_name": room.guest_name,
            "customer": room.guest_customer,
            "status": "Booked",
            "payment_status": "Pending",
            "items": reservation_items,
            "net_total": room.room_total,
            "reservation_type": 'Corporate' if reservation.reservation_type == 'Corporate' else 'Individual'
        })
        
        hrr.flags.ignore_permissions = True
        hrr.insert()
        hrr.submit()
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Reservation created for room {0}").format(room.room_number),
            "reservation_name": hrr.name
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Room Reservation Error")
        frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def create_all_room_reservations(reservation_name):
    """
    NEW: Create Hotel Room Reservations for ALL rooms at once
    Called from check-in dialog (corporate bookings)
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        created_count = 0
        already_exist = 0
        
        for idx, room in enumerate(reservation.rooms):
            # Skip if already created
            if room.hotel_room_reservation:
                already_exist += 1
                continue
            
            # Create reservation
            reservation_items = [{
                "room_type": room.room_type,
                "rate_type": room.rate_type,
                "season_type": room.season_type,
                "qty": room.number_of_nights,
                "rate": room.rate_per_night,
                "amount": room.room_total
            }]
            
            hrr = frappe.get_doc({
                "doctype": "Hotel Room Reservation",
                "booking_number": reservation.reservation_number,
                "front_desk_reservation": reservation.name,
                "room_number": room.room_number,
                "from_date": reservation.from_date,
                "to_date": reservation.to_date,
                "rate": room.rate_per_night,
                "discount": 0,
                "guest_name": room.guest_name,
                "customer": room.guest_customer,
                "status": "Booked",
                "payment_status": "Pending",
                "items": reservation_items,
                "net_total": room.room_total
            })
            
            hrr.flags.ignore_permissions = True
            hrr.insert()
            hrr.submit()
            
            created_count += 1
        
        frappe.db.commit()
        
        message = _("Created {0} reservation(s)").format(created_count)
        if already_exist > 0:
            message += _(", {0} already exist(s)").format(already_exist)
        
        return {
            "success": True,
            "message": message,
            "created": created_count,
            "already_exist": already_exist
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create All Room Reservations Error")
        frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def check_in_reservation(reservation_name, check_in_notes="", create_reservations=False):
    """
    Check in all rooms from a reservation
    For corporate: optionally create room reservations first
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        # Check if reservation is submitted (docstatus=1)
        # Don't check the status field as it may vary
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before checking in guests"))
        
        # For corporate, create reservations if needed
        if create_reservations and reservation.reservation_type == "Corporate":
            result = create_all_room_reservations(reservation_name)
            if not result.get("success"):
                frappe.throw(_("Failed to create room reservations"))
            # Reload to get updated references
            reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        # Auto-fill guest names from primary guest if not provided
        for room in reservation.rooms:
            if not room.guest_name or room.guest_name.startswith("Guest - Room"):
                # Use primary guest name
                if reservation.primary_guest_name:
                    room.guest_name = reservation.primary_guest_name
                else:
                    # Fallback: use a generic name
                    room.guest_name = f"Guest - Room {room.room_number}"
        
        checked_in_rooms = []
        
        for room in reservation.rooms:
            if not room.hotel_guest:
                # Use the guest name from FDR room for consistency
                # This ensures the check-in data matches the reservation
                guest_name = room.guest_name
                
                # Check if guest already exists
                existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
                
                if existing_guest:
                    # Guest already exists, reuse it
                    room.hotel_guest = existing_guest
                else:
                    try:
                        # Create new guest with FDR guest name
                        hotel_guest = frappe.get_doc({
                            "doctype": "Hotel Guest",
                            "hotel_guest_name": guest_name,
                            "gender": room.guest_gender or "Male",
                            "phone_number": room.guest_phone or "",
                            "email": room.guest_email or "",
                            "id_type": room.guest_id_type or "Passport",
                            "id_number": room.guest_id_number or "",
                            "customer": room.guest_customer,
                            "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
                        })
                        hotel_guest.flags.ignore_permissions = True
                        hotel_guest.insert()
                        
                        if room.guest_phone:
                            frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", room.guest_phone, update_modified=False)
                        
                        room.hotel_guest = hotel_guest.name
                    except frappe.DuplicateEntryError:
                        # Guest was created by another process, get it
                        existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
                        if existing_guest:
                            room.hotel_guest = existing_guest
                        else:
                            # If still not found, use the original name (will be handled by system)
                            room.hotel_guest = guest_name
            
            # Create check-in
            check_in = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "guest": room.hotel_guest,
                "room_number": room.room_number,
                "check_in_datetime": now_datetime(),
                "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
                "expected_check_out_datetime": get_datetime(f"{reservation.to_date} {reservation.expected_check_out_time or '12:00:00'}"),
                "rate_amount": room.rate_per_night or 0,
                "status": "Checked In"
            })
            
            check_in.flags.ignore_permissions = True
            check_in.insert()
            check_in.submit()
            
            # Update room reservation if exists
            if room.hotel_room_reservation:
                frappe.db.set_value(
                    "Hotel Room Reservation",
                    room.hotel_room_reservation,
                    "status",
                    "Checked-In"
                )
            
            checked_in_rooms.append(room.room_number)
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Checked in {0} room(s)").format(len(checked_in_rooms)),
            "rooms": checked_in_rooms
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In Reservation Error")
        frappe.throw(_("Error: {0}").format(str(e)))




# @frappe.whitelist()
# def get_available_rooms_for_dropdown(doctype, txt, searchfield, start, page_length, filters, **kwargs):
#     """
#     ✅ FIXED: Query method for room_number dropdown in child table
    
#     Called from set_query in client script for room_number field
#     This ensures the room_number dropdown ONLY shows rooms that are:
#     - Vacant
#     - In Service
#     - Not in maintenance
#     - NOT held by active Temporary Bookings
#     - NOT booked with overlapping reservations
#     - NOT currently checked in
    
#     Args:
#         doctype: 'Hotel Room'
#         txt: Search text
#         searchfield: 'name' (room number)
#         start: Pagination start
#         page_length: Number of results
#         filters: Base filters
#         **kwargs: Contains from_date, to_date, room_type
#     """
#     try:
#         # Extract dates from kwargs
#         from_date = kwargs.get('from_date')
#         to_date = kwargs.get('to_date')
#         room_type = kwargs.get('room_type')
        
#         # If dates not provided, return vacant rooms only
#         if not from_date or not to_date:
#             all_rooms = frappe.get_all(
#                 "Hotel Room",
#                 # filters={
#                 #     "status": "Vacant",
#                 #     "operational_status": "In Service",
#                 #     "maintenance_flag": 0
#                 # },
#                 fields=["name"],
#                 limit_page_length=int(page_length) if page_length else 10,
#                 order_by="name asc"
#             )
#             return [[r.name] for r in all_rooms]
        
#         # Parse dates
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             return []
        
#         # ═══════════════════════════════════════════════════════════════════
#         # STEP 1: Get base vacant rooms
#         # ═══════════════════════════════════════════════════════════════════
#         # base_filters = {
#         #     "status": "Vacant",
#         #     "operational_status": "In Service",
#         #     "maintenance_flag": 0
#         # }
        
#         if room_type:
#             base_filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             # filters=base_filters,
#             fields=["name", "room_type", "floor", "capacity"],
#             # limit_page_length=int(page_length) if page_length else 10,
#             order_by="name asc"
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
#         # ═══════════════════════════════════════════════════════════════════
#         # STEP 2: ✅ CRITICAL: Get held rooms from Temporary Booking
#         # ═══════════════════════════════════════════════════════════════════
#         current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
#         held_rooms_query = frappe.db.sql("""
#             SELECT DISTINCT tbr.room_number
#             FROM `tabTemporary Booking` tb
#             INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
#             WHERE tbr.room_number IN ({rooms})
#             AND tb.status IN ('Hold', 'Payment Link Generated')
#             AND tb.payment_status = 'Pending'
#             AND tb.booking_status = 'Held'
#             AND tb.hold_expires_at > %s
#         """.format(rooms=", ".join(["%s"] * len(room_numbers))),
#         tuple(room_numbers) + (current_time,),
#         as_dict=True)
        
#         held_room_list = set([r.room_number for r in held_rooms_query])
        
#         # ═══════════════════════════════════════════════════════════════════
#         # STEP 3: Get booked rooms with overlapping reservations
#         # ═══════════════════════════════════════════════════════════════════
#         overlapping_reservations = frappe.db.sql("""
#             SELECT DISTINCT room_number
#             FROM `tabHotel Room Reservation`
#             WHERE room_number IN ({rooms})
#             AND status NOT IN ('Cancelled', 'Completed')
#             AND from_date < %s
#             AND to_date > %s
#         """.format(rooms=", ".join(["%s"] * len(room_numbers))),
#         tuple(room_numbers) + (to_date, from_date),
#         as_dict=True)
        
#         booked_room_list = set([r.room_number for r in overlapping_reservations])
        
#         # ═══════════════════════════════════════════════════════════════════
#         # STEP 4: Get checked-in rooms
#         # ═══════════════════════════════════════════════════════════════════
#         active_checkins = frappe.db.sql("""
#             SELECT DISTINCT room_number
#             FROM `tabHotel Room Check In`
#             WHERE room_number IN ({rooms})
#             AND status IN ('Draft', 'Checked In')
#             AND DATE(check_in_datetime) < %s
#             AND DATE(expected_check_out_datetime) > %s
#         """.format(rooms=", ".join(["%s"] * len(room_numbers))),
#         tuple(room_numbers) + (to_date, from_date),
#         as_dict=True)
        
#         checked_in_room_list = set([r.room_number for r in active_checkins])
        
#         # ═══════════════════════════════════════════════════════════════════
#         # STEP 5: ✅ Combine all unavailable rooms
#         # ═══════════════════════════════════════════════════════════════════
#         unavailable_rooms = held_room_list | booked_room_list | checked_in_room_list
        
#         # ═══════════════════════════════════════════════════════════════════
#         # STEP 6: Filter and return available rooms
#         # ═══════════════════════════════════════════════════════════════════
#         available_rooms = [r.name for r in all_rooms if r.name not in unavailable_rooms]
        
#         # Return as list of tuples for dropdown
#         return [[room] for room in available_rooms]
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms for Dropdown Error")
#         return []

@frappe.whitelist()
def get_available_rooms_for_dropdown(doctype, txt, searchfield, start, page_length, filters, **kwargs):
    """
    Query method for room_number dropdown in child table.
    Shows all rooms, regardless of status/maintenance, but excludes:
    - Rooms held by active Temporary Bookings
    - Rooms with overlapping reservations
    - Rooms currently checked in
    """
    try:
        from_date = kwargs.get('from_date')
        to_date = kwargs.get('to_date')
        room_type = kwargs.get('room_type')
        
        # If dates not provided, return all rooms
        if not from_date or not to_date:
            all_rooms = frappe.get_all(
                "Hotel Room",
                fields=["name"],
                # limit_page_length=int(page_length) if page_length else 10,
                order_by="name asc"
            )
            return [[r.name] for r in all_rooms]
        
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
        if to_date_obj <= from_date_obj:
            return []
        
        # Fetch all rooms, optionally filtering by room_type
        filters_dict = {}
        if room_type:
            filters_dict["room_type"] = room_type
        
        all_rooms = frappe.get_all(
            "Hotel Room",
            filters=filters_dict if filters_dict else None,
            fields=["name", "room_type", "floor", "capacity"],
            order_by="name asc"
        )
        if not all_rooms:
            return []

        room_numbers = [r.name for r in all_rooms]

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Exclude held rooms from Temporary Booking
        held_rooms_query = frappe.db.sql("""
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
        as_dict=True)
        held_room_list = set([r.room_number for r in held_rooms_query])

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
        booked_room_list = set([r.room_number for r in overlapping_reservations])

        # Exclude checked-in rooms
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
        checked_in_room_list = set([r.room_number for r in active_checkins])

        unavailable_rooms = held_room_list | booked_room_list | checked_in_room_list
        available_rooms = [r.name for r in all_rooms if r.name not in unavailable_rooms]

        return [[room] for room in available_rooms]

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Available Rooms for Dropdown Error")
        return []


@frappe.whitelist()
def get_available_rooms(from_date, to_date, room_type=None):
    """Get available rooms for selected dates - EXCLUDES HELD ROOMS"""
    try:
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
        
        if to_date_obj <= from_date_obj:
            frappe.throw(_("Check-out date must be after check-in date"))
        
        # filters = {
        #     # "status": "Vacant",
        #     "operational_status": "In Service",
        #     "maintenance_flag": 0
        # }
        
        if room_type:
            filters["room_type"] = room_type
        
        all_rooms = frappe.get_all(
            "Hotel Room",
            # filters=filters,
            fields=["name", "room_type", "floor", "capacity"]
        )
        
        if not all_rooms:
            return []
        
        room_numbers = [r.name for r in all_rooms]
        # return all_rooms
        
        
        # ✅ CRITICAL FIX #1: Exclude rooms with active holds from Temporary Booking
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        held_rooms = frappe.db.sql("""
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
        as_dict=True)
        
        held_room_list = [r.room_number for r in held_rooms]
        
        # Exclude overlapping reservations
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
        
        # Exclude active check-ins
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
        
        # ✅ CRITICAL FIX #2: Combine all unavailable rooms
        # Order matters: held_room_list first, then booked, then checked in
        unavailable = set(held_room_list + booked_rooms + checked_in_rooms)
        available_rooms = [r for r in all_rooms if r.name not in unavailable]
        
        # Calculate pricing for each available room
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
    """Update guest names for rooms in a reservation"""
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
            
            if room_idx is None or not guest_name:
                continue
            
            room = reservation.rooms[room_idx]
            room.guest_name = guest_name
            if guest_email:
                room.guest_email = guest_email
            if guest_phone:
                room.guest_phone = guest_phone
            
            if not room.hotel_guest:
                hotel_guest = frappe.get_doc({
                    "doctype": "Hotel Guest",
                    "hotel_guest_name": guest_name,
                    "phone_number": guest_phone or "",
                    "email": guest_email or "",
                    "gender": "Male",
                    "id_type": "Passport",
                    "id_number": "",
                    "customer": room.guest_customer,
                    "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
                })
                hotel_guest.flags.ignore_permissions = True
                hotel_guest.insert()
                
                if guest_phone:
                    frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", guest_phone, update_modified=False)
                
                room.hotel_guest = hotel_guest.name
            
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
            "message": _("Updated guest names for {0} room(s)").format(len(updated_rooms)),
            "rooms": updated_rooms
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Guest Names Error")
        frappe.throw(_("Error: {0}").format(str(e)))
        
        
        


# @frappe.whitelist()
# def create_sales_invoice_for_reservation(reservation_name):
#     """
#     Create a Sales Invoice for a Front Desk Reservation
#     ✅ For CORPORATE bookings: Invoices all rooms to the corporate customer
#     ✅ For non-corporate: Invoices all rooms to individual customers
    
#     Args:
#         reservation_name: Name of the Hotel Front Desk Reservation
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted before creating invoice"))
        
#         if reservation.sales_invoice:
#             frappe.throw(_("Sales invoice already exists for this reservation: {0}").format(reservation.sales_invoice))
        
#         # Determine customer
#         if reservation.reservation_type == "Corporate":
#             customer = reservation.customer
#             if not customer:
#                 frappe.throw(_("Corporate customer not set for this reservation"))
#         else:
#             customer = reservation.customer
#             if not customer:
#                 frappe.throw(_("Customer not set for this reservation"))
        
#         # Create line items for all rooms
#         line_items = []
        
#         for room in reservation.rooms:
#             # Create or get item for this room type
#             item_name = create_or_get_room_item(room.room_type)
            
#             line_items.append({
#                 "item_code": item_name,
#                 "item_name": f"{room.room_number} - ({room.room_type})",
#                 "description": f"Room {room.room_number} ({room.room_type}) - {reservation.number_of_nights} night(s)",
#                 "qty": reservation.number_of_nights,
#                 # "uom": "Night",
#                 "rate": room.rate_per_night,
#                 "amount": room.room_total
#             })
        
#         # Create Sales Invoice
#         si = frappe.get_doc({
#             "doctype": "Sales Invoice",
#             "customer": customer,
#             "posting_date": nowdate(),
#             "due_date": reservation.to_date,
#             "invoice_period_from_date": reservation.from_date,
#             "invoice_period_to_date": reservation.to_date,
#             "reference_no": reservation.reservation_number,
#             "remarks": f"Hotel Reservation {reservation.name} - {', '.join([r.room_number for r in reservation.rooms])}",
#             "items": line_items
#         })
        
#         # Set discount if applicable
#         if reservation.discount_type and reservation.discount:
#             if reservation.discount_type == "Percentage":
#                 si.discount_type = "Percentage"
#                 si.discount = reservation.discount
#             elif reservation.discount_type == "Amount":
#                 # For amount-based discount, we'll add it to the invoice total
#                 si.discount_type = "Fixed"
#                 si.discount = reservation.discount_amount
        
#         si.flags.ignore_permissions = True
#         si.insert()
#         si.submit()
        
#         # Link the invoice back to the reservation
#         frappe.db.set_value(
#             "Hotel Front Desk Reservation",
#             reservation.name,
#             "sales_invoice",
#             si.name
#         )
        
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Sales Invoice {0} created successfully").format(si.name),
#             "invoice_name": si.name
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Sales Invoice Error")
#         frappe.throw(_("Error creating sales invoice: {0}").format(str(e)))

@frappe.whitelist()
def create_sales_invoice_for_reservation(reservation_name):
    """
    Create a Sales Invoice for a Front Desk Reservation
    ✅ For CORPORATE bookings: Invoices all rooms to the corporate customer
    ✅ EXCLUDE: Rooms that have been checked in (already have check-ins)
    ✅ If ALL rooms checked in: Throw error - don't create invoice
    
    Args:
        reservation_name: Name of the Hotel Front Desk Reservation
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before creating invoice"))
        
        if reservation.sales_invoice:
            frappe.throw(_("Sales invoice already exists for this reservation: {0}").format(reservation.sales_invoice))
        
        # ✅ NEW: Get all rooms that have been checked in
        checked_in_rooms = frappe.db.get_all(
            "Hotel Room Check In",
            filters={
                "front_desk_reservation": reservation_name,
                "status": ["in", ["Draft", "Checked In"]]
            },
            fields=["room_number"],
            distinct=True
        )
        
        checked_in_room_numbers = set([r.room_number for r in checked_in_rooms])
        
        # ✅ NEW: Filter rooms - exclude checked-in rooms
        rooms_to_invoice = [
            room for room in reservation.rooms 
            if room.room_number not in checked_in_room_numbers
        ]
        
        # ✅ NEW: If all rooms checked in, don't create invoice
        if len(rooms_to_invoice) == 0:
            frappe.throw(
                _("Cannot create invoice: All rooms have already been checked in. "
                  "Use the check-in process to create individual room invoices.")
            )
        
        # ✅ NEW: Log which rooms are excluded
        if len(checked_in_room_numbers) > 0:
            frappe.log_error(
                title=f"Excluding checked-in rooms from invoice - {reservation_name}",
                message="Rooms excluded from invoice: {0}".format(
                    ", ".join(sorted(checked_in_room_numbers))
                )
            )
        
        # Determine customer
        if reservation.reservation_type == "Corporate":
            customer = reservation.customer
            if not customer:
                frappe.throw(_("Corporate customer not set for this reservation"))
        else:
            customer = reservation.customer
            if not customer:
                frappe.throw(_("Customer not set for this reservation"))
        
        # ✅ Create line items for NON-CHECKED-IN rooms only
        line_items = []
        
        for room in rooms_to_invoice:
            # Create or get item for this room type
            item_name = create_or_get_room_item(room.room_type)
            
            line_items.append({
                "item_code": item_name,
                "item_name": f"{room.room_number} - ({room.room_type})",
                "description": f"Room {room.room_number} ({room.room_type}) - {reservation.number_of_nights} night(s)",
                "qty": reservation.number_of_nights,
                "rate": room.rate_per_night,
                "amount": room.room_total
            })
        
        # Create Sales Invoice
        si = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": customer,
            "posting_date": nowdate(),
            "due_date": reservation.to_date,
            "invoice_period_from_date": reservation.from_date,
            "invoice_period_to_date": reservation.to_date,
            "reference_no": reservation.reservation_number,
            "remarks": f"Hotel Reservation {reservation.name} - {', '.join([r.room_number for r in rooms_to_invoice])}",
            "items": line_items
        })
        
        # Set discount if applicable
        if reservation.discount_type and reservation.discount:
            if reservation.discount_type == "Percentage":
                si.discount_type = "Percentage"
                si.discount = reservation.discount
            elif reservation.discount_type == "Amount":
                si.discount_type = "Fixed"
                si.discount = reservation.discount_amount
        
        si.flags.ignore_permissions = True
        si.insert()
        si.submit()
        
        # Link the invoice back to the reservation
        frappe.db.set_value(
            "Hotel Front Desk Reservation",
            reservation.name,
            "sales_invoice",
            si.name
        )
        
        frappe.db.commit()
        
        # ✅ NEW: Show which rooms were invoiced
        invoiced_rooms = ", ".join([r.room_number for r in rooms_to_invoice])
        message = _("Sales Invoice {0} created successfully for room(s): {1}").format(
            si.name,
            invoiced_rooms
        )
        
        if len(checked_in_room_numbers) > 0:
            message += _("<br/><br/>Excluded from invoice (already checked in): {0}").format(
                ", ".join(sorted(checked_in_room_numbers))
            )
        
        return {
            "success": True,
            "message": message,
            "invoice_name": si.name,
            "invoiced_rooms": invoiced_rooms,
            "excluded_rooms": list(checked_in_room_numbers)
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Sales Invoice Error")
        frappe.throw(_("Error creating sales invoice: {0}").format(str(e)))

def create_or_get_room_item(room_type):
    """
    Create or get an Item for a room type
    Items are used in Sales Invoices for proper accounting
    
    Args:
        room_type: Name of the Hotel Room Type
    
    Returns:
        item_code: The code of the created/existing item
    """
    try:
        # Check if item already exists
        existing_item = frappe.db.get_value(
            "Item",
            {"item_name": room_type, "item_group": "Services"},
            "name"
        )
        
        if existing_item:
            return existing_item
        
        # Create new item
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": f"ROOM-{room_type.upper().replace(' ', '-')}",
            "item_name": room_type,
            "item_group": "Services",
            "is_stock_item": 0,
            "valuation_method": "FIFO",
            "uom": "Night",
            "standard_selling_rate": 0  # Rate will be set in invoice
        })
        
        item.flags.ignore_permissions = True
        item.insert()
        
        return item.item_code
    
    except frappe.exceptions.DuplicateEntryError:
        # Item already exists, get it
        return frappe.db.get_value("Item", {"item_name": room_type}, "name")
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Room Item Error")
        # If we can't create item, return a generic code
        return f"ROOM-{room_type.upper().replace(' ', '-')}"




# @frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
#     """
#     Check in SELECTED rooms with Sales Invoice creation BEFORE check-in submission
#     WITH ALERTS for user feedback
#     """
#     try:
#         if isinstance(room_indices, str):
#             import json
#             room_indices = json.loads(room_indices)
        
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
#         created_sales_invoices = []  # Track all created SIs
        
#         for idx in room_indices:
#             if idx >= len(reservation.rooms):
#                 continue
            
#             room = reservation.rooms[idx]
            
#             # Get HRR
#             hrr_name = frappe.db.get_value(
#                 "Hotel Room Reservation",
#                 {
#                     "front_desk_reservation": reservation.name,
#                     "room_number": room.room_number,
#                     "docstatus": 1
#                 },
#                 "name"
#             )
            
#             if not hrr_name:
#                 result = create_room_reservation_for_checkin(reservation_name, idx)
#                 if not result.get("success"):
#                     frappe.throw(
#                         _("Failed to create Hotel Room Reservation for room {0}").format(
#                             room.room_number
#                         )
#                     )
#                 hrr_name = result.get("reservation_name")
            
#             # Get HRR document
#             hrr = frappe.get_doc("Hotel Room Reservation", hrr_name)
            
#             # Get rate_type from HRR.items child table
#             rate_type = None
#             if hasattr(hrr, 'items') and len(hrr.items) > 0:
#                 rate_type = hrr.items[0].rate_type
            
#             # Get or create Hotel Guest
#             guest_name = hrr.guest_name
            
#             hotel_guest_id = frappe.db.get_value(
#                 "Hotel Guest",
#                 {"hotel_guest_name": guest_name},
#                 "name"
#             )
            
#             if not hotel_guest_id:
#                 hotel_guest = frappe.get_doc({
#                     "doctype": "Hotel Guest",
#                     "hotel_guest_name": guest_name,
#                     "customer": hrr.customer,
#                     "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
#                 })
#                 hotel_guest.flags.ignore_permissions = True
#                 hotel_guest.insert()
#                 hotel_guest_id = hotel_guest.name
            
#             # Get room_type from Hotel Room document
#             room_doc = frappe.get_doc("Hotel Room", hrr.room_number)
#             room_type = room_doc.room_type if hasattr(room_doc, 'room_type') else None
            
#             # Calculate number of nights
#             number_of_nights = date_diff(
#                 getdate(hrr.to_date),
#                 getdate(hrr.from_date)
#             )
            
#             # ✅ STEP 7: CREATE SALES INVOICE BEFORE CHECK-IN
#             if not room_doc.erpnext_item:
#                 frappe.throw(
#                     _("Hotel Room {0} does not have an ERPNext item configured").format(
#                         hrr.room_number
#                     )
#                 )
            
#             # Create Sales Invoice
#             si = frappe.new_doc("Sales Invoice")
#             si.customer = hrr.customer  # Corporate customer from HRR
#             si.posting_date = nowdate()
#             si.due_date = getdate(hrr.to_date)
#             si.invoice_period_from_date = hrr.from_date
#             si.invoice_period_to_date = hrr.to_date
#             si.reference_no = hrr.booking_number
#             si.remarks = _("Room {0} - {1} night(s) from {2} to {3}").format(
#                 hrr.room_number,
#                 number_of_nights,
#                 hrr.from_date,
#                 hrr.to_date
#             )
            
#             # Add item line
#             si.append("items", {
#                 "item_code": room_doc.erpnext_item,
#                 "rate": hrr.rate,
#                 "qty": number_of_nights,
#                 "amount": hrr.rate * number_of_nights,
#                 "description": _("Room charge for {0}").format(hrr.room_number)
#             })
            
#             si.set_taxes()
            
#             # Insert and submit SI
#             si.flags.ignore_permissions = True
#             si.insert()
#             si.submit()
            
#             # ✅ ALERT 1: Sales Invoice Created Successfully
#             frappe.msgprint({
#                 'title': _('Sales Invoice Created'),
#                 'message': _('Sales Invoice <b>{0}</b> created for Room <b>{1}</b><br/>Amount: <b>{2}</b>').format(
#                     si.name,
#                     hrr.room_number,
#                     frappe.format_value(si.grand_total, df={"fieldtype": "Currency"})
#                 ),
#                 'indicator': 'green',
#                 'alert': False  # Use alert=False to show as notification, not modal
#             })
            
#             created_sales_invoices.append({
#                 "invoice": si.name,
#                 "room": hrr.room_number,
#                 "amount": si.grand_total
#             })
            
#             # Log for debugging
#             frappe.log_error(
#                 title=f"Sales Invoice Created - Room {room.room_number}",
#                 message="Sales Invoice: {0}\nAmount: {1}".format(
#                     si.name,
#                     si.grand_total
#                 )
#             )
            
#             # Build check-in data
#             check_in_data = {
#                 "doctype": "Hotel Room Check In",
#                 "guest": hotel_guest_id,
#                 "room_number": hrr.room_number,
#                 "room_type": room_type,
#                 "rate_type": rate_type,
#                 "rate_amount": hrr.rate or 0,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": number_of_nights,
#                 "expected_check_out_datetime": get_datetime(
#                     f"{hrr.to_date} {reservation.expected_check_out_time or '12:00:00'}"
#                 ),
#                 "status": "Checked In",
#                 "front_desk_reservation": reservation.name,
#                 "reservation": hrr_name
#             }
            
#             # Create and submit check-in
#             try:
#                 check_in = frappe.get_doc(check_in_data)
#                 check_in.flags.ignore_permissions = True
#                 check_in.insert()
#                 check_in.submit()
                
#                 # ✅ ALERT 2: Check-In Created Successfully
#                 frappe.msgprint({
#                     'title': _('Check-In Confirmed'),
#                     'message': _('Room <b>{0}</b> checked in successfully<br/>Guest: <b>{1}</b><br/>Check-In: <b>{2}</b>').format(
#                         hrr.room_number,
#                         guest_name,
#                         check_in.name
#                     ),
#                     'indicator': 'green',
#                     'alert': False
#                 })
                
#             except Exception as e:
#                 frappe.log_error(
#                     title=f"Check In FAILED - Room {room.room_number}",
#                     message="Error: {0}\n\nData that caused error:\n{1}".format(
#                         str(e),
#                         frappe.as_json(check_in_data, indent=2)
#                     )
#                 )
#                 raise
            
#             # Update HRR status
#             frappe.db.set_value(
#                 "Hotel Room Reservation",
#                 hrr_name,
#                 "status",
#                 "Checked-In"
#             )
            
#             checked_in_rooms.append(room.room_number)
        
#         frappe.db.commit()
        
#         # ✅ FINAL ALERT: Summary of all checked-in rooms
#         summary_message = _("Successfully checked in {0} room(s)<br/><br/>").format(len(checked_in_rooms))
        
#         if created_sales_invoices:
#             summary_message += _("<b>Sales Invoices Created:</b><br/>")
#             for si_data in created_sales_invoices:
#                 summary_message += _(
#                     "• Room {0}: Invoice {1} (₦{2:,.2f})<br/>"
#                 ).format(
#                     si_data["room"],
#                     si_data["invoice"],
#                     si_data["amount"]
#                 )
        
#         frappe.msgprint({
#             'title': _('Check-In Complete'),
#             'message': summary_message,
#             'indicator': 'green',
#             'alert': True  # This is the final alert, make it modal
#         })
        
#         return {
#             "success": True,
#             "message": _("Checked in {0} room(s)").format(len(checked_in_rooms)),
#             "rooms": checked_in_rooms,
#             "sales_invoices": created_sales_invoices
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))  

@frappe.whitelist()
def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
    """
    Check in SELECTED rooms with Sales Invoice creation BEFORE check-in submission
    WITH ALERTS for user feedback
    AND tracking invoices in FDR.sales_invoices child table (using db.sql with UUID)
    """
    try:
        if isinstance(room_indices, str):
            import json
            room_indices = json.loads(room_indices)
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
            
        # ✅ Prevent check-in if bulk invoice exists
        if reservation.sales_invoice:
            frappe.throw(
                _("Cannot check in: Bulk Sales Invoice {0} already created for this reservation. "
                "Checking in these rooms will duplicate costs.\n\n"
                "Use 'Check In All Rooms' button instead.").format(reservation.sales_invoice)
            )
        
        checked_in_rooms = []
        created_sales_invoices = []  # Track all created SIs
        
        for idx in room_indices:
            if idx >= len(reservation.rooms):
                continue
            
            room = reservation.rooms[idx]
            
            # Get HRR
            hrr_name = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation.name,
                    "room_number": room.room_number,
                    "docstatus": 1
                },
                "name"
            )
            
            if not hrr_name:
                result = create_room_reservation_for_checkin(reservation_name, idx)
                if not result.get("success"):
                    frappe.throw(
                        _("Failed to create Hotel Room Reservation for room {0}").format(
                            room.room_number
                        )
                    )
                hrr_name = result.get("reservation_name")
            
            # Get HRR document
            hrr = frappe.get_doc("Hotel Room Reservation", hrr_name)
            
            # Get rate_type from HRR.items child table
            rate_type = None
            if hasattr(hrr, 'items') and len(hrr.items) > 0:
                rate_type = hrr.items[0].rate_type
            
            # Get or create Hotel Guest
            guest_name = hrr.guest_name
            
            hotel_guest_id = frappe.db.get_value(
                "Hotel Guest",
                {"hotel_guest_name": guest_name},
                "name"
            )
            
            if not hotel_guest_id:
                hotel_guest = frappe.get_doc({
                    "doctype": "Hotel Guest",
                    "hotel_guest_name": guest_name,
                    "customer": hrr.customer,
                    "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
                })
                hotel_guest.flags.ignore_permissions = True
                hotel_guest.insert()
                hotel_guest_id = hotel_guest.name
            
            # Get room_type from Hotel Room document
            room_doc = frappe.get_doc("Hotel Room", hrr.room_number)
            room_type = room_doc.room_type if hasattr(room_doc, 'room_type') else None
            
            # Calculate number of nights
            number_of_nights = date_diff(
                getdate(hrr.to_date),
                getdate(hrr.from_date)
            )
            
            # ✅ STEP 7: CREATE SALES INVOICE BEFORE CHECK-IN
            if not room_doc.erpnext_item:
                frappe.throw(
                    _("Hotel Room {0} does not have an ERPNext item configured").format(
                        hrr.room_number
                    )
                )
            
            # Create Sales Invoice
            si = frappe.new_doc("Sales Invoice")
            si.customer = hrr.customer  # Corporate customer from HRR
            si.posting_date = nowdate()
            si.due_date = getdate(hrr.to_date)
            si.invoice_period_from_date = hrr.from_date
            si.invoice_period_to_date = hrr.to_date
            si.reference_no = hrr.booking_number
            si.remarks = _("Room {0} - {1} night(s) from {2} to {3}").format(
                hrr.room_number,
                number_of_nights,
                hrr.from_date,
                hrr.to_date
            )
            
            # Add item line
            si.append("items", {
                "item_code": room_doc.erpnext_item,
                "rate": hrr.rate,
                "qty": number_of_nights,
                "amount": hrr.rate * number_of_nights,
                "description": _("Room charge for {0}").format(hrr.room_number)
            })
            
            si.set_taxes()
            
            # Insert and submit SI
            si.flags.ignore_permissions = True
            si.insert()
            si.submit()
            
            # ✅ ALERT 1: Sales Invoice Created Successfully
            frappe.msgprint({
                'title': _('Sales Invoice Created'),
                'message': _('Sales Invoice <b>{0}</b> created for Room <b>{1}</b><br/>Amount: <b>{2}</b>').format(
                    si.name,
                    hrr.room_number,
                    frappe.format_value(si.grand_total, df={"fieldtype": "Currency"})
                ),
                'indicator': 'green',
                'alert': False
            })
            
            # ✅ TRACK THE INVOICE
            created_sales_invoices.append({
                "invoice": si.name,
                "room": hrr.room_number,
                "guest": guest_name,
                "amount": si.grand_total,
                "created_at": now_datetime()
            })
            
            # Log for debugging
            frappe.log_error(
                title=f"Sales Invoice Created - Room {room.room_number}",
                message="Sales Invoice: {0}\nAmount: {1}".format(
                    si.name,
                    si.grand_total
                )
            )
            
            # Build check-in data
            check_in_data = {
                "doctype": "Hotel Room Check In",
                "guest": hotel_guest_id,
                "room_number": hrr.room_number,
                "room_type": room_type,
                "rate_type": rate_type,
                "rate_amount": hrr.rate or 0,
                "check_in_datetime": now_datetime(),
                "number_of_nights": number_of_nights,
                "expected_check_out_datetime": get_datetime(
                    f"{hrr.to_date} {reservation.expected_check_out_time or '12:00:00'}"
                ),
                "status": "Checked In",
                "front_desk_reservation": reservation.name,
                "reservation": hrr_name
            }
            
            # Create and submit check-in
            try:
                check_in = frappe.get_doc(check_in_data)
                check_in.flags.ignore_permissions = True
                check_in.insert()
                check_in.submit()
                
                # ✅ ALERT 2: Check-In Created Successfully
                frappe.msgprint({
                    'title': _('Check-In Confirmed'),
                    'message': _('Room <b>{0}</b> checked in successfully<br/>Guest: <b>{1}</b><br/>Check-In: <b>{2}</b>').format(
                        hrr.room_number,
                        guest_name,
                        check_in.name
                    ),
                    'indicator': 'green',
                    'alert': False
                })
                
            except Exception as e:
                frappe.log_error(
                    title=f"Check In FAILED - Room {room.room_number}",
                    message="Error: {0}\n\nData that caused error:\n{1}".format(
                        str(e),
                        frappe.as_json(check_in_data, indent=2)
                    )
                )
                raise
            
            # Update HRR status
            frappe.db.set_value(
                "Hotel Room Reservation",
                hrr_name,
                "status",
                "Checked-In"
            )
            
            checked_in_rooms.append(room.room_number)
        
        # ✅ FIXED: ADD ALL INVOICES TO FDR.sales_invoices CHILD TABLE USING db.sql WITH UUID
        if created_sales_invoices:
            import uuid
            
            for invoice_data in created_sales_invoices:
                # ✅ Generate unique name for child table row
                child_name = str(uuid.uuid4())
                
                # ✅ Insert directly using SQL (bypasses submitted document restrictions)
                frappe.db.sql("""
                    INSERT INTO `tabHotel Front Desk Reservation Invoice`
                    (name, parent, parenttype, parentfield, room_number, guest_name, sales_invoice, amount, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    child_name,                                 # name (unique ID)
                    reservation_name,                           # parent
                    "Hotel Front Desk Reservation",             # parenttype
                    "sales_invoices",                           # parentfield
                    invoice_data["room"],                       # room_number
                    invoice_data["guest"],                      # guest_name
                    invoice_data["invoice"],                    # sales_invoice
                    invoice_data["amount"],                     # amount
                    invoice_data["created_at"]                  # created_at
                ))
            
            frappe.log_error(
                title=f"FDR Invoices Tracked - {reservation_name}",
                message="Added {0} invoice(s) to FDR.sales_invoices via SQL".format(len(created_sales_invoices))
            )
        
        frappe.db.commit()
        
        # ✅ FINAL ALERT: Summary of all checked-in rooms
        summary_message = _("Successfully checked in {0} room(s)<br/><br/>").format(len(checked_in_rooms))
        
        if created_sales_invoices:
            summary_message += _("<b>Sales Invoices Created:</b><br/>")
            for si_data in created_sales_invoices:
                summary_message += _(
                    "• Room {0}: Invoice {1} (₦{2:,.2f})<br/>"
                ).format(
                    si_data["room"],
                    si_data["invoice"],
                    si_data["amount"]
                )
        
        frappe.msgprint({
            'title': _('Check-In Complete'),
            'message': summary_message,
            'indicator': 'green',
            'alert': True
        })
        
        return {
            "success": True,
            "message": _("Checked in {0} room(s)").format(len(checked_in_rooms)),
            "rooms": checked_in_rooms,
            "sales_invoices": created_sales_invoices
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
        frappe.throw(_("Error: {0}").format(str(e)))
        
@frappe.whitelist()
def check_in_all_rooms(reservation_name, check_in_notes=""):
    """
    Check in ALL rooms using Hotel Room Reservations
    
    Same workflow as check_in_selected_rooms but for all rooms
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        checked_in_rooms = []
        
        # Check in all rooms
        for idx, room in enumerate(reservation.rooms):
            
            # ✅ Get Hotel Room Reservation
            hrr_name = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation.name,
                    "room_number": room.room_number,
                    "docstatus": 1
                },
                "name"
            )
            
            if not hrr_name:
                # Create if not exists
                result = create_room_reservation_for_checkin(reservation_name, idx)
                if not result.get("success"):
                    frappe.throw(
                        _("Failed to create Hotel Room Reservation for room {0}").format(
                            room.room_number
                        )
                    )
                hrr_name = result.get("reservation_name")
            
            # ✅ Get HRR document - get ALL data from here
            hrr = frappe.get_doc("Hotel Room Reservation", hrr_name)
            
            # ✅ Get rate_type from HRR.items (child table) - KEY FIX!
            rate_type = None
            if hasattr(hrr, 'items') and len(hrr.items) > 0:
                rate_type = hrr.items[0].rate_type
            
            # ✅ Get or create Hotel Guest
            guest_name = hrr.guest_name
            hotel_guest_id = frappe.db.get_value(
                "Hotel Guest",
                {"hotel_guest_name": guest_name},
                "name"
            )
            
            if not hotel_guest_id:
                hotel_guest = frappe.get_doc({
                    "doctype": "Hotel Guest",
                    "hotel_guest_name": guest_name,
                    "customer": hrr.customer,
                    "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
                })
                hotel_guest.flags.ignore_permissions = True
                hotel_guest.insert()
                hotel_guest_id = hotel_guest.name
            
            # ✅ Get room_type from Hotel Room
            room_doc = frappe.get_doc("Hotel Room", hrr.room_number)
            room_type = room_doc.room_type if hasattr(room_doc, 'room_type') else None
            
            # ✅ Calculate number of nights
            number_of_nights = date_diff(
                getdate(hrr.to_date),
                getdate(hrr.from_date)
            )
            
            # ✅ Create check-in using ALL required fields from HRR
            check_in = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                # Guest Details
                "guest": hotel_guest_id,  # ← From HRR
                # Room Details
                "room_number": hrr.room_number,  # ← From HRR
                "room_type": room_type,  # ← From Hotel Room (REQUIRED)
                # Pricing - rate_type from HRR.items!
                "rate_type": rate_type,  # ← From HRR.items[0].rate_type
                "rate_amount": hrr.rate or 0,  # ← From HRR (REQUIRED)
                # Dates & Times
                "check_in_datetime": now_datetime(),
                "number_of_nights": number_of_nights,  # ← Calculated from HRR dates
                "expected_check_out_datetime": get_datetime(
                    f"{hrr.to_date} {reservation.expected_check_out_time or '12:00:00'}"
                ),
                # Status
                "status": "Checked In",
                # Linking
                "front_desk_reservation": reservation.name,
                "reservation": hrr_name  # ← Link to HRR
            })
            
            check_in.flags.ignore_permissions = True
            check_in.insert()
            check_in.submit()
            
            # ✅ Update HRR status
            frappe.db.set_value(
                "Hotel Room Reservation",
                hrr_name,
                "status",
                "Checked-In"
            )
            
            checked_in_rooms.append(room.room_number)
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Checked in all {0} room(s)").format(len(checked_in_rooms))
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
        frappe.throw(_("Error: {0}").format(str(e)))

