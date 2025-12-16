# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HallService(Document):
	pass

	def validate(self):
		# create Item if not exists
		if not self.item_name:
			self.create_item_if_not_exists()
	def create_item_if_not_exists(self):
		#create Hall Service Item group if not exists
		item_group = None
		if not frappe.db.exists("Item Group", "Hall Service"):
			item_group = frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": "Hall Service",
			})
			item_group.insert(ignore_permissions=True)
			frappe.db.commit()
		else:
			item_group = frappe.get_doc("Item Group", "Hall Service")
		# create Item if not exists
		if not frappe.db.exists("Item", self.service):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": self.service,
				"item_name": self.service,
				"item_group": item_group.name,
				"is_stock_item": 0,
				"standard_rate": self.rate,
			})
			item.insert(ignore_permissions=True)
			self.item_name = item.name
			frappe.db.commit()
		else:
			item = frappe.get_doc("Item", self.service)
			self.item_name = item.name
			frappe.db.commit()


@frappe.whitelist()
def get_service_rate(hall_service):
	service = frappe.get_doc("Hall Service", hall_service)
	return service.rate
