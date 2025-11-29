# # """
# # Hotel Search - Available Rooms Module
# # Handles room availability search with proper hold validation
# # IMPROVED: Excludes held rooms from search results
# # IMPROVED: Validates room existence and capacity across multiple rooms
# # """

# # import frappe
# # from frappe.utils import getdate
# # from datetime import datetime, timedelta

# # # Import shared utilities
# # from .shared_utilities import (
# #     parse_date,
# #     validate_date_range,
# #     validate_guest_count,
# #     validate_guests_fit_room,
# #     get_room_tariff,
# #     get_pricing_breakdown,
# #     calculate_room_price,
# #     get_available_room_list,
# #     get_room_type_details,
# #     get_room_images
# # )


# # @frappe.whitelist(allow_guest=True, methods=['POST'])
# # def search_available_rooms(check_in_date, check_out_date, num_rooms=1, adults=1, children=0):
# #     """
# #     Search for available rooms based on dates and guest requirements.
    
# #     EXCLUDES:
# #     - Rooms with reservations overlapping requested dates
# #     - Rooms with active check-ins during requested dates
# #     - Rooms currently held by other temporary bookings
# #     - Rooms in maintenance or out of service
    
# #     Args:
# #         check_in_date (str): Check-in date (YYYY-MM-DD)
# #         check_out_date (str): Check-out date (YYYY-MM-DD)
# #         num_rooms (int): Number of rooms needed
# #         adults (int): Number of adults
# #         children (int): Number of children
    
# #     Returns:
# #         dict: Available rooms grouped by type with pricing and details
# #     """
    
# #     try:
# #         # === CONVERT AND VALIDATE INPUTS ===
# #         try:
# #             num_rooms = int(num_rooms) if num_rooms else 1
# #             adults = int(adults) if adults else 1
# #             children = int(children) if children else 0
# #         except (ValueError, TypeError):
# #             frappe.throw("Invalid number format for rooms, adults, or children")
        
# #         if num_rooms < 1:
# #             frappe.throw("Number of rooms must be at least 1")
# #         if num_rooms > 10:
# #             frappe.throw("Maximum 10 rooms per booking")
        
# #         if adults < 1:
# #             frappe.throw("Number of adults must be at least 1")
# #         if adults > 20:
# #             frappe.throw("Maximum 20 adults per booking")
        
# #         if children < 0:
# #             frappe.throw("Number of children cannot be negative")
# #         if children > 20:
# #             frappe.throw("Maximum 20 children per booking")
        
# #         # === PARSE AND VALIDATE DATES ===
# #         check_in_str, check_in = parse_date(check_in_date, "check_in_date")
# #         check_out_str, check_out = parse_date(check_out_date, "check_out_date")
# #         num_nights = validate_date_range(check_in, check_out)
        
# #         # === GET ROOM TYPES ===
# #         room_types = frappe.get_all(
# #             "Hotel Room Type",
# #             filters={"is_active": 1},
# #             fields=["name", "capacity", "extra_bed_capacity", "max_adult", "max_child"]
# #         )
        
# #         if not room_types:
# #             return {
# #                 "check_in_date": check_in_str,
# #                 "check_out_date": check_out_str,
# #                 "number_of_nights": num_nights,
# #                 "adults": adults,
# #                 "children": children,
# #                 "rooms_requested": num_rooms,
# #                 "available_rooms": {},
# #                 "total_results": 0,
# #                 "status": "no_room_types",
# #                 "message": "No room types are currently available"
# #             }
        
# #         # === SEARCH AVAILABLE ROOMS ===
# #         available_rooms = {}
# #         rooms_without_tariff = []
# #         rooms_not_matching_guests = []
        
# #         for room_type in room_types:
# #             room_type_name = room_type["name"]
            
# #             # === CHECK GUEST CAPACITY ===
# #             max_adults = room_type.get("max_adult", 0) or 0
# #             max_children = room_type.get("max_child", 0) or 0
# #             room_capacity = room_type["capacity"]
            
# #             # Calculate total capacity across all requested rooms
# #             total_room_capacity = room_capacity * num_rooms
# #             total_max_adults = max_adults * num_rooms if max_adults > 0 else float('inf')
# #             total_max_children = max_children * num_rooms if max_children > 0 else float('inf')
# #             total_guest_count = adults + children
            
# #             # Check if total capacity across all rooms can fit guests
# #             can_fit = (
# #                 total_room_capacity >= total_guest_count and
# #                 (max_adults == 0 or total_max_adults >= adults) and
# #                 (max_children == 0 or total_max_children >= children)
# #             )
            
# #             if not can_fit:
# #                 capacity_msg = f"capacity {total_room_capacity}"
# #                 max_adults_msg = f"{int(total_max_adults)} adults" if total_max_adults != float('inf') else "unlimited adults"
# #                 max_children_msg = f"{int(total_max_children)} children" if total_max_children != float('inf') else "unlimited children"
                
# #                 error_msg = (
# #                     f"{room_type_name}: {num_rooms} room(s) can accommodate max "
# #                     f"{max_adults_msg}, {max_children_msg} ({capacity_msg}). "
# #                     f"You requested {adults} adults, {children} children."
# #                 )
# #                 rooms_not_matching_guests.append(error_msg)
# #                 continue
            
# #             # === COUNT AVAILABLE ROOMS ===
# #             # Step 1: Get all vacant rooms of this type
# #             total_vacant = frappe.db.count(
# #                 "Hotel Room",
# #                 filters={
# #                     "room_type": room_type_name,
# #                     "status": "Vacant",
# #                     "maintenance_flag": 0,
# #                     "operational_status": "In Service"
# #                 }
# #             )
            
# #             # Step 2: Get rooms with reservations that overlap the requested dates
# #             booked_rooms = frappe.db.sql("""
# #                 SELECT COUNT(DISTINCT hr.room_number) 
# #                 FROM `tabHotel Room Reservation` hr
# #                 INNER JOIN `tabHotel Room` room ON hr.room_number = room.name
# #                 WHERE room.room_type = %s 
# #                 AND room.operational_status = 'In Service'
# #                 AND hr.status != 'Cancelled'
# #                 AND hr.from_date < %s
# #                 AND hr.to_date > %s
# #             """, (room_type_name, check_out_str, check_in_str))
            
# #             booked_count = booked_rooms[0][0] if booked_rooms else 0
            
# #             # Step 3: Get rooms with active check-ins during the requested dates
# #             checked_in_rooms = frappe.db.sql("""
# #                 SELECT COUNT(DISTINCT chkin.room_number)
# #                 FROM `tabHotel Room Check In` chkin
# #                 INNER JOIN `tabHotel Room` room ON chkin.room_number = room.name
# #                 WHERE room.room_type = %s
# #                 AND room.operational_status = 'In Service'
# #                 AND chkin.status IN ('Draft', 'Checked In')
# #                 AND DATE(chkin.check_in_datetime) < %s
# #                 AND DATE(chkin.expected_check_out_datetime) > %s
# #             """, (room_type_name, check_out_str, check_in_str))
            
# #             checked_in_count = checked_in_rooms[0][0] if checked_in_rooms else 0
            
# #             # Step 4: Get rooms currently held by temporary bookings (NEW VALIDATION)
# #             held_rooms = frappe.db.sql("""
# #                 SELECT COUNT(DISTINCT room.name)
# #                 FROM `tabHotel Room` room
# #                 WHERE room.room_type = %s
# #                 AND room.operational_status = 'In Service'
# #                 AND room.booking_status = 'Held'
# #                 AND room.hold_expires_at > %s
# #             """, (room_type_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
# #             held_count = held_rooms[0][0] if held_rooms else 0
            
# #             # Calculate available rooms: total vacant minus booked minus checked-in minus held
# #             unavailable_count = booked_count + checked_in_count + held_count
# #             available_count = total_vacant - unavailable_count
            
# #             # Skip if not enough rooms available
# #             if available_count < num_rooms:
# #                 continue
            
# #             # === CALCULATE PRICING ===
# #             price_info = calculate_room_price(
# #                 room_type_name, check_in_str, num_nights,
# #                 room_capacity, adults, children
# #             )
            
# #             if not price_info:
# #                 rooms_without_tariff.append(room_type_name)
# #                 continue
            
# #             # Adjust pricing for multiple rooms
# #             price_info["price_per_night"] = price_info["price_per_night"] * num_rooms
# #             price_info["total_price"] = price_info["total_price"] * num_rooms
            
# #             # === GET ROOM DETAILS ===
# #             room_list = get_available_room_list_excluding_held(
# #                 room_type_name, check_in_str, check_out_str
# #             )
            
# #             if len(room_list) < num_rooms:
# #                 continue
            
# #             room_type_doc = frappe.get_doc("Hotel Room Type", room_type_name)
# #             room_images = [{"image": row.image, "caption": row.caption} for row in room_type_doc.hotel_room_images]
# #             room_amenities = [{"item": row.item, "billable": row.billable} for row in room_type_doc.amenities]
            
# #             # === BUILD RESPONSE ===
# #             available_rooms[room_type_name] = {
# #                 "available_count": available_count,
# #                 "requested_count": num_rooms,
# #                 "can_fulfill": available_count >= num_rooms,
# #                 "available_rooms": room_list[:num_rooms],
# #                 "total_available_rooms": len(room_list),
# #                 "base_rate": price_info["base_rate"],
# #                 "price_per_night": price_info["price_per_night"],
# #                 "number_of_nights": num_nights,
# #                 "extra_charges": price_info["extra_charges"],
# #                 "total_price": price_info["total_price"],
# #                 "pricing_breakdown": price_info["breakdown"],
# #                 "single_room_capacity": {
# #                     "max_adults": max_adults if max_adults > 0 else "Unlimited",
# #                     "max_children": max_children if max_children > 0 else "Unlimited",
# #                     "base_capacity": room_capacity
# #                 },
# #                 "total_guest_capacity": {
# #                     "max_adults": int(total_max_adults) if total_max_adults != float('inf') else "Unlimited",
# #                     "max_children": int(total_max_children) if total_max_children != float('inf') else "Unlimited",
# #                     "base_capacity": total_room_capacity,
# #                     "number_of_rooms": num_rooms
# #                 },
# #                 "images": room_images,
# #                 "amenities": room_amenities
# #             }
        
# #         # === BUILD FINAL RESPONSE ===
# #         response = {
# #             "check_in_date": check_in_str,
# #             "check_out_date": check_out_str,
# #             "number_of_nights": num_nights,
# #             "guests": {
# #                 "adults": adults,
# #                 "children": children,
# #                 "total": adults + children
# #             },
# #             "rooms_requested": num_rooms,
# #             "available_rooms": available_rooms,
# #             "total_results": len(available_rooms)
# #         }
        
# #         # Add warnings
# #         if rooms_without_tariff:
# #             response["warning_no_tariff"] = (
# #                 f"The following room types have no pricing: {', '.join(rooms_without_tariff)}"
# #             )
        
# #         if rooms_not_matching_guests:
# #             response["warning_guest_mismatch"] = (
# #                 f"Capacity mismatch: {'; '.join(rooms_not_matching_guests)}"
# #             )
        
# #         # Set status
# #         if not available_rooms:
# #             response["status"] = "no_availability"
# #             response["message"] = "No rooms available for your dates"
# #         else:
# #             response["status"] = "success"
        
# #         return response
    
# #     except frappe.ValidationError as e:
# #         frappe.throw(str(e))
# #     except ValueError as e:
# #         frappe.throw(f"Invalid date format. Use YYYY-MM-DD: {str(e)}")
# #     except Exception as e:
# #         frappe.log_error(frappe.get_traceback(), "Search Available Rooms Error")
# #         frappe.throw(f"Error: {str(e)}")


# # def get_available_room_list_excluding_held(room_type, check_in_date, check_out_date):
# #     """
# #     Get available rooms of a type, EXCLUDING held rooms with valid holds.
# #     Returns list of room objects with numbers, capacity, floor info.
# #     """
# #     try:
# #         current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
# #         rooms = frappe.db.sql("""
# #             SELECT 
# #                 room.name as room_number,
# #                 room.capacity,
# #                 room.floor,
# #                 room.room_type
# #             FROM `tabHotel Room` room
# #             WHERE room.room_type = %s
# #             AND room.operational_status = 'In Service'
# #             AND room.status = 'Vacant'
# #             AND room.maintenance_flag = 0
# #             -- EXCLUDE rooms with valid holds
# #             AND NOT (room.booking_status = 'Held' AND room.hold_expires_at > %s)
# #             -- EXCLUDE booked rooms
# #             AND NOT EXISTS (
# #                 SELECT 1 FROM `tabHotel Room Reservation` res
# #                 WHERE res.room_number = room.name
# #                 AND res.status != 'Cancelled'
# #                 AND res.from_date < %s
# #                 AND res.to_date > %s
# #             )
# #             -- EXCLUDE checked-in rooms
# #             AND NOT EXISTS (
# #                 SELECT 1 FROM `tabHotel Room Check In` chkin
# #                 WHERE chkin.room_number = room.name
# #                 AND chkin.status IN ('Draft', 'Checked In')
# #                 AND DATE(chkin.check_in_datetime) < %s
# #                 AND DATE(chkin.expected_check_out_datetime) > %s
# #             )
# #             ORDER BY room.name ASC
# #         """, (room_type, current_time, check_out_date, check_in_date, check_out_date, check_in_date), as_dict=True)
        
# #         return [{"room_number": r["room_number"], "capacity": r["capacity"], "floor": r["floor"]} for r in rooms]
    
# #     except Exception as e:
# #         frappe.log_error(f"Error getting available rooms: {str(e)}")
# #         return []


# # @frappe.whitelist(allow_guest=True)
# # def get_room_type_info(room_type):
# #     """Get detailed information about a specific room type."""
# #     try:
# #         details = get_room_type_details(room_type)
# #         return {"success": True, "room_type": details}
# #     except frappe.ValidationError as e:
# #         frappe.throw(str(e))
# #     except Exception as e:
# #         frappe.throw(f"Error: {str(e)}")


# # @frappe.whitelist(allow_guest=True)
# # def get_room_pricing_for_dates(room_type, check_in_date, check_out_date, num_rooms=1):
# #     """Get pricing breakdown for a room type for specific dates."""
# #     try:
# #         num_rooms = int(num_rooms) if num_rooms else 1
        
# #         check_in_str, check_in = parse_date(check_in_date, "check_in_date")
# #         check_out_str, check_out = parse_date(check_out_date, "check_out_date")
# #         num_nights = validate_date_range(check_in, check_out)
        
# #         tariff = get_room_tariff(room_type, check_in_str)
# #         if not tariff:
# #             raise frappe.ValidationError(f"No tariff found for {room_type}")
        
# #         base_rate = float(tariff["rate_amount"])
# #         single_room_total = base_rate * num_nights
# #         total_price = single_room_total * num_rooms
# #         breakdown = get_pricing_breakdown(room_type, check_in_str, check_out_str, base_rate)
        
# #         return {
# #             "success": True,
# #             "room_type": room_type,
# #             "check_in_date": check_in_str,
# #             "check_out_date": check_out_str,
# #             "number_of_nights": num_nights,
# #             "number_of_rooms": num_rooms,
# #             "base_rate": base_rate,
# #             "single_room_total": single_room_total,
# #             "total_price": total_price,
# #             "breakdown": breakdown
# #         }
    
# #     except frappe.ValidationError as e:
# #         frappe.throw(str(e))
# #     except Exception as e:
# #         frappe.throw(f"Error: {str(e)}")


# # @frappe.whitelist(allow_guest=True)
# # def get_occupancy_status(check_in_date=None):
# #     """Get occupancy status for a specific date."""
# #     try:
# #         from frappe.utils import getdate
        
# #         if not check_in_date:
# #             check_date = getdate()
# #         else:
# #             _, check_date = parse_date(check_in_date, "check_date")
        
# #         total_rooms = frappe.db.count("Hotel Room", filters={"operational_status": "In Service"})
        
# #         occupied = frappe.db.sql("""
# #             SELECT COUNT(DISTINCT hr.room_number) 
# #             FROM `tabHotel Room Reservation` hr
# #             WHERE hr.status != 'Cancelled'
# #             AND hr.from_date <= %s
# #             AND hr.to_date > %s
# #         """, (check_date.strftime("%Y-%m-%d"), check_date.strftime("%Y-%m-%d")))
        
# #         occupied_count = occupied[0][0] if occupied else 0
# #         occupancy_rate = (occupied_count / total_rooms * 100) if total_rooms > 0 else 0
        
# #         return {
# #             "success": True,
# #             "date": check_date.strftime("%Y-%m-%d"),
# #             "total_rooms": total_rooms,
# #             "occupied_rooms": occupied_count,
# #             "vacant_rooms": total_rooms - occupied_count,
# #             "occupancy_rate": round(occupancy_rate, 2)
# #         }
    
# #     except Exception as e:
# #         return {"success": False, "error": str(e)}






































# # """
# # Hotel Search - Available Rooms Module
# # Handles room availability search with proper hold validation
# # IMPROVED: Excludes held rooms from Temporary Booking (not Hotel Room)
# # IMPROVED: Validates room existence and capacity across multiple rooms
# # UPDATED: Uses Temporary Booking as source of truth for holds
# # """

# # import frappe
# # from frappe.utils import getdate
# # from datetime import datetime, timedelta

# # # Import shared utilities
# # from .shared_utilities import (
# #     parse_date,
# #     validate_date_range,
# #     validate_guest_count,
# #     validate_guests_fit_room,
# #     get_room_tariff,
# #     get_pricing_breakdown,
# #     calculate_room_price,
# #     get_available_room_list,
# #     get_room_type_details,
# #     get_room_images
# # )


# # @frappe.whitelist(allow_guest=True, methods=['POST'])
# # def search_available_rooms(check_in_date, check_out_date, num_rooms=1, adults=1, children=0):
# #     """
# #     Search for available rooms based on dates and guest requirements.
    
# #     EXCLUDES:
# #     - Rooms with reservations overlapping requested dates
# #     - Rooms with active check-ins during requested dates
# #     - Rooms currently held by active temporary bookings (with Held status)
# #     - Rooms in maintenance or out of service
    
# #     Args:
# #         check_in_date (str): Check-in date (YYYY-MM-DD)
# #         check_out_date (str): Check-out date (YYYY-MM-DD)
# #         num_rooms (int): Number of rooms needed
# #         adults (int): Number of adults
# #         children (int): Number of children
    
# #     Returns:
# #         dict: Available rooms grouped by type with pricing and details
# #     """
    
# #     try:
# #         # === CONVERT AND VALIDATE INPUTS ===
# #         try:
# #             num_rooms = int(num_rooms) if num_rooms else 1
# #             adults = int(adults) if adults else 1
# #             children = int(children) if children else 0
# #         except (ValueError, TypeError):
# #             frappe.throw("Invalid number format for rooms, adults, or children")
        
# #         if num_rooms < 1:
# #             frappe.throw("Number of rooms must be at least 1")
# #         if num_rooms > 10:
# #             frappe.throw("Maximum 10 rooms per booking")
        
# #         if adults < 1:
# #             frappe.throw("Number of adults must be at least 1")
# #         if adults > 20:
# #             frappe.throw("Maximum 20 adults per booking")
        
# #         if children < 0:
# #             frappe.throw("Number of children cannot be negative")
# #         if children > 20:
# #             frappe.throw("Maximum 20 children per booking")
        
# #         # === PARSE AND VALIDATE DATES ===
# #         check_in_str, check_in = parse_date(check_in_date, "check_in_date")
# #         check_out_str, check_out = parse_date(check_out_date, "check_out_date")
# #         num_nights = validate_date_range(check_in, check_out)
        
# #         # === GET ROOM TYPES ===
# #         room_types = frappe.get_all(
# #             "Hotel Room Type",
# #             filters={"is_active": 1},
# #             fields=["name", "capacity", "extra_bed_capacity", "max_adult", "max_child"]
# #         )
        
# #         if not room_types:
# #             return {
# #                 "check_in_date": check_in_str,
# #                 "check_out_date": check_out_str,
# #                 "number_of_nights": num_nights,
# #                 "adults": adults,
# #                 "children": children,
# #                 "rooms_requested": num_rooms,
# #                 "available_rooms": {},
# #                 "total_results": 0,
# #                 "status": "no_room_types",
# #                 "message": "No room types are currently available"
# #             }
        
# #         # === SEARCH AVAILABLE ROOMS ===
# #         available_rooms = {}
# #         rooms_without_tariff = []
# #         rooms_not_matching_guests = []
        
# #         for room_type in room_types:
# #             room_type_name = room_type["name"]
            
# #             # === CHECK GUEST CAPACITY ===
# #             max_adults = room_type.get("max_adult", 0) or 0
# #             max_children = room_type.get("max_child", 0) or 0
# #             room_capacity = room_type["capacity"]
            
# #             # Calculate total capacity across all requested rooms
# #             total_room_capacity = room_capacity * num_rooms
# #             total_max_adults = max_adults * num_rooms if max_adults > 0 else float('inf')
# #             total_max_children = max_children * num_rooms if max_children > 0 else float('inf')
# #             total_guest_count = adults + children
            
# #             # Check if total capacity across all rooms can fit guests
# #             can_fit = (
# #                 total_room_capacity >= total_guest_count and
# #                 (max_adults == 0 or total_max_adults >= adults) and
# #                 (max_children == 0 or total_max_children >= children)
# #             )
            
# #             if not can_fit:
# #                 capacity_msg = f"capacity {total_room_capacity}"
# #                 max_adults_msg = f"{int(total_max_adults)} adults" if total_max_adults != float('inf') else "unlimited adults"
# #                 max_children_msg = f"{int(total_max_children)} children" if total_max_children != float('inf') else "unlimited children"
                
# #                 error_msg = (
# #                     f"{room_type_name}: {num_rooms} room(s) can accommodate max "
# #                     f"{max_adults_msg}, {max_children_msg} ({capacity_msg}). "
# #                     f"You requested {adults} adults, {children} children."
# #                 )
# #                 rooms_not_matching_guests.append(error_msg)
# #                 continue
            
# #             # === COUNT AVAILABLE ROOMS ===
# #             # Step 1: Get all vacant rooms of this type
# #             total_vacant = frappe.db.count(
# #                 "Hotel Room",
# #                 filters={
# #                     "room_type": room_type_name,
# #                     "status": "Vacant",
# #                     "maintenance_flag": 0,
# #                     "operational_status": "In Service"
# #                 }
# #             )
            
# #             # Step 2: Get rooms with reservations that overlap the requested dates
# #             booked_rooms = frappe.db.sql("""
# #                 SELECT COUNT(DISTINCT hr.room_number) 
# #                 FROM `tabHotel Room Reservation` hr
# #                 INNER JOIN `tabHotel Room` room ON hr.room_number = room.name
# #                 WHERE room.room_type = %s 
# #                 AND room.operational_status = 'In Service'
# #                 AND hr.status != 'Cancelled'
# #                 AND hr.from_date < %s
# #                 AND hr.to_date > %s
# #             """, (room_type_name, check_out_str, check_in_str))
            
# #             booked_count = booked_rooms[0][0] if booked_rooms else 0
            
# #             # Step 3: Get rooms with active check-ins during the requested dates
# #             checked_in_rooms = frappe.db.sql("""
# #                 SELECT COUNT(DISTINCT chkin.room_number)
# #                 FROM `tabHotel Room Check In` chkin
# #                 INNER JOIN `tabHotel Room` room ON chkin.room_number = room.name
# #                 WHERE room.room_type = %s
# #                 AND room.operational_status = 'In Service'
# #                 AND chkin.status IN ('Draft', 'Checked In')
# #                 AND DATE(chkin.check_in_datetime) < %s
# #                 AND DATE(chkin.expected_check_out_datetime) > %s
# #             """, (room_type_name, check_out_str, check_in_str))
            
# #             checked_in_count = checked_in_rooms[0][0] if checked_in_rooms else 0
            
# #             # Step 4: Get rooms currently held by active temporary bookings
# #             # ✅ UPDATED: Query Temporary Booking instead of Hotel Room
# #             held_rooms_query = frappe.db.sql("""
# #                 SELECT COUNT(DISTINCT tbr.room_number)
# #                 FROM `tabTemporary Booking` tb
# #                 INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
# #                 INNER JOIN `tabHotel Room` room ON tbr.room_number = room.name
# #                 WHERE room.room_type = %s
# #                 AND room.operational_status = 'In Service'
# #                 AND tb.status IN ('Hold', 'Payment Link Generated')
# #                 AND tb.payment_status = 'Pending'
# #                 AND tb.booking_status = 'Held'
# #                 AND tb.hold_expires_at > %s
# #             """, (room_type_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
# #             held_count = held_rooms_query[0][0] if held_rooms_query else 0
            
# #             # Calculate available rooms: total vacant minus booked minus checked-in minus held
# #             unavailable_count = booked_count + checked_in_count + held_count
# #             available_count = total_vacant - unavailable_count
            
# #             # Skip if not enough rooms available
# #             if available_count < num_rooms:
# #                 continue
            
# #             # === CALCULATE PRICING ===
# #             price_info = calculate_room_price(
# #                 room_type_name, check_in_str, num_nights,
# #                 room_capacity, adults, children
# #             )
            
# #             if not price_info:
# #                 rooms_without_tariff.append(room_type_name)
# #                 continue
            
# #             # Adjust pricing for multiple rooms
# #             price_info["price_per_night"] = price_info["price_per_night"] * num_rooms
# #             price_info["total_price"] = price_info["total_price"] * num_rooms
            
# #             # === GET ROOM DETAILS ===
# #             room_list = get_available_room_list_excluding_held(
# #                 room_type_name, check_in_str, check_out_str
# #             )
            
# #             if len(room_list) < num_rooms:
# #                 continue
            
# #             room_type_doc = frappe.get_doc("Hotel Room Type", room_type_name)
# #             room_images = [{"image": row.image, "caption": row.caption} for row in room_type_doc.hotel_room_images]
# #             room_amenities = [{"item": row.item, "billable": row.billable} for row in room_type_doc.amenities]
            
# #             # === BUILD RESPONSE ===
# #             available_rooms[room_type_name] = {
# #                 "available_count": available_count,
# #                 "requested_count": num_rooms,
# #                 "can_fulfill": available_count >= num_rooms,
# #                 "available_rooms": room_list[:num_rooms],
# #                 "total_available_rooms": len(room_list),
# #                 "base_rate": price_info["base_rate"],
# #                 "price_per_night": price_info["price_per_night"],
# #                 "number_of_nights": num_nights,
# #                 "extra_charges": price_info["extra_charges"],
# #                 "total_price": price_info["total_price"],
# #                 "pricing_breakdown": price_info["breakdown"],
# #                 "single_room_capacity": {
# #                     "max_adults": max_adults if max_adults > 0 else "Unlimited",
# #                     "max_children": max_children if max_children > 0 else "Unlimited",
# #                     "base_capacity": room_capacity
# #                 },
# #                 "total_guest_capacity": {
# #                     "max_adults": int(total_max_adults) if total_max_adults != float('inf') else "Unlimited",
# #                     "max_children": int(total_max_children) if total_max_children != float('inf') else "Unlimited",
# #                     "base_capacity": total_room_capacity,
# #                     "number_of_rooms": num_rooms
# #                 },
# #                 "images": room_images,
# #                 "amenities": room_amenities
# #             }
        
# #         # === BUILD FINAL RESPONSE ===
# #         response = {
# #             "check_in_date": check_in_str,
# #             "check_out_date": check_out_str,
# #             "number_of_nights": num_nights,
# #             "guests": {
# #                 "adults": adults,
# #                 "children": children,
# #                 "total": adults + children
# #             },
# #             "rooms_requested": num_rooms,
# #             "available_rooms": available_rooms,
# #             "total_results": len(available_rooms)
# #         }
        
# #         # Add warnings
# #         if rooms_without_tariff:
# #             response["warning_no_tariff"] = (
# #                 f"The following room types have no pricing: {', '.join(rooms_without_tariff)}"
# #             )
        
# #         if rooms_not_matching_guests:
# #             response["warning_guest_mismatch"] = (
# #                 f"Capacity mismatch: {'; '.join(rooms_not_matching_guests)}"
# #             )
        
# #         # Set status
# #         if not available_rooms:
# #             response["status"] = "no_availability"
# #             response["message"] = "No rooms available for your dates"
# #         else:
# #             response["status"] = "success"
        
# #         return response
    
# #     except frappe.ValidationError as e:
# #         frappe.throw(str(e))
# #     except ValueError as e:
# #         frappe.throw(f"Invalid date format. Use YYYY-MM-DD: {str(e)}")
# #     except Exception as e:
# #         frappe.log_error(frappe.get_traceback(), "Search Available Rooms Error")
# #         frappe.throw(f"Error: {str(e)}")


# # def get_available_room_list_excluding_held(room_type, check_in_date, check_out_date):
# #     """
# #     Get available rooms of a type, EXCLUDING rooms held by active temporary bookings.
# #     Returns list of room objects with numbers, capacity, floor info.
# #     ✅ UPDATED: Uses Temporary Booking for hold status instead of Hotel Room
# #     """
# #     try:
# #         current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
# #         rooms = frappe.db.sql("""
# #             SELECT 
# #                 room.name as room_number,
# #                 room.capacity,
# #                 room.floor,
# #                 room.room_type
# #             FROM `tabHotel Room` room
# #             WHERE room.room_type = %s
# #             AND room.operational_status = 'In Service'
# #             AND room.status = 'Vacant'
# #             AND room.maintenance_flag = 0
# #             -- EXCLUDE rooms held by active temporary bookings
# #             AND NOT EXISTS (
# #                 SELECT 1 FROM `tabTemporary Booking` tb
# #                 INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
# #                 WHERE tbr.room_number = room.name
# #                 AND tb.status IN ('Hold', 'Payment Link Generated')
# #                 AND tb.payment_status = 'Pending'
# #                 AND tb.booking_status = 'Held'
# #                 AND tb.hold_expires_at > %s
# #             )
# #             -- EXCLUDE booked rooms
# #             AND NOT EXISTS (
# #                 SELECT 1 FROM `tabHotel Room Reservation` res
# #                 WHERE res.room_number = room.name
# #                 AND res.status != 'Cancelled'
# #                 AND res.from_date < %s
# #                 AND res.to_date > %s
# #             )
# #             -- EXCLUDE checked-in rooms
# #             AND NOT EXISTS (
# #                 SELECT 1 FROM `tabHotel Room Check In` chkin
# #                 WHERE chkin.room_number = room.name
# #                 AND chkin.status IN ('Draft', 'Checked In')
# #                 AND DATE(chkin.check_in_datetime) < %s
# #                 AND DATE(chkin.expected_check_out_datetime) > %s
# #             )
# #             ORDER BY room.name ASC
# #         """, (room_type, current_time, check_out_date, check_in_date, check_out_date, check_in_date), as_dict=True)
        
# #         return [{"room_number": r["room_number"], "capacity": r["capacity"], "floor": r["floor"]} for r in rooms]
    
# #     except Exception as e:
# #         frappe.log_error(f"Error getting available rooms: {str(e)}")
# #         return []


# # @frappe.whitelist(allow_guest=True)
# # def get_room_type_info(room_type):
# #     """Get detailed information about a specific room type."""
# #     try:
# #         details = get_room_type_details(room_type)
# #         return {"success": True, "room_type": details}
# #     except frappe.ValidationError as e:
# #         frappe.throw(str(e))
# #     except Exception as e:
# #         frappe.throw(f"Error: {str(e)}")


# # @frappe.whitelist(allow_guest=True)
# # def get_room_pricing_for_dates(room_type, check_in_date, check_out_date, num_rooms=1):
# #     """Get pricing breakdown for a room type for specific dates."""
# #     try:
# #         num_rooms = int(num_rooms) if num_rooms else 1
        
# #         check_in_str, check_in = parse_date(check_in_date, "check_in_date")
# #         check_out_str, check_out = parse_date(check_out_date, "check_out_date")
# #         num_nights = validate_date_range(check_in, check_out)
        
# #         tariff = get_room_tariff(room_type, check_in_str)
# #         if not tariff:
# #             raise frappe.ValidationError(f"No tariff found for {room_type}")
        
# #         base_rate = float(tariff["rate_amount"])
# #         single_room_total = base_rate * num_nights
# #         total_price = single_room_total * num_rooms
# #         breakdown = get_pricing_breakdown(room_type, check_in_str, check_out_str, base_rate)
        
# #         return {
# #             "success": True,
# #             "room_type": room_type,
# #             "check_in_date": check_in_str,
# #             "check_out_date": check_out_str,
# #             "number_of_nights": num_nights,
# #             "number_of_rooms": num_rooms,
# #             "base_rate": base_rate,
# #             "single_room_total": single_room_total,
# #             "total_price": total_price,
# #             "breakdown": breakdown
# #         }
    
# #     except frappe.ValidationError as e:
# #         frappe.throw(str(e))
# #     except Exception as e:
# #         frappe.throw(f"Error: {str(e)}")


# # @frappe.whitelist(allow_guest=True)
# # def get_occupancy_status(check_in_date=None):
# #     """Get occupancy status for a specific date."""
# #     try:
# #         from frappe.utils import getdate
        
# #         if not check_in_date:
# #             check_date = getdate()
# #         else:
# #             _, check_date = parse_date(check_in_date, "check_date")
        
# #         total_rooms = frappe.db.count("Hotel Room", filters={"operational_status": "In Service"})
        
# #         occupied = frappe.db.sql("""
# #             SELECT COUNT(DISTINCT hr.room_number) 
# #             FROM `tabHotel Room Reservation` hr
# #             WHERE hr.status != 'Cancelled'
# #             AND hr.from_date <= %s
# #             AND hr.to_date > %s
# #         """, (check_date.strftime("%Y-%m-%d"), check_date.strftime("%Y-%m-%d")))
        
# #         occupied_count = occupied[0][0] if occupied else 0
# #         occupancy_rate = (occupied_count / total_rooms * 100) if total_rooms > 0 else 0
        
# #         return {
# #             "success": True,
# #             "date": check_date.strftime("%Y-%m-%d"),
# #             "total_rooms": total_rooms,
# #             "occupied_rooms": occupied_count,
# #             "vacant_rooms": total_rooms - occupied_count,
# #             "occupancy_rate": round(occupancy_rate, 2)
# #         }
    
# #     except Exception as e:
# #         return {"success": False, "error": str(e)}








# """
# Hotel Search - Available Rooms Module
# Handles room availability search with proper hold validation
# FIXED: Only subtract checked-in/booked rooms that are actually Vacant
# """

# import frappe
# from frappe.utils import getdate
# from datetime import datetime, timedelta

# # Import shared utilities
# from .shared_utilities import (
#     parse_date,
#     validate_date_range,
#     validate_guest_count,
#     validate_guests_fit_room,
#     get_room_tariff,
#     get_pricing_breakdown,
#     calculate_room_price,
#     get_available_room_list,
#     get_room_type_details,
#     get_room_images
# )


# @frappe.whitelist(allow_guest=True, methods=['POST'])
# def search_available_rooms(check_in_date, check_out_date, num_rooms=1, adults=1, children=0):
#     """
#     Search for available rooms based on dates and guest requirements.
    
#     EXCLUDES:
#     - Rooms with reservations overlapping requested dates
#     - Rooms with active check-ins during requested dates
#     - Rooms currently held by active temporary bookings (with Held status)
#     - Rooms in maintenance or out of service
    
#     Args:
#         check_in_date (str): Check-in date (YYYY-MM-DD)
#         check_out_date (str): Check-out date (YYYY-MM-DD)
#         num_rooms (int): Number of rooms needed
#         adults (int): Number of adults
#         children (int): Number of children
    
#     Returns:
#         dict: Available rooms grouped by type with pricing and details
#     """
    
#     try:
#         # === CONVERT AND VALIDATE INPUTS ===
#         try:
#             num_rooms = int(num_rooms) if num_rooms else 1
#             adults = int(adults) if adults else 1
#             children = int(children) if children else 0
#         except (ValueError, TypeError):
#             frappe.throw("Invalid number format for rooms, adults, or children")
        
#         if num_rooms < 1:
#             frappe.throw("Number of rooms must be at least 1")
#         if num_rooms > 10:
#             frappe.throw("Maximum 10 rooms per booking")
        
#         if adults < 1:
#             frappe.throw("Number of adults must be at least 1")
#         if adults > 20:
#             frappe.throw("Maximum 20 adults per booking")
        
#         if children < 0:
#             frappe.throw("Number of children cannot be negative")
#         if children > 20:
#             frappe.throw("Maximum 20 children per booking")
        
#         # === PARSE AND VALIDATE DATES ===
#         check_in_str, check_in = parse_date(check_in_date, "check_in_date")
#         check_out_str, check_out = parse_date(check_out_date, "check_out_date")
#         num_nights = validate_date_range(check_in, check_out)
        
#         # === GET ROOM TYPES ===
#         room_types = frappe.get_all(
#             "Hotel Room Type",
#             filters={"is_active": 1},
#             fields=["name", "capacity", "extra_bed_capacity", "max_adult", "max_child"]
#         )
        
#         if not room_types:
#             return {
#                 "check_in_date": check_in_str,
#                 "check_out_date": check_out_str,
#                 "number_of_nights": num_nights,
#                 "adults": adults,
#                 "children": children,
#                 "rooms_requested": num_rooms,
#                 "available_rooms": {},
#                 "total_results": 0,
#                 "status": "no_room_types",
#                 "message": "No room types are currently available"
#             }
        
#         # === SEARCH AVAILABLE ROOMS ===
#         available_rooms = {}
#         rooms_without_tariff = []
#         rooms_not_matching_guests = []
        
#         for room_type in room_types:
#             room_type_name = room_type["name"]
            
#             # === CHECK GUEST CAPACITY ===
#             max_adults = room_type.get("max_adult", 0) or 0
#             max_children = room_type.get("max_child", 0) or 0
#             room_capacity = room_type["capacity"]
            
#             # Calculate total capacity across all requested rooms
#             total_room_capacity = room_capacity * num_rooms
#             total_max_adults = max_adults * num_rooms if max_adults > 0 else float('inf')
#             total_max_children = max_children * num_rooms if max_children > 0 else float('inf')
#             total_guest_count = adults + children
            
#             # Check if total capacity across all rooms can fit guests
#             can_fit = (
#                 total_room_capacity >= total_guest_count and
#                 (max_adults == 0 or total_max_adults >= adults) and
#                 (max_children == 0 or total_max_children >= children)
#             )
            
#             if not can_fit:
#                 capacity_msg = f"capacity {total_room_capacity}"
#                 max_adults_msg = f"{int(total_max_adults)} adults" if total_max_adults != float('inf') else "unlimited adults"
#                 max_children_msg = f"{int(total_max_children)} children" if total_max_children != float('inf') else "unlimited children"
                
#                 error_msg = (
#                     f"{room_type_name}: {num_rooms} room(s) can accommodate max "
#                     f"{max_adults_msg}, {max_children_msg} ({capacity_msg}). "
#                     f"You requested {adults} adults, {children} children."
#                 )
#                 rooms_not_matching_guests.append(error_msg)
#                 continue
            
#             # === COUNT AVAILABLE ROOMS ===
#             # Step 1: Get all vacant rooms of this type
#             total_vacant = frappe.db.count(
#                 "Hotel Room",
#                 filters={
#                     "room_type": room_type_name,
#                     "status": "Vacant",
#                     "maintenance_flag": 0,
#                     "operational_status": "In Service"
#                 }
#             )
            
#             # Step 2: Get rooms with reservations that overlap the requested dates
#             # ✅ FIXED: Only count Vacant rooms (status = 'Vacant')
#             booked_rooms = frappe.db.sql("""
#                 SELECT COUNT(DISTINCT hr.room_number) 
#                 FROM `tabHotel Room Reservation` hr
#                 INNER JOIN `tabHotel Room` room ON hr.room_number = room.name
#                 WHERE room.room_type = %s 
#                 AND room.operational_status = 'In Service'
#                 AND room.status = 'Vacant'
#                 AND hr.status != 'Cancelled'
#                 AND hr.from_date < %s
#                 AND hr.to_date > %s
#             """, (room_type_name, check_out_str, check_in_str))
            
#             booked_count = booked_rooms[0][0] if booked_rooms else 0
            
#             # Step 3: Get rooms with active check-ins during the requested dates
#             # ✅ FIXED: Only count Vacant rooms (status = 'Vacant')
#             checked_in_rooms = frappe.db.sql("""
#                 SELECT COUNT(DISTINCT chkin.room_number)
#                 FROM `tabHotel Room Check In` chkin
#                 INNER JOIN `tabHotel Room` room ON chkin.room_number = room.name
#                 WHERE room.room_type = %s
#                 AND room.operational_status = 'In Service'
#                 AND room.status = 'Vacant'
#                 AND chkin.status IN ('Draft', 'Checked In')
#                 AND DATE(chkin.check_in_datetime) < %s
#                 AND DATE(chkin.expected_check_out_datetime) > %s
#             """, (room_type_name, check_out_str, check_in_str))
            
#             checked_in_count = checked_in_rooms[0][0] if checked_in_rooms else 0
            
#             # Step 4: Get rooms currently held by active temporary bookings
#             # ✅ UPDATED: Query Temporary Booking instead of Hotel Room
#             held_rooms_query = frappe.db.sql("""
#                 SELECT COUNT(DISTINCT tbr.room_number)
#                 FROM `tabTemporary Booking` tb
#                 INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
#                 INNER JOIN `tabHotel Room` room ON tbr.room_number = room.name
#                 WHERE room.room_type = %s
#                 AND room.operational_status = 'In Service'
#                 AND tb.status IN ('Hold', 'Payment Link Generated')
#                 AND tb.payment_status = 'Pending'
#                 AND tb.booking_status = 'Held'
#                 AND tb.hold_expires_at > %s
#             """, (room_type_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
#             held_count = held_rooms_query[0][0] if held_rooms_query else 0
            
#             # Calculate available rooms: total vacant minus booked minus checked-in minus held
#             unavailable_count = booked_count + checked_in_count + held_count
#             available_count = total_vacant - unavailable_count
            
#             # Skip if not enough rooms available
#             if available_count < num_rooms:
#                 continue
            
#             # === CALCULATE PRICING ===
#             price_info = calculate_room_price(
#                 room_type_name, check_in_str, num_nights,
#                 room_capacity, adults, children
#             )
            
#             if not price_info:
#                 rooms_without_tariff.append(room_type_name)
#                 continue
            
#             # Adjust pricing for multiple rooms
#             price_info["price_per_night"] = price_info["price_per_night"] * num_rooms
#             price_info["total_price"] = price_info["total_price"] * num_rooms
            
#             # === GET ROOM DETAILS ===
#             room_list = get_available_room_list_excluding_held(
#                 room_type_name, check_in_str, check_out_str
#             )
            
#             if len(room_list) < num_rooms:
#                 continue
            
#             room_type_doc = frappe.get_doc("Hotel Room Type", room_type_name)
#             room_images = [{"image": row.image, "caption": row.caption} for row in room_type_doc.hotel_room_images]
#             room_amenities = [{"item": row.item, "billable": row.billable} for row in room_type_doc.amenities]
            
#             # === BUILD RESPONSE ===
#             available_rooms[room_type_name] = {
#                 "available_count": available_count,
#                 "requested_count": num_rooms,
#                 "can_fulfill": available_count >= num_rooms,
#                 "available_rooms": room_list[:num_rooms],
#                 "total_available_rooms": len(room_list),
#                 "base_rate": price_info["base_rate"],
#                 "price_per_night": price_info["price_per_night"],
#                 "number_of_nights": num_nights,
#                 "extra_charges": price_info["extra_charges"],
#                 "total_price": price_info["total_price"],
#                 "pricing_breakdown": price_info["breakdown"],
#                 "single_room_capacity": {
#                     "max_adults": max_adults if max_adults > 0 else "Unlimited",
#                     "max_children": max_children if max_children > 0 else "Unlimited",
#                     "base_capacity": room_capacity
#                 },
#                 "total_guest_capacity": {
#                     "max_adults": int(total_max_adults) if total_max_adults != float('inf') else "Unlimited",
#                     "max_children": int(total_max_children) if total_max_children != float('inf') else "Unlimited",
#                     "base_capacity": total_room_capacity,
#                     "number_of_rooms": num_rooms
#                 },
#                 "images": room_images,
#                 "amenities": room_amenities
#             }
        
#         # === BUILD FINAL RESPONSE ===
#         response = {
#             "check_in_date": check_in_str,
#             "check_out_date": check_out_str,
#             "number_of_nights": num_nights,
#             "guests": {
#                 "adults": adults,
#                 "children": children,
#                 "total": adults + children
#             },
#             "rooms_requested": num_rooms,
#             "available_rooms": available_rooms,
#             "total_results": len(available_rooms)
#         }
        
#         # Add warnings
#         if rooms_without_tariff:
#             response["warning_no_tariff"] = (
#                 f"The following room types have no pricing: {', '.join(rooms_without_tariff)}"
#             )
        
#         if rooms_not_matching_guests:
#             response["warning_guest_mismatch"] = (
#                 f"Capacity mismatch: {'; '.join(rooms_not_matching_guests)}"
#             )
        
#         # Set status
#         if not available_rooms:
#             response["status"] = "no_availability"
#             response["message"] = "No rooms available for your dates"
#         else:
#             response["status"] = "success"
        
#         return response
    
#     except frappe.ValidationError as e:
#         frappe.throw(str(e))
#     except ValueError as e:
#         frappe.throw(f"Invalid date format. Use YYYY-MM-DD: {str(e)}")
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Search Available Rooms Error")
#         frappe.throw(f"Error: {str(e)}")


# def get_available_room_list_excluding_held(room_type, check_in_date, check_out_date):
#     """
#     Get available rooms of a type, EXCLUDING rooms held by active temporary bookings.
#     Returns list of room objects with numbers, capacity, floor info.
#     ✅ UPDATED: Uses Temporary Booking for hold status instead of Hotel Room
#     """
#     try:
#         current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
#         rooms = frappe.db.sql("""
#             SELECT 
#                 room.name as room_number,
#                 room.capacity,
#                 room.floor,
#                 room.room_type
#             FROM `tabHotel Room` room
#             WHERE room.room_type = %s
#             AND room.operational_status = 'In Service'
#             AND room.status = 'Vacant'
#             AND room.maintenance_flag = 0
#             -- EXCLUDE rooms held by active temporary bookings
#             AND NOT EXISTS (
#                 SELECT 1 FROM `tabTemporary Booking` tb
#                 INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
#                 WHERE tbr.room_number = room.name
#                 AND tb.status IN ('Hold', 'Payment Link Generated')
#                 AND tb.payment_status = 'Pending'
#                 AND tb.booking_status = 'Held'
#                 AND tb.hold_expires_at > %s
#             )
#             -- EXCLUDE booked rooms
#             AND NOT EXISTS (
#                 SELECT 1 FROM `tabHotel Room Reservation` res
#                 WHERE res.room_number = room.name
#                 AND res.status != 'Cancelled'
#                 AND res.from_date < %s
#                 AND res.to_date > %s
#             )
#             -- EXCLUDE checked-in rooms
#             AND NOT EXISTS (
#                 SELECT 1 FROM `tabHotel Room Check In` chkin
#                 WHERE chkin.room_number = room.name
#                 AND chkin.status IN ('Draft', 'Checked In')
#                 AND DATE(chkin.check_in_datetime) < %s
#                 AND DATE(chkin.expected_check_out_datetime) > %s
#             )
#             ORDER BY room.name ASC
#         """, (room_type, current_time, check_out_date, check_in_date, check_out_date, check_in_date), as_dict=True)
        
#         return [{"room_number": r["room_number"], "capacity": r["capacity"], "floor": r["floor"]} for r in rooms]
    
#     except Exception as e:
#         frappe.log_error(f"Error getting available rooms: {str(e)}")
#         return []


# @frappe.whitelist(allow_guest=True)
# def get_room_type_info(room_type):
#     """Get detailed information about a specific room type."""
#     try:
#         details = get_room_type_details(room_type)
#         return {"success": True, "room_type": details}
#     except frappe.ValidationError as e:
#         frappe.throw(str(e))
#     except Exception as e:
#         frappe.throw(f"Error: {str(e)}")


# @frappe.whitelist(allow_guest=True)
# def get_room_pricing_for_dates(room_type, check_in_date, check_out_date, num_rooms=1):
#     """Get pricing breakdown for a room type for specific dates."""
#     try:
#         num_rooms = int(num_rooms) if num_rooms else 1
        
#         check_in_str, check_in = parse_date(check_in_date, "check_in_date")
#         check_out_str, check_out = parse_date(check_out_date, "check_out_date")
#         num_nights = validate_date_range(check_in, check_out)
        
#         tariff = get_room_tariff(room_type, check_in_str)
#         if not tariff:
#             raise frappe.ValidationError(f"No tariff found for {room_type}")
        
#         base_rate = float(tariff["rate_amount"])
#         single_room_total = base_rate * num_nights
#         total_price = single_room_total * num_rooms
#         breakdown = get_pricing_breakdown(room_type, check_in_str, check_out_str, base_rate)
        
#         return {
#             "success": True,
#             "room_type": room_type,
#             "check_in_date": check_in_str,
#             "check_out_date": check_out_str,
#             "number_of_nights": num_nights,
#             "number_of_rooms": num_rooms,
#             "base_rate": base_rate,
#             "single_room_total": single_room_total,
#             "total_price": total_price,
#             "breakdown": breakdown
#         }
    
#     except frappe.ValidationError as e:
#         frappe.throw(str(e))
#     except Exception as e:
#         frappe.throw(f"Error: {str(e)}")


# @frappe.whitelist(allow_guest=True)
# def get_occupancy_status(check_in_date=None):
#     """Get occupancy status for a specific date."""
#     try:
#         from frappe.utils import getdate
        
#         if not check_in_date:
#             check_date = getdate()
#         else:
#             _, check_date = parse_date(check_in_date, "check_date")
        
#         total_rooms = frappe.db.count("Hotel Room", filters={"operational_status": "In Service"})
        
#         occupied = frappe.db.sql("""
#             SELECT COUNT(DISTINCT hr.room_number) 
#             FROM `tabHotel Room Reservation` hr
#             WHERE hr.status != 'Cancelled'
#             AND hr.from_date <= %s
#             AND hr.to_date > %s
#         """, (check_date.strftime("%Y-%m-%d"), check_date.strftime("%Y-%m-%d")))
        
#         occupied_count = occupied[0][0] if occupied else 0
#         occupancy_rate = (occupied_count / total_rooms * 100) if total_rooms > 0 else 0
        
#         return {
#             "success": True,
#             "date": check_date.strftime("%Y-%m-%d"),
#             "total_rooms": total_rooms,
#             "occupied_rooms": occupied_count,
#             "vacant_rooms": total_rooms - occupied_count,
#             "occupancy_rate": round(occupancy_rate, 2)
#         }
    
#     except Exception as e:
#         return {"success": False, "error": str(e)}










"""
Hotel Search - Available Rooms Module
Handles room availability search with proper hold validation
FIXED: Only subtract checked-in/booked rooms that are actually Vacant
UPDATED: Uses get_room_rate instead of get_room_tariff
"""

import frappe
from frappe.utils import getdate
from datetime import datetime, timedelta
from .api import get_room_rate
# Import shared utilities
from .shared_utilities import (
    parse_date,
    validate_date_range,
    validate_guest_count,
    validate_guests_fit_room,
    get_pricing_breakdown,
    calculate_room_price,
    get_available_room_list,
    get_room_type_details,
    get_room_images
)


@frappe.whitelist(allow_guest=True, methods=['POST'])
def search_available_rooms(check_in_date, check_out_date, num_rooms=1, adults=1, children=0):
    """
    Search for available rooms based on dates and guest requirements.
    
    EXCLUDES:
    - Rooms with reservations overlapping requested dates
    - Rooms with active check-ins during requested dates
    - Rooms currently held by active temporary bookings (with Held status)
    - Rooms in maintenance or out of service
    
    Args:
        check_in_date (str): Check-in date (YYYY-MM-DD)
        check_out_date (str): Check-out date (YYYY-MM-DD)
        num_rooms (int): Number of rooms needed
        adults (int): Number of adults
        children (int): Number of children
    
    Returns:
        dict: Available rooms grouped by type with pricing and details
    """
    
    try:
        # === CONVERT AND VALIDATE INPUTS ===
        try:
            num_rooms = int(num_rooms) if num_rooms else 1
            adults = int(adults) if adults else 1
            children = int(children) if children else 0
        except (ValueError, TypeError):
            frappe.throw("Invalid number format for rooms, adults, or children")
        
        if num_rooms < 1:
            frappe.throw("Number of rooms must be at least 1")
        # if num_rooms > 10:
        #     frappe.throw("Maximum 10 rooms per booking")
        
        if adults < 1:
            frappe.throw("Number of adults must be at least 1")
        # if adults > 20:
        #     frappe.throw("Maximum 20 adults per booking")
        
        if children < 0:
            frappe.throw("Number of children cannot be negative")
        # if children > 20:
        #     frappe.throw("Maximum 20 children per booking")
        
        # === PARSE AND VALIDATE DATES ===
        check_in_str, check_in = parse_date(check_in_date, "check_in_date")
        check_out_str, check_out = parse_date(check_out_date, "check_out_date")
        num_nights = validate_date_range(check_in, check_out)
        
        # === GET ROOM TYPES ===
        room_types = frappe.get_all(
            "Hotel Room Type",
            filters={"is_active": 1},
            fields=["name", "capacity", "extra_bed_capacity", "max_adult", "max_child"]
        )
        
        if not room_types:
            return {
                "check_in_date": check_in_str,
                "check_out_date": check_out_str,
                "number_of_nights": num_nights,
                "adults": adults,
                "children": children,
                "rooms_requested": num_rooms,
                "available_rooms": {},
                "total_results": 0,
                "status": "no_room_types",
                "message": "No room types are currently available"
            }
        
        # === SEARCH AVAILABLE ROOMS ===
        available_rooms = {}
        rooms_without_tariff = []
        rooms_not_matching_guests = []
        
        for room_type in room_types:
            room_type_name = room_type["name"]
            
            # === CHECK GUEST CAPACITY ===
            max_adults = room_type.get("max_adult", 0) or 0
            max_children = room_type.get("max_child", 0) or 0
            room_capacity = room_type["capacity"]
            
            # Calculate total capacity across all requested rooms
            total_room_capacity = room_capacity * num_rooms
            total_max_adults = max_adults * num_rooms if max_adults > 0 else float('inf')
            total_max_children = max_children * num_rooms if max_children > 0 else float('inf')
            total_guest_count = adults + children
            
            # Check if total capacity across all rooms can fit guests
            can_fit = (
                total_room_capacity >= total_guest_count and
                (max_adults == 0 or total_max_adults >= adults) and
                (max_children == 0 or total_max_children >= children)
            )
            
            if not can_fit:
                capacity_msg = f"capacity {total_room_capacity}"
                max_adults_msg = f"{int(total_max_adults)} adults" if total_max_adults != float('inf') else "unlimited adults"
                max_children_msg = f"{int(total_max_children)} children" if total_max_children != float('inf') else "unlimited children"
                
                error_msg = (
                    f"{room_type_name}: {num_rooms} room(s) can accommodate max "
                    f"{max_adults_msg}, {max_children_msg} ({capacity_msg}). "
                    f"You requested {adults} adults, {children} children."
                )
                rooms_not_matching_guests.append(error_msg)
                continue
            
            # === COUNT AVAILABLE ROOMS ===
            # Step 1: Get all vacant rooms of this type
            total_vacant = frappe.db.count(
                "Hotel Room",
                filters={
                    "room_type": room_type_name,
                    "status": "Vacant",
                    "maintenance_flag": 0,
                    "operational_status": "In Service"
                }
            )
            
            # Step 2: Get rooms with reservations that overlap the requested dates
            # ✅ FIXED: Only count Vacant rooms (status = 'Vacant')
            booked_rooms = frappe.db.sql("""
                SELECT COUNT(DISTINCT hr.room_number) 
                FROM `tabHotel Room Reservation` hr
                INNER JOIN `tabHotel Room` room ON hr.room_number = room.name
                WHERE room.room_type = %s 
                AND room.operational_status = 'In Service'
                AND room.status = 'Vacant'
                AND hr.status != 'Cancelled'
                AND hr.from_date < %s
                AND hr.to_date > %s
            """, (room_type_name, check_out_str, check_in_str))
            
            booked_count = booked_rooms[0][0] if booked_rooms else 0
            
            # Step 3: Get rooms with active check-ins during the requested dates
            # ✅ FIXED: Only count Vacant rooms (status = 'Vacant')
            checked_in_rooms = frappe.db.sql("""
                SELECT COUNT(DISTINCT chkin.room_number)
                FROM `tabHotel Room Check In` chkin
                INNER JOIN `tabHotel Room` room ON chkin.room_number = room.name
                WHERE room.room_type = %s
                AND room.operational_status = 'In Service'
                AND room.status = 'Vacant'
                AND chkin.status IN ('Draft', 'Checked In')
                AND DATE(chkin.check_in_datetime) < %s
                AND DATE(chkin.expected_check_out_datetime) > %s
            """, (room_type_name, check_out_str, check_in_str))
            
            checked_in_count = checked_in_rooms[0][0] if checked_in_rooms else 0
            
            # Step 4: Get rooms currently held by active temporary bookings
            # ✅ UPDATED: Query Temporary Booking instead of Hotel Room
            held_rooms_query = frappe.db.sql("""
                SELECT COUNT(DISTINCT tbr.room_number)
                FROM `tabTemporary Booking` tb
                INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
                INNER JOIN `tabHotel Room` room ON tbr.room_number = room.name
                WHERE room.room_type = %s
                AND room.operational_status = 'In Service'
                AND tb.status IN ('Hold', 'Payment Link Generated')
                AND tb.payment_status = 'Pending'
                AND tb.booking_status = 'Held'
                AND tb.hold_expires_at > %s
            """, (room_type_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            held_count = held_rooms_query[0][0] if held_rooms_query else 0
            
            # Calculate available rooms: total vacant minus booked minus checked-in minus held
            unavailable_count = booked_count + checked_in_count + held_count
            available_count = total_vacant - unavailable_count
            
            # Skip if not enough rooms available
            if available_count < num_rooms:
                continue
            
            # === CALCULATE PRICING ===
            price_info = calculate_room_price(
                room_type_name, check_in_str, num_nights,
                room_capacity, adults, children
            )
            
            if not price_info:
                rooms_without_tariff.append(room_type_name)
                continue
            
            # Adjust pricing for multiple rooms
            price_info["price_per_night"] = price_info["price_per_night"] * num_rooms
            price_info["total_price"] = price_info["total_price"] * num_rooms
            
            # === GET ROOM DETAILS ===
            room_list = get_available_room_list_excluding_held(
                room_type_name, check_in_str, check_out_str
            )
            
            if len(room_list) < num_rooms:
                continue
            
            room_type_doc = frappe.get_doc("Hotel Room Type", room_type_name)
            room_images = [{"image": row.image, "caption": row.caption} for row in room_type_doc.hotel_room_images]
            room_amenities = [{"item": row.item, "billable": row.billable} for row in room_type_doc.amenities]
            
            # === BUILD RESPONSE ===
            available_rooms[room_type_name] = {
                "available_count": available_count,
                "requested_count": num_rooms,
                "can_fulfill": available_count >= num_rooms,
                "available_rooms": room_list[:num_rooms],
                "total_available_rooms": len(room_list),
                "base_rate": price_info["base_rate"],
                "price_per_night": price_info["price_per_night"],
                "number_of_nights": num_nights,
                "extra_charges": price_info["extra_charges"],
                "total_price": price_info["total_price"],
                "pricing_breakdown": price_info["breakdown"],
                "single_room_capacity": {
                    "max_adults": max_adults if max_adults > 0 else "Unlimited",
                    "max_children": max_children if max_children > 0 else "Unlimited",
                    "base_capacity": room_capacity
                },
                "total_guest_capacity": {
                    "max_adults": int(total_max_adults) if total_max_adults != float('inf') else "Unlimited",
                    "max_children": int(total_max_children) if total_max_children != float('inf') else "Unlimited",
                    "base_capacity": total_room_capacity,
                    "number_of_rooms": num_rooms
                },
                "images": room_images,
                "amenities": room_amenities
            }
        
        # === BUILD FINAL RESPONSE ===
        response = {
            "check_in_date": check_in_str,
            "check_out_date": check_out_str,
            "number_of_nights": num_nights,
            "guests": {
                "adults": adults,
                "children": children,
                "total": adults + children
            },
            "rooms_requested": num_rooms,
            "available_rooms": available_rooms,
            "total_results": len(available_rooms)
        }
        
        # Add warnings
        if rooms_without_tariff:
            response["warning_no_tariff"] = (
                f"The following room types have no pricing: {', '.join(rooms_without_tariff)}"
            )
        
        if rooms_not_matching_guests:
            response["warning_guest_mismatch"] = (
                f"Capacity mismatch: {'; '.join(rooms_not_matching_guests)}"
            )
        
        # Set status
        if not available_rooms:
            response["status"] = "no_availability"
            response["message"] = "No rooms available for your dates"
        else:
            response["status"] = "success"
        
        return response
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except ValueError as e:
        frappe.throw(f"Invalid date format. Use YYYY-MM-DD: {str(e)}")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Search Available Rooms Error")
        frappe.throw(f"Error: {str(e)}")


def get_available_room_list_excluding_held(room_type, check_in_date, check_out_date):
    """
    Get available rooms of a type, EXCLUDING rooms held by active temporary bookings.
    Returns list of room objects with numbers, capacity, floor info.
    ✅ UPDATED: Uses Temporary Booking for hold status instead of Hotel Room
    """
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        rooms = frappe.db.sql("""
            SELECT 
                room.name as room_number,
                room.capacity,
                room.floor,
                room.room_type
            FROM `tabHotel Room` room
            WHERE room.room_type = %s
            AND room.operational_status = 'In Service'
            AND room.status = 'Vacant'
            AND room.maintenance_flag = 0
            -- EXCLUDE rooms held by active temporary bookings
            AND NOT EXISTS (
                SELECT 1 FROM `tabTemporary Booking` tb
                INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
                WHERE tbr.room_number = room.name
                AND tb.status IN ('Hold', 'Payment Link Generated')
                AND tb.payment_status = 'Pending'
                AND tb.booking_status = 'Held'
                AND tb.hold_expires_at > %s
            )
            -- EXCLUDE booked rooms
            AND NOT EXISTS (
                SELECT 1 FROM `tabHotel Room Reservation` res
                WHERE res.room_number = room.name
                AND res.status != 'Cancelled'
                AND res.from_date < %s
                AND res.to_date > %s
            )
            -- EXCLUDE checked-in rooms
            AND NOT EXISTS (
                SELECT 1 FROM `tabHotel Room Check In` chkin
                WHERE chkin.room_number = room.name
                AND chkin.status IN ('Draft', 'Checked In')
                AND DATE(chkin.check_in_datetime) < %s
                AND DATE(chkin.expected_check_out_datetime) > %s
            )
            ORDER BY room.name ASC
        """, (room_type, current_time, check_out_date, check_in_date, check_out_date, check_in_date), as_dict=True)
        
        return [{"room_number": r["room_number"], "capacity": r["capacity"], "floor": r["floor"]} for r in rooms]
    
    except Exception as e:
        frappe.log_error(f"Error getting available rooms: {str(e)}")
        return []


@frappe.whitelist(allow_guest=True)
def get_room_type_info(room_type):
    """Get detailed information about a specific room type."""
    try:
        details = get_room_type_details(room_type)
        return {"success": True, "room_type": details}
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist(allow_guest=True)
def get_room_pricing_for_dates(room_type, check_in_date, check_out_date, num_rooms=1):
    """Get pricing breakdown for a room type for specific dates."""
    try:
        num_rooms = int(num_rooms) if num_rooms else 1
        
        check_in_str, check_in = parse_date(check_in_date, "check_in_date")
        check_out_str, check_out = parse_date(check_out_date, "check_out_date")
        num_nights = validate_date_range(check_in, check_out)
        
        # ✅ UPDATED: Using get_room_rate (returns number)
        rate_amount = get_room_rate(room_type, check_in_date=check_in_str)
        if not rate_amount or rate_amount == 0:
            raise frappe.ValidationError(f"No tariff found for {room_type}")
        
        base_rate = float(rate_amount)
        single_room_total = base_rate * num_nights
        total_price = single_room_total * num_rooms
        breakdown = get_pricing_breakdown(room_type, check_in_str, check_out_str, base_rate)
        
        return {
            "success": True,
            "room_type": room_type,
            "check_in_date": check_in_str,
            "check_out_date": check_out_str,
            "number_of_nights": num_nights,
            "number_of_rooms": num_rooms,
            "base_rate": base_rate,
            "single_room_total": single_room_total,
            "total_price": total_price,
            "breakdown": breakdown
        }
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist(allow_guest=True)
def get_occupancy_status(check_in_date=None):
    """Get occupancy status for a specific date."""
    try:
        from frappe.utils import getdate
        
        if not check_in_date:
            check_date = getdate()
        else:
            _, check_date = parse_date(check_in_date, "check_date")
        
        total_rooms = frappe.db.count("Hotel Room", filters={"operational_status": "In Service"})
        
        occupied = frappe.db.sql("""
            SELECT COUNT(DISTINCT hr.room_number) 
            FROM `tabHotel Room Reservation` hr
            WHERE hr.status != 'Cancelled'
            AND hr.from_date <= %s
            AND hr.to_date > %s
        """, (check_date.strftime("%Y-%m-%d"), check_date.strftime("%Y-%m-%d")))
        
        occupied_count = occupied[0][0] if occupied else 0
        occupancy_rate = (occupied_count / total_rooms * 100) if total_rooms > 0 else 0
        
        return {
            "success": True,
            "date": check_date.strftime("%Y-%m-%d"),
            "total_rooms": total_rooms,
            "occupied_rooms": occupied_count,
            "vacant_rooms": total_rooms - occupied_count,
            "occupancy_rate": round(occupancy_rate, 2)
        }
    
    except Exception as e:
        return {"success": False, "error": str(e)}