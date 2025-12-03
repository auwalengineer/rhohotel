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
            
            # # Only create room reservations for NON-CORPORATE
            # if self.reservation_type != "Corporate":
            #     self.create_room_reservations()
            #     self.status = "Booked"
            #     self.db_set("status", "Booked")
            #     frappe.msgprint(
            #         _("Reservation {0} confirmed. Hotel room reservations created.").format(self.name),
            #         indicator="green",
            #         alert=True
            #     )
            # else:
            #     # Corporate: Just confirm, don't create reservations yet
            #     self.status = "Booked"
            #     self.db_set("status", "Booked")
            #     frappe.msgprint(
            #         _("Corporate Reservation {0} confirmed. Rooms ready for check-in.").format(self.name),
            #         indicator="green",
            #         alert=True
            #     )
            
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
        room_status = frappe.db.get_value("Hotel Room", room_number, "status")
        if room_status != "Vacant":
            return False
        
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
                "net_total": room.room_total
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
            "net_total": room.room_total
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


# ADD THIS NEW METHOD to your hotel_front_desk_reservation.py file
# Place it BEFORE the existing get_available_rooms method
# ADD THIS NEW METHOD to your hotel_front_desk_reservation.py file
# Place it BEFORE the existing get_available_rooms method

# @frappe.whitelist()
# def get_available_rooms_for_dropdown(doctype, txt, searchfield, start, page_length, filters, **kwargs):
#     """
#     Query method for dropdown - returns only available rooms
#     Called from set_query in client script for room_number field
    
#     This ensures the room_number dropdown in the child table (Front Desk Reservation Room)
#     only shows rooms that are actually available for the selected dates
#     """
#     try:
#         # Extract from_date and to_date from kwargs
#         from_date = kwargs.get('from_date')
#         to_date = kwargs.get('to_date')
#         room_type = kwargs.get('room_type')
        
#         if not from_date or not to_date:
#             # If dates not provided, return all vacant rooms
#             all_rooms = frappe.get_all(
#                 "Hotel Room",
#                 filters={
#                     "status": "Vacant",
#                     "operational_status": "In Service",
#                     "maintenance_flag": 0
#                 },
#                 fields=["name"],
#                 limit_page_length=int(page_length) if page_length else 10
#             )
#             return [[r.name] for r in all_rooms]
        
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             return []
        
#         base_filters = {
#             "status": "Vacant",
#             "operational_status": "In Service",
#             "maintenance_flag": 0
#         }
        
#         if room_type:
#             base_filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             filters=base_filters,
#             fields=["name", "room_type", "floor", "capacity"],
#             limit_page_length=int(page_length) if page_length else 10
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
#         # Check for overlapping reservations
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
        
#         booked_rooms = [r.room_number for r in overlapping_reservations]
        
#         # Check for active check-ins
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
        
#         checked_in_rooms = [r.room_number for r in active_checkins]
        
#         # Filter out unavailable rooms
#         unavailable = set(booked_rooms + checked_in_rooms)
#         available_rooms = [r.name for r in all_rooms if r.name not in unavailable]
        
#         # Return as list of tuples for dropdown
#         return [[room] for room in available_rooms]
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms for Dropdown Error")
#         return []
    
# @frappe.whitelist()
# def get_available_rooms(from_date, to_date, room_type=None):
#     """Get available rooms for selected dates"""
#     try:
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             frappe.throw(_("Check-out date must be after check-in date"))
        
#         filters = {
#             "status": "Vacant",
#             "operational_status": "In Service",
#             "maintenance_flag": 0
#         }
        
#         if room_type:
#             filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             filters=filters,
#             fields=["name", "room_type", "floor", "capacity"]
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
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
        
#         booked_rooms = [r.room_number for r in overlapping_reservations]
        
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
        
#         checked_in_rooms = [r.room_number for r in active_checkins]
        
#         unavailable = set(booked_rooms + checked_in_rooms)
#         available_rooms = [r for r in all_rooms if r.name not in unavailable]
        
#         for room in available_rooms:
#             rate = get_room_rate(room.room_type, check_in_date=str(from_date))
#             room["rate_per_night"] = rate
#             num_nights = date_diff(to_date_obj, from_date_obj)
#             room["total_amount"] = rate * num_nights
        
#         return available_rooms
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def get_available_rooms_for_dropdown(doctype, txt, searchfield, start, page_length, filters, **kwargs):
    """
    ✅ FIXED: Query method for room_number dropdown in child table
    
    Called from set_query in client script for room_number field
    This ensures the room_number dropdown ONLY shows rooms that are:
    - Vacant
    - In Service
    - Not in maintenance
    - NOT held by active Temporary Bookings
    - NOT booked with overlapping reservations
    - NOT currently checked in
    
    Args:
        doctype: 'Hotel Room'
        txt: Search text
        searchfield: 'name' (room number)
        start: Pagination start
        page_length: Number of results
        filters: Base filters
        **kwargs: Contains from_date, to_date, room_type
    """
    try:
        # Extract dates from kwargs
        from_date = kwargs.get('from_date')
        to_date = kwargs.get('to_date')
        room_type = kwargs.get('room_type')
        
        # If dates not provided, return vacant rooms only
        if not from_date or not to_date:
            all_rooms = frappe.get_all(
                "Hotel Room",
                filters={
                    "status": "Vacant",
                    "operational_status": "In Service",
                    "maintenance_flag": 0
                },
                fields=["name"],
                limit_page_length=int(page_length) if page_length else 10,
                order_by="name asc"
            )
            return [[r.name] for r in all_rooms]
        
        # Parse dates
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
        
        if to_date_obj <= from_date_obj:
            return []
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: Get base vacant rooms
        # ═══════════════════════════════════════════════════════════════════
        base_filters = {
            "status": "Vacant",
            "operational_status": "In Service",
            "maintenance_flag": 0
        }
        
        if room_type:
            base_filters["room_type"] = room_type
        
        all_rooms = frappe.get_all(
            "Hotel Room",
            filters=base_filters,
            fields=["name", "room_type", "floor", "capacity"],
            # limit_page_length=int(page_length) if page_length else 10,
            order_by="name asc"
        )
        
        if not all_rooms:
            return []
        
        room_numbers = [r.name for r in all_rooms]
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: ✅ CRITICAL: Get held rooms from Temporary Booking
        # ═══════════════════════════════════════════════════════════════════
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
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
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 3: Get booked rooms with overlapping reservations
        # ═══════════════════════════════════════════════════════════════════
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
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: Get checked-in rooms
        # ═══════════════════════════════════════════════════════════════════
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
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: ✅ Combine all unavailable rooms
        # ═══════════════════════════════════════════════════════════════════
        unavailable_rooms = held_room_list | booked_room_list | checked_in_room_list
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 6: Filter and return available rooms
        # ═══════════════════════════════════════════════════════════════════
        available_rooms = [r.name for r in all_rooms if r.name not in unavailable_rooms]
        
        # Return as list of tuples for dropdown
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
        
        filters = {
            "status": "Vacant",
            "operational_status": "In Service",
            "maintenance_flag": 0
        }
        
        if room_type:
            filters["room_type"] = room_type
        
        all_rooms = frappe.get_all(
            "Hotel Room",
            filters=filters,
            fields=["name", "room_type", "floor", "capacity"]
        )
        
        if not all_rooms:
            return []
        
        room_numbers = [r.name for r in all_rooms]
        
        
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
        
        
        




# # ADD THESE NEW METHODS to your hotel_front_desk_reservation.py file

# @frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
#     """
#     Check in SELECTED rooms only - does NOT create reservations
#     For corporate bookings where user selects which rooms to check in
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         room_indices: List of room indices to check in (0-based)
#         check_in_notes: Optional notes for check-in
#     """
#     try:
#         if isinstance(room_indices, str):
#             import json
#             room_indices = json.loads(room_indices)
        
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
        
#         # Process only selected rooms
#         for idx in room_indices:
#             if idx >= len(reservation.rooms):
#                 continue
            
#             room = reservation.rooms[idx]
            
#             # Ensure guest has a name
#             if not room.guest_name or room.guest_name.startswith("Guest - Room"):
#                 return {
#                     "success": False,
#                     "missing_guest_names": True,
#                     "message": _("Guest names required for rooms: {0}").format(room.room_number)
#                 }
            
#             # Create/get hotel guest
#             if not room.hotel_guest:
#                 guest_name = room.guest_name
#                 existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
                
#                 if existing_guest:
#                     room.hotel_guest = existing_guest
#                 else:
#                     try:
#                         hotel_guest = frappe.get_doc({
#                             "doctype": "Hotel Guest",
#                             "hotel_guest_name": guest_name,
#                             "gender": room.guest_gender or "Male",
#                             "phone_number": room.guest_phone or "",
#                             "email": room.guest_email or "",
#                             "id_type": room.guest_id_type or "Passport",
#                             "id_number": room.guest_id_number or "",
#                             "customer": room.guest_customer,
#                             "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
#                         })
#                         hotel_guest.flags.ignore_permissions = True
#                         hotel_guest.insert()
                        
#                         if room.guest_phone:
#                             frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", room.guest_phone, update_modified=False)
                        
#                         room.hotel_guest = hotel_guest.name
#                     except frappe.DuplicateEntryError:
#                         existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
#                         if existing_guest:
#                             room.hotel_guest = existing_guest
            
#             # Create check-in record
#             check_in = frappe.get_doc({
#                 "doctype": "Hotel Room Check In",
#                 "guest": room.hotel_guest,
#                 "room_number": room.room_number,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
#                 "expected_check_out_datetime": get_datetime(f"{reservation.to_date} {reservation.expected_check_out_time or '12:00:00'}"),
#                 "rate_amount": room.rate_per_night or 0,
#                 "status": "Checked In"
#             })
            
#             check_in.flags.ignore_permissions = True
#             check_in.insert()
#             check_in.submit()
            
#             checked_in_rooms.append(room.room_number)
        
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Checked in {0} room(s): {1}").format(len(checked_in_rooms), ", ".join(checked_in_rooms))
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_all_rooms(reservation_name, check_in_notes=""):
#     """
#     Check in ALL rooms at once - does NOT create reservations
#     For corporate bookings where user wants to check in everyone
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         check_in_notes: Optional notes for check-in
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
        
#         # Check all rooms have names
#         for room in reservation.rooms:
#             if not room.guest_name or room.guest_name.startswith("Guest - Room"):
#                 return {
#                     "success": False,
#                     "missing_guest_names": True,
#                     "message": _("Guest names required for rooms: {0}").format(room.room_number)
#                 }
        
#         # Check in ALL rooms
#         for room in reservation.rooms:
#             # Create/get hotel guest
#             if not room.hotel_guest:
#                 guest_name = room.guest_name
#                 existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
                
#                 if existing_guest:
#                     room.hotel_guest = existing_guest
#                 else:
#                     try:
#                         hotel_guest = frappe.get_doc({
#                             "doctype": "Hotel Guest",
#                             "hotel_guest_name": guest_name,
#                             "gender": room.guest_gender or "Male",
#                             "phone_number": room.guest_phone or "",
#                             "email": room.guest_email or "",
#                             "id_type": room.guest_id_type or "Passport",
#                             "id_number": room.guest_id_number or "",
#                             "customer": room.guest_customer,
#                             "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
#                         })
#                         hotel_guest.flags.ignore_permissions = True
#                         hotel_guest.insert()
                        
#                         if room.guest_phone:
#                             frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", room.guest_phone, update_modified=False)
                        
#                         room.hotel_guest = hotel_guest.name
#                     except frappe.DuplicateEntryError:
#                         existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
#                         if existing_guest:
#                             room.hotel_guest = existing_guest
            
#             # Create check-in record
#             check_in = frappe.get_doc({
#                 "doctype": "Hotel Room Check In",
#                 "guest": room.hotel_guest,
#                 "room_number": room.room_number,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
#                 "expected_check_out_datetime": get_datetime(f"{reservation.to_date} {reservation.expected_check_out_time or '12:00:00'}"),
#                 "rate_amount": room.rate_per_night or 0,
#                 "status": "Checked In"
#             })
            
#             check_in.flags.ignore_permissions = True
#             check_in.insert()
#             check_in.submit()
            
#             checked_in_rooms.append(room.room_number)
        
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Checked in all {0} room(s)").format(len(checked_in_rooms))
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))

# ADD THIS FUNCTION to your hotel_front_desk_reservation.py file
# This creates a Sales Invoice for the entire Front Desk Reservation

@frappe.whitelist()
def create_sales_invoice_for_reservation(reservation_name):
    """
    Create a Sales Invoice for a Front Desk Reservation
    ✅ For CORPORATE bookings: Invoices all rooms to the corporate customer
    ✅ For non-corporate: Invoices all rooms to individual customers
    
    Args:
        reservation_name: Name of the Hotel Front Desk Reservation
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before creating invoice"))
        
        if reservation.sales_invoice:
            frappe.throw(_("Sales invoice already exists for this reservation: {0}").format(reservation.sales_invoice))
        
        # Determine customer
        if reservation.reservation_type == "Corporate":
            customer = reservation.customer
            if not customer:
                frappe.throw(_("Corporate customer not set for this reservation"))
        else:
            customer = reservation.customer
            if not customer:
                frappe.throw(_("Customer not set for this reservation"))
        
        # Create line items for all rooms
        line_items = []
        
        for room in reservation.rooms:
            # Create or get item for this room type
            item_name = create_or_get_room_item(room.room_type)
            
            line_items.append({
                "item_code": item_name,
                "item_name": f"{room.room_number} - ({room.room_type})",
                "description": f"Room {room.room_number} ({room.room_type}) - {reservation.number_of_nights} night(s)",
                "qty": reservation.number_of_nights,
                # "uom": "Night",
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
            "remarks": f"Hotel Reservation {reservation.name} - {', '.join([r.room_number for r in reservation.rooms])}",
            "items": line_items
        })
        
        # Set discount if applicable
        if reservation.discount_type and reservation.discount:
            if reservation.discount_type == "Percentage":
                si.discount_type = "Percentage"
                si.discount = reservation.discount
            elif reservation.discount_type == "Amount":
                # For amount-based discount, we'll add it to the invoice total
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
        
        return {
            "success": True,
            "message": _("Sales Invoice {0} created successfully").format(si.name),
            "invoice_name": si.name
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





# REPLACE THE EXISTING CHECK-IN METHODS with these
# These now automatically create Hotel Room Reservations when checking in

@frappe.whitelist()
def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
    """
    Check in SELECTED rooms and automatically create Hotel Room Reservations
    For corporate bookings where user selects which rooms to check in
    
    Args:
        reservation_name: Front Desk Reservation name
        room_indices: List of room indices to check in (0-based)
        check_in_notes: Optional notes for check-in
    """
    try:
        if isinstance(room_indices, str):
            import json
            room_indices = json.loads(room_indices)
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        checked_in_rooms = []
        
        # Process only selected rooms
        for idx in room_indices:
            if idx >= len(reservation.rooms):
                continue
            
            room = reservation.rooms[idx]
            
            # Ensure guest has a name
            if not room.guest_name or room.guest_name.startswith("Guest - Room"):
                return {
                    "success": False,
                    "missing_guest_names": True,
                    "message": _("Guest names required for rooms: {0}").format(room.room_number)
                }
            
            # # ✅ Step 1: Create Hotel Room Reservation if not exists
            # if not room.hotel_room_reservation:
            #     reservation_items = [{
            #         "room_type": room.room_type,
            #         "rate_type": room.rate_type or "Standard",
            #         "season_type": room.season_type or "",
            #         "qty": room.number_of_nights,
            #         "rate": room.rate_per_night,
            #         "amount": room.room_total
            #     }]
                
            #     hrr = frappe.get_doc({
            #         "doctype": "Hotel Room Reservation",
            #         "booking_number": reservation.reservation_number,
            #         "front_desk_reservation": reservation.name,
            #         "room_number": room.room_number,
            #         "from_date": reservation.from_date,
            #         "to_date": reservation.to_date,
            #         "rate": room.rate_per_night,
            #         "discount": 0,
            #         "guest_name": room.guest_name,
            #         "customer": room.guest_customer,
            #         "status": "Booked",
            #         "payment_status": "Pending",
            #         "items": reservation_items,
            #         "net_total": room.room_total
            #     })
                
            #     hrr.flags.ignore_permissions = True
            #     hrr.insert()
            #     hrr.submit()
                
            #     # Update the reference
            #     room.hotel_room_reservation = hrr.name
            
            # # ✅ Step 2: Create/get hotel guest
            # if not room.hotel_guest:
            #     guest_name = room.guest_name
            #     existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
                
            #     if existing_guest:
            #         room.hotel_guest = existing_guest
            #     else:
            #         try:
            #             hotel_guest = frappe.get_doc({
            #                 "doctype": "Hotel Guest",
            #                 "hotel_guest_name": guest_name,
            #                 "gender": room.guest_gender or "Male",
            #                 "phone_number": room.guest_phone or "",
            #                 "email": room.guest_email or "",
            #                 "id_type": room.guest_id_type or "Passport",
            #                 "id_number": room.guest_id_number or "",
            #                 "customer": room.guest_customer,
            #                 "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
            #             })
            #             hotel_guest.flags.ignore_permissions = True
            #             hotel_guest.insert()
                        
            #             if room.guest_phone:
            #                 frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", room.guest_phone, update_modified=False)
                        
            #             room.hotel_guest = hotel_guest.name
            #         except frappe.DuplicateEntryError:
            #             existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
            #             if existing_guest:
            #                 room.hotel_guest = existing_guest
            
            # ✅ Step 3: Create check-in record
            check_in = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "guest": room.hotel_guest,
                "room_number": room.room_number,
                "check_in_datetime": now_datetime(),
                "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
                "expected_check_out_datetime": get_datetime(f"{reservation.to_date} {reservation.expected_check_out_time or '12:00:00'}"),
                "rate_amount": room.rate_per_night or 0,
                "status": "Checked In",
                "front_desk_reservation": reservation.name,  # ✅ ADD THIS
                "front_desk_reservation": reservation.name,  # ✅ ADD THIS
                "reservation": room.hotel_room_reservation    # ✅ ADD THIS


            })
            
            check_in.flags.ignore_permissions = True
            check_in.insert()
            check_in.submit()
            
            checked_in_rooms.append(room.room_number)
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Checked in {0} room(s) and created reservations: {1}").format(len(checked_in_rooms), ", ".join(checked_in_rooms))
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
        frappe.throw(_("Error: {0}").format(str(e)))


@frappe.whitelist()
def check_in_all_rooms(reservation_name, check_in_notes=""):
    """
    Check in ALL rooms and automatically create Hotel Room Reservations
    For corporate bookings where user wants to check in everyone
    
    Args:
        reservation_name: Front Desk Reservation name
        check_in_notes: Optional notes for check-in
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        checked_in_rooms = []
        
        # Check all rooms have names
        for room in reservation.rooms:
            if not room.guest_name or room.guest_name.startswith("Guest - Room"):
                return {
                    "success": False,
                    "missing_guest_names": True,
                    "message": _("Guest names required for rooms: {0}").format(room.room_number)
                }
        
        # Check in ALL rooms
        for room in reservation.rooms:
            # # ✅ Step 1: Create Hotel Room Reservation if not exists
            # if not room.hotel_room_reservation:
            #     reservation_items = [{
            #         "room_type": room.room_type,
            #         "rate_type": room.rate_type or "Standard",
            #         "season_type": room.season_type or "",
            #         "qty": room.number_of_nights,
            #         "rate": room.rate_per_night,
            #         "amount": room.room_total
            #     }]
                
            #     hrr = frappe.get_doc({
            #         "doctype": "Hotel Room Reservation",
            #         "booking_number": reservation.reservation_number,
            #         "front_desk_reservation": reservation.name,
            #         "room_number": room.room_number,
            #         "from_date": reservation.from_date,
            #         "to_date": reservation.to_date,
            #         "rate": room.rate_per_night,
            #         "discount": 0,
            #         "guest_name": room.guest_name,
            #         "customer": room.guest_customer,
            #         "status": "Booked",
            #         "payment_status": "Pending",
            #         "items": reservation_items,
            #         "net_total": room.room_total
            #     })
                
            #     hrr.flags.ignore_permissions = True
            #     hrr.insert()
            #     hrr.submit()
                
            #     # Update the reference
            #     room.hotel_room_reservation = hrr.name
            
            # # ✅ Step 2: Create/get hotel guest
            # if not room.hotel_guest:
            #     guest_name = room.guest_name
            #     existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
                
            #     if existing_guest:
            #         room.hotel_guest = existing_guest
            #     else:
            #         try:
            #             hotel_guest = frappe.get_doc({
            #                 "doctype": "Hotel Guest",
            #                 "hotel_guest_name": guest_name,
            #                 "gender": room.guest_gender or "Male",
            #                 "phone_number": room.guest_phone or "",
            #                 "email": room.guest_email or "",
            #                 "id_type": room.guest_id_type or "Passport",
            #                 "id_number": room.guest_id_number or "",
            #                 "customer": room.guest_customer,
            #                 "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
            #             })
            #             hotel_guest.flags.ignore_permissions = True
            #             hotel_guest.insert()
                        
            #             if room.guest_phone:
            #                 frappe.db.set_value("Hotel Guest", hotel_guest.name, "phone_number", room.guest_phone, update_modified=False)
                        
            #             room.hotel_guest = hotel_guest.name
            #         except frappe.DuplicateEntryError:
            #             existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": guest_name}, "name")
            #             if existing_guest:
            #                 room.hotel_guest = existing_guest
            
            # ✅ Step 3: Create check-in record
            check_in = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "guest": room.hotel_guest,
                "room_number": room.room_number,
                "check_in_datetime": now_datetime(),
                "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
                "expected_check_out_datetime": get_datetime(f"{reservation.to_date} {reservation.expected_check_out_time or '12:00:00'}"),
                "rate_amount": room.rate_per_night or 0,
                "status": "Checked In",
                "front_desk_reservation": reservation.name,  # ✅ ADD THIS
                "reservation": room.hotel_room_reservation    # ✅ ADD THIS
            })
            
            check_in.flags.ignore_permissions = True
            check_in.insert()
            check_in.submit()
            
            checked_in_rooms.append(room.room_number)
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Checked in all {0} room(s) and created reservations").format(len(checked_in_rooms))
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
        frappe.throw(_("Error: {0}").format(str(e)))























# # REFACTORED Hotel Front Desk Reservation v3
# # KEY CHANGES:
# # 1. Corporate bookings now CREATE hotel room reservations on submit (like non-corporate)
# # 2. Guest names can be edited before check-in with proper customer/guest creation
# # 3. Check-in creates individual sales invoices per selected rooms (not all rooms)
# # 4. Check-in status tracked per room
# # 5. Payment button on FDR doc for sales invoices

# import frappe
# from frappe import _
# from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days, now_datetime
# from datetime import datetime, timedelta
# import json

# from rhohotel.api import get_room_rate
# from rhohotel.shared_utilities import (
#     create_or_get_item,
#     generate_secure_booking_number
# )


# class HotelFrontDeskReservation(frappe.model.document.Document):
    
#     def before_insert(self):
#         """Generate reservation number before inserting"""
#         if not self.reservation_number:
#             self.reservation_number = generate_secure_booking_number()
    
#     def validate(self):
#         """Validate reservation data"""
#         self.validate_dates()
#         self.validate_rooms()
#         self.calculate_pricing()
#         self.set_total_rooms()
        
#         if self.reservation_type == "Corporate" and self.corporate_guest:
#             self.fetch_corporate_details()
    
#     def on_submit(self):
#         """
#         REFACTORED v3:
#         - ALL reservation types: Create customers + guests + room reservations
#         - Corporate now creates room reservations immediately (same as non-corporate)
#         - Guest names validated and linked properly
#         """
#         try:
#             self.create_customers()
#             self.create_hotel_guests_with_names()
            
#             # Create room reservations for ALL types (including corporate)
#             self.create_room_reservations()
            
#             self.status = "Confirmed"
#             self.db_set("status", "Confirmed")
            
#             frappe.msgprint(
#                 _("Reservation {0} confirmed. Hotel room reservations created.").format(self.name),
#                 indicator="green",
#                 alert=True
#             )
            
#         except Exception as e:
#             frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Submit Error")
#             frappe.throw(_("Error confirming reservation: {0}").format(str(e)))
    
#     def on_cancel(self):
#         """Cancel all linked Hotel Room Reservations"""
#         try:
#             room_reservations = frappe.get_all(
#                 "Hotel Room Reservation",
#                 filters={"front_desk_reservation": self.name, "docstatus": 1},
#                 fields=["name"]
#             )
            
#             for res in room_reservations:
#                 doc = frappe.get_doc("Hotel Room Reservation", res.name)
#                 doc.flags.ignore_permissions = True
#                 doc.cancel()
            
#             self.status = "Cancelled"
            
#         except Exception as e:
#             frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Cancel Error")
#             frappe.throw(_("Error cancelling reservation: {0}").format(str(e)))
    
#     # ═══════════════════════════════════════════════════════════════════════
#     # VALIDATION
#     # ═══════════════════════════════════════════════════════════════════════
    
#     def validate_dates(self):
#         """Validate check-in and check-out dates"""
#         if not self.from_date or not self.to_date:
#             frappe.throw(_("Check-in and Check-out dates are required"))
        
#         from_date = getdate(self.from_date)
#         to_date = getdate(self.to_date)
        
#         if to_date <= from_date:
#             frappe.throw(_("Check-out date must be after check-in date"))
        
#         self.number_of_nights = date_diff(to_date, from_date)
        
#         if self.number_of_nights < 1:
#             frappe.throw(_("Minimum 1 night required"))
    
#     def validate_rooms(self):
#         """Validate room availability and details"""
#         if not self.rooms:
#             frappe.throw(_("At least one room is required"))
        
#         seen_rooms = set()
        
#         for idx, room in enumerate(self.rooms, 1):
#             if room.room_number in seen_rooms:
#                 frappe.throw(_("Room {0} appears multiple times").format(room.room_number))
#             seen_rooms.add(room.room_number)
            
#             if not self.is_room_available(room.room_number):
#                 frappe.throw(_("Room {0} is not available for selected dates").format(room.room_number))
            
#             if not room.guest_name:
#                 room.guest_name = self.primary_guest_name or f"Guest - Room {room.room_number}"
            
#             room.number_of_nights = self.number_of_nights
            
#             room_doc = frappe.get_doc("Hotel Room", room.room_number)
#             room.room_type = room_doc.room_type
            
#             rate_per_night = get_room_rate(room.room_type, check_in_date=str(self.from_date))
            
#             if not rate_per_night or rate_per_night == 0:
#                 frappe.throw(_("No rate found for room type {0}").format(room.room_type))
            
#             room.rate_per_night = rate_per_night
#             room.room_total = rate_per_night * self.number_of_nights
            
#             tariff = frappe.db.get_value(
#                 "Hotel Room Tariff",
#                 {"room_type": room.room_type, "is_active": 1},
#                 ["rate_type", "hotel_season"],
#                 as_dict=True
#             )
            
#             if tariff:
#                 room.rate_type = tariff.get("rate_type", "Standard")
#                 season_type = frappe.db.get_value(
#                     "Hotel Season",
#                     tariff.get("hotel_season"),
#                     "season_type"
#                 ) if tariff.get("hotel_season") else None
#                 room.season_type = season_type or ""
    
#     def is_room_available(self, room_number):
#         """Check if room is available for the selected dates"""
#         room_status = frappe.db.get_value("Hotel Room", room_number, "status")
#         if room_status != "Vacant":
#             return False
        
#         overlapping = frappe.db.sql("""
#             SELECT COUNT(*) as count
#             FROM `tabHotel Room Reservation`
#             WHERE room_number = %s
#             AND status NOT IN ('Cancelled', 'Completed')
#             AND from_date < %s
#             AND to_date > %s
#         """, (room_number, self.to_date, self.from_date), as_dict=True)
        
#         if overlapping and overlapping[0].count > 0:
#             return False
        
#         checked_in = frappe.db.sql("""
#             SELECT COUNT(*) as count
#             FROM `tabHotel Room Check In`
#             WHERE room_number = %s
#             AND status IN ('Draft', 'Checked In')
#             AND DATE(check_in_datetime) < %s
#             AND DATE(expected_check_out_datetime) > %s
#         """, (room_number, self.to_date, self.from_date), as_dict=True)
        
#         if checked_in and checked_in[0].count > 0:
#             return False
        
#         return True
    
#     def calculate_pricing(self):
#         """Calculate total pricing with discount"""
#         self.subtotal = sum(room.room_total for room in self.rooms)
        
#         self.discount_amount = 0
#         if self.discount_type and self.discount:
#             if self.discount_type == "Percentage":
#                 self.discount_amount = (self.subtotal * self.discount) / 100
#             elif self.discount_type == "Amount":
#                 self.discount_amount = self.discount
        
#         self.total_amount = self.subtotal - self.discount_amount
        
#         if self.total_amount < 0:
#             self.total_amount = 0
    
#     def set_total_rooms(self):
#         """Set total number of rooms"""
#         self.total_rooms = len(self.rooms)
    
#     def fetch_corporate_details(self):
#         """Fetch corporate guest details"""
#         if not self.corporate_guest:
#             return
        
#         corporate = frappe.get_doc("Hotel Guest", self.corporate_guest)
        
#         if corporate.guest_type != "Corporate":
#             frappe.throw(_("Selected guest is not a corporate client"))
        
#         self.customer = corporate.customer
#         self.primary_guest_name = corporate.hotel_guest_name
#         self.primary_guest_email = corporate.email or ""
#         self.primary_guest_phone = corporate.phone_number or ""
    
#     # ═══════════════════════════════════════════════════════════════════════
#     # DOCUMENT CREATION
#     # ═══════════════════════════════════════════════════════════════════════
    
#     def create_customers(self):
#         """Create or get customers for each guest"""
#         if self.reservation_type == "Corporate":
#             for room in self.rooms:
#                 room.guest_customer = self.customer
#         else:
#             for room in self.rooms:
#                 customer_id = self.get_or_create_customer(
#                     room.guest_name,
#                     room.guest_email,
#                     room.guest_phone
#                 )
#                 room.guest_customer = customer_id
                
#                 if not self.customer:
#                     self.customer = customer_id
    
#     def get_or_create_customer(self, name, email, phone):
#         """Get existing or create new customer"""
#         if email:
#             existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
#             if existing:
#                 return existing
        
#         if phone:
#             clean_phone = phone.replace(" ", "").replace("-", "")
#             existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
#             if existing:
#                 return existing
        
#         customer = frappe.get_doc({
#             "doctype": "Customer",
#             "customer_name": name,
#             "customer_type": "Individual",
#             "email_id": email or "",
#             "mobile_no": phone or "",
#             "territory": frappe.db.get_default("territory") or "Nigeria",
#             "customer_group": frappe.db.get_default("customer_group") or "Individual"
#         })
#         customer.flags.ignore_permissions = True
#         customer.insert()
        
#         return customer.name
    
#     def create_hotel_guests_with_names(self):
#         """
#         Create Hotel Guests with smart name handling:
#         - Use guest_name from room
#         - Apply proper validation and linking
#         """
#         rooms_missing_names = []
        
#         for room in self.rooms:
#             guest_name = room.guest_name
            
#             # Try to derive name if missing
#             if not guest_name or guest_name.startswith("Guest - Room"):
#                 if self.primary_guest_name:
#                     guest_name = self.primary_guest_name
                
#                 # Still no name?
#                 if not guest_name or guest_name.startswith("Guest - Room"):
#                     rooms_missing_names.append(room.room_number)
#                     continue
#                 else:
#                     room.guest_name = guest_name
            
#             # Create guest
#             self.get_or_create_hotel_guest(room)
        
#         # Notify if any rooms missing names
#         if rooms_missing_names:
#             frappe.msgprint({
#                 'title': _('Guest Names Required'),
#                 'message': _('The following rooms do not have guest names: {0}').format(', '.join(rooms_missing_names)),
#                 'indicator': 'orange'
#             })
    
#     def get_or_create_hotel_guest(self, room):
#         """Create Hotel Guest if not exists"""
#         guest_name = room.guest_name
        
#         if not guest_name or guest_name.startswith("Guest - Room"):
#             return None
        
#         if frappe.db.exists("Hotel Guest", {'hotel_guest_name': guest_name}):
#             room.hotel_guest = guest_name
#             return guest_name
        
#         try:
#             guest = frappe.get_doc({
#                 "doctype": "Hotel Guest",
#                 "hotel_guest_name": guest_name,
#                 "phone_number": room.guest_phone or "",
#                 "email": room.guest_email or "",
#                 "gender": room.guest_gender or "Male",
#                 "id_type": room.guest_id_type or "Passport",
#                 "id_number": room.guest_id_number or "",
#                 "customer": room.guest_customer,
#                 "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
#             })
#             guest.flags.ignore_permissions = True
#             guest.insert()
#             room.hotel_guest = guest.name
#             return guest.name
            
#         except frappe.exceptions.InvalidPhoneNumberError:
#             # Retry without phone
#             guest = frappe.get_doc({
#                 "doctype": "Hotel Guest",
#                 "hotel_guest_name": guest_name,
#                 "phone_number": "",
#                 "email": room.guest_email or "",
#                 "gender": room.guest_gender or "Male",
#                 "id_type": room.guest_id_type or "Passport",
#                 "id_number": room.guest_id_number or "",
#                 "customer": room.guest_customer,
#                 "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
#             })
#             guest.flags.ignore_permissions = True
#             guest.insert()
            
#             if room.guest_phone:
#                 frappe.db.set_value(
#                     "Hotel Guest",
#                     guest.name,
#                     "phone_number",
#                     room.guest_phone,
#                     update_modified=False
#                 )
            
#             room.hotel_guest = guest.name
#             return guest.name
    
#     def create_room_reservations(self):
#         """Create Hotel Room Reservations for ALL types"""
#         for room in self.rooms:
#             reservation_items = [{
#                 "room_type": room.room_type,
#                 "rate_type": room.rate_type,
#                 "season_type": room.season_type,
#                 "qty": room.number_of_nights,
#                 "rate": room.rate_per_night,
#                 "amount": room.room_total
#             }]
            
#             reservation = frappe.get_doc({
#                 "doctype": "Hotel Room Reservation",
#                 "booking_number": self.reservation_number,
#                 "front_desk_reservation": self.name,
#                 "room_number": room.room_number,
#                 "from_date": self.from_date,
#                 "to_date": self.to_date,
#                 "rate": room.rate_per_night,
#                 "discount": 0,
#                 "guest_name": room.guest_name,
#                 "customer": room.guest_customer,
#                 "status": "Booked",
#                 "payment_status": "Pending",
#                 "items": reservation_items,
#                 "net_total": room.room_total
#             })
            
#             reservation.flags.ignore_permissions = True
#             reservation.insert()
#             reservation.submit()
            
#             # Store reference back to child table
#             room.hotel_room_reservation = reservation.name


# # ═══════════════════════════════════════════════════════════════════════════
# # API ENDPOINTS
# # ═══════════════════════════════════════════════════════════════════════════

# @frappe.whitelist()
# def update_guest_names_before_checkin(reservation_name, guest_updates):
#     """
#     Update guest names and details BEFORE check-in
#     Creates/updates customers and hotel guests with proper linking
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         guest_updates: List of {room_idx, guest_name, guest_email, guest_phone}
#     """
#     try:
#         if isinstance(guest_updates, str):
#             guest_updates = json.loads(guest_updates)
        
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Can only update guest names for submitted reservations"))
        
#         updated_rooms = []
        
#         for update in guest_updates:
#             room_idx = update.get("room_idx")
#             guest_name = update.get("guest_name", "").strip()
#             guest_email = update.get("guest_email", "").strip()
#             guest_phone = update.get("guest_phone", "").strip()
            
#             if room_idx is None:
#                 continue
            
#             if room_idx >= len(reservation.rooms):
#                 continue
            
#             room = reservation.rooms[room_idx]
            
#             # Update room with new guest info
#             room.guest_name = guest_name or room.guest_name
#             if guest_email:
#                 room.guest_email = guest_email
#             if guest_phone:
#                 room.guest_phone = guest_phone
            
#             # Create/update customer
#             if not room.guest_customer or room.guest_customer == "":
#                 customer_id = frappe.db.get_value(
#                     "Customer",
#                     {"email_id": guest_email},
#                     "name"
#                 ) if guest_email else None
                
#                 if not customer_id:
#                     customer_id = frappe.db.get_value(
#                         "Customer",
#                         {"mobile_no": guest_phone},
#                         "name"
#                     ) if guest_phone else None
                
#                 if not customer_id:
#                     # Create new customer
#                     customer = frappe.get_doc({
#                         "doctype": "Customer",
#                         "customer_name": guest_name,
#                         "customer_type": "Individual",
#                         "email_id": guest_email or "",
#                         "mobile_no": guest_phone or "",
#                         "territory": frappe.db.get_default("territory") or "Nigeria",
#                         "customer_group": frappe.db.get_default("customer_group") or "Individual"
#                     })
#                     customer.flags.ignore_permissions = True
#                     customer.insert()
#                     customer_id = customer.name
                
#                 room.guest_customer = customer_id
            
#             # Create/get hotel guest
#             if not room.hotel_guest or room.hotel_guest == "":
#                 existing_guest = frappe.db.get_value(
#                     "Hotel Guest",
#                     {"hotel_guest_name": guest_name},
#                     "name"
#                 )
                
#                 if existing_guest:
#                     room.hotel_guest = existing_guest
#                 else:
#                     try:
#                         hotel_guest = frappe.get_doc({
#                             "doctype": "Hotel Guest",
#                             "hotel_guest_name": guest_name,
#                             "phone_number": guest_phone or "",
#                             "email": guest_email or "",
#                             "gender": room.guest_gender or "Male",
#                             "id_type": room.guest_id_type or "Passport",
#                             "id_number": room.guest_id_number or "",
#                             "customer": room.guest_customer,
#                             "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
#                         })
#                         hotel_guest.flags.ignore_permissions = True
#                         hotel_guest.insert()
#                         room.hotel_guest = hotel_guest.name
#                     except frappe.DuplicateEntryError:
#                         existing_guest = frappe.db.get_value(
#                             "Hotel Guest",
#                             {"hotel_guest_name": guest_name},
#                             "name"
#                         )
#                         if existing_guest:
#                             room.hotel_guest = existing_guest
            
#             # Update linked hotel room reservation
#             if room.hotel_room_reservation:
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     room.hotel_room_reservation,
#                     {
#                         "guest_name": guest_name,
#                         "customer": room.guest_customer
#                     }
#                 )
            
#             updated_rooms.append(room.room_number)
        
#         # Save the reservation with updated values
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Updated guest information for {0} room(s)").format(len(updated_rooms)),
#             "rooms": updated_rooms
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Update Guest Names Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
#     """
#     Check in SELECTED rooms and create individual sales invoices per room
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         room_indices: List of room indices to check in (0-based)
#         check_in_notes: Optional notes for check-in
#     """
#     try:
#         if isinstance(room_indices, str):
#             room_indices = json.loads(room_indices)
        
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
#         created_invoices = []
        
#         # Process only selected rooms
#         for idx in room_indices:
#             if idx >= len(reservation.rooms):
#                 continue
            
#             room = reservation.rooms[idx]
            
#             # Ensure guest has a name
#             if not room.guest_name or room.guest_name.startswith("Guest - Room"):
#                 return {
#                     "success": False,
#                     "missing_guest_names": True,
#                     "message": _("Guest names required for rooms: {0}").format(room.room_number)
#                 }
            
#             # Ensure guest exists
#             if not room.hotel_guest:
#                 frappe.throw(_("Hotel guest not found for room {0}").format(room.room_number))
            
#             # ✅ Step 1: Create check-in record
#             check_in = frappe.get_doc({
#                 "doctype": "Hotel Room Check In",
#                 "guest": room.hotel_guest,
#                 "room_number": room.room_number,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
#                 "expected_check_out_datetime": get_datetime(f"{reservation.to_date} 12:00:00"),
#                 "rate_amount": room.rate_per_night or 0,
#                 "status": "Checked In",
#                 "front_desk_reservation": reservation.name,
#                 "reservation": room.hotel_room_reservation
#             })
            
#             check_in.flags.ignore_permissions = True
#             check_in.insert()
#             check_in.submit()
            
#             # ✅ Step 2: Update room reservation status
#             if room.hotel_room_reservation:
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     room.hotel_room_reservation,
#                     "status",
#                     "Checked-In"
#                 )
            
#             # ✅ Step 3: Create individual sales invoice for THIS ROOM ONLY
#             invoice = create_sales_invoice_for_single_room(reservation, room)
#             if invoice:
#                 created_invoices.append(invoice)
            
#             # Mark room as checked in
#             room.check_in_reference = check_in.name
#             room.check_in_status = "Checked In"
            
#             checked_in_rooms.append(room.room_number)
        
#         # Save FDR with updated check-in statuses
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         message = _("Checked in {0} room(s)").format(len(checked_in_rooms))
#         if created_invoices:
#             message += _(" and created {0} invoice(s)").format(len(created_invoices))
        
#         return {
#             "success": True,
#             "message": message,
#             "rooms": checked_in_rooms,
#             "invoices": created_invoices
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_all_rooms(reservation_name, check_in_notes=""):
#     """
#     Check in ALL rooms and create individual sales invoices per room
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
#         created_invoices = []
        
#         # Check all rooms have names
#         for room in reservation.rooms:
#             if not room.guest_name or room.guest_name.startswith("Guest - Room"):
#                 return {
#                     "success": False,
#                     "missing_guest_names": True,
#                     "message": _("Guest names required for all rooms")
#                 }
        
#         # Check in ALL rooms
#         for room in reservation.rooms:
#             if not room.hotel_guest:
#                 frappe.throw(_("Hotel guest not found for room {0}").format(room.room_number))
            
#             # Create check-in record
#             check_in = frappe.get_doc({
#                 "doctype": "Hotel Room Check In",
#                 "guest": room.hotel_guest,
#                 "room_number": room.room_number,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
#                 "expected_check_out_datetime": get_datetime(f"{reservation.to_date} 12:00:00"),
#                 "rate_amount": room.rate_per_night or 0,
#                 "status": "Checked In",
#                 "front_desk_reservation": reservation.name,
#                 "reservation": room.hotel_room_reservation
#             })
            
#             check_in.flags.ignore_permissions = True
#             check_in.insert()
#             check_in.submit()
            
#             # Update room reservation status
#             if room.hotel_room_reservation:
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     room.hotel_room_reservation,
#                     "status",
#                     "Checked-In"
#                 )
            
#             # Create individual invoice for this room
#             invoice = create_sales_invoice_for_single_room(reservation, room)
#             if invoice:
#                 created_invoices.append(invoice)
            
#             room.check_in_reference = check_in.name
#             room.check_in_status = "Checked In"
            
#             checked_in_rooms.append(room.room_number)
        
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Checked in all {0} room(s) and created invoices").format(len(checked_in_rooms)),
#             "rooms": checked_in_rooms,
#             "invoices": created_invoices
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# def create_sales_invoice_for_single_room(reservation, room):
#     """
#     Create a Sales Invoice for a SINGLE room during check-in
#     Called from check_in_selected_rooms or check_in_all_rooms
    
#     Args:
#         reservation: Hotel Front Desk Reservation doc
#         room: Room dict from child table
    
#     Returns:
#         invoice_name or None
#     """
#     try:
#         # Create item for this room type
#         item_name = create_or_get_room_item(room.room_type)
        
#         # Create line items (single room)
#         line_items = [{
#             "item_code": item_name,
#             "item_name": f"{room.room_number} - ({room.room_type})",
#             "description": f"Room {room.room_number} ({room.room_type}) - {reservation.number_of_nights} night(s)",
#             "qty": reservation.number_of_nights,
#             "rate": room.rate_per_night,
#             "amount": room.room_total
#         }]
        
#         # Create Sales Invoice
#         si = frappe.get_doc({
#             "doctype": "Sales Invoice",
#             "customer": room.guest_customer,
#             "posting_date": nowdate(),
#             "due_date": reservation.to_date,
#             "invoice_period_from_date": reservation.from_date,
#             "invoice_period_to_date": reservation.to_date,
#             "reference_no": reservation.reservation_number,
#             "remarks": f"Check-in for Room {room.room_number} - Reservation {reservation.name}",
#             "items": line_items
#         })
        
#         si.flags.ignore_permissions = True
#         si.insert()
#         si.submit()
        
#         # Link to room reservation if exists
#         if room.hotel_room_reservation:
#             frappe.db.set_value(
#                 "Hotel Room Reservation",
#                 room.hotel_room_reservation,
#                 "sales_invoice",
#                 si.name
#             )
        
#         frappe.db.commit()
        
#         return si.name
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Sales Invoice for Single Room Error")
#         return None


# @frappe.whitelist()
# def create_sales_invoice_for_reservation(reservation_name):
#     """
#     Create a Sales Invoice for ENTIRE reservation
#     Used by 'Create Invoice' button (for all rooms not yet checked in)
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted before creating invoice"))
        
#         if reservation.sales_invoice:
#             frappe.throw(_("Sales invoice already exists for this reservation: {0}").format(reservation.sales_invoice))
        
#         # Determine customer
#         customer = reservation.customer
#         if not customer:
#             frappe.throw(_("Customer not set for this reservation"))
        
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


# @frappe.whitelist()
# def pay_sales_invoice(invoice_name, amount, payment_method="Card"):
#     """
#     Create a Payment Entry for a Sales Invoice
#     Called from 'Pay Invoice' button on FDR doc
#     """
#     try:
#         invoice = frappe.get_doc("Sales Invoice", invoice_name)
        
#         if invoice.docstatus != 1:
#             frappe.throw(_("Invoice must be submitted"))
        
#         if invoice.outstanding_amount <= 0:
#             frappe.throw(_("Invoice already paid"))
        
#         # Create Payment Entry
#         payment = frappe.get_doc({
#             "doctype": "Payment Entry",
#             "payment_type": "Receive",
#             "party_type": "Customer",
#             "party": invoice.customer,
#             "posting_date": nowdate(),
#             "paid_amount": min(amount, invoice.outstanding_amount),
#             "received_amount": min(amount, invoice.outstanding_amount),
#             "payment_method": payment_method,
#             "reference_no": invoice.name,
#             "allocations": [{
#                 "doctype": "Payment Entry Detail",
#                 "reference_type": "Sales Invoice",
#                 "reference_name": invoice.name,
#                 "allocation_type": "Received",
#                 "amount": min(amount, invoice.outstanding_amount)
#             }]
#         })
        
#         payment.flags.ignore_permissions = True
#         payment.insert()
#         payment.submit()
        
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Payment recorded successfully"),
#             "payment_entry": payment.name
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Pay Sales Invoice Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# def create_or_get_room_item(room_type):
#     """Create or get an Item for a room type"""
#     try:
#         existing_item = frappe.db.get_value(
#             "Item",
#             {"item_name": room_type, "item_group": "Services"},
#             "name"
#         )
        
#         if existing_item:
#             return existing_item
        
#         item = frappe.get_doc({
#             "doctype": "Item",
#             "item_code": f"ROOM-{room_type.upper().replace(' ', '-')}",
#             "item_name": room_type,
#             "item_group": "Services",
#             "is_stock_item": 0,
#             "valuation_method": "FIFO",
#             "uom": "Night",
#             "standard_selling_rate": 0
#         })
        
#         item.flags.ignore_permissions = True
#         item.insert()
        
#         return item.item_code
    
#     except frappe.exceptions.DuplicateEntryError:
#         return frappe.db.get_value("Item", {"item_name": room_type}, "name")
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Room Item Error")
#         return f"ROOM-{room_type.upper().replace(' ', '-')}"


# @frappe.whitelist()
# def get_available_rooms_for_dropdown(doctype, txt, searchfield, start, page_length, filters, **kwargs):
#     """Query method for dropdown - returns only available rooms"""
#     try:
#         from_date = kwargs.get('from_date')
#         to_date = kwargs.get('to_date')
#         room_type = kwargs.get('room_type')
        
#         if not from_date or not to_date:
#             all_rooms = frappe.get_all(
#                 "Hotel Room",
#                 filters={
#                     "status": "Vacant",
#                     "operational_status": "In Service",
#                     "maintenance_flag": 0
#                 },
#                 fields=["name"],
#                 limit_page_length=int(page_length) if page_length else 10
#             )
#             return [[r.name] for r in all_rooms]
        
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             return []
        
#         base_filters = {
#             "status": "Vacant",
#             "operational_status": "In Service",
#             "maintenance_flag": 0
#         }
        
#         if room_type:
#             base_filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             filters=base_filters,
#             fields=["name", "room_type", "floor", "capacity"],
#             limit_page_length=int(page_length) if page_length else 10
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
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
        
#         booked_rooms = [r.room_number for r in overlapping_reservations]
        
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
        
#         checked_in_rooms = [r.room_number for r in active_checkins]
        
#         unavailable = set(booked_rooms + checked_in_rooms)
#         available_rooms = [r.name for r in all_rooms if r.name not in unavailable]
        
#         return [[room] for room in available_rooms]
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms for Dropdown Error")
#         return []


# @frappe.whitelist()
# def get_available_rooms(from_date, to_date, room_type=None):
#     """Get available rooms for selected dates"""
#     try:
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             frappe.throw(_("Check-out date must be after check-in date"))
        
#         filters = {
#             "status": "Vacant",
#             "operational_status": "In Service",
#             "maintenance_flag": 0
#         }
        
#         if room_type:
#             filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             filters=filters,
#             fields=["name", "room_type", "floor", "capacity"]
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
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
        
#         booked_rooms = [r.room_number for r in overlapping_reservations]
        
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
        
#         checked_in_rooms = [r.room_number for r in active_checkins]
        
#         unavailable = set(booked_rooms + checked_in_rooms)
#         available_rooms = [r for r in all_rooms if r.name not in unavailable]
        
#         for room in available_rooms:
#             rate = get_room_rate(room.room_type, check_in_date=str(from_date))
#             room["rate_per_night"] = rate
#             num_nights = date_diff(to_date_obj, from_date_obj)
#             room["total_amount"] = rate * num_nights
        
#         return available_rooms
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))



















# # REFACTORED Hotel Front Desk Reservation v3
# # KEY CHANGES:
# # 1. Corporate bookings now CREATE hotel room reservations on submit (like non-corporate)
# # 2. Guest names can be edited before check-in with proper customer/guest creation
# # 3. Check-in creates individual sales invoices per selected rooms (not all rooms)
# # 4. Check-in status tracked per room
# # 5. Payment button on FDR doc for sales invoices

# import frappe
# from frappe import _
# from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days, now_datetime
# from datetime import datetime, timedelta
# import json

# from rhohotel.api import get_room_rate
# from rhohotel.shared_utilities import (
#     create_or_get_item,
#     generate_secure_booking_number
# )


# class HotelFrontDeskReservation(frappe.model.document.Document):
    
#     def before_insert(self):
#         """Generate reservation number before inserting"""
#         if not self.reservation_number:
#             self.reservation_number = generate_secure_booking_number()
    
#     def validate(self):
#         """Validate reservation data"""
#         self.validate_dates()
#         self.validate_rooms()
#         self.calculate_pricing()
#         self.set_total_rooms()
        
#         if self.reservation_type == "Corporate" and self.corporate_guest:
#             self.fetch_corporate_details()
    
#     def on_submit(self):
#         """
#         REFACTORED v3:
#         - ALL reservation types: Create customers + guests + room reservations
#         - Corporate now creates room reservations immediately (same as non-corporate)
#         - Guest names validated and linked properly
#         """
#         try:
#             self.create_customers()
#             self.create_hotel_guests_with_names()
            
#             # Create room reservations for ALL types (including corporate)
#             self.create_room_reservations()
            
#             self.status = "Confirmed"
#             self.db_set("status", "Confirmed")
            
#             frappe.msgprint(
#                 _("Reservation {0} confirmed. Hotel room reservations created.").format(self.name),
#                 indicator="green",
#                 alert=True
#             )
            
#         except Exception as e:
#             frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Submit Error")
#             frappe.throw(_("Error confirming reservation: {0}").format(str(e)))
    
#     def on_cancel(self):
#         """Cancel all linked Hotel Room Reservations"""
#         try:
#             room_reservations = frappe.get_all(
#                 "Hotel Room Reservation",
#                 filters={"front_desk_reservation": self.name, "docstatus": 1},
#                 fields=["name"]
#             )
            
#             for res in room_reservations:
#                 doc = frappe.get_doc("Hotel Room Reservation", res.name)
#                 doc.flags.ignore_permissions = True
#                 doc.cancel()
            
#             self.status = "Cancelled"
            
#         except Exception as e:
#             frappe.log_error(frappe.get_traceback(), "Front Desk Reservation Cancel Error")
#             frappe.throw(_("Error cancelling reservation: {0}").format(str(e)))
    
#     # ═══════════════════════════════════════════════════════════════════════
#     # VALIDATION
#     # ═══════════════════════════════════════════════════════════════════════
    
#     def validate_dates(self):
#         """Validate check-in and check-out dates"""
#         if not self.from_date or not self.to_date:
#             frappe.throw(_("Check-in and Check-out dates are required"))
        
#         from_date = getdate(self.from_date)
#         to_date = getdate(self.to_date)
        
#         if to_date <= from_date:
#             frappe.throw(_("Check-out date must be after check-in date"))
        
#         self.number_of_nights = date_diff(to_date, from_date)
        
#         if self.number_of_nights < 1:
#             frappe.throw(_("Minimum 1 night required"))
    
#     def validate_rooms(self):
#         """Validate room availability and details"""
#         if not self.rooms:
#             frappe.throw(_("At least one room is required"))
        
#         seen_rooms = set()
        
#         for idx, room in enumerate(self.rooms, 1):
#             if room.room_number in seen_rooms:
#                 frappe.throw(_("Room {0} appears multiple times").format(room.room_number))
#             seen_rooms.add(room.room_number)
            
#             if not self.is_room_available(room.room_number):
#                 frappe.throw(_("Room {0} is not available for selected dates").format(room.room_number))
            
#             if not room.guest_name:
#                 room.guest_name = self.primary_guest_name or f"Guest - Room {room.room_number}"
            
#             room.number_of_nights = self.number_of_nights
            
#             room_doc = frappe.get_doc("Hotel Room", room.room_number)
#             room.room_type = room_doc.room_type
            
#             rate_per_night = get_room_rate(room.room_type, check_in_date=str(self.from_date))
            
#             if not rate_per_night or rate_per_night == 0:
#                 frappe.throw(_("No rate found for room type {0}").format(room.room_type))
            
#             room.rate_per_night = rate_per_night
#             room.room_total = rate_per_night * self.number_of_nights
            
#             tariff = frappe.db.get_value(
#                 "Hotel Room Tariff",
#                 {"room_type": room.room_type, "is_active": 1},
#                 ["rate_type", "hotel_season"],
#                 as_dict=True
#             )
            
#             if tariff:
#                 room.rate_type = tariff.get("rate_type", "Standard")
#                 season_type = frappe.db.get_value(
#                     "Hotel Season",
#                     tariff.get("hotel_season"),
#                     "season_type"
#                 ) if tariff.get("hotel_season") else None
#                 room.season_type = season_type or ""
    
#     def is_room_available(self, room_number):
#         """Check if room is available for the selected dates"""
#         room_status = frappe.db.get_value("Hotel Room", room_number, "status")
#         if room_status != "Vacant":
#             return False
        
#         overlapping = frappe.db.sql("""
#             SELECT COUNT(*) as count
#             FROM `tabHotel Room Reservation`
#             WHERE room_number = %s
#             AND status NOT IN ('Cancelled', 'Completed')
#             AND from_date < %s
#             AND to_date > %s
#         """, (room_number, self.to_date, self.from_date), as_dict=True)
        
#         if overlapping and overlapping[0].count > 0:
#             return False
        
#         checked_in = frappe.db.sql("""
#             SELECT COUNT(*) as count
#             FROM `tabHotel Room Check In`
#             WHERE room_number = %s
#             AND status IN ('Draft', 'Checked In')
#             AND DATE(check_in_datetime) < %s
#             AND DATE(expected_check_out_datetime) > %s
#         """, (room_number, self.to_date, self.from_date), as_dict=True)
        
#         if checked_in and checked_in[0].count > 0:
#             return False
        
#         return True
    
#     def calculate_pricing(self):
#         """Calculate total pricing with discount"""
#         self.subtotal = sum(room.room_total for room in self.rooms)
        
#         self.discount_amount = 0
#         if self.discount_type and self.discount:
#             if self.discount_type == "Percentage":
#                 self.discount_amount = (self.subtotal * self.discount) / 100
#             elif self.discount_type == "Amount":
#                 self.discount_amount = self.discount
        
#         self.total_amount = self.subtotal - self.discount_amount
        
#         if self.total_amount < 0:
#             self.total_amount = 0
    
#     def set_total_rooms(self):
#         """Set total number of rooms"""
#         self.total_rooms = len(self.rooms)
    
#     def fetch_corporate_details(self):
#         """Fetch corporate guest details"""
#         if not self.corporate_guest:
#             return
        
#         corporate = frappe.get_doc("Hotel Guest", self.corporate_guest)
        
#         if corporate.guest_type != "Corporate":
#             frappe.throw(_("Selected guest is not a corporate client"))
        
#         self.customer = corporate.customer
#         self.primary_guest_name = corporate.hotel_guest_name
#         self.primary_guest_email = corporate.email or ""
#         self.primary_guest_phone = corporate.phone_number or ""
    
#     # ═══════════════════════════════════════════════════════════════════════
#     # DOCUMENT CREATION
#     # ═══════════════════════════════════════════════════════════════════════
    
#     def create_customers(self):
#         """Create or get customers for each guest"""
#         if self.reservation_type == "Corporate":
#             for room in self.rooms:
#                 room.guest_customer = self.customer
#         else:
#             for room in self.rooms:
#                 customer_id = self.get_or_create_customer(
#                     room.guest_name,
#                     room.guest_email,
#                     room.guest_phone
#                 )
#                 room.guest_customer = customer_id
                
#                 if not self.customer:
#                     self.customer = customer_id
    
#     def get_or_create_customer(self, name, email, phone):
#         """Get existing or create new customer"""
#         if email:
#             existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
#             if existing:
#                 return existing
        
#         if phone:
#             clean_phone = phone.replace(" ", "").replace("-", "")
#             existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
#             if existing:
#                 return existing
        
#         customer = frappe.get_doc({
#             "doctype": "Customer",
#             "customer_name": name,
#             "customer_type": "Individual",
#             "email_id": email or "",
#             "mobile_no": phone or "",
#             "territory": frappe.db.get_default("territory") or "Nigeria",
#             "customer_group": frappe.db.get_default("customer_group") or "Individual"
#         })
#         customer.flags.ignore_permissions = True
#         customer.insert()
        
#         return customer.name
    
#     def create_hotel_guests_with_names(self):
#         """
#         Create Hotel Guests with smart name handling:
#         - Use guest_name from room
#         - Apply proper validation and linking
#         """
#         rooms_missing_names = []
        
#         for room in self.rooms:
#             guest_name = room.guest_name
            
#             # Try to derive name if missing
#             if not guest_name or guest_name.startswith("Guest - Room"):
#                 if self.primary_guest_name:
#                     guest_name = self.primary_guest_name
                
#                 # Still no name?
#                 if not guest_name or guest_name.startswith("Guest - Room"):
#                     rooms_missing_names.append(room.room_number)
#                     continue
#                 else:
#                     room.guest_name = guest_name
            
#             # Create guest
#             self.get_or_create_hotel_guest(room)
        
#         # Notify if any rooms missing names
#         if rooms_missing_names:
#             frappe.msgprint({
#                 'title': _('Guest Names Required'),
#                 'message': _('The following rooms do not have guest names: {0}').format(', '.join(rooms_missing_names)),
#                 'indicator': 'orange'
#             })
    
#     def get_or_create_hotel_guest(self, room):
#         """Create Hotel Guest if not exists - ALWAYS as Individual"""
#         guest_name = room.guest_name
        
#         if not guest_name or guest_name.startswith("Guest - Room"):
#             return None
        
#         if frappe.db.exists("Hotel Guest", {'hotel_guest_name': guest_name}):
#             room.hotel_guest = guest_name
#             return guest_name
        
#         try:
#             guest = frappe.get_doc({
#                 "doctype": "Hotel Guest",
#                 "hotel_guest_name": guest_name,
#                 "phone_number": room.guest_phone or "",
#                 "email": room.guest_email or "",
#                 "gender": room.guest_gender or "Male",
#                 "id_type": room.guest_id_type or "Passport",
#                 "id_number": room.guest_id_number or "",
#                 "customer": room.guest_customer,
#                 "guest_type": "Individual"  # ✅ ALWAYS Individual, never Corporate
#             })
#             guest.flags.ignore_permissions = True
#             guest.insert()
#             room.hotel_guest = guest.name
#             return guest.name
            
#         except frappe.exceptions.InvalidPhoneNumberError:
#             # Retry without phone
#             guest = frappe.get_doc({
#                 "doctype": "Hotel Guest",
#                 "hotel_guest_name": guest_name,
#                 "phone_number": "",
#                 "email": room.guest_email or "",
#                 "gender": room.guest_gender or "Male",
#                 "id_type": room.guest_id_type or "Passport",
#                 "id_number": room.guest_id_number or "",
#                 "customer": room.guest_customer,
#                 "guest_type": "Individual"  # ✅ ALWAYS Individual, never Corporate
#             })
#             guest.flags.ignore_permissions = True
#             guest.insert()
            
#             if room.guest_phone:
#                 frappe.db.set_value(
#                     "Hotel Guest",
#                     guest.name,
#                     "phone_number",
#                     room.guest_phone,
#                     update_modified=False
#                 )
            
#             room.hotel_guest = guest.name
#             return guest.name
    
#     def create_room_reservations(self):
#         """Create Hotel Room Reservations for ALL types"""
#         for room in self.rooms:
#             reservation_items = [{
#                 "room_type": room.room_type,
#                 "rate_type": room.rate_type,
#                 "season_type": room.season_type,
#                 "qty": room.number_of_nights,
#                 "rate": room.rate_per_night,
#                 "amount": room.room_total
#             }]
            
#             reservation = frappe.get_doc({
#                 "doctype": "Hotel Room Reservation",
#                 "booking_number": self.reservation_number,
#                 "front_desk_reservation": self.name,
#                 "room_number": room.room_number,
#                 "from_date": self.from_date,
#                 "to_date": self.to_date,
#                 "rate": room.rate_per_night,
#                 "discount": 0,
#                 "guest_name": room.guest_name,
#                 # "customer": room.guest_customer,
#                 "status": "Booked",
#                 "payment_status": "Pending",
#                 "items": reservation_items,
#                 "net_total": room.room_total
#             })
            
#             reservation.flags.ignore_permissions = True
#             reservation.insert()
#             reservation.submit()
            
#             # Store reference back to child table
#             room.hotel_room_reservation = reservation.name


# # ═══════════════════════════════════════════════════════════════════════════
# # API ENDPOINTS
# # ═══════════════════════════════════════════════════════════════════════════


# # @frappe.whitelist()
# # def update_guest_details_all_rooms(reservation_name, guest_updates):
# #     """
# #     Update guest details for all/multiple rooms
# #     Called from "Edit Guest Data" button
    
# #     IMPROVEMENTS:
# #     1. Lookup Hotel Guest by email/phone FIRST (not just name)
# #     2. Properly update linked Hotel Room Reservation with guest_name and customer
# #     3. Debug logging to track what's being updated
    
# #     Args:
# #         reservation_name: Front Desk Reservation name
# #         guest_updates: List of {room_idx, guest_name, guest_gender, guest_id_type, 
# #                                guest_id_number, guest_phone, guest_email}
# #     """
# #     try:
# #         if isinstance(guest_updates, str):
# #             guest_updates = json.loads(guest_updates)
        
# #         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
# #         if reservation.docstatus != 1:
# #             frappe.throw(_("Can only update guest details for submitted reservations"))
        
# #         updated_rooms = []
        
# #         for update in guest_updates:
# #             room_idx = update.get("room_idx")
# #             guest_name = update.get("guest_name", "").strip()
# #             guest_gender = update.get("guest_gender", "Male")
# #             guest_id_type = update.get("guest_id_type", "")
# #             guest_id_number = update.get("guest_id_number", "")
# #             guest_phone = update.get("guest_phone", "").strip()
# #             guest_email = update.get("guest_email", "").strip()
            
# #             if room_idx is None or not guest_name:
# #                 continue
            
# #             if room_idx >= len(reservation.rooms):
# #                 continue
            
# #             room = reservation.rooms[room_idx]
            
# #             frappe.logger().info(f"Updating room {room.room_number}: {guest_name}")
            
# #             # Update room with new guest info
# #             room.guest_name = guest_name
# #             room.guest_gender = guest_gender
# #             room.guest_id_type = guest_id_type
# #             room.guest_id_number = guest_id_number
# #             if guest_email:
# #                 room.guest_email = guest_email
# #             if guest_phone:
# #                 room.guest_phone = guest_phone
            
# #             # ═══════════════════════════════════════════════════════════════
# #             # CREATE/UPDATE CUSTOMER
# #             # ═══════════════════════════════════════════════════════════════
            
# #             if not room.guest_customer or room.guest_customer == "":
# #                 customer_id = None
                
# #                 # Try to find by email
# #                 if guest_email:
# #                     customer_id = frappe.db.get_value(
# #                         "Customer",
# #                         {"email_id": guest_email},
# #                         "name"
# #                     )
                
# #                 # Try to find by phone
# #                 if not customer_id and guest_phone:
# #                     clean_phone = guest_phone.replace(" ", "").replace("-", "")
# #                     customer_id = frappe.db.get_value(
# #                         "Customer",
# #                         {"mobile_no": clean_phone},
# #                         "name"
# #                     )
                
# #                 # Create new customer if not found
# #                 if not customer_id:
# #                     customer = frappe.get_doc({
# #                         "doctype": "Customer",
# #                         "customer_name": guest_name,
# #                         "customer_type": "Individual",
# #                         "email_id": guest_email or "",
# #                         "mobile_no": guest_phone or "",
# #                         "territory": frappe.db.get_default("territory") or "Nigeria",
# #                         "customer_group": frappe.db.get_default("customer_group") or "Individual"
# #                     })
# #                     customer.flags.ignore_permissions = True
# #                     customer.insert()
# #                     customer_id = customer.name
# #                     frappe.logger().info(f"Created customer {customer_id} for {guest_name}")
                
# #                 room.guest_customer = customer_id
            
# #             # ═══════════════════════════════════════════════════════════════
# #             # CREATE/UPDATE HOTEL GUEST (lookup by email/phone, not just name)
# #             # ═══════════════════════════════════════════════════════════════
            
# #             if not room.hotel_guest or room.hotel_guest == "":
# #                 existing_guest = None
                
# #                 # Try to find existing guest by email first
# #                 if guest_email:
# #                     existing_guest = frappe.db.get_value(
# #                         "Hotel Guest",
# #                         {"email": guest_email},
# #                         "name"
# #                     )
# #                     if existing_guest:
# #                         frappe.logger().info(f"Found existing guest by email: {existing_guest}")
                
# #                 # Try to find by phone if not found by email
# #                 if not existing_guest and guest_phone:
# #                     clean_phone = guest_phone.replace(" ", "").replace("-", "")
# #                     existing_guest = frappe.db.get_value(
# #                         "Hotel Guest",
# #                         {"phone_number": clean_phone},
# #                         "name"
# #                     )
# #                     if existing_guest:
# #                         frappe.logger().info(f"Found existing guest by phone: {existing_guest}")
                
# #                 # Fall back to name if still not found
# #                 if not existing_guest:
# #                     existing_guest = frappe.db.get_value(
# #                         "Hotel Guest",
# #                         {"hotel_guest_name": guest_name},
# #                         "name"
# #                     )
# #                     if existing_guest:
# #                         frappe.logger().info(f"Found existing guest by name: {existing_guest}")
                
# #                 if existing_guest:
# #                     room.hotel_guest = existing_guest
# #                     # Update existing guest record with new details
# #                     frappe.db.set_value(
# #                         "Hotel Guest",
# #                         existing_guest,
# #                         {
# #                             "hotel_guest_name": guest_name,
# #                             "phone_number": guest_phone or "",
# #                             "email": guest_email or "",
# #                             "gender": guest_gender or "Male",
# #                             "id_type": guest_id_type or "Passport",
# #                             "id_number": guest_id_number or "",
# #                             "customer": room.guest_customer
# #                         }
# #                     )
# #                     frappe.logger().info(f"Updated existing guest {existing_guest}")
# #                 else:
# #                     # Create new hotel guest
# #                     try:
# #                         hotel_guest = frappe.get_doc({
# #                             "doctype": "Hotel Guest",
# #                             "hotel_guest_name": guest_name,
# #                             "phone_number": guest_phone or "",
# #                             "email": guest_email or "",
# #                             "gender": guest_gender or "Male",
# #                             "id_type": guest_id_type or "Passport",
# #                             "id_number": guest_id_number or "",
# #                             "customer": room.guest_customer,
# #                             "guest_type": "Individual"  # ✅ Always Individual
# #                         })
# #                         hotel_guest.flags.ignore_permissions = True
# #                         hotel_guest.insert()
# #                         room.hotel_guest = hotel_guest.name
# #                         frappe.logger().info(f"Created new hotel guest {hotel_guest.name}")
# #                     except frappe.DuplicateEntryError:
# #                         # If duplicate, try to fetch by email/phone again
# #                         existing_guest = None
# #                         if guest_email:
# #                             existing_guest = frappe.db.get_value(
# #                                 "Hotel Guest",
# #                                 {"email": guest_email},
# #                                 "name"
# #                             )
# #                         if not existing_guest and guest_phone:
# #                             clean_phone = guest_phone.replace(" ", "").replace("-", "")
# #                             existing_guest = frappe.db.get_value(
# #                                 "Hotel Guest",
# #                                 {"phone_number": clean_phone},
# #                                 "name"
# #                             )
# #                         if existing_guest:
# #                             room.hotel_guest = existing_guest
# #                             frappe.logger().info(f"Resolved duplicate by finding {existing_guest}")
# #             else:
# #                 # Update existing hotel guest
# #                 frappe.db.set_value(
# #                     "Hotel Guest",
# #                     room.hotel_guest,
# #                     {
# #                         "hotel_guest_name": guest_name,
# #                         "phone_number": guest_phone or "",
# #                         "email": guest_email or "",
# #                         "gender": guest_gender or "Male",
# #                         "id_type": guest_id_type or "Passport",
# #                         "id_number": guest_id_number or ""
# #                     }
# #                 )
# #                 frappe.logger().info(f"Updated hotel guest {room.hotel_guest}")
            
# #             # ═══════════════════════════════════════════════════════════════
# #             # UPDATE LINKED HOTEL ROOM RESERVATION
# #             # ═══════════════════════════════════════════════════════════════
            
# #             if room.hotel_room_reservation:
# #                 frappe.logger().info(f"Updating hotel room reservation: {room.hotel_room_reservation}")
                
# #                 # Hotel Room Reservation only has: guest_name, customer
# #                 # These are the only fields available to update
# #                 frappe.db.set_value(
# #                     "Hotel Room Reservation",
# #                     room.hotel_room_reservation,
# #                     {
# #                         "guest_name": guest_name,
# #                         "customer": room.guest_customer
# #                     },
# #                     update_modified=False
# #                 )
                
# #                 frappe.logger().info(f"Updated hotel room reservation {room.hotel_room_reservation}: guest_name={guest_name}, customer={room.guest_customer}")
# #             else:
# #                 frappe.logger().warn(f"Room {room.room_number} has no hotel_room_reservation link!")
            
# #             updated_rooms.append(room.room_number)
        
# #         # Save the reservation with updated values
# #         reservation.flags.ignore_permissions = True
# #         reservation.save()
# #         frappe.db.commit()
        
# #         frappe.logger().info(f"Successfully updated {len(updated_rooms)} rooms: {updated_rooms}")
        
# #         return {
# #             "success": True,
# #             "message": _("Updated guest details for {0} room(s)").format(len(updated_rooms)),
# #             "rooms": updated_rooms
# #         }
    
# #     except Exception as e:
# #         frappe.log_error(frappe.get_traceback(), "Update Guest Details Error")
# #         frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def update_guest_names_before_checkin(reservation_name, guest_updates):
#     """
#     Update guest names and details BEFORE check-in
#     Creates/updates customers and hotel guests with proper linking
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         guest_updates: List of {room_idx, guest_name, guest_email, guest_phone}
#     """
#     try:
#         if isinstance(guest_updates, str):
#             guest_updates = json.loads(guest_updates)
        
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Can only update guest names for submitted reservations"))
        
#         updated_rooms = []
        
#         for update in guest_updates:
#             room_idx = update.get("room_idx")
#             guest_name = update.get("guest_name", "").strip()
#             guest_email = update.get("guest_email", "").strip()
#             guest_phone = update.get("guest_phone", "").strip()
            
#             if room_idx is None:
#                 continue
            
#             if room_idx >= len(reservation.rooms):
#                 continue
            
#             room = reservation.rooms[room_idx]
            
#             # Update room with new guest info
#             room.guest_name = guest_name or room.guest_name
#             if guest_email:
#                 room.guest_email = guest_email
#             if guest_phone:
#                 room.guest_phone = guest_phone
            
#             # Create/update customer
#             if not room.guest_customer or room.guest_customer == "":
#                 customer_id = frappe.db.get_value(
#                     "Customer",
#                     {"email_id": guest_email},
#                     "name"
#                 ) if guest_email else None
                
#                 if not customer_id:
#                     customer_id = frappe.db.get_value(
#                         "Customer",
#                         {"mobile_no": guest_phone},
#                         "name"
#                     ) if guest_phone else None
                
#                 if not customer_id:
#                     # Create new customer
#                     customer = frappe.get_doc({
#                         "doctype": "Customer",
#                         "customer_name": guest_name,
#                         "customer_type": "Individual",
#                         "email_id": guest_email or "",
#                         "mobile_no": guest_phone or "",
#                         "territory": frappe.db.get_default("territory") or "Nigeria",
#                         "customer_group": frappe.db.get_default("customer_group") or "Individual"
#                     })
#                     customer.flags.ignore_permissions = True
#                     customer.insert()
#                     customer_id = customer.name
                
#                 room.guest_customer = customer_id
            
#             # Create/get hotel guest
#             if not room.hotel_guest or room.hotel_guest == "":
#                 existing_guest = frappe.db.get_value(
#                     "Hotel Guest",
#                     {"hotel_guest_name": guest_name},
#                     "name"
#                 )
                
#                 if existing_guest:
#                     room.hotel_guest = existing_guest
#                 else:
#                     try:
#                         hotel_guest = frappe.get_doc({
#                             "doctype": "Hotel Guest",
#                             "hotel_guest_name": guest_name,
#                             "phone_number": guest_phone or "",
#                             "email": guest_email or "",
#                             "gender": room.guest_gender or "Male",
#                             "id_type": room.guest_id_type or "Passport",
#                             "id_number": room.guest_id_number or "",
#                             "customer": room.guest_customer,
#                             "guest_type": "Individual"  # ✅ ALWAYS Individual
#                         })
#                         hotel_guest.flags.ignore_permissions = True
#                         hotel_guest.insert()
#                         room.hotel_guest = hotel_guest.name
#                     except frappe.DuplicateEntryError:
#                         existing_guest = frappe.db.get_value(
#                             "Hotel Guest",
#                             {"hotel_guest_name": guest_name},
#                             "name"
#                         )
#                         if existing_guest:
#                             room.hotel_guest = existing_guest
            
#             # Update linked hotel room reservation
#             if room.hotel_room_reservation:
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     room.hotel_room_reservation,
#                     {
#                         "guest_name": guest_name,
#                         "customer": room.guest_customer
#                     }
#                 )
            
#             updated_rooms.append(room.room_number)
        
#         # Save the reservation with updated values
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Updated guest information for {0} room(s)").format(len(updated_rooms)),
#             "rooms": updated_rooms
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Update Guest Names Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
#     """
#     Check in SELECTED rooms and create individual sales invoices per room
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         room_indices: List of room indices to check in (0-based)
#         check_in_notes: Optional notes for check-in
#     """
#     try:
#         if isinstance(room_indices, str):
#             room_indices = json.loads(room_indices)
        
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
#         created_invoices = []
        
#         # Process only selected rooms
#         for idx in room_indices:
#             if idx >= len(reservation.rooms):
#                 continue
            
#             room = reservation.rooms[idx]
            
#             # Ensure guest has a name
#             if not room.guest_name or room.guest_name.startswith("Guest - Room"):
#                 return {
#                     "success": False,
#                     "missing_guest_names": True,
#                     "message": _("Guest names required for rooms: {0}").format(room.room_number)
#                 }
            
#             # Ensure guest exists
#             if not room.hotel_guest:
#                 frappe.throw(_("Hotel guest not found for room {0}").format(room.room_number))
            
#             # ✅ Step 1: Create check-in record
#             check_in = frappe.get_doc({
#                 "doctype": "Hotel Room Check In",
#                 "guest": room.hotel_guest,
#                 "room_number": room.room_number,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
#                 "expected_check_out_datetime": get_datetime(f"{reservation.to_date} 12:00:00"),
#                 "rate_amount": room.rate_per_night or 0,
#                 "status": "Checked In",
#                 "front_desk_reservation": reservation.name,
#                 "reservation": room.hotel_room_reservation
#             })
            
#             check_in.flags.ignore_permissions = True
#             check_in.insert()
#             check_in.submit()
            
#             # ✅ Step 2: Update room reservation status
#             if room.hotel_room_reservation:
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     room.hotel_room_reservation,
#                     "status",
#                     "Checked-In"
#                 )
            
#             # ✅ Step 3: Create individual sales invoice for THIS ROOM ONLY
#             invoice = create_sales_invoice_for_single_room(reservation, room)
#             if invoice:
#                 created_invoices.append(invoice)
            
#             # Mark room as checked in
#             room.check_in_reference = check_in.name
#             room.check_in_status = "Checked In"
            
#             checked_in_rooms.append(room.room_number)
        
#         # Save FDR with updated check-in statuses
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         message = _("Checked in {0} room(s)").format(len(checked_in_rooms))
#         if created_invoices:
#             message += _(" and created {0} invoice(s)").format(len(created_invoices))
        
#         return {
#             "success": True,
#             "message": message,
#             "rooms": checked_in_rooms,
#             "invoices": created_invoices
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_all_rooms(reservation_name, check_in_notes=""):
#     """
#     Check in ALL rooms and create individual sales invoices per room
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted"))
        
#         checked_in_rooms = []
#         created_invoices = []
        
#         # Check all rooms have names
#         for room in reservation.rooms:
#             if not room.guest_name or room.guest_name.startswith("Guest - Room"):
#                 return {
#                     "success": False,
#                     "missing_guest_names": True,
#                     "message": _("Guest names required for all rooms")
#                 }
        
#         # Check in ALL rooms
#         for room in reservation.rooms:
#             if not room.hotel_guest:
#                 frappe.throw(_("Hotel guest not found for room {0}").format(room.room_number))
            
#             # Create check-in record
#             check_in = frappe.get_doc({
#                 "doctype": "Hotel Room Check In",
#                 "guest": room.hotel_guest,
#                 "room_number": room.room_number,
#                 "check_in_datetime": now_datetime(),
#                 "number_of_nights": date_diff(getdate(reservation.to_date), getdate(reservation.from_date)),
#                 "expected_check_out_datetime": get_datetime(f"{reservation.to_date} 12:00:00"),
#                 "rate_amount": room.rate_per_night or 0,
#                 "status": "Checked In",
#                 "front_desk_reservation": reservation.name,
#                 "reservation": room.hotel_room_reservation
#             })
            
#             check_in.flags.ignore_permissions = True
#             check_in.insert()
#             check_in.submit()
            
#             # Update room reservation status
#             if room.hotel_room_reservation:
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     room.hotel_room_reservation,
#                     "status",
#                     "Checked-In"
#                 )
            
#             # Create individual invoice for this room
#             invoice = create_sales_invoice_for_single_room(reservation, room)
#             if invoice:
#                 created_invoices.append(invoice)
            
#             room.check_in_reference = check_in.name
#             room.check_in_status = "Checked In"
            
#             checked_in_rooms.append(room.room_number)
        
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Checked in all {0} room(s) and created invoices").format(len(checked_in_rooms)),
#             "rooms": checked_in_rooms,
#             "invoices": created_invoices
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))


# def create_sales_invoice_for_single_room(reservation, room):
#     """
#     Create a Sales Invoice for a SINGLE room during check-in
#     Called from check_in_selected_rooms or check_in_all_rooms
    
#     Args:
#         reservation: Hotel Front Desk Reservation doc
#         room: Room dict from child table
    
#     Returns:
#         invoice_name or None
#     """
#     try:
#         # Create item for this room type
#         item_name = create_or_get_room_item(room.room_type)
        
#         # Create line items (single room)
#         line_items = [{
#             "item_code": item_name,
#             "item_name": f"{room.room_number} - ({room.room_type})",
#             "description": f"Room {room.room_number} ({room.room_type}) - {reservation.number_of_nights} night(s)",
#             "qty": reservation.number_of_nights,
#             "rate": room.rate_per_night,
#             "amount": room.room_total
#         }]
        
#         # Create Sales Invoice
#         si = frappe.get_doc({
#             "doctype": "Sales Invoice",
#             "customer": room.guest_customer,
#             "posting_date": nowdate(),
#             "due_date": reservation.to_date,
#             "invoice_period_from_date": reservation.from_date,
#             "invoice_period_to_date": reservation.to_date,
#             "reference_no": reservation.reservation_number,
#             "remarks": f"Check-in for Room {room.room_number} - Reservation {reservation.name}",
#             "items": line_items
#         })
        
#         si.flags.ignore_permissions = True
#         si.insert()
#         si.submit()
        
#         # Link to room reservation if exists
#         if room.hotel_room_reservation:
#             frappe.db.set_value(
#                 "Hotel Room Reservation",
#                 room.hotel_room_reservation,
#                 "sales_invoice",
#                 si.name
#             )
        
#         frappe.db.commit()
        
#         return si.name
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Sales Invoice for Single Room Error")
#         return None


# @frappe.whitelist()
# def create_sales_invoice_for_reservation(reservation_name):
#     """
#     Create a Sales Invoice for ENTIRE reservation
#     Used by 'Create Invoice' button (for all rooms not yet checked in)
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted before creating invoice"))
        
#         if reservation.sales_invoice:
#             frappe.throw(_("Sales invoice already exists for this reservation: {0}").format(reservation.sales_invoice))
        
#         # Determine customer
#         customer = reservation.customer
#         if not customer:
#             frappe.throw(_("Customer not set for this reservation"))
        
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


# # @frappe.whitelist()
# # def update_guest_details_all_rooms(reservation_name, guest_updates):
# #     """
# #     Update guest details for all/multiple rooms
# #     Called from "Edit Guest Data" button
    
# #     Key: Creates INDIVIDUAL Hotel Guests (not corporate) for edited rooms
    
# #     Args:
# #         reservation_name: Front Desk Reservation name
# #         guest_updates: List of {room_idx, guest_name, guest_gender, guest_id_type, guest_id_number, guest_phone, guest_email}
# #     """
# #     try:
# #         if isinstance(guest_updates, str):
# #             guest_updates = json.loads(guest_updates)
        
# #         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
# #         if reservation.docstatus != 1:
# #             frappe.throw(_("Can only update guest details for submitted reservations"))
        
# #         updated_rooms = []
        
# #         for update in guest_updates:
# #             room_idx = update.get("room_idx")
# #             guest_name = update.get("guest_name", "").strip()
# #             guest_gender = update.get("guest_gender", "Male")
# #             guest_id_type = update.get("guest_id_type", "")
# #             guest_id_number = update.get("guest_id_number", "")
# #             guest_phone = update.get("guest_phone", "").strip()
# #             guest_email = update.get("guest_email", "").strip()
            
# #             if room_idx is None or not guest_name:
# #                 continue
            
# #             if room_idx >= len(reservation.rooms):
# #                 continue
            
# #             room = reservation.rooms[room_idx]
            
# #             # Update room with new guest info
# #             room.guest_name = guest_name
# #             room.guest_gender = guest_gender
# #             room.guest_id_type = guest_id_type
# #             room.guest_id_number = guest_id_number
# #             if guest_email:
# #                 room.guest_email = guest_email
# #             if guest_phone:
# #                 room.guest_phone = guest_phone
            
# #             # ✅ For Corporate Reservations:
# #             # If no individual customer exists, use corporate customer
# #             # If editing, create individual customer
# #             if not room.guest_customer or room.guest_customer == "":
# #                 # Try to find existing customer by email or phone
# #                 customer_id = None
                
# #                 if guest_email:
# #                     customer_id = frappe.db.get_value(
# #                         "Customer",
# #                         {"email_id": guest_email},
# #                         "name"
# #                     )
                
# #                 if not customer_id and guest_phone:
# #                     clean_phone = guest_phone.replace(" ", "").replace("-", "")
# #                     customer_id = frappe.db.get_value(
# #                         "Customer",
# #                         {"mobile_no": clean_phone},
# #                         "name"
# #                     )
                
# #                 if not customer_id:
# #                     # Create new individual customer
# #                     customer = frappe.get_doc({
# #                         "doctype": "Customer",
# #                         "customer_name": guest_name,
# #                         "customer_type": "Individual",
# #                         "email_id": guest_email or "",
# #                         "mobile_no": guest_phone or "",
# #                         "territory": frappe.db.get_default("territory") or "Nigeria",
# #                         "customer_group": frappe.db.get_default("customer_group") or "Individual"
# #                     })
# #                     customer.flags.ignore_permissions = True
# #                     customer.insert()
# #                     customer_id = customer.name
                
# #                 room.guest_customer = customer_id
            
# #             # ✅ Create INDIVIDUAL Hotel Guest (not corporate type)
# #             # Even for corporate bookings, individual guests created here are "Individual" type
# #             if not room.hotel_guest or room.hotel_guest == "":
# #                 existing_guest = frappe.db.get_value(
# #                     "Hotel Guest",
# #                     {"hotel_guest_name": guest_name},
# #                     "name"
# #                 )
                
# #                 if existing_guest:
# #                     room.hotel_guest = existing_guest
# #                 else:
# #                     try:
# #                         # ✅ KEY: guest_type = "Individual" even for corporate reservations
# #                         hotel_guest = frappe.get_doc({
# #                             "doctype": "Hotel Guest",
# #                             "hotel_guest_name": guest_name,
# #                             "phone_number": guest_phone or "",
# #                             "email": guest_email or "",
# #                             "gender": guest_gender or "Male",
# #                             "id_type": guest_id_type or "Passport",
# #                             "id_number": guest_id_number or "",
# #                             "customer": room.guest_customer,
# #                             "guest_type": "Individual"  # ✅ Always Individual when edited
# #                         })
# #                         hotel_guest.flags.ignore_permissions = True
# #                         hotel_guest.insert()
# #                         room.hotel_guest = hotel_guest.name
# #                     except frappe.DuplicateEntryError:
# #                         existing_guest = frappe.db.get_value(
# #                             "Hotel Guest",
# #                             {"hotel_guest_name": guest_name},
# #                             "name"
# #                         )
# #                         if existing_guest:
# #                             room.hotel_guest = existing_guest
# #             else:
# #                 # Update existing hotel guest
# #                 frappe.db.set_value(
# #                     "Hotel Guest",
# #                     room.hotel_guest,
# #                     {
# #                         "phone_number": guest_phone or "",
# #                         "email": guest_email or "",
# #                         "gender": guest_gender or "Male",
# #                         "id_type": guest_id_type or "Passport",
# #                         "id_number": guest_id_number or ""
# #                     }
# #                 )
            
# #             # Update linked hotel room reservation with new details
# #             if room.hotel_room_reservation:
# #                 frappe.db.set_value(
# #                     "Hotel Room Reservation",
# #                     room.hotel_room_reservation,
# #                     {
# #                         "guest_name": guest_name,
# #                         "customer": room.guest_customer
# #                     }
# #                 )
            
# #             updated_rooms.append(room.room_number)
        
# #         # Save the reservation with updated values
# #         reservation.flags.ignore_permissions = True
# #         reservation.save()
# #         frappe.db.commit()
        
# #         return {
# #             "success": True,
# #             "message": _("Updated guest details for {0} room(s)").format(len(updated_rooms)),
# #             "rooms": updated_rooms
# #         }
    
# #     except Exception as e:
# #         frappe.log_error(frappe.get_traceback(), "Update Guest Details Error")
# #         frappe.throw(_("Error: {0}").format(str(e)))



# #     """
# #     Create a Payment Entry for a Sales Invoice
# #     Called from 'Pay Invoice' button on FDR doc
# #     """
# #     try:
# #         invoice = frappe.get_doc("Sales Invoice", invoice_name)
        
# #         if invoice.docstatus != 1:
# #             frappe.throw(_("Invoice must be submitted"))
        
# #         if invoice.outstanding_amount <= 0:
# #             frappe.throw(_("Invoice already paid"))
        
# #         # Create Payment Entry
# #         payment = frappe.get_doc({
# #             "doctype": "Payment Entry",
# #             "payment_type": "Receive",
# #             "party_type": "Customer",
# #             "party": invoice.customer,
# #             "posting_date": nowdate(),
# #             "paid_amount": min(amount, invoice.outstanding_amount),
# #             "received_amount": min(amount, invoice.outstanding_amount),
# #             "payment_method": payment_method,
# #             "reference_no": invoice.name,
# #             "allocations": [{
# #                 "doctype": "Payment Entry Detail",
# #                 "reference_type": "Sales Invoice",
# #                 "reference_name": invoice.name,
# #                 "allocation_type": "Received",
# #                 "amount": min(amount, invoice.outstanding_amount)
# #             }]
# #         })
        
# #         payment.flags.ignore_permissions = True
# #         payment.insert()
# #         payment.submit()
        
# #         frappe.db.commit()
        
# #         return {
# #             "success": True,
# #             "message": _("Payment recorded successfully"),
# #             "payment_entry": payment.name
# #         }
    
# #     except Exception as e:
# #         frappe.log_error(frappe.get_traceback(), "Pay Sales Invoice Error")
# #         frappe.throw(_("Error: {0}").format(str(e)))

# @frappe.whitelist()
# def update_guest_details_all_rooms(reservation_name, guest_updates):
#     """
#     Update guest details for all/multiple rooms
#     Called from "Edit Guest Data" button
    
#     KEY FIXES:
#     1. Reload FDR to get fresh data from DB
#     2. Lookup Hotel Guest by email/phone (not just name)
#     3. Update child table directly in DB for Hotel Room Reservation
#     4. Better logging to track what's happening
    
#     Args:
#         reservation_name: Front Desk Reservation name
#         guest_updates: List of {room_idx, guest_name, guest_gender, guest_id_type, 
#                                guest_id_number, guest_phone, guest_email}
#     """
#     try:
#         if isinstance(guest_updates, str):
#             guest_updates = json.loads(guest_updates)
        
#         # ✅ Reload the reservation from DB to get fresh data
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Can only update guest details for submitted reservations"))
        
#         updated_rooms = []
#         updated_reservations = []
        
#         for update in guest_updates:
#             room_idx = update.get("room_idx")
#             guest_name = update.get("guest_name", "").strip()
#             guest_gender = update.get("guest_gender", "Male")
#             guest_id_type = update.get("guest_id_type", "")
#             guest_id_number = update.get("guest_id_number", "")
#             guest_phone = update.get("guest_phone", "").strip()
#             guest_email = update.get("guest_email", "").strip()
            
#             if room_idx is None or not guest_name:
#                 frappe.logger().warn(f"Skipping update: room_idx={room_idx}, guest_name={guest_name}")
#                 continue
            
#             if room_idx >= len(reservation.rooms):
#                 frappe.logger().warn(f"Room index {room_idx} out of range (max {len(reservation.rooms)-1})")
#                 continue
            
#             room = reservation.rooms[room_idx]
            
#             frappe.logger().info(f"═══ Updating Room {room.room_number} ═══")
#             frappe.logger().info(f"Guest: {guest_name} | Phone: {guest_phone} | Email: {guest_email}")
#             frappe.logger().info(f"Hotel Room Reservation link: {room.hotel_room_reservation}")
            
#             # Update room with new guest info
#             room.guest_name = guest_name
#             room.guest_gender = guest_gender
#             room.guest_id_type = guest_id_type
#             room.guest_id_number = guest_id_number
#             if guest_email:
#                 room.guest_email = guest_email
#             if guest_phone:
#                 room.guest_phone = guest_phone
            
#             # ═══════════════════════════════════════════════════════════════
#             # CREATE/UPDATE CUSTOMER
#             # ═══════════════════════════════════════════════════════════════
            
#             if not room.guest_customer or room.guest_customer == "":
#                 customer_id = None
                
#                 # Try to find by email
#                 if guest_email:
#                     customer_id = frappe.db.get_value(
#                         "Customer",
#                         {"email_id": guest_email},
#                         "name"
#                     )
#                     if customer_id:
#                         frappe.logger().info(f"Found existing customer by email: {customer_id}")
                
#                 # Try to find by phone
#                 if not customer_id and guest_phone:
#                     clean_phone = guest_phone.replace(" ", "").replace("-", "")
#                     customer_id = frappe.db.get_value(
#                         "Customer",
#                         {"mobile_no": clean_phone},
#                         "name"
#                     )
#                     if customer_id:
#                         frappe.logger().info(f"Found existing customer by phone: {customer_id}")
                
#                 # Create new customer if not found
#                 if not customer_id:
#                     customer = frappe.get_doc({
#                         "doctype": "Customer",
#                         "customer_name": guest_name,
#                         "customer_type": "Individual",
#                         "email_id": guest_email or "",
#                         "mobile_no": guest_phone or "",
#                         "territory": frappe.db.get_default("territory") or "Nigeria",
#                         "customer_group": frappe.db.get_default("customer_group") or "Individual"
#                     })
#                     customer.flags.ignore_permissions = True
#                     customer.insert()
#                     customer_id = customer.name
#                     frappe.logger().info(f"Created new customer: {customer_id}")
                
#                 room.guest_customer = customer_id
            
#             # ═══════════════════════════════════════════════════════════════
#             # CREATE/UPDATE HOTEL GUEST (lookup by email/phone, not just name)
#             # ═══════════════════════════════════════════════════════════════
            
#             if not room.hotel_guest or room.hotel_guest == "":
#                 existing_guest = None
                
#                 # Try to find existing guest by email first
#                 if guest_email:
#                     existing_guest = frappe.db.get_value(
#                         "Hotel Guest",
#                         {"email": guest_email},
#                         "name"
#                     )
#                     if existing_guest:
#                         frappe.logger().info(f"Found existing guest by email: {existing_guest}")
                
#                 # Try to find by phone if not found by email
#                 if not existing_guest and guest_phone:
#                     clean_phone = guest_phone.replace(" ", "").replace("-", "")
#                     existing_guest = frappe.db.get_value(
#                         "Hotel Guest",
#                         {"phone_number": clean_phone},
#                         "name"
#                     )
#                     if existing_guest:
#                         frappe.logger().info(f"Found existing guest by phone: {existing_guest}")
                
#                 # Fall back to name if still not found
#                 if not existing_guest:
#                     existing_guest = frappe.db.get_value(
#                         "Hotel Guest",
#                         {"hotel_guest_name": guest_name},
#                         "name"
#                     )
#                     if existing_guest:
#                         frappe.logger().info(f"Found existing guest by name: {existing_guest}")
                
#                 if existing_guest:
#                     room.hotel_guest = existing_guest
#                     # Update existing guest record with new details
#                     frappe.db.set_value(
#                         "Hotel Guest",
#                         existing_guest,
#                         {
#                             "hotel_guest_name": guest_name,
#                             "phone_number": guest_phone or "",
#                             "email": guest_email or "",
#                             "gender": guest_gender or "Male",
#                             "id_type": guest_id_type or "Passport",
#                             "id_number": guest_id_number or "",
#                             "customer": room.guest_customer
#                         },
#                         update_modified=False
#                     )
#                     frappe.logger().info(f"Updated existing guest {existing_guest}")
#                 else:
#                     # Create new hotel guest
#                     try:
#                         hotel_guest = frappe.get_doc({
#                             "doctype": "Hotel Guest",
#                             "hotel_guest_name": guest_name,
#                             "phone_number": guest_phone or "",
#                             "email": guest_email or "",
#                             "gender": guest_gender or "Male",
#                             "id_type": guest_id_type or "Passport",
#                             "id_number": guest_id_number or "",
#                             "customer": room.guest_customer,
#                             "guest_type": "Individual"
#                         })
#                         hotel_guest.flags.ignore_permissions = True
#                         hotel_guest.insert()
#                         room.hotel_guest = hotel_guest.name
#                         frappe.logger().info(f"Created new hotel guest: {hotel_guest.name}")
#                     except frappe.DuplicateEntryError:
#                         # If duplicate, try to fetch by email/phone again
#                         existing_guest = None
#                         if guest_email:
#                             existing_guest = frappe.db.get_value(
#                                 "Hotel Guest",
#                                 {"email": guest_email},
#                                 "name"
#                             )
#                         if not existing_guest and guest_phone:
#                             clean_phone = guest_phone.replace(" ", "").replace("-", "")
#                             existing_guest = frappe.db.get_value(
#                                 "Hotel Guest",
#                                 {"phone_number": clean_phone},
#                                 "name"
#                             )
#                         if existing_guest:
#                             room.hotel_guest = existing_guest
#                             frappe.logger().info(f"Resolved duplicate by finding {existing_guest}")
#             else:
#                 # Update existing hotel guest
#                 frappe.db.set_value(
#                     "Hotel Guest",
#                     room.hotel_guest,
#                     {
#                         "hotel_guest_name": guest_name,
#                         "phone_number": guest_phone or "",
#                         "email": guest_email or "",
#                         "gender": guest_gender or "Male",
#                         "id_type": guest_id_type or "Passport",
#                         "id_number": guest_id_number or ""
#                     },
#                     update_modified=False
#                 )
#                 frappe.logger().info(f"Updated hotel guest {room.hotel_guest}")
            
#             # ═══════════════════════════════════════════════════════════════
#             # UPDATE LINKED HOTEL ROOM RESERVATION - CRITICAL FIX
#             # ═══════════════════════════════════════════════════════════════
            
#             if room.hotel_room_reservation:
#                 hrr_name = room.hotel_room_reservation
#                 frappe.logger().info(f"Updating Hotel Room Reservation: {hrr_name}")
                
#                 # Update the Hotel Room Reservation document with guest_name and customer
#                 # These are the ONLY fields available in HRR for guest info
#                 frappe.db.set_value(
#                     "Hotel Room Reservation",
#                     hrr_name,
#                     {
#                         "guest_name": guest_name,
#                         "customer": room.guest_customer
#                     },
#                     update_modified=False
#                 )
                
#                 frappe.logger().info(f"✓ Updated HRR {hrr_name}: guest_name={guest_name}, customer={room.guest_customer}")
#                 updated_reservations.append(hrr_name)
#             else:
#                 frappe.logger().error(f"❌ Room {room.room_number} has NO hotel_room_reservation link!")
            
#             updated_rooms.append(room.room_number)
        
#         # ═══════════════════════════════════════════════════════════════════
#         # SAVE FDR WITH UPDATED VALUES
#         # ═══════════════════════════════════════════════════════════════════
        
#         frappe.logger().info(f"Saving FDR {reservation_name} with {len(updated_rooms)} updated rooms")
#         reservation.flags.ignore_permissions = True
#         reservation.save()
#         frappe.db.commit()
        
#         frappe.logger().info(f"✓ FDR Saved")
#         frappe.logger().info(f"✓ Updated HRRs: {updated_reservations}")
        
#         return {
#             "success": True,
#             "message": _("Updated guest details for {0} room(s)").format(len(updated_rooms)),
#             "rooms": updated_rooms,
#             "updated_reservations": updated_reservations
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Update Guest Details Error")
#         frappe.throw(_("Error: {0}").format(str(e)))
        
        
# def create_or_get_room_item(room_type):
#     """Create or get an Item for a room type"""
#     try:
#         existing_item = frappe.db.get_value(
#             "Item",
#             {"item_name": room_type, "item_group": "Services"},
#             "name"
#         )
        
#         if existing_item:
#             return existing_item
        
#         item = frappe.get_doc({
#             "doctype": "Item",
#             "item_code": f"ROOM-{room_type.upper().replace(' ', '-')}",
#             "item_name": room_type,
#             "item_group": "Services",
#             "is_stock_item": 0,
#             "valuation_method": "FIFO",
#             "uom": "Night",
#             "standard_selling_rate": 0
#         })
        
#         item.flags.ignore_permissions = True
#         item.insert()
        
#         return item.item_code
    
#     except frappe.exceptions.DuplicateEntryError:
#         return frappe.db.get_value("Item", {"item_name": room_type}, "name")
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Room Item Error")
#         return f"ROOM-{room_type.upper().replace(' ', '-')}"


# @frappe.whitelist()
# def get_available_rooms_for_dropdown(doctype, txt, searchfield, start, page_length, filters, **kwargs):
#     """Query method for dropdown - returns only available rooms"""
#     try:
#         from_date = kwargs.get('from_date')
#         to_date = kwargs.get('to_date')
#         room_type = kwargs.get('room_type')
        
#         if not from_date or not to_date:
#             all_rooms = frappe.get_all(
#                 "Hotel Room",
#                 filters={
#                     "status": "Vacant",
#                     "operational_status": "In Service",
#                     "maintenance_flag": 0
#                 },
#                 fields=["name"],
#                 limit_page_length=int(page_length) if page_length else 10
#             )
#             return [[r.name] for r in all_rooms]
        
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             return []
        
#         base_filters = {
#             "status": "Vacant",
#             "operational_status": "In Service",
#             "maintenance_flag": 0
#         }
        
#         if room_type:
#             base_filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             filters=base_filters,
#             fields=["name", "room_type", "floor", "capacity"],
#             limit_page_length=int(page_length) if page_length else 10
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
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
        
#         booked_rooms = [r.room_number for r in overlapping_reservations]
        
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
        
#         checked_in_rooms = [r.room_number for r in active_checkins]
        
#         unavailable = set(booked_rooms + checked_in_rooms)
#         available_rooms = [r.name for r in all_rooms if r.name not in unavailable]
        
#         return [[room] for room in available_rooms]
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms for Dropdown Error")
#         return []


# @frappe.whitelist()
# def get_available_rooms(from_date, to_date, room_type=None):
#     """Get available rooms for selected dates"""
#     try:
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)
        
#         if to_date_obj <= from_date_obj:
#             frappe.throw(_("Check-out date must be after check-in date"))
        
#         filters = {
#             "status": "Vacant",
#             "operational_status": "In Service",
#             "maintenance_flag": 0
#         }
        
#         if room_type:
#             filters["room_type"] = room_type
        
#         all_rooms = frappe.get_all(
#             "Hotel Room",
#             filters=filters,
#             fields=["name", "room_type", "floor", "capacity"]
#         )
        
#         if not all_rooms:
#             return []
        
#         room_numbers = [r.name for r in all_rooms]
        
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
        
#         booked_rooms = [r.room_number for r in overlapping_reservations]
        
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
        
#         checked_in_rooms = [r.room_number for r in active_checkins]
        
#         unavailable = set(booked_rooms + checked_in_rooms)
#         available_rooms = [r for r in all_rooms if r.name not in unavailable]
        
#         for room in available_rooms:
#             rate = get_room_rate(room.room_type, check_in_date=str(from_date))
#             room["rate_per_night"] = rate
#             num_nights = date_diff(to_date_obj, from_date_obj)
#             room["total_amount"] = rate * num_nights
        
#         return available_rooms
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
#         frappe.throw(_("Error: {0}").format(str(e)))