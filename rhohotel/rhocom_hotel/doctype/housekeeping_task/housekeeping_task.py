# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HousekeepingTask(Document):
	pass
	
	def on_update(self):
		# Update room to clear if status is 'Completed'
		if self.status == "Completed":
			room = frappe.get_doc("Hotel Room", self.room)
			room.housekeeping_status = "Clean"
			room.save()
			frappe.publish_realtime('rhohotel_front_desk_update')

