import frappe
import json
from frappe.utils import nowdate

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
        room_filters['hotel_room_type'] = filters.get('room_type')
    if filters.get('status'):
        room_filters['status'] = filters.get('status')
    if filters.get('housekeeping_status'):
        room_filters['housekeeping_status'] = filters.get('housekeeping_status')

    rooms = frappe.get_all(
        "Hotel Room",
        fields=["name", "room_number", "hotel_room_type", "floor", "status", "housekeeping_status", "maintenance_flag", "current_check_in"],
        filters=room_filters,
        order_by="room_number"
    )

    return rooms