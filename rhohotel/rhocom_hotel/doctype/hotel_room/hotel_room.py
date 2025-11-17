# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HotelRoom(Document):
	def validate(self):
		if not self.capacity:
			self.capacity, self.extra_bed_capacity = frappe.db.get_value('Hotel Room Type',
					self.hotel_room_type, ['capacity', 'extra_bed_capacity'])

	def on_update(self):
		frappe.publish_realtime('rhohotel_front_desk_update')

	def on_submit(self):

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
				self.save()

		frappe.publish_realtime('rhohotel_front_desk_update')