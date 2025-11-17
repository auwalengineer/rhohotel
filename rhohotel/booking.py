import frappe
from frappe.utils import nowdate, add_days, cstr, get_datetime
from datetime import datetime, timedelta
import json
from decimal import Decimal

_ = frappe._

# ============================================================================
# ROOM AVAILABILITY & SEARCH ENDPOINTS
# ============================================================================

@frappe.whitelist(allow_guest=True)
def search_available_rooms(check_in_date, check_out_date, num_rooms=1, adults=1, children=0):
    """
    Search for available rooms based on guest requirements.
    
    Args:
        check_in_date (str): Check-in date (YYYY-MM-DD)
        check_out_date (str): Check-out date (YYYY-MM-DD)
        num_rooms (int): Number of rooms needed
        adults (int): Number of adults
        children (int): Number of children
    
    Returns:
        dict: Available rooms grouped by room type with pricing
    """
    try:
        # Validate dates
        checkin = datetime.strptime(check_in_date, "%Y-%m-%d").date()
        checkout = datetime.strptime(check_out_date, "%Y-%m-%d").date()
        
        if checkin >= checkout:
            frappe.throw(_("Check-out date must be after check-in date"))
        
        if checkin < datetime.now().date():
            frappe.throw(_("Check-in date cannot be in the past"))
        
        num_rooms = int(num_rooms)
        adults = int(adults)
        children = int(children)
        
        if num_rooms < 1 or adults < 1:
            frappe.throw(_("Invalid number of rooms or guests"))
        
        # Get all active room types
        room_types = frappe.get_all("Hotel Room Type", filters={"is_active": 1}, fields=["name", "capacity", "extra_bed_capacity"])
        
        if not room_types:
            return {"available_rooms": [], "message": "No room types available"}
        
        available_rooms = {}
        
        for room_type in room_types:
            # Check if room type can accommodate guests
            total_capacity = room_type.get("capacity", 0) + room_type.get("extra_bed_capacity", 0)
            if total_capacity < adults:
                continue
            
            # Find available rooms of this type for the entire stay
            available_room_count = get_available_room_count(
                room_type.get("name"),
                check_in_date,
                check_out_date
            )
            
            if available_room_count >= num_rooms:
                # Calculate pricing for the stay
                pricing_info = calculate_stay_pricing(
                    room_type.get("name"),
                    check_in_date,
                    check_out_date,
                    adults,
                    children
                )
                
                available_rooms[room_type.get("name")] = {
                    "room_type": room_type.get("name"),
                    "available_count": available_room_count,
                    "requested_count": num_rooms,
                    "capacity": room_type.get("capacity"),
                    "extra_bed_capacity": room_type.get("extra_bed_capacity"),
                    "base_rate": pricing_info.get("base_rate"),
                    "pricing_breakdown": pricing_info.get("pricing_breakdown"),
                    "total_price": pricing_info.get("total_price"),
                    "price_per_night": pricing_info.get("price_per_night"),
                    "number_of_nights": pricing_info.get("number_of_nights"),
                    "extra_adult_charges": pricing_info.get("extra_adult_charges", 0),
                    "extra_child_charges": pricing_info.get("extra_child_charges", 0)
                }
        
        return {
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "number_of_nights": (checkout - checkin).days,
            "adults": adults,
            "children": children,
            "rooms_requested": num_rooms,
            "available_rooms": available_rooms,
            "total_results": len(available_rooms)
        }
    
    except ValueError as e:
        frappe.throw(_("Invalid date format. Use YYYY-MM-DD"))
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Search Available Rooms Error")
        frappe.throw(_("Error searching rooms: {0}").format(str(e)))


def get_available_room_count(room_type, check_in_date, check_out_date):
    """
    Get the count of available rooms for a given room type during a date range.
    A room is available if it's not booked or checked-in during this period.
    """
    try:
        # Total rooms of this type
        total_rooms = frappe.db.count(
            "Hotel Room",
            filters={"room_type": room_type, "status": ["!=", "Maintenance"]}
        )
        
        # Booked/checked-in rooms during this period
        booked_rooms = frappe.db.count(
            "Hotel Room Check In",
            filters={
                "room_type": room_type,
                "status": "Checked In",
                "from_date": ["<", check_out_date],
                "to_date": [">", check_in_date]
            }
        )
        
        # Reserved rooms during this period
        reserved_rooms = frappe.db.count(
            "Hotel Room Reservation",
            filters={
                "status": ["not in", ["Cancelled", "Completed"]],
                "from_date": ["<", check_out_date],
                "to_date": [">", check_in_date]
            }
        )
        
        available = total_rooms - booked_rooms - reserved_rooms
        return max(0, available)
    
    except Exception as e:
        frappe.log_error(f"Error calculating available rooms: {str(e)}", "Room Availability")
        return 0


def calculate_stay_pricing(room_type, check_in_date, check_out_date, adults, children):
    """
    Calculate total pricing for a stay including extra adults/children charges.
    """
    try:
        checkin = datetime.strptime(check_in_date, "%Y-%m-%d").date()
        checkout = datetime.strptime(check_out_date, "%Y-%m-%d").date()
        num_nights = (checkout - checkin).days
        
        pricing_breakdown = []
        total_price = Decimal("0")
        nightly_total = Decimal("0")
        extra_adult_charges = Decimal("0")
        extra_child_charges = Decimal("0")
        
        # Room type capacity
        room_type_doc = frappe.get_doc("Hotel Room Type", room_type)
        base_capacity = room_type_doc.capacity if hasattr(room_type_doc, 'capacity') else 2
        
        # Calculate price for each night
        for i in range(num_nights):
            night_date = checkin + timedelta(days=i)
            night_rate = get_room_rate(room_type, "", night_date.strftime("%Y-%m-%d"))
            nightly_total = Decimal(str(night_rate or 0))
            total_price += nightly_total
            
            pricing_breakdown.append({
                "date": night_date.strftime("%Y-%m-%d"),
                "rate": float(nightly_total)
            })
        
        # Calculate extra charges if guests exceed base capacity
        if adults > base_capacity:
            extra_adults = adults - base_capacity
            tariff = frappe.db.get_value(
                "Hotel Room Tariff",
                {"room_type": room_type, "is_active": 1},
                "extra_adult_amount"
            )
            extra_adult_rate = Decimal(str(tariff or 0))
            extra_adult_charges = extra_adult_rate * extra_adults * num_nights
            total_price += extra_adult_charges
        
        if children > 0:
            tariff = frappe.db.get_value(
                "Hotel Room Tariff",
                {"room_type": room_type, "is_active": 1},
                "extra_child_amount"
            )
            extra_child_rate = Decimal(str(tariff or 0))
            extra_child_charges = extra_child_rate * children * num_nights
            total_price += extra_child_charges
        
        return {
            "base_rate": float(nightly_total),
            "number_of_nights": num_nights,
            "price_per_night": float(nightly_total),
            "pricing_breakdown": pricing_breakdown,
            "extra_adult_charges": float(extra_adult_charges),
            "extra_child_charges": float(extra_child_charges),
            "total_price": float(total_price)
        }
    
    except Exception as e:
        frappe.log_error(f"Error calculating pricing: {str(e)}", "Pricing Calculation")
        return {
            "base_rate": 0,
            "number_of_nights": 0,
            "price_per_night": 0,
            "pricing_breakdown": [],
            "extra_adult_charges": 0,
            "extra_child_charges": 0,
            "total_price": 0
        }


# ============================================================================
# ROOM DETAILS & AMENITIES
# ============================================================================

@frappe.whitelist(allow_guest=True)
def get_room_type_details(room_type_name):
    """Get detailed information about a room type including amenities and images."""
    try:
        room_type = frappe.get_doc("Hotel Room Type", room_type_name)
        
        amenities = []
        if hasattr(room_type, 'amenities') and room_type.amenities:
            amenities = [{"name": item.amenity, "description": item.get("description", "")} 
                        for item in room_type.amenities]
        
        images = []
        if hasattr(room_type, 'room_images') and room_type.room_images:
            images = [{"image": item.image, "caption": item.get("caption", "")} 
                     for item in room_type.room_images]
        
        return {
            "name": room_type.name,
            "description": room_type.get("description", ""),
            "capacity": room_type.get("capacity", 2),
            "extra_bed_capacity": room_type.get("extra_bed_capacity", 0),
            "amenities": amenities,
            "images": images
        }
    
    except Exception as e:
        frappe.log_error(f"Error fetching room type details: {str(e)}", "Room Type Details")
        frappe.throw(_("Room type not found"))


@frappe.whitelist(allow_guest=True)
def get_room_images(room_type_name):
    """Get all images for a specific room type."""
    try:
        room_type = frappe.get_doc("Hotel Room Type", room_type_name)
        
        images = []
        if hasattr(room_type, 'room_images') and room_type.room_images:
            for img in room_type.room_images:
                images.append({
                    "image_url": img.image,
                    "caption": img.get("caption", "")
                })
        
        return {"room_type": room_type_name, "images": images}
    
    except Exception as e:
        frappe.throw(_("Error fetching room images"))