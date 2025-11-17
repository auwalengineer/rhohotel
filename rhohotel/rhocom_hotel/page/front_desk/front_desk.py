import frappe
import json
from frappe.utils import nowdate


@frappe.whitelist()
def get_checkins():
    return frappe.get_all(
        "Hotel Room Check In",
        fields=["name", "guest", "room_number", "check_in_datetime", "expected_check_out_datetime"],
        filters={"docstatus": 1},
        order_by="check_in_datetime desc"
    )


@frappe.whitelist()
def get_room_statistics():
    vacant = frappe.db.count("Hotel Room", {"status": "Vacant"})
    occupied = frappe.db.count("Hotel Room", {"status": "Occupied"})
    dirty = frappe.db.count("Hotel Room", {"housekeeping_status": "Dirty"})
    maintenance = frappe.db.count("Hotel Room", {"maintenance_flag": 1})

    today = nowdate()
    reserved_rooms = frappe.get_all(
        "Hotel Room Reservation",
        filters={
            "from_date": ("<=", today),
            "to_date": (">=", today),
            "status": ("not in", ["Cancelled", "Checked Out"]),
        },
        fields=["room_number"],
        distinct=True,
    )
    reserved = len(reserved_rooms)

    return {
        "vacant": vacant,
        "occupied": occupied,
        "dirty": dirty,
        "maintenance": maintenance,
        "reserved": reserved,
    }

@frappe.whitelist()
def get_rooms(filters=None):
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    else:
        filters = {}

    room_filters = {}
    if filters.get('floor'):
        room_filters['floor'] = filters.get('floor')
    if filters.get('room_type'):
        room_filters['room_type'] = filters.get('room_type')
    if filters.get('status'):
        room_filters['status'] = filters.get('status')
    if filters.get('housekeeping_status'):
        room_filters['housekeeping_status'] = filters.get('housekeeping_status')

    # Handle "Checking Out Today" filter
    if filters.get('checkout_today') and filters.get('today_date'):
        today = filters.get('today_date')
        check_ins_today = frappe.get_all(
            "Hotel Room Check In",
            filters={"expected_check_out_datetime": ["between", [f"{today} 00:00:00", f"{today} 23:59:59"]]},
            pluck="name"
        )
        if check_ins_today:
            room_filters['current_check_in'] = ["in", check_ins_today]
        else:
            # If no check-ins are for today, return no rooms
            return []

    rooms = frappe.get_all(
        "Hotel Room",
        fields=["name", "room_number", "room_type", "floor", "status", "housekeeping_status", "maintenance_flag", "current_check_in", "current_guest"],
        filters=room_filters,
        order_by="room_number"
    )

    # Fetch expected_check_out_datetime for all relevant check-ins in one query
    check_in_ids = [room.get("current_check_in") for room in rooms if room.get("current_check_in")]
    check_in_map = {}
    if check_in_ids:
        check_in_details = frappe.get_all("Hotel Room Check In", filters={"name": ["in", check_in_ids]}, fields=["name", "expected_check_out_datetime", "check_in_datetime"], as_list=1)
        check_in_map = {d[0]: {"expected_check_out": d[1], "check_in": d[2]} for d in check_in_details}

    # Build a clean list of room objects for the frontend
    result = []
    for room in rooms:
        room_obj = room.copy()
        check_in_info = check_in_map.get(room.current_check_in)
        if check_in_info:
            room_obj.expected_check_out_datetime = check_in_info.get("expected_check_out")
            room_obj.check_in_datetime = check_in_info.get("check_in")
        else:
            room_obj.expected_check_out_datetime = None
            room_obj.check_in_datetime = None
        result.append(room_obj)

    return result