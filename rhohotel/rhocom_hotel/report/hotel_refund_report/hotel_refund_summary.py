import frappe

def execute(filters=None):
	columns = [
		{"label": "Refund ID", "fieldname": "name", "fieldtype": "Link", "options": "Hotel Refund", "width": 120},
		{"label": "Guest", "fieldname": "guest", "fieldtype": "Link", "options": "Hotel Guest", "width": 150},
		{"label": "Check In", "fieldname": "check_in", "fieldtype": "Link", "options": "Hotel Room Check In", "width": 150},
		{"label": "Refund Amount", "fieldname": "refund_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Reasons", "fieldname": "reasons", "fieldtype": "Data", "width": 180},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Check Out", "fieldname": "check_out", "fieldtype": "Date", "width": 120},
		{"label": "Sales Invoice", "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 120}
	]

	data = frappe.get_all(
		"Hotel Refund",
		fields=[c["fieldname"] for c in columns],
		filters=filters or {},
		order_by="modified desc"
	)

	return columns, data
