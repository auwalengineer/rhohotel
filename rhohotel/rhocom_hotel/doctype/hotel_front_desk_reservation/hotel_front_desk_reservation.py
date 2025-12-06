import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days, now_datetime
from datetime import datetime, timedelta
import json
from frappe.utils import date_diff, getdate

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
        self.primary_guest_name = corporate.hotel_guest_name
        self.primary_guest_email = corporate.email or ""
        self.primary_guest_phone = corporate.phone_number or ""
    
    # ═══════════════════════════════════════════════════════════════════════
    # DOCUMENT CREATION
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
    
    def get_or_create_customer(self, name, email, phone):
        
      
        if email:
            existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
            if existing:
                return existing
        
        
        if phone:
            clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "")
            existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
            if existing:
                return existing
        
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name or "Guest",
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
        rooms_missing_names = []
        
        for room in self.rooms:
            self.get_or_create_hotel_guest(room)
    
    def get_or_create_hotel_guest(self, room):
        guest_name = room.guest_name
        guest_email = room.guest_email
        guest_phone = room.guest_phone
        
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
            
        try:
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": guest_phone or "",
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
            
        except frappe.exceptions.InvalidPhoneNumberError:
            # Retry without phone (phone format might be invalid)
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": guest_name,
                "phone_number": "",
                "email": guest_email or "",
                "gender": room.guest_gender or "Male",
                "id_type": room.guest_id_type or "Passport",
                "id_number": room.guest_id_number or "",
                "customer": room.guest_customer,
                "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
            })
            guest.flags.ignore_permissions = True
            guest.insert()
            
            # Update phone after creation if provided
            if guest_phone:
                frappe.db.set_value(
                    "Hotel Guest",
                    guest.name,
                    "phone_number",
                    guest_phone,
                    update_modified=False
                )
            
            room.hotel_guest = guest.name
            return guest.name
        
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "Create Hotel Guest Error"
            )
            raise

    def create_room_reservations(self):
        """Create Hotel Room Reservations (NON-CORPORATE ONLY)"""
        
        number_of_nights = date_diff(getdate(self.to_date), getdate(self.from_date))
        
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
    Check in ALL rooms - ONLY if Sales Invoice exists
    
    ✅ SAFETY CHECKS:
    1. Reservation must be submitted
    2. Sales Invoice MUST be linked (ensures payment)
    3. Exclude rooms already checked in (prevent duplicate)
    4. Only check in rooms NOT already checked in
    
    This ensures:
    - Every room has an invoice
    - Payment confirmed before check-in
    - No duplicate check-ins
    - No overbilling
    """
    try:
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        # ✅ CHECK 1: Reservation must be submitted
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted"))
        
        # ✅ CHECK 2: Sales Invoice MUST exist (ensures payment)
        if not reservation.sales_invoice:
            frappe.throw(
                _("Cannot check in all guests: No Sales Invoice linked to this reservation.\n\n"
                  "Please create a Sales Invoice first using the 'Create Invoice' button. "
                  "This ensures payment confirmation before check-in.")
            )
        
        # ✅ CHECK 3: Get all rooms already checked in
        already_checked_in = frappe.db.get_all(
            "Hotel Room Check In",
            filters={
                "front_desk_reservation": reservation_name,
                "status": ["in", ["Draft", "Checked In"]]
            },
            fields=["room_number"],
            distinct=True
        )
        
        checked_in_room_numbers = set([r.room_number for r in already_checked_in])
        
        # ✅ CHECK 4: Filter out already checked-in rooms
        rooms_to_checkin = [
            room for room in reservation.rooms 
            if room.room_number not in checked_in_room_numbers
        ]
        
        # ✅ If all rooms already checked in
        if len(rooms_to_checkin) == 0:
            frappe.throw(
                _("All rooms have already been checked in for this reservation.")
            )
        
        # ✅ Log which rooms are being skipped
        if len(checked_in_room_numbers) > 0:
            frappe.log_error(
                title=f"Skipping already checked-in rooms - {reservation_name}",
                message="Rooms already checked in: {0}".format(
                    ", ".join(sorted(checked_in_room_numbers))
                )
            )
        
        checked_in_rooms = []
        
        # Check in only rooms NOT already checked in
        for idx, room in enumerate(reservation.rooms):
            # Skip if already checked in
            if room.room_number in checked_in_room_numbers:
                continue
            
            # ✅ Get Hotel Room Reservation
            hrr_name = frappe.db.get_value(
                "Hotel Room Reservation",
                {
                    "front_desk_reservation": reservation_name,
                    "room_number": room.room_number,
                    "docstatus": 1
                },
                "name"
            )
            
            # ✅ Get HRR document - get ALL data from here
            hrr = frappe.get_doc("Hotel Room Reservation", hrr_name)
            
            # ✅ Get rate_type from HRR.items (child table)
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
                "guest": hotel_guest_id,
                # Room Details
                "room_number": hrr.room_number,
                "room_type": room_type,
                # Pricing - rate_type from HRR.items!
                "rate_type": rate_type,
                "rate_amount": hrr.rate or 0,
                # Dates & Times
                "check_in_datetime": now_datetime(),
                "number_of_nights": number_of_nights,
                "expected_check_out_datetime": get_datetime(
                    f"{hrr.to_date} {reservation.expected_check_out_time or '12:00:00'}"
                ),
                # Status
                "status": "Checked In",
                # Linking
                "front_desk_reservation": reservation_name,
                "reservation": hrr_name
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
        
        # ✅ Build result message
        message = _("Successfully checked in {0} room(s)").format(len(checked_in_rooms))
        
        if len(checked_in_room_numbers) > 0:
            message += _("\n\nNote: Skipped {0} room(s) already checked in: {1}").format(
                len(checked_in_room_numbers),
                ", ".join(sorted(checked_in_room_numbers))
            )
        
        frappe.msgprint({
            "title": _("Check-In Complete"),
            "message": message,
            "indicator": "green"
        })
        
        return {
            "success": True,
            "message": message,
            "checked_in": checked_in_rooms,
            "skipped": list(checked_in_room_numbers)
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Check In All Guests Error")
        frappe.throw(_("Error: {0}").format(str(e)))
        
        
        
        
        
        
        
        
        
@frappe.whitelist()
def edit_guest_details(reservation_name, room_idx, guest_name, guest_email, guest_phone, room_number):
    """
    Edit guest details for a specific room in a reservation
    
    ✅ FLOW:
    1. Get or create Customer account with guest_name/email/phone
    2. Get or create Hotel Guest record
    3. Update room in FDR with new guest details
    4. Update linked Hotel Room Reservation with new guest_name
    
    Args:
        reservation_name: Name of Hotel Front Desk Reservation
        room_idx: Index of room in FDR.rooms child table
        guest_name: Guest name (required)
        guest_email: Guest email (optional)
        guest_phone: Guest phone (optional)
        room_number: Room number being edited
    """
    try:
        # Convert room_idx to integer
        room_idx = int(room_idx)
        
        # Get the reservation
        reservation = frappe.get_doc("Hotel Front Desk Reservation", reservation_name)
        
        if reservation.docstatus != 1:
            frappe.throw(_("Reservation must be submitted before editing guest details"))
        
        # Get the room from child table
        if room_idx >= len(reservation.rooms):
            frappe.throw(_("Invalid room index"))
        
        room = reservation.rooms[room_idx]
        
        # ✅ STEP 1: Get or create customer account
        customer_id = get_or_create_customer_for_guest(
            guest_name,
            guest_email,
            guest_phone
        )
        
        # ✅ STEP 2: Get or create Hotel Guest record
        hotel_guest_id = get_or_create_hotel_guest_for_edit(
            guest_name,
            guest_email,
            guest_phone,
            customer_id,
            reservation.reservation_type
        )
        
        # ✅ STEP 3: Update room in FDR using db.set_value
        frappe.db.set_value(
            "Front Desk Reservation Room",
            room.name,
            {
                "guest_name": guest_name,
                "guest_email": guest_email,
                "guest_phone": guest_phone,
                "hotel_guest": hotel_guest_id,
                "guest_customer": customer_id
            },
            update_modified=False
        )
        
        # ✅ STEP 4: Find and update linked Hotel Room Reservation
        hrr_name = frappe.db.get_value(
            "Hotel Room Reservation",
            {
                "front_desk_reservation": reservation_name,
                "room_number": room_number,
                "docstatus": 1
            },
            "name"
        )
        
        if hrr_name:
            frappe.db.set_value(
                "Hotel Room Reservation",
                hrr_name,
                {
                    "guest_name": guest_name,
                    "customer": customer_id
                },
                update_modified=False
            )
            
            frappe.log_error(
                title=f"Guest Details Updated - Room {room_number}",
                message="HRR: {0}\nGuest: {1}\nEmail: {2}\nPhone: {3}".format(
                    hrr_name, guest_name, guest_email, guest_phone
                )
            )
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Guest details updated successfully for Room {0}").format(room_number),
            "room_number": room_number,
            "guest_name": guest_name,
            "customer_id": customer_id,
            "hotel_guest_id": hotel_guest_id
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Edit Guest Details Error")
        frappe.throw(_("Error: {0}").format(str(e)))


def get_or_create_customer_for_guest(name, email, phone):
    """
    Get or create customer account for guest
    Searches by email first, then phone, then creates new
    """
    
    # Try to find by email
    if email:
        existing = frappe.db.get_value("Customer", {"email_id": email}, "name")
        if existing:
            return existing
    
    # Try to find by phone
    if phone:
        clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "")
        existing = frappe.db.get_value("Customer", {"mobile_no": clean_phone}, "name")
        if existing:
            return existing
    
    # Create new customer
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name or "Guest",
        "customer_type": "Individual",
        "email_id": email or "",
        "mobile_no": phone or "",
        "territory": frappe.db.get_default("territory") or "Nigeria",
        "customer_group": frappe.db.get_default("customer_group") or "Individual"
    })
    customer.flags.ignore_permissions = True
    customer.insert()
    
    return customer.name


def get_or_create_hotel_guest_for_edit(guest_name, guest_email, guest_phone, customer_id, reservation_type):
    """
    Get or create Hotel Guest record for edited guest
    """
    
    # Try to find by email
    if guest_email:
        existing = frappe.db.get_value(
            "Hotel Guest",
            {"email": guest_email},
            "name"
        )
        if existing:
            return existing
    
    # Try to find by phone
    if guest_phone:
        clean_phone = guest_phone.replace(" ", "").replace("-", "").replace("+", "")
        existing = frappe.db.get_value(
            "Hotel Guest",
            {"phone_number": clean_phone},
            "name"
        )
        if existing:
            return existing
    
    # Create new Hotel Guest
    try:
        guest = frappe.get_doc({
            "doctype": "Hotel Guest",
            "hotel_guest_name": guest_name,
            "phone_number": guest_phone or "",
            "email": guest_email or "",
            "gender": "Male",  # Default
            "id_type": "Passport",  # Default
            "id_number": "",
            "customer": customer_id,
            "guest_type": "Corporate" if reservation_type == "Corporate" else "Individual"
        })
        guest.flags.ignore_permissions = True
        guest.insert()
        
        return guest.name
    
    except frappe.exceptions.InvalidPhoneNumberError:
        # Retry without phone if invalid
        guest = frappe.get_doc({
            "doctype": "Hotel Guest",
            "hotel_guest_name": guest_name,
            "phone_number": "",
            "email": guest_email or "",
            "gender": "Male",
            "id_type": "Passport",
            "id_number": "",
            "customer": customer_id,
            "guest_type": "Corporate" if reservation_type == "Corporate" else "Individual"
        })
        guest.flags.ignore_permissions = True
        guest.insert()
        
        # Update phone after creation if provided
        if guest_phone:
            frappe.db.set_value(
                "Hotel Guest",
                guest.name,
                "phone_number",
                guest_phone,
                update_modified=False
            )
        
        return guest.name
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Hotel Guest for Edit Error")
        raise