"""
Hotel Booking - Shared Utilities Module
Common functions used by both search_available_rooms and booking operations

Location: rhohotel/rhohotel/shared_utilities.py
"""

import frappe
from datetime import datetime, timedelta
import secrets


# ════════════════════════════════════════════════════════════════════════════
# DATE & TIME UTILITIES
# ════════════════════════════════════════════════════════════════════════════


def parse_date(date_input, date_name="date"):
	"""
	Parse date input (string or date object) to both string and date formats.

	Args:
	    date_input: String (YYYY-MM-DD) or date object
	    date_name: Name for error messages

	Returns:
	    tuple: (date_string, date_object) or raises ValidationError
	"""
	try:
		if isinstance(date_input, str):
			date_str = date_input
			try:
				date_obj = datetime.strptime(date_input, "%Y-%m-%d").date()
			except ValueError:
				raise frappe.ValidationError(f"Invalid {date_name} format. Use YYYY-MM-DD")
		else:
			date_obj = date_input
			date_str = date_input.strftime("%Y-%m-%d")

		return date_str, date_obj
	except frappe.ValidationError:
		raise
	except Exception as e:
		raise frappe.ValidationError(f"Error parsing {date_name}: {str(e)}")


def validate_date_range(check_in_date, check_out_date):
	"""
	Validate check-in and check-out dates.

	Args:
	    check_in_date (date): Check-in date
	    check_out_date (date): Check-out date

	Returns:
	    int: Number of nights
	"""
	from frappe.utils import getdate

	today = getdate()

	if check_in_date < today:
		raise frappe.ValidationError("Check-in date cannot be in the past")

	if check_in_date >= check_out_date:
		raise frappe.ValidationError("Check-out date must be after check-in date")

	num_nights = (check_out_date - check_in_date).days

	if num_nights < 1:
		raise frappe.ValidationError("Minimum stay is 1 night")

	if num_nights > 365:
		raise frappe.ValidationError("Maximum stay is 365 days")

	max_future_date = today + timedelta(days=730)
	if check_out_date > max_future_date:
		raise frappe.ValidationError("Bookings not available beyond 2 years")

	return num_nights


# ════════════════════════════════════════════════════════════════════════════
# TARIFF & PRICING UTILITIES
# ════════════════════════════════════════════════════════════════════════════


def get_room_rate(room_type, rate_type=None, check_in_date=None):
	"""
	Get the applicable rate for a room type on a specific date.
	Determines if date is weekend or weekday and gets corresponding rate.

	Args:
	    room_type (str): Room type name
	    rate_type (str): Rate type (optional, currently unused)
	    check_in_date (str): Date to check (YYYY-MM-DD format)

	Returns:
	    float: Rate amount or 0 if not found
	"""
	try:
		# --- Convert and determine the day type ---
		day_of_week = datetime.strptime(check_in_date, "%Y-%m-%d").weekday()
		day_type = "Weekend" if day_of_week >= 5 else "Weekday"

		# --- Base filters ---
		base_filters = {"room_type": room_type, "is_active": 1}

		# --- 1. Try exact match: room type + day type ---
		rate_amount = frappe.db.get_value(
			"Hotel Room Tariff", {**base_filters, "day_type": day_type}, "rate_amount"
		)

		# --- 2. If not found, try fallback: room type only ---
		if not rate_amount:
			rate_amount = frappe.db.get_value("Hotel Room Tariff", base_filters, "rate_amount")

		# --- Final return ---
		return rate_amount or 0

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error fetching room rate")
		return 0


def get_day_type(check_date):
	"""
	Get the day type (Weekend/Weekday) for a given date.

	Args:
	    check_date (str or date): Date to check

	Returns:
	    str: "Weekend" or "Weekday"
	"""
	try:
		if isinstance(check_date, str):
			date_obj = datetime.strptime(check_date, "%Y-%m-%d").date()
		else:
			date_obj = check_date

		day_of_week = date_obj.weekday()
		# Friday(4), Saturday(5), Sunday(6) - but we're using >= 5 for Sat/Sun
		return "Weekend" if day_of_week >= 5 else "Weekday"

	except Exception as e:
		frappe.log_error(f"Error getting day type: {str(e)}")
		return "Weekday"


def get_pricing_breakdown(room_type, check_in_date, check_out_date, base_rate):
	"""
	Get daily pricing breakdown for a room type across stay duration.
	Shows rate for each night (weekday/weekend differentiation).

	Args:
	    room_type (str): Room type name
	    check_in_date (str or date): Check-in date
	    check_out_date (str or date): Check-out date
	    base_rate (float): Base rate for fallback

	Returns:
	    list: Daily breakdown [{date, day_type, rate}, ...]
	"""
	try:
		check_in_str, check_in = parse_date(check_in_date, "check_in_date")
		check_out_str, check_out = parse_date(check_out_date, "check_out_date")

		breakdown = []
		current_date = check_in

		while current_date < check_out:
			current_date_str = current_date.strftime("%Y-%m-%d")

			# Get rate for this specific date
			rate = get_room_rate(room_type, check_in_date=current_date_str)
			if not rate or rate == 0:
				rate = base_rate

			# Get day type
			day_type = get_day_type(current_date)

			breakdown.append({"date": current_date_str, "day_type": day_type, "rate": float(rate)})

			current_date += timedelta(days=1)

		return breakdown

	except Exception as e:
		frappe.log_error(f"Error in pricing breakdown: {str(e)}")
		return []


def calculate_room_price(room_type, check_in_date, num_nights, room_capacity, adults, children):
	"""
	Calculate total price for a room including extra bed charges.

	Args:
	    room_type (str): Room type name
	    check_in_date (str or date): Check-in date (for tariff lookup)
	    num_nights (int): Number of nights
	    room_capacity (int): Standard capacity
	    adults (int): Number of adults
	    children (int): Number of children

	Returns:
	    dict: {
	        "base_rate": float,
	        "price_per_night": float,
	        "total_price": float,
	        "extra_charges": float,
	        "breakdown": list
	    }
	"""
	try:
		# Parse check_in_date to string format
		if isinstance(check_in_date, str):
			check_in_str = check_in_date
		else:
			check_in_str = check_in_date.strftime("%Y-%m-%d")

		# Get rate for check-in date
		rate_amount = get_room_rate(room_type, check_in_date=check_in_str)
		if not rate_amount or rate_amount == 0:
			return None

		base_rate = float(rate_amount)
		price_per_night = base_rate

		# Calculate extra bed charges
		extra_guests = (adults - room_capacity) + children
		extra_charges = 0

		if extra_guests > 0:
			# Extra bed is 20% of base rate per night
			extra_charges = (base_rate * 0.2) * num_nights

		total_price = (price_per_night * num_nights) + extra_charges

		# Calculate checkout date for breakdown
		check_in_date_obj = datetime.strptime(check_in_str, "%Y-%m-%d").date()
		check_out_date_obj = check_in_date_obj + timedelta(days=num_nights)

		return {
			"base_rate": base_rate,
			"price_per_night": price_per_night,
			"extra_charges": extra_charges,
			"total_price": total_price,
			"breakdown": get_pricing_breakdown(
				room_type, check_in_str, check_out_date_obj.strftime("%Y-%m-%d"), base_rate
			),
		}

	except Exception as e:
		frappe.log_error(f"Error calculating room price: {str(e)}")
		return None


# ════════════════════════════════════════════════════════════════════════════
# ROOM AVAILABILITY UTILITIES
# ════════════════════════════════════════════════════════════════════════════


def get_available_room_list(room_type, check_in_date_str, check_out_date_str):
	"""
	Get list of specific available rooms with their details.

	Args:
	    room_type (str): Room type name
	    check_in_date_str (str): Check-in date (YYYY-MM-DD)
	    check_out_date_str (str): Check-out date (YYYY-MM-DD)

	Returns:
	    list: [{room_number, floor, capacity}, ...]
	"""
	try:
		vacant_rooms = frappe.db.get_list(
			"Hotel Room",
			filters={
				"room_type": room_type,
				"status": "Vacant",
				"maintenance_flag": 0,
				"operational_status": "In Service",
			},
			fields=["name", "floor", "capacity"],
		)

		# Get booked rooms during this period
		booked_rooms_list = frappe.db.sql(
			"""
            SELECT DISTINCT hr.room_number
            FROM `tabHotel Room Reservation` hr
            INNER JOIN `tabHotel Room` room ON hr.room_number = room.name
            WHERE room.room_type = %s 
            AND room.operational_status = 'In Service'
            AND hr.status != 'Cancelled'
            AND hr.from_date < %s
            AND hr.to_date > %s
        """,
			(room_type, check_out_date_str, check_in_date_str),
		)

		booked_room_numbers = [row[0] for row in booked_rooms_list]

		# Filter to only available rooms
		available = []
		for room in vacant_rooms:
			if room["name"] not in booked_room_numbers:
				available.append(
					{
						"room_number": room["name"],
						"floor": room.get("floor", "N/A"),
						"capacity": room.get("capacity", 1),
					}
				)

		return available

	except Exception as e:
		frappe.log_error(f"Error getting available room list: {str(e)}")
		return []


def get_available_room_count(room_type, check_in_date, check_out_date):
	"""
	Get count of available rooms for a specific type and date range.

	Args:
	    room_type (str): Room type name
	    check_in_date (str or date): Check-in date
	    check_out_date (str or date): Check-out date

	Returns:
	    int: Number of available rooms
	"""
	try:
		check_in_str, _ = parse_date(check_in_date, "check_in_date")
		check_out_str, _ = parse_date(check_out_date, "check_out_date")

		total_vacant_rooms = frappe.db.count(
			"Hotel Room",
			filters={
				"room_type": room_type,
				"status": "Vacant",
				"maintenance_flag": 0,
				"operational_status": "In Service",
			},
		)

		booked_rooms = frappe.db.sql(
			"""
            SELECT COUNT(DISTINCT hr.room_number) 
            FROM `tabHotel Room Reservation` hr
            INNER JOIN `tabHotel Room` room ON hr.room_number = room.name
            WHERE room.room_type = %s 
            AND room.operational_status = 'In Service'
            AND hr.status != 'Cancelled'
            AND hr.from_date < %s
            AND hr.to_date > %s
        """,
			(room_type, check_out_str, check_in_str),
		)

		booked_count = booked_rooms[0][0] if booked_rooms else 0
		return total_vacant_rooms - booked_count

	except Exception as e:
		frappe.log_error(f"Error getting available room count: {str(e)}")
		return 0


def validate_room_for_booking(room_number, check_in_date_str, check_out_date_str):
	"""
	Validate if a specific room can be booked.
	Checks: exists, in service, vacant, not under maintenance, not already booked.

	Args:
	    room_number (str): Room number
	    check_in_date_str (str): Check-in date (YYYY-MM-DD)
	    check_out_date_str (str): Check-out date (YYYY-MM-DD)

	Returns:
	    dict: {room_type, operational_status, status, erpnext_item} or raises ValidationError
	"""
	try:
		room = frappe.db.get_value(
			"Hotel Room",
			room_number,
			["name", "room_type", "status", "operational_status", "maintenance_flag", "erpnext_item"],
			as_dict=True,
		)

		if not room:
			raise frappe.ValidationError(f"Room {room_number} does not exist")

		if room.get("operational_status") != "In Service":
			raise frappe.ValidationError(f"Room {room_number} is not available for booking")

		if room.get("status") != "Vacant":
			raise frappe.ValidationError(f"Room {room_number} is not vacant")

		if room.get("maintenance_flag"):
			raise frappe.ValidationError(f"Room {room_number} is under maintenance")

		# Check if already booked
		existing_booking = frappe.db.sql(
			"""
            SELECT name FROM `tabHotel Room Reservation`
            WHERE room_number = %s
            AND status NOT IN ('Cancelled')
            AND from_date < %s
            AND to_date > %s
        """,
			(room_number, check_out_date_str, check_in_date_str),
		)

		if existing_booking:
			raise frappe.ValidationError(f"Room {room_number} is already booked for selected dates")

		return room

	except frappe.ValidationError:
		raise
	except Exception as e:
		raise frappe.ValidationError(f"Error validating room: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# ROOM TYPE UTILITIES
# ════════════════════════════════════════════════════════════════════════════


def get_room_type_details(room_type):
	"""
	Get details about a specific room type.

	Args:
	    room_type (str): Room type name

	Returns:
	    dict: Room type details or raises ValidationError
	"""
	try:
		details = frappe.get_doc("Hotel Room Type", room_type)
		images = [{"image": row.image, "caption": row.caption} for row in details.hotel_room_images]
		return {
			"name": details.name,
			"capacity": details.capacity,
			"extra_bed_capacity": details.extra_bed_capacity,
			"base_adult": details.base_adult,
			"max_adult": details.max_adult,
			"base_child": details.base_child,
			"max_child": details.max_child,
			"is_active": details.is_active,
			"images": images,
		}
	except frappe.DoesNotExistError:
		raise frappe.ValidationError(f"Room type {room_type} not found")
	except Exception as e:
		raise frappe.ValidationError(f"Error getting room type: {str(e)}")


def get_room_images(room_type_name):
	"""
	Get images for a room type.

	Args:
	    room_type (str): Room type name

	Returns:
	    list: [{image, caption}, ...]
	"""
	try:
		images = frappe.db.get_list(
			"Hotel Room Images", filters={"parent": room_type_name}, fields=["image", "caption"]
		)
		return images if images else []
	except Exception as e:
		frappe.log_error(f"Error getting room images: {str(e)}")
		return []


# ════════════════════════════════════════════════════════════════════════════
# BOOKING UTILITIES
# ════════════════════════════════════════════════════════════════════════════


def generate_secure_booking_number():
	"""
	Generate a secure random booking number.
	Format: BOOK-XXXXXXXXXX (where X is random alphanumeric)
	Example: BOOK-7K9M2R4X8P

	Features:
	- Cryptographically random (prevents guessing)
	- Unique (checks database)
	- Human-readable

	Returns:
	    str: Secure booking number
	"""
	try:
		# Generate 10 random alphanumeric characters
		random_string = "".join(secrets.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(10))
		booking_number = f"BOOK-{random_string}"

		# Verify uniqueness
		existing = frappe.db.get_value("Hotel Booking", booking_number)
		if existing:
			# Recursively retry if collision (extremely rare)
			return generate_secure_booking_number()

		return booking_number

	except Exception as e:
		frappe.log_error(f"Error generating booking number: {str(e)}")
		# Fallback to timestamp-based if random fails
		return f"BOOK-{int(datetime.now().timestamp())}"


def create_or_get_item(room_number, room_type, erpnext_item=None):
	"""
	Create or get ERPNext Item for a room.

	Args:
	    room_number (str): Room number
	    room_type (str): Room type (used as Item Group)
	    erpnext_item (str): Existing item code (optional)

	Returns:
	    str: Item code
	"""
	try:
		item_code = erpnext_item or room_number

		# Try to get existing item
		try:
			frappe.get_doc("Item", item_code)
			return item_code
		except frappe.DoesNotExistError:
			pass

		# Create new item
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": room_number,
				"item_name": room_number,
				"item_group": room_type,
				"stock_uom": "Nos",
				"is_stock_item": 0,  # Not inventory tracked
			}
		)
		item.insert()
		frappe.db.commit()

		return room_number

	except Exception as e:
		frappe.log_error(f"Error creating/getting item: {str(e)}")
		raise frappe.ValidationError(f"Error creating invoice item: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# VALIDATION UTILITIES
# ════════════════════════════════════════════════════════════════════════════


def validate_guest_count(num_rooms, adults, children):
	"""
	Validate guest count parameters.

	Args:
	    num_rooms (int): Number of rooms
	    adults (int): Number of adults
	    children (int): Number of children
	"""
	if not isinstance(num_rooms, int) or num_rooms < 1:
		raise frappe.ValidationError("Number of rooms must be at least 1")

	if not isinstance(adults, int) or adults < 1:
		raise frappe.ValidationError("At least 1 adult is required")

	if not isinstance(children, int) or children < 0:
		raise frappe.ValidationError("Children count cannot be negative")

	if adults + children > 20:
		raise frappe.ValidationError("Maximum 20 guests per booking")


def validate_guests_fit_room(max_adults, max_children, adults, children, room_name):
	"""
	Validate if guests fit in room type capacity.

	Args:
	    max_adults (int): Maximum adults for room type
	    max_children (int): Maximum children for room type
	    adults (int): Requested adults
	    children (int): Requested children
	    room_name (str): Room type name (for error messages)

	Returns:
	    bool: True if fits, False if doesn't
	    str: Error message if doesn't fit
	"""
	if max_adults > 0 and adults > max_adults:
		return False, f"{room_name} (max {max_adults} adult(s), you requested {adults})"

	if max_children > 0 and children > max_children:
		return False, f"{room_name} (max {max_children} child(ren), you requested {children})"

	return True, None
