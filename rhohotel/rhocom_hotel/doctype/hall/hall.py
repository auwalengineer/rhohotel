# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Hall(Document):
	pass

	def validate(self):
		# Create Item for the Hall if not exists
		if not frappe.db.exists("Item", self.hall_name):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_name": self.hall_name,
				"item_code": self.hall_name,
				"item_group": "Hall",
				"stock_uom": "Nos"
			})
			item.insert(ignore_permissions=True)
			self.item_name = item.name

	def onsave(self):
		# Create Item for the Hall if not exists
		if not frappe.db.exists("Item", self.item_name):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_name": self.item_name,
				"item_code": self.item_name,
				"item_group": "Hall",
				"stock_uom": "Nos"
			})
			item.insert(ignore_permissions=True)
			self.item_name = item.name
			self.save(ignore_permissions=True)
