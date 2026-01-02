# Copyright (c) 2024, Rhocom and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RestaurantOrder(Document):
	def before_save(self):
		self.calculate_total()

	def calculate_total(self):
		total = 0
		for item in self.items:
			item.amount = item.quantity * item.rate
			total += item.amount
		self.total_amount = total

