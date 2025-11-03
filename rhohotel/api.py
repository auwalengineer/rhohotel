from frappe import _
from frappe.utils import nowdate, add_days

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