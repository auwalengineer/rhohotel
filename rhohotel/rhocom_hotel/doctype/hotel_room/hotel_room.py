# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HotelRoom(Document):
	def validate(self):
		if not self.capacity:
			self.capacity, self.extra_bed_capacity = frappe.db.get_value('Hotel Room Type',
					self.hotel_room_type, ['capacity', 'extra_bed_capacity'])
		
		self.create_item()

	def on_update(self):
		# prevent changing current check in to none if the check in is already set and the status the Checked-In on Hotel room check in
		# if not self.current_check_in:
		# 	current_check_in = frappe.db.get_value('Hotel Room', self.name, 'current_check_in')
		# 	if current_check_in and not self.current_check_in:
		# 		frappe.throw("Cannot change current check-in to none while a check-in is active.")
		# prevent room from setting status to vacant if current check in is set
		if self.status == 'Vacant':
			current_check_in = frappe.db.get_value('Hotel Room', self.name, 'current_check_in')
			if current_check_in:
				frappe.throw("Cannot set room status to vacant while a check-in is active.")
    
		frappe.publish_realtime('rhohotel_front_desk_update')

	def after_insert(self):
		frappe.publish_realtime('rhohotel_front_desk_update')
	def create_item(self):

		#create ERPNEXT item if room.erpnext_item is not selected
		if not self.erpnext_item:
			# if item already exists with room name, link it
			item = frappe.db.get_value('Item', self.name)
			if item:
				self.erpnext_item = item
			else:
				new_item = frappe.new_doc('Item')
				new_item.item_code = self.name
				new_item.item_name = self.name
				new_item.item_group = self.room_type
				new_item.stock_uom = 'Nos'
				new_item.is_stock_item = 'No'
				new_item.insert()
				self.erpnext_item = new_item.name
				

		frappe.publish_realtime('rhohotel_front_desk_update')