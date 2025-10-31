import frappe


def add_checkin_room_fields():
	"""Patch to add custom fields used by check-in/checkout and front desk dashboard.
	Run with: bench --site <site> migrate (patch should be referenced in patches.txt)
	"""
	fields = [
		# Hotel Room fields
		{
			"dt": "Hotel Room",
			"fieldname": "floor",
			"label": "Floor",
			"fieldtype": "Link",
			"options": "Hotel Floor",
			"insert_after": "extra_bed_capacity"
		},
		{
			"dt": "Hotel Room",
			"fieldname": "room_status",
			"label": "Room Status",
			"fieldtype": "Select",
			"options": "Vacant\nOccupied\nReserved\nNon Operational",
			"insert_after": "power_code"
		},
		{
			"dt": "Hotel Room",
			"fieldname": "maintenance_flag",
			"label": "Maintenance Required",
			"fieldtype": "Check",
			"insert_after": "room_status"
		},
		{
			"dt": "Hotel Room",
			"fieldname": "last_keycard_user",
			"label": "Last Keycard User",
			"fieldtype": "Data",
			"insert_after": "maintenance_flag"
		},
		{
			"dt": "Hotel Room",
			"fieldname": "last_keycard_time",
			"label": "Last Keycard Time",
			"fieldtype": "Datetime",
			"insert_after": "last_keycard_user"
		},
		{
			"dt": "Hotel Room",
			"fieldname": "current_check_in",
			"label": "Current Check In",
			"fieldtype": "Link",
			"options": "Hotel Room Check In",
			"insert_after": "last_keycard_time"
		},
		# Hotel Room Check In fields
		{
			"dt": "Hotel Room Check In",
			"fieldname": "actual_check_out_datetime",
			"label": "Actual Check-out Time",
			"fieldtype": "Datetime",
			"insert_after": "expected_check_out_datetime"
		},
		{
			"dt": "Hotel Room Check In",
			"fieldname": "total_charges",
			"label": "Total Charges",
			"fieldtype": "Currency",
			"insert_after": "actual_check_out_datetime"
		},
		{
			"dt": "Hotel Room Check In",
			"fieldname": "payment_status",
			"label": "Payment Status",
			"fieldtype": "Select",
			"options": "Pending\nPaid\nPartially Paid",
			"insert_after": "total_charges"
		},
		{
			"dt": "Hotel Room Check In",
			"fieldname": "reservation_source",
			"label": "Reservation Source",
			"fieldtype": "Select",
			"options": "Local\nOnline\nOTA",
			"insert_after": "reservation"
		},
		{
			"dt": "Hotel Room Check In",
			"fieldname": "special_requests",
			"label": "Special Requests",
			"fieldtype": "Text",
			"insert_after": "reservation_source"
		},
		{
			"dt": "Hotel Room Check In",
			"fieldname": "keycard_assigned",
			"label": "Keycard Assigned",
			"fieldtype": "Data",
			"insert_after": "room"
		},
		{
			"dt": "Hotel Room Check In",
			"fieldname": "housekeeping_notes",
			"label": "Housekeeping Notes",
			"fieldtype": "Text",
			"insert_after": "special_requests"
		}
	]

	for f in fields:
		dt = f.pop("dt")
		fieldname = f.get("fieldname")
		exists = frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname})
		if exists:
			frappe.log("Custom Field exists: %s.%s" % (dt, fieldname))
			continue
		cf = frappe.get_doc({
			"doctype": "Custom Field",
			"dt": dt,
			"label": f.get("label"),
			"fieldname": fieldname,
			"fieldtype": f.get("fieldtype"),
			"insert_after": f.get("insert_after"),
			"options": f.get("options") if f.get("options") else None
		})
		cf.insert()
		frappe.db.commit()
		frappe.msgprint("Added custom field: %s.%s" % (dt, fieldname))

	# Rebuild schema if needed
	frappe.clear_cache()
	return
