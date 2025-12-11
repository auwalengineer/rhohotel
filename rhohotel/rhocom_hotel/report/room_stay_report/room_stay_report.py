# Copyright (c) 2025, Rhocom and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	return [
		{
			"label": _("Room Number"),
			"fieldname": "room_number",
			"fieldtype": "Link",
			"options": "Hotel Room",
			"width": 120,
		},
		{"label": _("Guest Name"), "fieldname": "guest_name", "fieldtype": "Data", "width": 200},
		{"label": _("Check-in"), "fieldname": "check_in_datetime", "fieldtype": "Datetime", "width": 160},
		{
			"label": _("Expected Check-out"),
			"fieldname": "expected_check_out_datetime",
			"fieldtype": "Datetime",
			"width": 160,
		},
		
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{
			"label": _("Check In Record"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Hotel Room Check In",
			"width": 150,
		},
	]


def get_data(filters):
	conditions = " AND ci.docstatus < 2 "

	if filters.get("from_date") and filters.get("to_date"):
		conditions += """
			AND ci.check_in_datetime <= %(to_date)s
			AND ci.expected_check_out_datetime >= %(from_date)s
		"""

	return frappe.db.sql(
		"""
		SELECT
			ci.name,
			ci.room_number,
			ci.guest as guest_name,
			ci.check_in_datetime,
			ci.expected_check_out_datetime,
			ci.status
		FROM
			`tabHotel Room Check In` as ci
		WHERE 1=1
			{conditions}
		ORDER BY
			ci.room_number, ci.check_in_datetime
	""".format(
			conditions=conditions
		),
		filters,
		as_dict=1,
	)