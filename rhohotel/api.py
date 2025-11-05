from frappe import _
from frappe.utils import nowdate, add_days
from datetime import datetime
import json
from frappe.utils import get_request_header



def get_occupancy_rate():
    """Return current occupancy percentage."""
    return {'value': 82.5, 'suffix': '%'}

def get_room_revenue():
    """Return chart data for last 7 days revenue."""
    return {
        'labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'datasets': [{'name': 'Revenue', 'values': [1200, 1500, 1800, 2000, 2200, 1950, 2500]}]
    }

def get_average_stay_length():
    """Return average stay length in days."""
    return {'value': 3.2, 'suffix': ' days'}

def get_maintenance_status_summary():
    """Return summary of hotel room maintenance statuses."""
    return {
        'labels': ['Active', 'Out of Order', 'Under Maintenance'],
        'datasets': [{'name': 'Room Status', 'values': [150, 5, 10]}]
    }

def get_occupancy_history():
    """Return occupancy history for the last 30 days."""
    labels = [add_days(nowdate(), -i) for i in range(30)][::-1]
    return {
        'labels': labels,
        'datasets': [{'name': 'Occupancy', 'values': [75, 78, 80, 82, 85, 88, 90, 85, 82, 80, 78, 75, 70, 72, 75, 80, 82, 85, 88, 90, 92, 95, 98, 100, 98, 95, 92, 90, 88, 85]}]
    }

def get_average_rate_per_room_type():
    """Return average rate per room type."""
    return {
        'labels': ['Standard', 'Deluxe', 'Suite'],
        'datasets': [{'name': 'Average Rate', 'values': [100, 150, 250]}]
    }

def get_active_rooms_count():
    """Return number of active rooms per type."""
    return {
        'labels': ['Standard', 'Deluxe', 'Suite'],
        'datasets': [{'name': 'Active Rooms', 'values': [80, 50, 20]}]
    }

def get_total_nights_stayed():
    """Return total nights stayed by a guest."""
    # This would typically be guest-specific, but for a general dashboard,
    # we can show an aggregation or a sample.
    return {'value': 25}

def get_guest_lifetime_value():
    """Return lifetime value of a guest."""
    return {'value': 5500, 'prefix': '$'}


@frappe.whitelist()
def get_active_checkin_for_room(room_number):
    checkin = frappe.db.get_value(
        "Hotel Room Check In",
        {"room_number": room_number, "status": "Checked In"},
        ["name", "guest"],
        as_dict=True
    )
    return checkin

@frappe.whitelist()
def get_room_rate(room_type, rate_type, check_in_date):
    try:
        # Determine the season
        season = frappe.db.get_value("Hotel Season", {
            "start_date": ("<=", check_in_date),
            "end_date": (">=", check_in_date),
            "is_active": 1
        }, "name")

        if not season:
            return {"error": "No active season found for the selected date."}

        # Determine the day type (Weekday/Weekend)
        day_of_week = datetime.strptime(check_in_date, "%Y-%m-%d").weekday()
        day_type = "Weekend" if day_of_week >= 5 else "Weekday" # 5: Saturday, 6: Sunday

        # Fetch the room rate
        rate_amount = frappe.db.get_value("Hotel Room Tariff", {
            "room_type": room_type,
            "rate_type": rate_type,
            "season": season,
            "day_type": day_type,
            "is_active": 1
        }, "rate_amount")

        return rate_amount or 0

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error fetching room rate")
        return {"error": str(e)}


