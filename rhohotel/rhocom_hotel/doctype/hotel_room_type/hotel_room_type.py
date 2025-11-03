# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe.model.document import Document


class HotelRoomType(Document):
	pass

@frappe.whitelist()
def get_item_group_descendants(parent):
	from frappe.desk.treeview import get_descendants
	return get_descendants("Item Group", parent)
