# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document


class HousekeepingRequest(Document):
	def on_update(self):
		frappe.publish_realtime('rhohotel_front_desk_update')

