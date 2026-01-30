
import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days, now_datetime, format_datetime
from datetime import datetime, timedelta
import json

from rhohotel.api import get_room_rate
from rhohotel.shared_utilities import (
    create_or_get_item,
    generate_secure_booking_number
)

def format_phone_number(phone, country_code="+234"):
    """
    Format phone number with country code.
    - 08012345678 → +2348012345678
    - 8012345678 → +2348012345678
    - +2348012345678 → +2348012345678 (unchanged)
    - Empty/None → ""
    """
    if not phone:
        return ""
    
    clean_phone = phone.replace(" ", "").replace("-", "")
    
    if not clean_phone:
        return ""
    
    # Already has country code
    if clean_phone.startswith("+"):
        return clean_phone
    
    # Remove leading 0 if present
    if clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]
    
    return f"{country_code}{clean_phone}"


def normalize_phone_for_search(phone):
    """
    Normalize phone for database search (last 10 digits).
    This handles matching regardless of format.
    """
    if not phone:
        return ""
    
    clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "")
    
    # Return last 10 digits for matching
    if len(clean_phone) > 10:
        return clean_phone[-10:]
    
    # Remove leading 0
    if clean_phone.startswith("0"):
        return clean_phone[1:]
    
    return clean_phone

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
        """Create customers, guests, and room reservations on submit"""
        try:
            self.create_customers()
            self.create_hotel_guests_with_names()
            self.save_guest_links_to_child_table()
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
            
    def save_guest_links_to_child_table(self):
        for room in self.rooms:
            if room.guest_customer or room.hotel_guest:
                frappe.db.set_value(
                    "Front Desk Reservation Room",
                    room.name,
                    {
                        "guest_customer": room.guest_customer,
                        "hotel_guest": room.hotel_guest
                    },
                    update_modified=False
            )
    
    def on_cancel(self):
        """Cancel all linked Hotel Room Reservations"""
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
                room.guest_name = self.primary_guest_name or ""
            
            if not room.guest_email:
                room.guest_email = self.primary_guest_email or ""
            
            if not room.guest_phone:
                room.guest_phone = self.primary_guest_phone or ""
            
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
        if not self.primary_guest_name:
            self.primary_guest_name = corporate.hotel_guest_name
        if not self.primary_guest_email:
            self.primary_guest_email = corporate.email or ""
        if not self.primary_guest_phone:
            self.primary_guest_phone = corporate.phone_number or ""
    
    # ═══════════════════════════════════════════════════════════════════════
    # DOCUMENT CREATION METHODS
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_customers(self):
        for room in self.rooms:
            customer_id = self.get_or_create_customer(
                room.guest_name,
                room.guest_email,
                room.guest_phone
            )
            room.guest_customer = customer_id
            
            if not self.customer:
                self.customer = customer_id
    
    # def get_or_create_customer(self, name, email, phone):
    #     if email:
    #         existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
    #         if existing:
    #             return existing
        
    #     if phone:
    #         clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "")
    #         existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
    #         if existing:
    #             return existing
        
    #     customer = frappe.get_doc({
    #         "doctype": "Customer",
    #         "customer_name": name or "Guest",
    #         "customer_type": "Individual",
    #         "email_id": email or "",
    #         "mobile_no": phone or "",
    #         "territory": frappe.db.get_default("territory") or "Nigeria",
    #         "customer_group": frappe.db.get_default("customer_group") or "Individual"
    #     })
    #     customer.flags.ignore_permissions = True
    #     customer.insert()
        
    #     return customer.name

    def get_or_create_customer(self, name, email, phone):
        # Check by email first
        if email:
            existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
            if existing:
                return existing
        
        # Check by phone (search by last 10 digits to handle format differences)
        if phone:
            search_phone = normalize_phone_for_search(phone)
            if search_phone:
                # Search using LIKE to match any format
                existing = frappe.db.sql("""
                    SELECT name FROM `tabCustomer`
                    WHERE REPLACE(REPLACE(REPLACE(mobile_no, ' ', ''), '-', ''), '+', '') LIKE %s
                    LIMIT 1
                """, (f"%{search_phone}",), as_dict=True)
                
                if existing:
                    return existing[0].name
        
        # Format phone for new customer
        formatted_phone = format_phone_number(phone)
        
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name or "Guest",
            "customer_type": "Individual",
            "email_id": email or "",
            "mobile_no": formatted_phone,  # Use formatted phone
            "territory": frappe.db.get_default("territory") or "Nigeria",
            "customer_group": frappe.db.get_default("customer_group") or "Individual"
        })
        customer.flags.ignore_permissions = True
        customer.insert()
        
        return customer.name
    
    
    def create_hotel_guests_with_names(self):
        for room in self.rooms:
            self.get_or_create_hotel_guest(room)
    
    # def get_or_create_hotel_guest(self, room):
        guest_name = room.guest_name
        guest_email = room.guest_email
        guest_phone = room.guest_phone
        
        existing_by_name = frappe.db.get_value(
            "Hotel Guest",
            {"hotel_guest_name": guest_name},
            "name"
        )
        if existing_by_name:
            room.hotel_guest = existing_by_name
            return existing_by_name
        
        if guest_email:
            existing = frappe.db.get_value(
                "Hotel Guest",
                {"email": guest_email},
                "name"
            )
            if existing:
                room.hotel_guest = existing
                return existing
        
        if guest_phone:
            clean_phone = guest_phone.replace(" ", "").replace("-", "").replace("+", "")
            existing = frappe.db.get_value(
                "Hotel Guest",
                {"phone_number": clean_phone},
                "name"
            )
            if existing:
                room.hotel_guest = existing
                return existing
            
            
            # Format phone number with country code if provided

            formatted_phone = ""
            
            if guest_phone:
                clean_phone = guest_phone.replace(" ", "").replace("-", "")
                # If phone doesn't start with +, add Nigeria country code
                if clean_phone and not clean_phone.startswith("+"):
                    # Remove leading 0 if present
                    if clean_phone.startswith("0"):
                        clean_phone = clean_phone[1:]
                    formatted_phone = f"+234{clean_phone}"
                else:
                    formatted_phone = clean_phone
            
        try:
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": formatted_phone,
                "email": guest_email or "",
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
            
        except frappe.exceptions.DuplicateEntryError:
            existing = frappe.db.get_value(
                "Hotel Guest",
                {"hotel_guest_name": guest_name},
                "name"
            )
            if existing:
                room.hotel_guest = existing
                return existing
            raise
        
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Create Hotel Guest Error")
            raise
    
    def get_or_create_hotel_guest(self, room):
        guest_name = room.guest_name
        guest_email = room.guest_email
        guest_phone = room.guest_phone
        
        # Check by name first
        existing_by_name = frappe.db.get_value(
            "Hotel Guest",
            {"hotel_guest_name": guest_name},
            "name"
        )
        if existing_by_name:
            room.hotel_guest = existing_by_name
            return existing_by_name
        
        # Check by email
        if guest_email:
            existing = frappe.db.get_value(
                "Hotel Guest",
                {"email": guest_email},
                "name"
            )
            if existing:
                room.hotel_guest = existing
                return existing
        
        # Check by phone (search by last 10 digits to handle format differences)
        if guest_phone:
            search_phone = normalize_phone_for_search(guest_phone)
            if search_phone:
                existing = frappe.db.sql("""
                    SELECT name FROM `tabHotel Guest`
                    WHERE REPLACE(REPLACE(REPLACE(phone_number, ' ', ''), '-', ''), '+', '') LIKE %s
                    LIMIT 1
                """, (f"%{search_phone}",), as_dict=True)
                
                if existing:
                    room.hotel_guest = existing[0].name
                    return existing[0].name
        
        # Format phone for new hotel guest
        formatted_phone = format_phone_number(guest_phone)
        
        try:
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": formatted_phone,  # Use formatted phone
                "email": guest_email or "",
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
            
        except frappe.exceptions.DuplicateEntryError:
            existing = frappe.db.get_value(
                "Hotel Guest",
                {"hotel_guest_name": guest_name},
                "name"
            )
            if existing:
                room.hotel_guest = existing
                return existing
            raise
        
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Create Hotel Guest Error")
            raise
    
    def create_room_reservations(self):
        """Create Hotel Room Reservations"""
        number_of_nights = date_diff(getdate(self.to_date), getdate(self.from_date))
        
        for room in self.rooms:
            reservation_items = [{
                "room_type": room.room_type,
                "rate_type": getattr(room, 'rate_type', 'Standard'),
                "season_type": getattr(room, 'season_type', ''),
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
                "reservation_type": 'Corporate' if self.reservation_type == 'Corporate' else 'Individual',
                "number_of_nights": number_of_nights,
            })
            
            reservation.flags.ignore_permissions = True
            reservation.insert()
            reservation.submit()


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_available_rooms(from_date, to_date, room_type=None):
    """Get available rooms for selected dates"""
    try:
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
        
        if to_date_obj <= from_date_obj:
            frappe.throw(_("Check-out date must be after check-in date"))
        
        filters = {}
        if room_type:
            filters["room_type"] = room_type
        
        all_rooms = frappe.get_all(
            "Hotel Room",
            filters=filters if filters else None,
            fields=["name", "room_type", "floor", "capacity"]
        )
        
        if not all_rooms:
            return []
        
        room_numbers = [r.name for r in all_rooms]
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Exclude rooms with active holds
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
        
        unavailable = set(held_room_list + booked_rooms + checked_in_rooms)
        available_rooms = [r for r in all_rooms if r.name not in unavailable]
        
        # Calculate pricing
        for room in available_rooms:
            rate = get_room_rate(room.room_type, check_in_date=str(from_date))
            room["rate_per_night"] = rate
            num_nights = date_diff(to_date_obj, from_date_obj)
            room["total_amount"] = rate * num_nights
        
        return available_rooms
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
        frappe.throw(_("Error: {0}").format(str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# CHECK-IN ROOMS IN BULK INVOICE (NEW v4.0)
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_rooms_in_bulk_invoice(reservation_name):
    """
    Get rooms that are included in the bulk invoice for this reservation.
    Returns rooms that can be checked in without creating new invoices.
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            return {"success": False, "message": "Reservation not submitted"}
        
        # Check if bulk invoice exists
        if not reservation.sales_invoice:
            return {
                "success": False,
                "message": "No bulk invoice found for this reservation",
                "has_bulk_invoice": False
            }
        
        # Get rooms from the reservation
        all_rooms = []
        for room in reservation.rooms:
            # Check if room already has a check-in
            existing_checkin = frappe.db.get_value(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "status": ["in", ["Draft", "Checked In"]]
                },
                ["name", "status"],
                as_dict=True
            )
            
            all_rooms.append({
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
                "checkin_name": existing_checkin.get("name") if existing_checkin else None
            })
        
        return {
            "success": True,
            "has_bulk_invoice": True,
            "bulk_invoice": reservation.sales_invoice,
            "rooms": all_rooms,
            "total_rooms": len(all_rooms),
            "rooms_checked_in": len([r for r in all_rooms if r["has_checkin"]]),
            "rooms_pending": len([r for r in all_rooms if not r["has_checkin"]])
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Rooms in Bulk Invoice Error")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def check_in_rooms_in_bulk_invoice(reservation_name, room_indices, check_in_notes=""):
    
    """
    Check in selected rooms that are already in a bulk invoice.
    NO new invoice is created since rooms are already in the bulk invoice.
    
    Args:
        reservation_name: Name of Hotel Front Desk Reservation
        room_indices: List of room indices (from rooms child table) to check in
        check_in_notes: Optional notes for check-in
    
    Returns:
        Dictionary with success status and check-in details
    """
    try:
        if isinstance(room_indices, str):
            room_indices = json.loads(room_indices)
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        # Validate reservation
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before check-in"))
        
        # Validate bulk invoice exists
        if not reservation.sales_invoice:
            frappe.throw(_("No bulk invoice found for this reservation. Use regular check-in instead."))
        
        # Get check-in/out times from settings
        settings = frappe.get_single('Hotel Settings')
        check_in_time = now_datetime().strftime("%H:%M:%S")
        check_out_time = settings.default_check_out_time or "11:00:00"
        
        checked_in_rooms = []
        skipped_rooms = []
        
        for idx in room_indices:
            idx = int(idx)
            
            # Find the room in the reservation
            room = None
            for r in reservation.rooms:
                if r.idx == idx + 1:  # idx is 0-based from JS, but idx in child table is 1-based
                    room = r
                    break
            
            if not room:
                skipped_rooms.append({
                    "idx": idx,
                    "reason": "Room not found in reservation"
                })
                continue
            
            # Check if room already has active check-in
            existing_checkin = frappe.db.get_value(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "status": ["in", ["Draft", "Checked In"]]
                },
                "name"
            )
            
            if existing_checkin:
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "Already checked in"
                })
                continue
            
            # Check if guest name exists
            if not room.guest_name or room.guest_name.startswith('Guest - Room'):
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "Guest name required"
                })
                continue
            
            # Get Hotel Room Reservation for this room
            hrr = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "docstatus": 1
                },
                "name"
            )
            
            if not hrr:
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "No room reservation found"
                })
                continue
            
            # Create check-in datetime
            check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
            expected_checkout_datetime = get_datetime(f"{reservation.to_date} {check_out_time}")
            
            frappe.log_error(
                title="Bulk single checkin",
                message=(
                    "Reservation: {reservation}\n"
                    "Hotel Room Reservation: {hrr}\n"
                    "Room Number: {room_number}\n"
                    "Room Type: {room_type}\n"
                    "Guest: {guest}\n"
                    "Guest Name: {guest_name}\n"
                    "Guest Email: {guest_email}\n"
                    "Guest Phone: {guest_phone}\n"
                    "Customer: {customer}\n"
                    "Check-in Datetime: {checkin_dt}\n"
                    "Expected Checkout: {checkout_dt}\n"
                    "Number of Nights: {nights}\n"
                    "Rate per Night: {rate}\n"
                    "Total Amount: {total}\n"
                    "Payment Status: Paid\n"
                    "Sales Invoice: {invoice}\n"
                    "Is Bulk Invoice Room: 1\n"
                    "Discount: {discount}\n"
                    "Discount Type: {discount_type}\n"
                    "Total Charges: {charges}\n"
                ).format(
                    reservation=reservation_name,
                    hrr=hrr,
                    room_number=room.room_number,
                    room_type=room.room_type,
                    guest=room.hotel_guest,
                    guest_name=room.guest_name,
                    guest_email=room.guest_email or reservation.primary_guest_email,
                    guest_phone=room.guest_phone or reservation.primary_guest_phone,
                    customer=room.guest_customer or reservation.customer,
                    checkin_dt=check_in_datetime,
                    checkout_dt=expected_checkout_datetime,
                    nights=reservation.number_of_nights,
                    rate=room.rate_per_night,
                    total=room.room_total,
                    invoice=reservation.sales_invoice,
                    discount=reservation.discount_amount or 0,
                    discount_type=reservation.discount_type or "None",
                    charges=room.room_total,
                )
            )

            rate_type = getattr(room, 'rate_type', None)
            # Create Hotel Room Check In (NO invoice creation)
            checkin = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "front_desk_reservation": reservation_name,
                "reservation": hrr,
                "room_number": room.room_number,
                "room_type": room.room_type,
                "rate_type": rate_type,
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
                "payment_status": "Paid",  # Already in bulk invoice
                "check_in_notes": check_in_notes,
                "sales_invoice": reservation.sales_invoice,  # Link to bulk invoice
                "is_bulk_invoice_room": 1,  # Flag to indicate bulk invoice room
                "discount": reservation.discount_amount or 0,  # Set discount
                "discount_type": reservation.discount_type if reservation.discount_type else "None",
                "total_charges": room.room_total
            })
            
            checkin.flags.ignore_permissions = True
            checkin.insert()
            checkin.submit()
            
            # Update Hotel Room Reservation status
            frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")
            
            checked_in_rooms.append({
                "room_number": room.room_number,
                "guest_name": room.guest_name,
                "checkin_name": checkin.name
            })
        
        # Update reservation status if any rooms were checked in
        if checked_in_rooms:
            # Check if all rooms are now checked in
            total_rooms = len(reservation.rooms)
            all_checkins = frappe.db.count(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "status": ["in", ["Draft", "Checked In"]]
                }
            )
            
            if all_checkins >= total_rooms:
                frappe.db.set_value(
                    "Hotel Front Desk Reservation",
                    reservation_name,
                    "status",
                    "Checked In"
                )
            elif all_checkins > 0:
                # Partial check-in - keep status as Confirmed or update to Checked In
                current_status = reservation.status
                if current_status == "Confirmed":
                    frappe.db.set_value(
                        "Hotel Front Desk Reservation",
                        reservation_name,
                        "status",
                        "Checked In"
                    )
        
        frappe.db.commit()
        
        message = _("{0} room(s) checked in successfully (bulk invoice).").format(len(checked_in_rooms))
        if skipped_rooms:
            message += _(" {0} room(s) skipped.").format(len(skipped_rooms))
        
        return {
            "success": True,
            "message": message,
            "checked_in_rooms": checked_in_rooms,
            "skipped_rooms": skipped_rooms,
            "bulk_invoice": reservation.sales_invoice,
            "total_checked_in": len(checked_in_rooms),
            "total_skipped": len(skipped_rooms)
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In Rooms in Bulk Invoice Error")
        frappe.throw(_("Error checking in rooms: {0}").format(str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# ADJUST STAY FUNCTIONS (FIXED v4.0 - with adjustment invoice tracking)
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_default_check_out_time():
    """Fetch default check-out time from Hotel Settings"""
    try:
        settings = frappe.get_single('Hotel Settings')
        return settings.default_check_out_time or "12:00:00"
    except:
        return "12:00:00"


@frappe.whitelist()
def get_default_check_in_time():
    """Fetch default check-in time from Hotel Settings"""
    try:
        return now_datetime().strftime("%H:%M:%S")
    except:
        return "11:00:00"


@frappe.whitelist()
def get_reservation_status_info(reservation_name):
    """Get current status information about reservation for adjustment validation"""
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            return {"valid": False, "message": "Reservation not submitted"}
        
        active_checkins = frappe.db.get_all(
            "Hotel Room Check In",
            filters={
                "front_desk_reservation": reservation_name,
                "status": ["in", ["Draft", "Checked In"]]
            },
            fields=["name", "room_number", "status", "check_in_datetime"]
        )
        
        is_checked_in = len(active_checkins) > 0
        
        return {
            "valid": True,
            "reservation_number": reservation.reservation_number,
            "status": reservation.status,
            "is_checked_in": is_checked_in,
            "checked_in_count": len(active_checkins),
            "total_rooms": len(reservation.rooms),
            "current_checkin": reservation.from_date,
            "current_checkout": reservation.to_date,
            "current_nights": reservation.number_of_nights,
            "current_total": float(reservation.total_amount or 0),
            "has_invoice": bool(reservation.sales_invoice),
            "active_checkins": active_checkins
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Reservation Status Error")
        return {"valid": False, "message": str(e)}


def add_adjustment_invoice_to_reservation(
    reservation_name, 
    invoice_type, 
    sales_invoice, 
    amount, 
    nights_adjusted, 
    old_checkout, 
    new_checkout, 
    remarks="", 
    old_nights=None, 
    new_nights=None,
    old_checkout_datetime=None,  
    new_checkout_datetime=None   
):
    """
    Add an adjustment invoice entry to the reservation's child table.
    Updated to use Hotel Room Check In Stay Adjustments structure.
    
    Args:
        reservation_name: Name of Hotel Front Desk Reservation
        invoice_type: 'Extension' or 'Credit Note'
        sales_invoice: Sales Invoice name
        amount: Invoice amount
        nights_adjusted: Number of nights adjusted (positive or negative)
        old_checkout: Original checkout date (YYYY-MM-DD)
        new_checkout: New checkout date (YYYY-MM-DD)
        remarks: Optional remarks
        old_nights: Previous number of nights (optional - will calculate if not provided)
        new_nights: New number of nights (optional - will calculate if not provided)
        old_checkout_datetime: Previous checkout datetime (optional)
        new_checkout_datetime: New checkout datetime (optional)
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        # ✅ Calculate nights from dates if not provided
        if old_nights is None or new_nights is None:
            old_nights_calc = date_diff(getdate(old_checkout), getdate(reservation.from_date))
            new_nights_calc = date_diff(getdate(new_checkout), getdate(reservation.from_date))
            
            old_nights = old_nights if old_nights is not None else old_nights_calc
            new_nights = new_nights if new_nights is not None else new_nights_calc
        
        # ✅ Set checkout datetimes if not provided (default to 12:00:00)
        if old_checkout_datetime is None:
            old_checkout_datetime = get_datetime(f"{old_checkout} 11:00:00")
        
        if new_checkout_datetime is None:
            new_checkout_datetime = get_datetime(f"{new_checkout} 11:00:00")
        
        # Add to adjustment_invoices child table (using Hotel Room Check In Stay Adjustments)
        reservation.append("adjustment_invoices", {
            "adjustment_type": invoice_type,  # 'Extension' or 'Credit Note'
            "adjustment_nvoice": sales_invoice,  # Link to Sales Invoice
            "amount": abs(amount),
            "nights_adjusted": abs(nights_adjusted),
            "old_checkout": old_checkout,
            "new_checkout": new_checkout,
            "previous_number_of_nights": old_nights, 
            "new_number_of_nights": new_nights,  
            "previous_checkout_datetime": old_checkout_datetime,  # ✅ Previous checkout datetime
            "new_checkout_datetime": new_checkout_datetime,  # ✅ New checkout datetime
            "adjustment_date": now_datetime(),
            "reason": remarks
        })
        
        reservation.flags.ignore_permissions = True
        reservation.flags.ignore_validate_update_after_submit = True
        reservation.save()
        
        frappe.log_error(
            f"Added adjustment to {reservation_name}: {invoice_type} - {sales_invoice}",
            "Adjustment Invoice Added"
        )
        
    except Exception as e:
        frappe.log_error(
            f"Failed to add adjustment to {reservation_name}: {str(e)}\n{frappe.get_traceback()}",
            "Add Adjustment Invoice Error"
        )
        
        
@frappe.whitelist()
def adjust_front_desk_reservation(
    reservation_name,
    new_checkout_date,
    new_checkout_time,
    new_discount=0
):
    """
    Adjust a Front Desk Reservation stay duration (extend OR reduce)
    
    ✅ FIXED v4.0:
    1. Credit note creation with NEGATIVE quantities for ERPNext
    2. All type conversions handled properly
    3. Comprehensive logging for debugging
    4. NEW: Adds adjustment invoices to child table
    
    Args:
        reservation_name: Name of Hotel Front Desk Reservation
        new_checkout_date: New checkout date (YYYY-MM-DD format)
        new_checkout_time: New checkout time (HH:MM:SS format)
        new_discount: New total discount amount (optional)
    
    Returns:
        Dictionary with success status and adjustment details
    """
    try:
        # Convert inputs to correct types
        try:
            new_discount = float(new_discount) if new_discount else 0
        except (ValueError, TypeError):
            new_discount = 0
        
        # ═══════════════════════════════════════════════════════════════════
        # VALIDATION
        # ═══════════════════════════════════════════════════════════════════
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before adjusting stay"))
        
        # Check for active check-ins
        active_checkins = frappe.db.get_all(
            "Hotel Room Check In",
            filters={
                "front_desk_reservation": reservation_name,
                "status": ["in", ["Draft", "Checked In"]]
            },
            fields=["name", "room_number", "status"]
        )
        
        is_checked_in = len(active_checkins) > 0
        checked_in_rooms = [ci["room_number"] for ci in active_checkins] if is_checked_in else []
        
        # Parse dates
        new_checkout_str = f"{new_checkout_date} {new_checkout_time}"
        new_checkout_dt = get_datetime(new_checkout_str)
        current_checkout_dt = get_datetime(f"{reservation.to_date} 12:00:00")
        checkin_dt = get_datetime(f"{reservation.from_date} 00:00:00")
        now_dt = get_datetime(now_datetime())
        
        # Validate: New checkout must be after check-in
        if new_checkout_dt <= checkin_dt:
            frappe.throw(
                _("New checkout must be after check-in date: {0}").format(
                    format_datetime(checkin_dt)
                )
            )
        
        # Validate: For checked-in guests, cannot checkout in past
        if is_checked_in and new_checkout_dt < now_dt:
            frappe.throw(
                _("New checkout cannot be in the past. Current time: {0}").format(
                    format_datetime(now_dt)
                )
            )
        
        # Determine adjustment type
        is_extension = new_checkout_dt > current_checkout_dt
        is_reduction = new_checkout_dt < current_checkout_dt
        
        if new_checkout_dt == current_checkout_dt:
            frappe.throw(_("New checkout date is the same as current. No adjustment needed."))
        
        # ═══════════════════════════════════════════════════════════════════
        # CALCULATE NEW PRICING
        # ═══════════════════════════════════════════════════════════════════
        
        old_checkout_date = getdate(reservation.to_date)
        new_checkout_date_obj = getdate(new_checkout_date)
        checkin_date = getdate(reservation.from_date)
        
        old_nights = date_diff(old_checkout_date, checkin_date)
        new_nights = date_diff(new_checkout_date_obj, checkin_date)
        night_diff = new_nights - old_nights
        
        if new_nights < 1:
            frappe.throw(_("Minimum 1 night required. Cannot adjust further."))
        
        # Calculate room pricing
        old_subtotal = float(reservation.subtotal or 0)
        old_discount = float(reservation.discount_amount or 0)
        
        new_subtotal = 0
        room_pricing_changes = []
        
        for room in reservation.rooms:
            old_room_total = float(room.room_total or 0)
            rate_per_night = float(room.rate_per_night or 0)
            new_room_total = rate_per_night * new_nights
            room_change = new_room_total - old_room_total
            
            room_pricing_changes.append({
                "room_number": room.room_number,
                "room_type": room.room_type,
                "rate_per_night": rate_per_night,
                "old_total": old_room_total,
                "new_total": new_room_total,
                "change": room_change
            })
            
            new_subtotal += new_room_total
        
        amount_change = float(new_subtotal) - float(old_subtotal)
        new_total = float(new_subtotal) - float(new_discount)
        
        # Log calculation
        frappe.log_error(
            f"""
            ADJUST STAY CALCULATION
            ═══════════════════════════════════════════════════════
            Reservation: {reservation_name}
            Old Checkout: {old_checkout_date} -> New: {new_checkout_date_obj}
            Nights: {old_nights} -> {new_nights} (Diff: {night_diff})
            Subtotal: {old_subtotal} -> {new_subtotal}
            Amount Change: {amount_change}
            Extension: {is_extension}, Reduction: {is_reduction}
            Customer: {reservation.customer}
            """,
            "Adjust Stay - Calculation"
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # UPDATE RESERVATION DOCUMENT
        # ═══════════════════════════════════════════════════════════════════
        
        frappe.db.set_value(
            "Hotel Front Desk Reservation",
            reservation_name,
            {
                "to_date": new_checkout_date,
                "number_of_nights": new_nights,
                "subtotal": new_subtotal,
                "discount_amount": new_discount,
                "total_amount": new_total
            },
            update_modified=False
        )
        
        # Update room totals in child table
        for idx, room in enumerate(reservation.rooms):
            for child_table_name in ["Front Desk Reservation Room", "Hotel Front Desk Rooms"]:
                room_row = frappe.db.get_value(
                    child_table_name,
                    {"parent": reservation_name, "room_number": room.room_number},
                    "name"
                )
                
                if room_row:
                    frappe.db.set_value(
                        child_table_name,
                        room_row,
                        {
                            "room_total": room_pricing_changes[idx]["new_total"],
                            "number_of_nights": new_nights
                        },
                        update_modified=False
                    )
                    break
        
        # ═══════════════════════════════════════════════════════════════════
        # UPDATE LINKED DOCUMENTS
        # ═══════════════════════════════════════════════════════════════════
        
        # Update Hotel Room Reservations
        linked_hrrs = frappe.db.get_all(
            "Hotel Room Reservation",
            filters={
                "front_desk_reservation": reservation_name,
                "docstatus": 1
            },
            fields=["name", "room_number"]
        )
        
        for hrr_link in linked_hrrs:
            frappe.db.set_value(
                "Hotel Room Reservation",
                hrr_link.name,
                {
                    "to_date": new_checkout_date,
                    "number_of_nights": new_nights
                },
                update_modified=False
            )
        
        # Update Hotel Room Check Ins
        for checkin in active_checkins:
            ci_doc = frappe.get_doc("Hotel Room Check In", checkin["name"])
            ci_doc.expected_check_out_datetime = get_datetime(new_checkout_str)
            ci_doc.number_of_nights = new_nights
            ci_doc.flags.ignore_permissions = True
            ci_doc.save()
        
        # ═══════════════════════════════════════════════════════════════════
        # HANDLE INVOICING
        # ═══════════════════════════════════════════════════════════════════
        
        additional_invoice_name = None
        credit_note_name = None
        
        # EXTENSION: Create supplementary invoice
        if is_extension and amount_change > 0 and reservation.customer:
            frappe.log_error(
                f"Creating extension invoice for {reservation_name}, amount: {amount_change}",
                "Adjust Stay - Extension Invoice"
            )
            
            try:
                si = frappe.new_doc("Sales Invoice")
                si.customer = reservation.customer
                si.posting_date = nowdate()
                si.due_date = new_checkout_date
                si.is_return = 0
                si.po_no = f"{reservation.reservation_number} - Extension"
                si.remarks = _(
                    "Extension charges for {0} additional night(s). "
                    "Stay extended from {1} to {2}"
                ).format(abs(night_diff), old_checkout_date, new_checkout_date_obj)
                
                for room_info in room_pricing_changes:
                    if room_info["change"] > 0:
                        try:
                            item_name = create_or_get_item(room_info["room_type"])
                        except:
                            item_name = room_info["room_type"]
                        
                        si.append("items", {
                            "item_code": item_name,
                            "item_name": f"{room_info['room_number']} - Extension",
                            "description": _(
                                "Room {0} - {1} additional night(s) @ {2}/night"
                            ).format(
                                room_info["room_number"],
                                abs(night_diff),
                                room_info["rate_per_night"]
                            ),
                            "qty": abs(night_diff),
                            "rate": room_info["rate_per_night"],
                            "amount": abs(room_info["change"])
                        })
                
                if len(si.items) > 0:
                    si.flags.ignore_permissions = True
                    si.insert()
                    si.submit()
                    additional_invoice_name = si.name
                    
                    # ✅ NEW: Add to adjustment invoices child table
                    add_adjustment_invoice_to_reservation(
                        reservation_name=reservation_name,
                        invoice_type="Extension",
                        sales_invoice=si.name,
                        amount=amount_change,
                        nights_adjusted=abs(night_diff),
                        old_checkout=str(old_checkout_date),
                        new_checkout=str(new_checkout_date_obj),
                        remarks=f"Extension for {abs(night_diff)} additional night(s)"
                    )
                    
                    frappe.log_error(
                        f"Extension invoice created: {si.name}",
                        "Adjust Stay - Extension SUCCESS"
                    )
                    
            except Exception as e:
                frappe.log_error(
                    f"Failed to create extension invoice: {str(e)}\n{frappe.get_traceback()}",
                    "Adjust Stay - Extension FAILED"
                )
        
        # REDUCTION: Create credit note with NEGATIVE quantities
        elif is_reduction and amount_change < 0 and reservation.customer:
            frappe.log_error(
                f"""
                CREDIT NOTE CREATION STARTED
                ═══════════════════════════════════════════════════════
                Reservation: {reservation_name}
                Customer: {reservation.customer}
                Refund Amount: {abs(amount_change)}
                Night Difference: {abs(night_diff)}
                """,
                "Adjust Stay - Credit Note START"
            )
            
            try:
                cn = frappe.new_doc("Sales Invoice")
                cn.customer = reservation.customer
                cn.posting_date = nowdate()
                cn.due_date = nowdate()
                cn.is_return = 1  # ✅ Mark as credit note
                
                if reservation.sales_invoice:
                    cn.return_against = reservation.sales_invoice
                
                cn.po_no = f"{reservation.reservation_number} - Early Checkout"
                cn.remarks = _(
                    "Credit note for early checkout. "
                    "Stay reduced from {0} to {1} ({2} fewer nights)"
                ).format(old_checkout_date, new_checkout_date_obj, abs(night_diff))
                
                total_refund = 0
                
                for room_info in room_pricing_changes:
                    rate_per_night = room_info["rate_per_night"]
                    room_refund = rate_per_night * abs(night_diff)
                    
                    try:
                        item_name = create_or_get_item(room_info["room_type"])
                    except:
                        item_name = room_info["room_type"]
                    
                    # ✅ KEY FIX: NEGATIVE qty for credit notes
                    cn.append("items", {
                        "item_code": item_name,
                        "item_name": f"{room_info['room_number']} - Refund",
                        "description": _(
                            "Room {0} - {1} night(s) refund @ {2}/night"
                        ).format(
                            room_info["room_number"],
                            abs(night_diff),
                            rate_per_night
                        ),
                        "qty": -abs(night_diff),  # ✅ NEGATIVE
                        "rate": rate_per_night,
                    })
                    
                    total_refund += room_refund
                    
                    frappe.log_error(
                        f"Credit note item: {room_info['room_number']}, qty: -{abs(night_diff)}, rate: {rate_per_night}",
                        "Adjust Stay - Credit Note Item"
                    )
                
                if len(cn.items) > 0:
                    cn.flags.ignore_permissions = True
                    cn.flags.ignore_mandatory = True
                    cn.flags.ignore_links = True
                    cn.insert()
                    cn.submit()
                    credit_note_name = cn.name
                    
                    # ✅ NEW: Add to adjustment invoices child table
                    add_adjustment_invoice_to_reservation(
                        reservation_name=reservation_name,
                        invoice_type="Reduction",
                        sales_invoice=cn.name,
                        amount=abs(amount_change),
                        nights_adjusted=abs(night_diff),
                        old_checkout=str(old_checkout_date),
                        new_checkout=str(new_checkout_date_obj),
                        remarks=f"Credit note for {abs(night_diff)} night(s) reduction"
                    )
                    
                    frappe.log_error(
                        f"✅ Credit note created: {cn.name}, Total refund: {total_refund}",
                        "Adjust Stay - Credit Note SUCCESS"
                    )
                else:
                    frappe.log_error(
                        f"No items added to credit note for {reservation_name}",
                        "Adjust Stay - Credit Note WARNING"
                    )
                    
            except Exception as e:
                frappe.log_error(
                    f"❌ Credit note failed: {str(e)}\n{frappe.get_traceback()}",
                    "Adjust Stay - Credit Note FAILED"
                )
        
        # ═══════════════════════════════════════════════════════════════════
        # COMMIT & RETURN RESPONSE
        # ═══════════════════════════════════════════════════════════════════
        
        frappe.db.commit()
        
        adjustment_type = "Extension" if is_extension else "Reduction"
        
        frappe.log_error(
            f"""
            ✅ ADJUSTMENT COMPLETED
            ─────────────────────────
            Reservation: {reservation_name}
            Type: {adjustment_type}
            Nights: {old_nights} -> {new_nights}
            Amount Change: {amount_change}
            Invoice: {additional_invoice_name}
            Credit Note: {credit_note_name}
            """,
            "Adjust Stay - COMPLETED"
        )
        
        return {
            "success": True,
            "message": _("Stay {0} completed successfully!").format(adjustment_type),
            "adjustment_type": adjustment_type,
            "is_extension": is_extension,
            "is_reduction": is_reduction,
            "is_checked_in": is_checked_in,
            "checked_in_rooms": checked_in_rooms,
            "old_checkout": format_datetime(current_checkout_dt),
            "new_checkout": format_datetime(new_checkout_dt),
            "old_nights": old_nights,
            "new_nights": new_nights,
            "night_difference": night_diff,
            "old_subtotal": float(old_subtotal),
            "new_subtotal": float(new_subtotal),
            "amount_change": float(amount_change),
            "old_discount": float(old_discount),
            "new_discount": float(new_discount),
            "old_total": float(old_subtotal - old_discount),
            "new_total": float(new_total),
            "room_pricing_changes": room_pricing_changes,
            "additional_invoice": additional_invoice_name,
            "credit_note": credit_note_name,
            "updated_hrrs": len(linked_hrrs),
            "updated_checkins": len(active_checkins),
            "linked_documents": {
                "hrrs": [h["name"] for h in linked_hrrs],
                "checkins": [c["name"] for c in active_checkins]
            }
        }
    
    except frappe.exceptions.ValidationError as ve:
        frappe.log_error(frappe.get_traceback(), "Adjust FDR Validation Error")
        frappe.throw(str(ve))
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Adjust FDR Error")
        frappe.throw(_("Error adjusting reservation: {0}").format(str(e)))
        
        
# ═══════════════════════════════════════════════════════════════════════════
# MISSING FUNCTIONS - ADD THESE TO YOUR EXISTING hotel_front_desk_reservation.py
# ═══════════════════════════════════════════════════════════════════════════

# Add these functions at the end of your existing file (before the last line)


# @frappe.whitelist()
# def create_sales_invoice_for_reservation(reservation_name):
#     """
#     Create a bulk Sales Invoice for all rooms in the reservation.
#     This creates ONE invoice for all rooms (bulk invoice).
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted before creating invoice"))
        
#         if reservation.sales_invoice:
#             frappe.throw(_("Invoice already exists: {0}").format(reservation.sales_invoice))
        
#         if not reservation.customer:
#             frappe.throw(_("Customer is required to create invoice"))
        
#         # Create Sales Invoice
#         si = frappe.new_doc("Sales Invoice")
#         si.customer = reservation.customer
#         si.posting_date = nowdate()
#         si.due_date = reservation.to_date
#         si.po_no = reservation.reservation_number
#         si.remarks = _("Bulk invoice for reservation {0}").format(reservation.reservation_number)
        
#         # Add items for each room
#         for room in reservation.rooms:
#             try:
#                 item_name = create_or_get_item(room.room_type)
#             except:
#                 item_name = room.room_type
            
#             si.append("items", {
#                 "item_code": item_name,
#                 "item_name": f"{room.room_number} - {room.guest_name}",
#                 "description": _(
#                     "Room {0} ({1}) - {2} night(s) @ {3}/night for {4}"
#                 ).format(
#                     room.room_number,
#                     room.room_type,
#                     reservation.number_of_nights,
#                     room.rate_per_night,
#                     room.guest_name
#                 ),
#                 "qty": reservation.number_of_nights,
#                 "rate": room.rate_per_night,
#                 "amount": room.room_total
#             })
        
#         # Apply discount if any
#         if reservation.discount_amount and reservation.discount_amount > 0:
#             si.discount_amount = reservation.discount_amount
        
#         si.flags.ignore_permissions = True
#         si.insert()
#         si.submit()
        
#         # Update reservation with invoice reference
#         frappe.db.set_value(
#             "Hotel Front Desk Reservation",
#             reservation_name,
#             "sales_invoice",
#             si.name
#         )
        
#         frappe.db.commit()
        
#         return {
#             "success": True,
#             "message": _("Sales Invoice {0} created successfully").format(si.name),
#             "invoice": si.name
#         }
        
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Sales Invoice Error")
#         frappe.throw(_("Error creating invoice: {0}").format(str(e)))

@frappe.whitelist()
def create_sales_invoice_for_reservation(reservation_name):
    """
    Create a bulk Sales Invoice for all UNCHECKED-IN rooms in the reservation.
    This creates ONE invoice for all rooms (bulk invoice).
    
    ✅ FIXED v4.3:
    1. Excludes rooms that are already checked in
    2. Only includes unchecked rooms in the invoice
    3. Prevents duplicate invoicing for partially checked-in reservations
    4. Throws error if all rooms are already checked in
    
    Args:
        reservation_name: Name of Hotel Front Desk Reservation
    
    Returns:
        Dictionary with success status and invoice details
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before creating invoice"))
        
        if reservation.sales_invoice:
            frappe.throw(_("Invoice already exists: {0}").format(reservation.sales_invoice))
        
        if not reservation.customer:
            frappe.throw(_("Customer is required to create invoice"))
        
        # ✅ NEW: Get list of already checked-in rooms
        checked_in_rooms = frappe.db.get_all(
            "Hotel Room Check In",
            filters={
                "front_desk_reservation": reservation_name,
                "status": ["in", ["Draft", "Checked In"]]
            },
            fields=["room_number"]
        )
        
        checked_in_room_numbers = [r.room_number for r in checked_in_rooms]
        
        # ✅ NEW: Filter rooms - only include unchecked rooms
        unchecked_rooms = [
            room for room in reservation.rooms 
            if room.room_number not in checked_in_room_numbers
        ]
        
        # ✅ NEW: Throw error if all rooms are already checked in
        if not unchecked_rooms:
            frappe.throw(
                _(
                    "All rooms are already checked in. "
                    "Bulk invoice cannot be created for rooms that are already checked in."
                )
            )
        
        # Create Sales Invoice
        si = frappe.new_doc("Sales Invoice")
        si.customer = reservation.customer
        si.posting_date = nowdate()
        si.due_date = reservation.to_date
        si.po_no = reservation.reservation_number
        si.remarks = _("Bulk invoice for reservation {0}").format(reservation.reservation_number)
        
        # ✅ MODIFIED: Only add unchecked rooms to invoice
        total_amount = 0
        for room in unchecked_rooms:
            try:
                item_name = create_or_get_item(room.room_type)
            except:
                item_name = room.room_type
            
            si.append("items", {
                # "item_code": item_name,
                "item_code": room.room_number,
                "item_name": f"{room.room_number} - {room.guest_name}",
                "description": _(
                    "Room {0} ({1}) - {2} night(s) @ {3}/night for {4}"
                ).format(
                    room.room_number,
                    room.room_type,
                    reservation.number_of_nights,
                    room.rate_per_night,
                    room.guest_name
                ),
                "qty": reservation.number_of_nights,
                "rate": room.rate_per_night,
                "amount": room.room_total
            })
            
            total_amount += room.room_total
        
        # Apply discount if any
        if reservation.discount_amount and reservation.discount_amount > 0:
            si.discount_amount = reservation.discount_amount
        
        si.flags.ignore_permissions = True
        si.insert()
        si.submit()
        
        # Update reservation with invoice reference
        frappe.db.set_value(
            "Hotel Front Desk Reservation",
            reservation_name,
            "sales_invoice",
            si.name
        )
        
        frappe.db.commit()
        
        # ✅ NEW: Log information about excluded rooms
        if checked_in_rooms:
            frappe.log_error(
                f"""
                Sales Invoice Created with Excluded Checked-In Rooms
                ═══════════════════════════════════════════════════════
                Reservation: {reservation_name}
                Invoice: {si.name}
                Total Rooms: {len(reservation.rooms)}
                Unchecked Rooms: {len(unchecked_rooms)}
                Checked-In Rooms (Excluded): {len(checked_in_rooms)}
                Excluded Room Numbers: {', '.join(checked_in_room_numbers)}
                Total Amount (Unchecked Only): {total_amount}
                """,
                "Sales Invoice - Checked-In Rooms Excluded"
            )
        
        return {
            "success": True,
            "message": _(
                "Sales Invoice {0} created successfully for {1} room(s). "
                "{2} room(s) already checked in were excluded."
            ).format(si.name, len(unchecked_rooms), len(checked_in_rooms)),
            "invoice": si.name,
            "total_rooms": len(reservation.rooms),
            "unchecked_rooms": len(unchecked_rooms),
            "checked_in_rooms_excluded": len(checked_in_rooms),
            "excluded_room_numbers": checked_in_room_numbers,
            "total_amount": float(total_amount)
        }
        
    except frappe.exceptions.ValidationError as ve:
        frappe.log_error(frappe.get_traceback(), "Create Sales Invoice Validation Error")
        frappe.throw(str(ve))
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Sales Invoice Error")
        frappe.throw(_("Error creating invoice: {0}").format(str(e)))

@frappe.whitelist()
def check_in_selected_rooms(reservation_name, room_indices, check_in_notes=""):
    """
    Check in selected rooms from a reservation.
    Creates individual invoices for each room if not corporate bulk invoice.
    """
    try:
        if isinstance(room_indices, str):
            room_indices = json.loads(room_indices)
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before check-in"))
        
        if reservation.sales_invoice:
            frappe.throw(
                _(
                    "Bulk invoice {0} already exists for this reservation. "
                    "Please use 'Check In All Rooms' or 'Check In Selected Rooms from Invoice' instead. "
                    "This function is only for individual room reservations without bulk invoices."
                ).format(reservation.sales_invoice)
            )
        
        # Get check-in/out times from settings
        settings = frappe.get_single('Hotel Settings')
        check_in_time = check_in_time = now_datetime().strftime("%H:%M:%S") or "11:00:00"
        check_out_time = settings.default_check_out_time or "11:00:00"
        
        checked_in_rooms = []
        skipped_rooms = []
        missing_guest_names = []
        
        for idx in room_indices:
            idx = int(idx)
            
            # Find the room in the reservation
            room = None
            for r in reservation.rooms:
                if r.idx == idx + 1:  # idx is 0-based from JS, but idx in child table is 1-based
                    room = r
                    break
            
            if not room:
                skipped_rooms.append({
                    "idx": idx,
                    "reason": "Room not found in reservation"
                })
                continue
            
            # Check if room already has active check-in
            existing_checkin = frappe.db.get_value(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "status": ["in", ["Draft", "Checked In"]]
                },
                "name"
            )
            
            if existing_checkin:
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "Already checked in"
                })
                continue
            
            # Check if guest name exists
            if not room.guest_name or room.guest_name.startswith('Guest - Room'):
                missing_guest_names.append(room.room_number)
                continue
            
            # Get or create Hotel Room Reservation for this room
            hrr = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "docstatus": 1
                },
                "name"
            )
            
            if not hrr:
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "No room reservation found"
                })
                continue
            
            # Create check-in datetime
            check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
            expected_checkout_datetime = get_datetime(f"{reservation.to_date} {check_out_time}")
            
            # Create Sales Invoice for this room (if not bulk invoice)
            room_invoice = None
            if not reservation.sales_invoice:
                try:
                    si = frappe.new_doc("Sales Invoice")
                    # si.customer = room.guest_customer or reservation.customer
                    if reservation.reservation_type == "Corporate":
                        si.customer = reservation.customer
                    else:
                        si.customer = room.guest_customer or reservation.customer
                    si.posting_date = nowdate()
                    si.due_date = reservation.to_date
                    si.po_no = f"{reservation.reservation_number} - {room.room_number}"
                    
                    try:
                        item_name = create_or_get_item(room.room_type)
                    except:
                        item_name = room.room_type
                    
                    si.append("items", {
                        "item_code": item_name,
                        "item_name": f"{room.room_number} - {room.guest_name}",
                        "description": _(
                            "Room {0} - {1} night(s) @ {2}/night"
                        ).format(room.room_number, reservation.number_of_nights, room.rate_per_night),
                        "qty": reservation.number_of_nights,
                        "rate": room.rate_per_night,
                        "amount": room.room_total
                    })
                    
                    si.flags.ignore_permissions = True
                    si.insert()
                    si.submit()
                    room_invoice = si.name
                    
                    # Add to sales_invoices child table
                    reservation.append("sales_invoices", {
                        "room_number": room.room_number,
                        "guest_name": room.guest_name,
                        "sales_invoice": si.name,
                        "amount": room.room_total,
                        "created_at": now_datetime()
                    })
                    reservation.flags.ignore_permissions = True
                    reservation.flags.ignore_validate_update_after_submit = True
                    reservation.save()
                    
                except Exception as e:
                    frappe.log_error(
                        f"Failed to create invoice for room {room.room_number}: {str(e)}",
                        "Check In Invoice Error"
                    )
            else:
                room_invoice = reservation.sales_invoice
                
            frappe.log_error(
                title="Front Desk rrrrr",
                message=(
                    f"Room: {room.room_number}\n"
                    # f"Date: {start_date}\n"
                    f"Guest: {room.hotel_guest}\n"
                    f"Reservations Found:\n{frappe.as_json(reservation)}"
                )
            )
            
            rate_type = getattr(room, 'rate_type', None)
            
            # Create Hotel Room Check In
            checkin = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "front_desk_reservation": reservation_name,
                "hotel_room_reservation": hrr,
                "reservation": hrr,
                "room_number": room.room_number,
                "room_type": room.room_type,
                "rate_type": rate_type,
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
                "payment_status": "Pending",
                "check_in_notes": check_in_notes,
                "sales_invoice": room_invoice,
                "discount": reservation.discount_amount or 0,  # Set discount
                "discount_type": reservation.discount_type if reservation.discount_type else "None",
                "total_charges": room.room_total
            })
            
            checkin.flags.ignore_permissions = True
            checkin.insert()
            checkin.submit()
            
            # Update Hotel Room Reservation status
            frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")
            
            checked_in_rooms.append({
                "room_number": room.room_number,
                "guest_name": room.guest_name,
                "checkin_name": checkin.name,
                "invoice": room_invoice
            })
        
        # Check for missing guest names
        if missing_guest_names and len(checked_in_rooms) == 0:
            return {
                "success": False,
                "missing_guest_names": True,
                "message": _("Guest names required for rooms: {0}").format(", ".join(missing_guest_names))
            }
        
        # Update reservation status if any rooms were checked in
        if checked_in_rooms:
            total_rooms = len(reservation.rooms)
            all_checkins = frappe.db.count(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "status": ["in", ["Draft", "Checked In"]]
                }
            )
            
            if all_checkins >= total_rooms:
                frappe.db.set_value(
                    "Hotel Front Desk Reservation",
                    reservation_name,
                    "status",
                    "Checked In"
                )
            elif all_checkins > 0:
                current_status = reservation.status
                if current_status == "Confirmed":
                    frappe.db.set_value(
                        "Hotel Front Desk Reservation",
                        reservation_name,
                        "status",
                        "Checked In"
                    )
        
        frappe.db.commit()
        
        message = _("{0} room(s) checked in successfully.").format(len(checked_in_rooms))
        if skipped_rooms:
            message += _(" {0} room(s) skipped.").format(len(skipped_rooms))
        if missing_guest_names:
            message += _(" {0} room(s) need guest names.").format(len(missing_guest_names))
        
        return {
            "success": True,
            "message": message,
            "checked_in_rooms": checked_in_rooms,
            "skipped_rooms": skipped_rooms,
            "missing_guest_names": missing_guest_names
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In Selected Rooms Error")
        frappe.throw(_("Error checking in rooms: {0}").format(str(e)))


# @frappe.whitelist()
# def check_in_all_rooms(reservation_name, check_in_notes=""):
#     """
#     Check in all rooms from a reservation.
#     """
#     try:
#         reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
#         if reservation.docstatus != 1:
#             frappe.throw(_("Reservation must be submitted before check-in"))
        
#         # Get all room indices
#         room_indices = [r.idx - 1 for r in reservation.rooms]
        
#         # Use check_in_selected_rooms for all rooms
#         return check_in_selected_rooms(reservation_name, room_indices, check_in_notes)
        
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
#         frappe.throw(_("Error checking in all rooms: {0}").format(str(e)))


@frappe.whitelist()
def check_in_all_rooms(reservation_name, check_in_notes=""):
    """
    Check in ALL rooms from a reservation using the bulk invoice.
    
    ✅ FIXED v4.1:
    1. Requires sales invoice (bulk invoice) to exist
    2. Does NOT create new invoices
    3. Checks all unchecked rooms using the bulk invoice
    4. Uses same pattern as check_in_rooms_in_bulk_invoice()
    
    Args:
        reservation_name: Name of Hotel Front Desk Reservation
        check_in_notes: Optional notes for check-in
    
    Returns:
        Dictionary with success status and check-in details
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        # Validate reservation
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before check-in"))
        
        # ✅ NEW: Require bulk invoice to exist
        if not reservation.sales_invoice:
            frappe.throw(
                _("Sales invoice required to check in all rooms. "
                  "Please create a bulk invoice first using 'Create Invoice' button.")
            )
        
        # Get check-in/out times from settings
        settings = frappe.get_single('Hotel Settings')
        check_in_time = now_datetime().strftime("%H:%M:%S")
        check_out_time = settings.default_check_out_time or "11:00:00"
        
        checked_in_rooms = []
        skipped_rooms = []
        
        # ✅ Check in ALL rooms
        for room in reservation.rooms:
            # Check if room already has active check-in
            existing_checkin = frappe.db.get_value(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "status": ["in", ["Draft", "Checked In"]]
                },
                "name"
            )
            
            if existing_checkin:
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "Already checked in"
                })
                continue
            
            # Check if guest name exists
            if not room.guest_name or room.guest_name.startswith('Guest - Room'):
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "Guest name required"
                })
                continue
            
            # Get Hotel Room Reservation for this room
            hrr = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "docstatus": 1
                },
                "name"
            )
            
            if not hrr:
                skipped_rooms.append({
                    "room_number": room.room_number,
                    "reason": "No room reservation found"
                })
                continue
            
            # Create check-in datetime
            check_in_datetime = get_datetime(f"{reservation.from_date} {check_in_time}")
            expected_checkout_datetime = get_datetime(f"{reservation.to_date} {check_out_time}")
            
            rate_type = getattr(room, 'rate_type', None)
            
            # ✅ Create Hotel Room Check In (NO invoice creation - uses bulk invoice)
            checkin = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "front_desk_reservation": reservation_name,
                "reservation": hrr,
                "room_number": room.room_number,
                "room_type": room.room_type,
                "rate_type": rate_type,
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
                "payment_status": "Paid",  # ✅ Already in bulk invoice
                "check_in_notes": check_in_notes,
                "sales_invoice": reservation.sales_invoice,  # ✅ Link to bulk invoice
                "is_bulk_invoice_room": 1,  # ✅ Flag to indicate bulk invoice room
                "discount": reservation.discount_amount or 0,
                "discount_type": reservation.discount_type if reservation.discount_type else "None",
                "total_charges": room.room_total
            })
            
            checkin.flags.ignore_permissions = True
            checkin.insert()
            checkin.submit()
            
            # Update Hotel Room Reservation status
            frappe.db.set_value("Hotel Room Reservation", hrr, "status", "Checked In")
            
            checked_in_rooms.append({
                "room_number": room.room_number,
                "guest_name": room.guest_name,
                "checkin_name": checkin.name
            })
        
        # Update reservation status if any rooms were checked in
        if checked_in_rooms:
            total_rooms = len(reservation.rooms)
            all_checkins = frappe.db.count(
                "Hotel Room Check In",
                {
                    "front_desk_reservation": reservation_name,
                    "status": ["in", ["Draft", "Checked In"]]
                }
            )
            
            if all_checkins >= total_rooms:
                frappe.db.set_value(
                    "Hotel Front Desk Reservation",
                    reservation_name,
                    "status",
                    "Checked In"
                )
            elif all_checkins > 0:
                # Partial check-in
                current_status = reservation.status
                if current_status == "Confirmed":
                    frappe.db.set_value(
                        "Hotel Front Desk Reservation",
                        reservation_name,
                        "status",
                        "Checked In"
                    )
        
        frappe.db.commit()
        
        message = _("{0} room(s) checked in successfully (bulk invoice).").format(len(checked_in_rooms))
        if skipped_rooms:
            message += _(" {0} room(s) skipped.").format(len(skipped_rooms))
        
        return {
            "success": True,
            "message": message,
            "checked_in_rooms": checked_in_rooms,
            "skipped_rooms": skipped_rooms,
            "bulk_invoice": reservation.sales_invoice,
            "total_checked_in": len(checked_in_rooms),
            "total_skipped": len(skipped_rooms),
            "all_checked_in": len(checked_in_rooms) == len(reservation.rooms)
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In All Rooms Error")
        frappe.throw(_("Error checking in all rooms: {0}").format(str(e)))


@frappe.whitelist()
def check_in_reservation(reservation_name, check_in_notes="", create_reservations=False):
    """
    Check in all rooms for non-corporate reservations.
    """
    return check_in_all_rooms(reservation_name, check_in_notes)


@frappe.whitelist()
def update_guest_names(reservation_name, guest_updates):
    """
    Update guest names for rooms in a reservation.
    """
    try:
        if isinstance(guest_updates, str):
            guest_updates = json.loads(guest_updates)
        
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        updated_count = 0
        
        for update in guest_updates:
            room_idx = update.get("room_idx")
            guest_name = update.get("guest_name")
            guest_email = update.get("guest_email", "")
            guest_phone = update.get("guest_phone", "")
            
            if room_idx is None or not guest_name:
                continue
            
            room = reservation.rooms[room_idx]
            
            # Update room in child table
            for child_table_name in ["Front Desk Reservation Room", "Hotel Front Desk Rooms"]:
                room_row = frappe.db.get_value(
                    child_table_name,
                    {"parent": reservation_name, "room_number": room.room_number},
                    "name"
                )
                
                if room_row:
                    frappe.db.set_value(
                        child_table_name,
                        room_row,
                        {
                            "guest_name": guest_name,
                            "guest_email": guest_email,
                            "guest_phone": guest_phone
                        },
                        update_modified=False
                    )
                    updated_count += 1
                    break
            
            # Update Hotel Room Reservation if exists
            hrr = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number
                },
                "name"
            )
            
            if hrr:
                frappe.db.set_value(
                    "Hotel Room Reservation",
                    hrr,
                    "guest_name",
                    guest_name
                )
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("{0} guest name(s) updated successfully").format(updated_count)
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Guest Names Error")
        frappe.throw(_("Error updating guest names: {0}").format(str(e)))


@frappe.whitelist()
def edit_guest_details(reservation_name, room_idx, guest_name, guest_email, guest_phone, room_number):
    """
    Edit guest details for a specific room.
    Also creates/updates customer and hotel guest records.
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        room_idx = int(room_idx)
        room = reservation.rooms[room_idx]
        
        existing_checkin = frappe.db.get_value(
            "Hotel Room Check In",
            {
                "front_desk_reservation": reservation_name,
                "room_number": room_number,
                "status": ["in", ["Draft", "Checked In"]]
            },
            "name"
        )
        
        if existing_checkin:
            frappe.throw(
                _("Cannot edit guest details for room {0} after check-in. "
                  "Room is already checked in.")
                .format(room_number)
            )
        
        
        # Get or create customer
        customer_id = None
        if guest_email:
            existing = frappe.db.get_value("Customer", {"email_id": guest_email}, "name")
            if existing:
                customer_id = existing
        
        if not customer_id and guest_phone:
            clean_phone = guest_phone.replace(" ", "").replace("-", "").replace("+", "")
            existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
            if existing:
                customer_id = existing
        
        if not customer_id:
            customer = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": guest_name,
                "customer_type": "Individual",
                "email_id": guest_email or "",
                "mobile_no": guest_phone or "",
                "territory": frappe.db.get_default("territory") or "Nigeria",
                "customer_group": frappe.db.get_default("customer_group") or "Individual"
            })
            customer.flags.ignore_permissions = True
            customer.insert()
            customer_id = customer.name
        
        # Get or create hotel guest
        hotel_guest_id = None
        existing_guest = frappe.db.get_value(
            "Hotel Guest",
            {"hotel_guest_name": guest_name},
            "name"
        )
        
        if existing_guest:
            hotel_guest_id = existing_guest
        else:
            if guest_email:
                existing_guest = frappe.db.get_value(
                    "Hotel Guest",
                    {"email": guest_email},
                    "name"
                )
                if existing_guest:
                    hotel_guest_id = existing_guest
        
        if not hotel_guest_id:
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": guest_phone or "",
                "email": guest_email or "",
                "customer": customer_id,
                "guest_type": "Corporate" if reservation.reservation_type == "Corporate" else "Individual"
            })
            guest.flags.ignore_permissions = True
            guest.insert()
            hotel_guest_id = guest.name
        
        # Update room in child table
        for child_table_name in ["Front Desk Reservation Room", "Hotel Front Desk Rooms"]:
            room_row = frappe.db.get_value(
                child_table_name,
                {"parent": reservation_name, "room_number": room_number},
                "name"
            )
            
            if room_row:
                frappe.db.set_value(
                    child_table_name,
                    room_row,
                    {
                        "guest_name": guest_name,
                        "guest_email": guest_email,
                        "guest_phone": guest_phone,
                        "guest_customer": customer_id,
                        "hotel_guest": hotel_guest_id
                    },
                    update_modified=False
                )
                break
        
        # Update Hotel Room Reservation if exists
        hrr = frappe.db.get_value(
            "Hotel Room Reservation",
            {
                "front_desk_reservation": reservation_name,
                "room_number": room_number
            },
            "name"
        )
        
        if hrr:
            frappe.db.set_value(
                "Hotel Room Reservation",
                hrr,
                {
                    "guest_name": guest_name,
                    "customer": customer_id
                }
            )
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Guest details updated for room {0}").format(room_number),
            "customer": customer_id,
            "hotel_guest": hotel_guest_id
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Edit Guest Details Error")
        frappe.throw(_("Error updating guest details: {0}").format(str(e)))
        
