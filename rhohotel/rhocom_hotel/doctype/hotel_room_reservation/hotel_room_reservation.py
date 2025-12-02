# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

class HotelRoomReservation(Document):
    def validate(self):
        self.validate_room_availability()
        number_of_nights = frappe.utils.date_diff(self.to_date, self.from_date)
        self.net_total = (number_of_nights * self.rate) - self.discount

    def before_insert(self):
        
        # reformat to_date time part to use default checkout time from hotel settings
        if self.to_date:
            hotel_settings = frappe.get_single("Hotel Settings")
            default_time_str = hotel_settings.default_check_out_time  # e.g. "12:00:00"

            if default_time_str:
                # Convert values
                to_dt = get_datetime(self.to_date)  # convert str → datetime
                default_time = datetime.strptime(default_time_str, "%H:%M:%S").time()

                # Replace time part safely
                self.to_date = datetime.combine(to_dt.date(), default_time)

        
        number_of_nights = frappe.utils.date_diff(self.to_date, self.from_date)
        self.net_total = (number_of_nights * self.rate) - self.discount
        self.create_guest_if_not_exists()

        
    # def create_guest_if_not_exists(self):
    #     """Create Hotel Guest if not exists"""
    #     if not frappe.db.exists("Hotel Guest", self.guest_name):
    #         guest = frappe.new_doc("Hotel Guest")
    #         guest.hotel_guest_name = self.guest_name
    #         guest.insert(ignore_permissions=True)
    #         guest.submit()
    
    def create_guest_if_not_exists(self):
        """Create Hotel Guest if not exists"""

        # If already exists by name, stop
        if frappe.db.exists("Hotel Guest", self.guest_name):
            return self.guest_name

        # Try create with phone number first
        try:
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": self.guest_name,
                "phone_number": "",
                "email": "",
                "gender":  "Male",
                "id_type": "Passport",
                "id_number":  "",
                "customer": self.customer,
                "guest_type":  "Individual"
            })

            guest.flags.ignore_permissions = True
            guest.insert()
            return guest.name

        except frappe.exceptions.InvalidPhoneNumberError:
            # Retry WITHOUT phone number
            guest = frappe.get_doc({
                "doctype": "Hotel Guest",
                "hotel_guest_name": self.guest_name,
                "phone_number": "",
                "email":  "",
                "gender":  "Male",
                "id_type": "Passport",
                "id_number": self.guest_id_number or "",
                "customer": self.customer,
                "guest_type": "Individual"
            })

            guest.flags.ignore_permissions = True
            guest.insert()

            # Now update phone manually after bypassing validation
            if self.guest_phone:
                frappe.db.set_value(
                    "Hotel Guest",
                    guest.name,
                    "phone_number",
                    self.guest_phone,
                    update_modified=False
                )

            return guest.name

    # def create_guest_if_not_exists(self):
    #     """Create Hotel Guest if not exists"""

    #     # If already exists by name, stop
    #     if frappe.db.exists("Hotel Guest", self.guest_name):
    #         return self.guest_name

    #     # Try create with phone number first
    #     try:
    #         guest = frappe.get_doc({
    #             "doctype": "Hotel Guest",
    #             "hotel_guest_name": self.guest_name,
    #             "phone_number": self.guest_phone or "",
    #             "email": self.guest_email or "",
    #             "gender": self.guest_gender or "Male",
    #             "id_type": self.guest_id_type or "Passport",
    #             "id_number": self.guest_id_number or "",
    #             "customer": self.customer,
    #             "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
    #         })

    #         guest.flags.ignore_permissions = True
    #         guest.insert()
    #         return guest.name

    #     except frappe.exceptions.InvalidPhoneNumberError:
    #         # Retry WITHOUT phone number
    #         guest = frappe.get_doc({
    #             "doctype": "Hotel Guest",
    #             "hotel_guest_name": self.guest_name,
    #             "phone_number": "",
    #             "email": self.guest_email or "",
    #             "gender": self.guest_gender or "Male",
    #             "id_type": self.guest_id_type or "Passport",
    #             "id_number": self.guest_id_number or "",
    #             "customer": self.customer,
    #             "guest_type": "Corporate" if self.reservation_type == "Corporate" else "Individual"
    #         })

    #         guest.flags.ignore_permissions = True
    #         guest.insert()

    #         # Now update phone manually after bypassing validation
    #         if self.guest_phone:
    #             frappe.db.set_value(
    #                 "Hotel Guest",
    #                 guest.name,
    #                 "phone_number",
    #                 self.guest_phone,
    #                 update_modified=False
    #             )

    #         return guest.name



    def validate_room_availability(self):
        """Validate if the room is available for the given period"""

        overlapping = frappe.db.sql("""
            SELECT name FROM `tabHotel Room Reservation`
            WHERE room_number = %s
            AND docstatus = 1 AND status != 'Cancelled' AND status != 'Completed'
            AND name != %s
            AND (
                from_date < %s  -- existing start < new end
                AND
                to_date > %s    -- existing end > new start
            )
        """, (
            self.room_number,
            self.name,
            self.to_date,
            self.from_date,
        ))

        if overlapping:
            frappe.throw(_("Room {0} is already booked between {1} and {2}.")
                        .format(self.room_number, self.from_date, self.to_date))

    
@frappe.whitelist()
def make_invoice(name):
    
    self = frappe.get_doc("Hotel Room Reservation", name)
    
    """ Make Sales Invoice for the  Hotel Room Reservation """
    
    guest = None

    # Check if guest exists
    if frappe.db.exists("Hotel Guest", self.guest_name):
        guest = frappe.get_doc("Hotel Guest", self.guest_name)
    else:
        # Create new guest
        guest = frappe.new_doc("Hotel Guest")
        guest.hotel_guest_name = self.guest_name
        guest.phone_number = ""
        guest.insert(ignore_permissions=True)
        guest.submit()
    
    customer = frappe.get_value("Hotel Guest", self.guest_name, "customer")
    if not customer:
        # create customer if not exists
        customer_doc = frappe.new_doc("Customer")
        customer_doc.customer_name = self.guest_name
        customer_doc.customer_type = "Individual"
        customer_doc.customer_group = frappe.get_cached_value('Selling Settings',  None,  'default_customer_group')
        customer_doc.territory = frappe.get_cached_value('Selling Settings',  None,  'default_territory')
        customer_doc.insert(ignore_permissions=True)
        customer = customer_doc.name
        frappe.db.set_value("Hotel Guest", self.guest_name, "customer", customer)
    
    room_doc = frappe.get_doc("Hotel Room", self.room_number)
    
    number_of_nights = frappe.utils.date_diff(self.to_date, self.from_date)
    
    si = frappe.new_doc("Sales Invoice")
    si.customer = customer
    # si.custom_hotel_room_check_in = self.name
    si.due_date = get_datetime(self.to_date).date()
    si.posting_date = datetime.now().date()	
    si.append("items", {
        "item_code": room_doc.erpnext_item,
        "rate": self.rate,
        "qty": number_of_nights,
        "amount": self.net_total,
        "description": _("Reservation charge for {0} from {1} to {2}").format(self.room_number, get_datetime(self.from_date).date(), get_datetime(self.to_date).date())
    })
    si.set_taxes()

    # set discount
    if self.discount:
        si.discount_amount = self.discount

    si.insert(ignore_permissions=True)
    si.submit()
    
    self.db_set("sales_invoice", si.name)

@frappe.whitelist()
def adjust_reservation(reservation_name, new_checkout, new_check_in):
    """
    Unified function for extending or reducing stay.
    Creates invoice (extension) or credit note (reduction) and logs adjustment in child table.
    """
    from frappe.utils import now_datetime, get_datetime, getdate, date_diff, flt
    
    doc = frappe.get_doc("Hotel Room Reservation", reservation_name)
    
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


# import json

# import frappe
# from frappe import _
# from frappe.model.document import Document
# from frappe.utils import add_days, date_diff, flt
# from frappe.utils import getdate


# class HotelRoomUnavailableError(frappe.ValidationError): pass
# class HotelRoomPricingNotSetError(frappe.ValidationError): pass


# 	def validate(self):
# 		self.total_rooms = {}
# 		self.set_rates()
# 		self.validate_availability()

# 	def on_update(self):
# 		frappe.publish_realtime('rhohotel_front_desk_update')

# 	def on_trash(self):
# 		frappe.publish_realtime('rhohotel_front_desk_update')

# 	def validate_availability(self):
# 		self.rooms_booked = {}
# 		for i in range(date_diff(self.to_date, self.from_date)):
# 			day = add_days(self.from_date, i)

# 			for d in self.items:
# 				if not d.item in self.rooms_booked:
# 					self.rooms_booked[d.item] = 0

# 				room_type = frappe.db.get_value("Hotel Room Package",
# 					d.item, 'hotel_room_type')
# 				rooms_booked = get_rooms_booked(room_type, day, exclude_reservation=self.name) \
# 					+ d.qty + self.rooms_booked.get(d.item)
# 				total_rooms = self.get_total_rooms(d.item)
# 				if total_rooms < rooms_booked:
# 					frappe.throw(_("Hotel Rooms of type {0} are unavailable on {1}").format(d.item,
# 						frappe.format(day, dict(fieldtype="Date"))), exc=HotelRoomUnavailableError)

# 				self.rooms_booked[d.item] += d.qty

# 	def get_total_rooms(self, item):
# 		if not item in self.total_rooms:
# 			self.total_rooms[item] = frappe.db.sql("""
# 				select count(*)
# 				from
# 					`tabHotel Room Package` package
# 				inner join
# 					`tabHotel Room` room on package.hotel_room_type = room.hotel_room_type
# 				where
# 					package.item = %s""", item)[0][0] or 0

# 		return self.total_rooms[item]

# 	def set_rates(self):
# 		self.net_total = 0
# 		self.grand_total = 0
# 		self.discount_amount = 0

# 		for d in self.items:
# 			# Use season period and duration for rate calculation
# 			season = frappe.get_doc("Hotel Season", d.season_type) if d.season_type else None
# 			tariff_filters = {
# 				'room_type': d.room_type,
# 				'rate_type': d.rate_type,
# 				'season_type': d.season_type or "",
# 				'is_active': 1
# 			}
# 			tariff = frappe.get_all('Hotel Room Tariff', filters=tariff_filters, fields=['rate_amount'], limit=1)
# 			if not tariff:
# 				frappe.throw(_(f"No active tariff found for Room Type: {d.room_type}, Rate: {d.rate_type}, Season: {d.season_type or 'Default'}"))
# 			d.rate = tariff[0].rate_amount
# 			d.amount = d.rate * flt(d.qty)
# 			self.net_total += d.amount

# 		self.apply_discount()
# 		self.grand_total = self.net_total - self.discount_amount

# 	def apply_discount(self):
# 		self.discount_amount = 0
# 		if not self.discount:
# 			return

# 		discount_doc = frappe.get_doc("Hotel Discount", self.discount)

# 		# Validate discount applicability
# 		if not discount_doc.is_active:
# 			frappe.throw(_("Selected discount '{0}' is not active.").format(self.discount))

# 		today = getdate()
# 		if (discount_doc.valid_from and getdate(self.from_date) < getdate(discount_doc.valid_from)) or \
# 		   (discount_doc.valid_to and getdate(self.to_date) > getdate(discount_doc.valid_to)):
# 			frappe.throw(_("Discount '{0}' is not valid for the selected reservation dates.").format(self.discount))

# 		if discount_doc.min_days_in_advance and date_diff(getdate(self.from_date), today) < discount_doc.min_days_in_advance:
# 			frappe.throw(_("To avail discount '{0}', booking must be made at least {1} days in advance.").format(self.discount, discount_doc.min_days_in_advance))

# 		if discount_doc.min_stay_duration and date_diff(self.to_date, self.from_date) < discount_doc.min_stay_duration:
# 			frappe.throw(_("To avail discount '{0}', minimum stay must be {1} nights.").format(self.discount, discount_doc.min_stay_duration))

# 		# Calculate discount
# 		if discount_doc.discount_type == "Percentage":
# 			self.discount_amount = self.net_total * (flt(discount_doc.discount_value) / 100)
# 		elif discount_doc.discount_type == "Fixed Amount":
# 			self.discount_amount = flt(discount_doc.discount_value)

# @frappe.whitelist()

# def get_room_rate(hotel_room_reservation):

# 	"""Calculate rate for each day as it may belong to different Hotel Room Pricing Item"""

# 	doc = frappe.get_doc(json.loads(hotel_room_reservation))

# 	doc.set_rates()

# 	return doc.as_dict()



# @frappe.whitelist()

# def extend_reservation(reservation_id, to_date):

#     original_reservation = frappe.get_doc("Hotel Room Reservation", reservation_id)



#     if not original_reservation.docstatus == 1:

#         frappe.throw(_("Only submitted reservations can be extended."))



#     new_reservation = frappe.copy_doc(original_reservation)

#     new_reservation.from_date = add_days(original_reservation.to_date, 1)

#     new_reservation.to_date = to_date

#     new_reservation.is_extension = 1

#     new_reservation.amended_from = original_reservation.name

#     new_reservation.insert()

#     new_reservation.submit()



#     return new_reservation



# def get_rooms_booked(room_type, day, exclude_reservation=None):

# 	exclude_condition = ''

# 	if exclude_reservation:

# 		exclude_condition = 'and reservation.name != {0}'.format(frappe.db.escape(exclude_reservation))



# 	return frappe.db.sql("""

# 		select sum(item.qty)

# 		from

# 			`tabHotel Room Package` room_package,

# 			`tabHotel Room Reservation Item` item,

# 			`tabHotel Room Reservation` reservation

# 		where

# 			item.parent = reservation.name

# 			and room_package.item = item.item

# 			and room_package.hotel_room_type = %s

# 			and reservation.docstatus = 1

# 			{exclude_condition}

# 			and %s between reservation.from_date

# 				and reservation.to_date""".format(exclude_condition=exclude_condition),

# 				(room_type, day))[0][0] or 0
