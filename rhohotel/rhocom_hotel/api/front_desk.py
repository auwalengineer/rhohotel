import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date

@frappe.whitelist()
def get_rooms_summary(filters=None):
	"""Return list of rooms with status, maintenance, current_check_in info and reservation/check-out times.
	filters (json string) can include: floor, room_type, status, maintenance, upcoming_checkout_hours
	"""
	import json
	filters = json.loads(filters) if filters else {}
	conds = ["1=1"]
	args = []
	if filters.get("floor"):
		conds.append("room.floor = %s")
		args.append(filters.get("floor"))
	if filters.get("room_type"):
		conds.append("room.hotel_room_type = %s")
		args.append(filters.get("room_type"))
	if filters.get("status"):
		conds.append("room.room_status = %s")
		args.append(filters.get("status"))
	if filters.get("maintenance"):
		conds.append("room.maintenance_flag = 1")
	if filters.get("housekeeper_present"):
		conds.append("room.last_keycard_user IS NOT NULL")

	# upcoming checkout window
	upcoming_hours = filters.get("upcoming_checkout_hours")
	if upcoming_hours:
		end = add_to_date(now_datetime(), hours=upcoming_hours)
		conds.append("(ci.expected_check_out_datetime between %s and %s)")
		args.extend([now_datetime(), end])

	query = f"""
		select
			room.name as room,
			room.hotel_room_type as room_type,
			room.floor as floor,
			room.room_status as status,
			room.maintenance_flag as maintenance,
			room.last_keycard_user as last_keycard_user,
			room.last_keycard_time as last_keycard_time,
			room.current_check_in as current_check_in,
			ci.guest_name as guest_name,
			ci.expected_check_out_datetime as expected_check_out_datetime,
			r.name as reservation,
			r.reservation_source as reservation_source
		from
			`tabHotel Room` room
		left join
			`tabHotel Room Check In` ci on ci.name = room.current_check_in
		left join
			`tabHotel Room Reservation` r on r.name = ci.reservation
		where {' AND '.join(conds)}
		order by room.floor, room.name
	"""
	rows = frappe.db.sql(query, tuple(args), as_dict=1)
	return rows

@frappe.whitelist()
def make_check_out(checkin_name):
	"""Perform checkout for the given Hotel Room Check In docname.
	Sets actual_check_out_datetime, status and frees up the room.
	"""
	ci = frappe.get_doc("Hotel Room Check In", checkin_name)
	if ci.status == "Checked Out":
		frappe.throw(_("Check-in {0} already checked out").format(checkin_name))
	ci.actual_check_out_datetime = now_datetime()
	ci.status = "Checked Out"
	# placeholder: calculate extra charges here if required
	if not ci.total_charges:
		ci.total_charges = 0.0
	ci.save()

	# update linked room
	if ci.room:
		room = frappe.get_doc("Hotel Room", ci.room)
		room.room_status = "Vacant"
		room.current_check_in = None
		room.save()

	# optionally submit the checkin doc if submittable
	if ci.docstatus == 0 and ci.meta.is_submittable:
		ci.submit()

	return {"success": True, "checkin": ci.name}
