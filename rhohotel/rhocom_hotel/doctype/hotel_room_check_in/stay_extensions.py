# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters=None):
	columns, data = [], []

	columns = get_columns()
	data = get_data(filters)

	return columns, data

def get_columns():
	return [
		{"label": _("Check In"), "fieldname": "check_in", "fieldtype": "Link", "options": "Hotel Room Check In", "width": 180},
		{"label": _("Guest"), "fieldname": "guest", "fieldtype": "Link", "options": "Hotel Guest", "width": 180},
		{"label": _("Room"), "fieldname": "room_number", "fieldtype": "Link", "options": "Hotel Room", "width": 120},
		{"label": _("Extension Date"), "fieldname": "extension_date", "fieldtype": "Datetime", "width": 160},
		{"label": _("Previous Checkout"), "fieldname": "previous_checkout_date", "fieldtype": "Datetime", "width": 160},
		{"label": _("New Checkout"), "fieldname": "new_checkout_date", "fieldtype": "Datetime", "width": 160},
		{"label": _("Nights Extended"), "fieldname": "number_of_nights", "fieldtype": "Int", "width": 120},
		{"label": _("Extension Invoice"), "fieldname": "extension_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
	]

def get_data(filters):
	conditions = ""
	if filters.get("from_date"):
		conditions += " AND ext.extension_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND ext.extension_date <= %(to_date)s"

	sql = """
		SELECT
			ext.parent AS check_in,
			ci.guest,
			ci.room_number,
			ext.extension_date,
			ext.previous_checkout_date,
			ext.new_checkout_date,
			ext.number_of_nights,
			ext.extension_invoice,
			ext.amount
		FROM `tabHotel Stay Extension` AS ext
		JOIN `tabHotel Room Check In` AS ci ON ext.parent = ci.name
		WHERE 1=1 {conditions}
		ORDER BY ext.extension_date DESC
	""".format(conditions=conditions)

	return frappe.db.sql(sql, filters, as_dict=1)