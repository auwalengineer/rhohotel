# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from frappe.model.document import Document


class HotelRoomReservationItem(Document):

	def validate(self):
		self.validate_tariff()
		self.set_amount()
	
	def validate_tariff(self):
		"""Check if tariff exists for the combination"""
		if not frappe.db.exists('Hotel Room Tariff', {
			'room_type': self.room_type,
			'rate_type': self.rate_type,
			'season_type': self.season_type,
			'is_active': 1
		}):
			frappe.throw(f"No active tariff found for Room Type: {self.room_type}, Rate: {self.rate_type}, Season: {self.season_type}")

	def set_amount(self):
		"""Set amount based on tariff and quantity"""
		tariff = frappe.get_all(
			'Hotel Room Tariff',
			filters={
				'room_type': self.room_type,
				'rate_type': self.rate_type,
				'season_type': self.season_type,
				'is_active': 1
			},
			fields=['amount'],
			limit=1
		)
	
		if tariff:
			self.rate = tariff[0].amount
			self.amount = self.rate * self.qty
