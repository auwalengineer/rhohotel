import frappe
from frappe import _
from frappe.utils import formatdate

def execute(filters=None):
	filters = filters or {}

	columns = [
		{"label": _("Guest"), "fieldname": "guest", "fieldtype": "Link", "options": "Hotel Guest", "width": 150},
		{"label": _("Room"), "fieldname": "room_number", "fieldtype": "Link", "options": "Hotel Room", "width": 120},
		{"label": _("Check-in Date"), "fieldname": "check_in_datetime", "fieldtype": "Datetime", "width": 160},
		{"label": _("Expected Check-out"), "fieldname": "expected_check_out_datetime", "fieldtype": "Datetime", "width": 160},
		{"label": _("Actual Check-out"), "fieldname": "actual_check_out_datetime", "fieldtype": "Datetime", "width": 160},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Data", "width": 200},
		{"label": _("Payments"), "fieldname": "payments", "fieldtype": "Data", "width": 200},
	]

	conditions = []
	if filters.get("guest"):
		conditions.append("hrc.guest = %(guest)s")
	if filters.get("room_number"):
		conditions.append("hrc.room_number = %(room_number)s")

	where_clause = "WHERE hrc.docstatus = 1"
	if conditions:
		where_clause += " AND " + " AND ".join(conditions)

	data = frappe.db.sql(f"""
		SELECT
			hrc.name AS checkin_id,
			hrc.guest,
			hrc.room_number,
			hrc.check_in_datetime,
			hrc.expected_check_out_datetime,
			hrc.actual_check_out_datetime,
			IFNULL(GROUP_CONCAT(DISTINCT inv.sales_invoice SEPARATOR ', '), '-') AS invoices,
			IFNULL(GROUP_CONCAT(DISTINCT pay.name SEPARATOR ', '), '-') AS payments
		FROM `tabHotel Room Check In` hrc
		LEFT JOIN `tabHotel Room Check In Invoice` inv ON inv.parent = hrc.name
		LEFT JOIN `tabPayment Entry Reference` pref ON pref.reference_name = hrc.name
		LEFT JOIN `tabPayment Entry` pay ON pay.name = pref.parent
		{where_clause}
		GROUP BY hrc.name
		ORDER BY hrc.check_in_datetime DESC
	""", filters, as_dict=True)

	return columns, data
