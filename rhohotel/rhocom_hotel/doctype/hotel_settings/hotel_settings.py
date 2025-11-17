# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HotelSettings(Document):
	pass


# API methods to get default check-in and check-out times
@frappe.whitelist()
def get_default_check_out_time():
	return frappe.get_single('Hotel Settings').default_check_out_time

@frappe.whitelist()
def get_default_check_in_time():
	return frappe.get_single('Hotel Settings').default_check_in_time	