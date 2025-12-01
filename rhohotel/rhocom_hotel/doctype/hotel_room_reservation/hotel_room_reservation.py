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
        number_of_nights = frappe.utils.date_diff(self.to_date, self.from_date)
        self.net_total = (number_of_nights * self.rate) - self.discount
        self.create_guest_if_not_exists()
        
    def create_guest_if_not_exists(self):
        """Create Hotel Guest if not exists"""
        if not frappe.db.exists("Hotel Guest", self.guest_name):
            guest = frappe.new_doc("Hotel Guest")
            guest.hotel_guest_name = self.guest_name
            guest.insert(ignore_permissions=True)
            guest.submit()

        
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
