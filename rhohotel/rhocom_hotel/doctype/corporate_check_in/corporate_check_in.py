# Copyright (c) 2024, Rhocom Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, get_datetime, date_diff  
class CorporateCheckIn(Document):
    
    
    def validate(self):
       self.calculate_number_of_nights()  # NEW
       self.validate_corporate_guest()
       self.validate_dates()  # NEW
       self.validate_rooms()
       self.calculate_totals()
        
    def calculate_number_of_nights(self):
       """Calculate number of nights from check-in and check-out dates"""
       if self.check_in_datetime and self.expected_check_out_datetime:
           check_in = get_datetime(self.check_in_datetime)
           check_out = get_datetime(self.expected_check_out_datetime)
           nights = date_diff(check_out, check_in)
           if nights <= 0:
               frappe.throw("Check-out date must be after check-in date")
           self.number_of_nights = nights
    
    def validate_dates(self):
       """Validate check-in and check-out dates"""
       if self.check_in_datetime and self.expected_check_out_datetime:
           check_in = get_datetime(self.check_in_datetime)
           check_out = get_datetime(self.expected_check_out_datetime)
           if check_out <= check_in:
               frappe.throw("Check-out date and time must be after check-in date and time")
    
    def validate_corporate_guest(self):
        """Ensure the selected guest is a corporate guest"""
        if self.corporate_guest:
            guest = frappe.get_doc("Hotel Guest", self.corporate_guest)
            if guest.guest_type != "Corporate":
                frappe.throw(f"Guest {self.corporate_guest} is not a Corporate guest. Please select a Corporate guest type.")
    
    def validate_rooms(self):
        """Validate room availability and guest details"""
        if not self.rooms:
            frappe.throw("Please add at least one room")
        
        room_numbers = []
        check_in_dt = get_datetime(self.check_in_datetime)
        check_out_dt = get_datetime(self.expected_check_out_datetime)
        
        for room in self.rooms:
            # Check for duplicate rooms
            if room.room_number in room_numbers:
                frappe.throw(f"Room {room.room_number} is selected multiple times. Each room can only be selected once.")
            room_numbers.append(room.room_number)
            
            # Validate room exists and get details
            room_doc = frappe.get_doc("Hotel Room", room.room_number)
            
            # Check if room is vacant
            if room_doc.status != "Vacant":
                frappe.throw(f"Room {room.room_number} is currently {room_doc.status}. Only vacant rooms can be checked in.")
            
            # Check if room is clean
            if room_doc.housekeeping_status != "Clean":
                frappe.throw(f"Room {room.room_number} housekeeping status is {room_doc.housekeeping_status}. Only clean rooms can be checked in.")
            
            # Check for overlapping reservations
            overlapping_reservations = frappe.db.sql("""
                SELECT name, from_date, to_date 
                FROM `tabHotel Room Reservation`
                WHERE room_number = %s
                AND docstatus = 1
                AND status IN ('Confirmed', 'Booked')
                AND (
                    (from_date <= %s AND to_date > %s)
                    OR (from_date < %s AND to_date >= %s)
                    OR (from_date >= %s AND to_date <= %s)
                )
            """, (room.room_number, check_in_dt, check_in_dt, check_out_dt, check_out_dt, check_in_dt, check_out_dt), as_dict=True)
            
            if overlapping_reservations:
                reservation_details = ", ".join([f"{r.name} ({r.from_date} to {r.to_date})" for r in overlapping_reservations])
                frappe.throw(f"Room {room.room_number} has overlapping reservation(s): {reservation_details}. Please choose another room or date.")
            
            # Check for overlapping check-ins
            overlapping_checkins = frappe.db.sql("""
                SELECT name, check_in_datetime, expected_check_out_datetime 
                FROM `tabHotel Room Check In`
                WHERE room_number = %s
                AND docstatus = 1
                AND status = 'Checked In'
                AND (
                    (check_in_datetime <= %s AND expected_check_out_datetime > %s)
                    OR (check_in_datetime < %s AND expected_check_out_datetime >= %s)
                    OR (check_in_datetime >= %s AND expected_check_out_datetime <= %s)
                )
            """, (room.room_number, check_in_dt, check_in_dt, check_out_dt, check_out_dt, check_in_dt, check_out_dt), as_dict=True)
            
            if overlapping_checkins:
                checkin_details = ", ".join([f"{c.name} ({c.check_in_datetime} to {c.expected_check_out_datetime})" for c in overlapping_checkins])
                frappe.throw(f"Room {room.room_number} is already checked in: {checkin_details}. Please choose another room.")
            
            # Validate guest details
            if not room.guest_name:
                frappe.throw(f"Guest name is required for Room {room.room_number}")
    
    def calculate_totals(self):
        """Calculate total charges with discount"""
        total_room_charges = 0
        
        for room in self.rooms:
            # Calculate total for this room
            room_total = flt(room.rate_amount) * flt(self.number_of_nights or 0)
            room.total_amount = room_total
            total_room_charges += room_total
        
        self.total_room_charges = total_room_charges
        
        # Calculate discount
        discount_amount = 0
        if self.discount_type == "Percentage":
            discount_amount = (total_room_charges * flt(self.discount)) / 100
        elif self.discount_type == "Amount":
            discount_amount = flt(self.discount)
            # Validate discount amount doesn't exceed total
            if discount_amount > total_room_charges:
                frappe.throw(f"Discount amount ({discount_amount}) cannot exceed total room charges ({total_room_charges})")
        
        self.discount_amount = discount_amount
        self.total_charges = total_room_charges - discount_amount
    
    def on_submit(self):
        """Create individual check-ins for each room"""
        self.validate_rooms()  # Re-validate before submission
        self.create_individual_check_ins()
        self.create_sales_invoice()
        self.status = "Checked In"
        self.save()
    
    def create_individual_check_ins(self):
        """Create Hotel Room Check In for each room"""
        for room in self.rooms:
            # Create or get guest customer
            guest_customer = self.create_guest_customer(room)
            
            # Calculate per-room discount
            room_charge = flt(room.rate_amount) * flt(self.number_of_nights)
            room_discount = (room_charge / self.total_room_charges) * self.discount_amount if self.total_room_charges else 0
            
            # Create check-in
            check_in = frappe.get_doc({
                "doctype": "Hotel Room Check In",
                "corporate_check_in": self.name,
                "guest": guest_customer,
                "room_number": room.room_number,
                "room_type": room.room_type,
                "rate_amount": room.rate_amount,
                "check_in_datetime": self.check_in_datetime,
                "expected_check_out_datetime": self.expected_check_out_datetime,
                "number_of_nights": self.number_of_nights,
                "discount": room_discount,
                "reservation_source": "Walk In",  # Corporate bookings are walk-ins
                "status": "Draft"
            })
            check_in.insert(ignore_permissions=True)
            check_in.submit()
            
            # Update room child table with reference
            room.check_in_reference = check_in.name
            room.guest_customer = guest_customer
    
    # def create_guest_customer(self, room):
    #     """Create individual guest as customer"""
    #     # Check if customer already exists by email or phone
    #     existing_customer = None
        
    #     if room.guest_email:
    #         existing_customer = frappe.db.get_value("Customer", {"email_id": room.guest_email}, "name")
        
    #     if not existing_customer and room.guest_phone:
    #         existing_customer = frappe.db.get_value("Customer", {"mobile_no": room.guest_phone}, "name")
        
    #     if not existing_customer:
    #         existing_customer = frappe.db.get_value("Customer", {"customer_name": room.guest_name}, "name")
        
    #     if existing_customer:
    #         return existing_customer
        
    #     # Create new customer
    #     customer = frappe.get_doc({
    #         "doctype": "Customer",
    #         "customer_name": room.guest_name,
    #         "customer_type": "Individual",
    #         "customer_group": "Individual",
    #         "territory": "All Territories",
    #         "mobile_no": room.guest_phone,
    #         "email_id": room.guest_email
    #     })
    #     customer.insert(ignore_permissions=True)
        
    #     return customer.name
    
    
    
    def create_guest_customer(self, room):
        """Create individual guest as Hotel Guest and Customer"""
        # Check if Hotel Guest already exists by email or phone
        existing_guest = None
        
        if room.guest_email:
            existing_guest = frappe.db.get_value("Hotel Guest", {"email": room.guest_email}, "name")
        
        if not existing_guest and room.guest_phone:
            existing_guest = frappe.db.get_value("Hotel Guest", {"phone_number": room.guest_phone}, "name")
        
        if not existing_guest:
            existing_guest = frappe.db.get_value("Hotel Guest", {"hotel_guest_name": room.guest_name}, "name")
        
        # If Hotel Guest exists, return their customer
        if existing_guest:
            guest_doc = frappe.get_doc("Hotel Guest", existing_guest)
            if guest_doc.customer:
                return guest_doc.customer
            else:
                # Guest exists but no customer, create customer and link
                customer = self.create_customer_for_guest(room)
                guest_doc.customer = customer
                guest_doc.save(ignore_permissions=True)
                return customer
        
        # Create new Hotel Guest and Customer
        customer = self.create_customer_for_guest(room)
        
        # Create Hotel Guest
        hotel_guest = frappe.get_doc({
            "doctype": "Hotel Guest",
            "hotel_guest_name": room.guest_name,
            "guest_type": "Individual",
            "gender": room.guest_gender,
            "id_type": room.guest_id_type,
            "id_number": room.guest_id_number,
            "phone_number": room.guest_phone,
            "email": room.guest_email,
            "customer": customer
        })
        hotel_guest.insert(ignore_permissions=True)
    
        return customer

    def create_customer_for_guest(self, room):
        """Create customer record for guest"""
        # Check if customer already exists by email or phone
        existing_customer = None
        
        if room.guest_email:
            existing_customer = frappe.db.get_value("Customer", {"email_id": room.guest_email}, "name")
        
        if not existing_customer and room.guest_phone:
            existing_customer = frappe.db.get_value("Customer", {"mobile_no": room.guest_phone}, "name")
        
        if not existing_customer:
            existing_customer = frappe.db.get_value("Customer", {"customer_name": room.guest_name}, "name")
        
        if existing_customer:
            return existing_customer
        
        # Create new customer
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": room.guest_name,
            "customer_type": "Individual",
            "customer_group": "Individual",
            "territory": "All Territories",
            "mobile_no": room.guest_phone,
            "email_id": room.guest_email
        })
        customer.insert(ignore_permissions=True)
        
        return customer.name

    def create_sales_invoice(self):
        """Create a single sales invoice for the corporate customer"""
        if not self.customer:
            frappe.throw("Corporate customer not found")
        
        # Get hotel settings for income account
        hotel_settings = frappe.get_single("Hotel Settings")
        income_account = hotel_settings.default_income_account
        
        if not income_account:
            frappe.throw("Default income account not set in Hotel Settings")
        
        items = []
        for room in self.rooms:
            room_charge = flt(room.rate_amount) * flt(self.number_of_nights)
            
            items.append({
                 "item_code": room.room_number,
                "item_name": f"Room {room.room_number} - {room.guest_name}",
                "description": f"Room booking for {self.number_of_nights} night(s)\nGuest: {room.guest_name}\nCheck-in: {self.check_in_datetime}\nCheck-out: {self.expected_check_out_datetime}",
                "qty": self.number_of_nights,
                "rate": room.rate_amount,
                "income_account": income_account
            })
        
        sales_invoice = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": self.customer,
            "posting_date": getdate(),
            "due_date": getdate(),
            "items": items,
            "discount_amount": self.discount_amount,
            "custom_corporate_check_in": self.name
        })
        
        sales_invoice.insert(ignore_permissions=True)
        sales_invoice.submit()
        
        frappe.msgprint(f"Sales Invoice {sales_invoice.name} created successfully")

@frappe.whitelist()
def get_available_rooms(check_in_datetime, expected_check_out_datetime, room_type=None):
    """Get list of available rooms for the given date range"""
    check_in_dt = get_datetime(check_in_datetime)
    check_out_dt = get_datetime(expected_check_out_datetime)
    
    # Build room type filter
    room_type_condition = ""
    if room_type:
        room_type_condition = f"AND hotel_room_type = '{room_type}'"
    
    # Get all vacant and clean rooms
    available_rooms = frappe.db.sql(f"""
        SELECT name, hotel_room_type, status, housekeeping_status
        FROM `tabHotel Room`
        WHERE status = 'Vacant'
        AND housekeeping_status = 'Clean'
        {room_type_condition}
    """, as_dict=True)
    
    # Filter out rooms with overlapping reservations or check-ins
    filtered_rooms = []
    for room in available_rooms:
        # Check reservations
        has_reservation = frappe.db.sql("""
            SELECT name 
            FROM `tabHotel Room Reservation`
            WHERE room_number = %s
            AND docstatus = 1
            AND status IN ('Confirmed', 'Booked')
            AND (
                (from_date <= %s AND to_date > %s)
                OR (from_date < %s AND to_date >= %s)
                OR (from_date >= %s AND to_date <= %s)
            )
            LIMIT 1
        """, (room.name, check_in_dt, check_in_dt, check_out_dt, check_out_dt, check_in_dt, check_out_dt))
        
        if has_reservation:
            continue
        
        # Check existing check-ins
        has_checkin = frappe.db.sql("""
            SELECT name 
            FROM `tabHotel Room Check In`
            WHERE room_number = %s
            AND docstatus = 1
            AND status = 'Checked In'
            AND (
                (check_in_datetime <= %s AND expected_check_out_datetime > %s)
                OR (check_in_datetime < %s AND expected_check_out_datetime >= %s)
                OR (check_in_datetime >= %s AND expected_check_out_datetime <= %s)
            )
            LIMIT 1
        """, (room.name, check_in_dt, check_in_dt, check_out_dt, check_out_dt, check_in_dt, check_out_dt))
        
        if not has_checkin:
            filtered_rooms.append(room)
    
    return filtered_rooms