import frappe
from frappe import _
from frappe.utils import nowdate, add_days, get_datetime

@frappe.whitelist()
def get_rooms(filters=None):
    """Get rooms with their current status, guest, and maintenance info"""
    conditions = []
    params = {}
    
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    if filters:
        if filters.get('floor'):
            conditions.append('r.floor = %(floor)s')
            params['floor'] = filters['floor']
            
        if filters.get('room_type'):
            conditions.append('r.hotel_room_type = %(room_type)s')
            params['room_type'] = filters['room_type']
            
        if filters.get('status'):
            conditions.append('r.status = %(status)s')
            params['status'] = filters['status']
            
        if filters.get('housekeeping_status'):
            conditions.append('r.housekeeping_status = %(housekeeping_status)s')
            params['housekeeping_status'] = filters['housekeeping_status']

    # Base query for rooms
    query = """
        SELECT 
            r.name,
            r.room_number,
            r.hotel_room_type,
            r.floor,
            f.floor_name,
            r.status,
            r.operational_status,
            r.housekeeping_status,
            r.current_key_card,
            ci.guest_name as current_guest,
            ci.name as check_in,
            ci.expected_check_out_datetime as expected_checkout,
            mr.name as maintenance_request,
            mr.description as maintenance_description
        FROM 
            `tabHotel Room` r
        LEFT JOIN
            `tabHotel Floor` f ON r.floor = f.name
        LEFT JOIN
            `tabHotel Room Check In` ci ON ci.room = r.name 
            AND ci.status = 'Checked In'
        LEFT JOIN
            `tabHotel Room Maintenance Request` mr ON mr.room = r.name 
            AND mr.status IN ('Open', 'In Progress')
    """
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
        
    if filters and filters.get('checkout_today'):
        checkout_condition = """
            AND DATE(ci.expected_check_out_datetime) = CURDATE()
        """
        query += checkout_condition

    query += ' ORDER BY r.room_number'
    
    rooms = frappe.db.sql(query, params, as_dict=1)
    
    # Add reservation info
    for room in rooms:
        if not room.current_guest:  # Only check reservations for vacant rooms
            reservation = frappe.db.sql("""
                SELECT 
                    r.guest_name,
                    r.from_date
                FROM 
                    `tabHotel Room Reservation` r
                INNER JOIN
                    `tabHotel Room Package` p ON p.hotel_room_type = %s
                WHERE 
                    r.docstatus = 1
                    AND r.status = 'Confirmed'
                    AND r.from_date <= %s
                    AND r.to_date >= %s
                ORDER BY r.from_date
                LIMIT 1
            """, (room.hotel_room_type, nowdate(), nowdate()), as_dict=1)
            
            if reservation:
                room.status = 'Reserved'
                room.upcoming_guest = reservation[0].guest_name
                room.check_in_date = reservation[0].from_date
    
    return rooms