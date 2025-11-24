# """
# Background Jobs for Hotel Booking System
# Handles automatic cleanup of expired temporary bookings
# """

# import frappe
# from datetime import datetime


# @frappe.whitelist()
# def clear_expired_temporary_bookings():
#     """
#     Clear (delete or mark as expired) temporary bookings that:
#     - Are in 'Hold' or 'Payment Link Generated' status
#     - Have hold_expires_at time in the past (expired)
#     - Have not been converted to Hotel Room Reservation
    
#     This job runs every 5 minutes
#     """
    
#     try:
#         current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
#         print(f"\n[{current_time}] Starting: Clear Expired Temporary Bookings")
        
#         # Find expired temporary bookings
#         expired_bookings = frappe.db.sql("""
#             SELECT name, booking_status, hold_expires_at
#             FROM `tabTemporary Booking`
#             WHERE status IN ('Hold', 'Payment Link Generated')
#             AND payment_status = 'Pending'
#             AND booking_status = 'Held'
#             AND hold_expires_at < %s
#         """, (current_time,), as_dict=True)
        
#         print(f"Found {len(expired_bookings)} expired temporary bookings")
        
#         expired_count = 0
        
#         for booking in expired_bookings:
#             try:
#                 # Get the booking document
#                 tb_doc = frappe.get_doc("Temporary Booking", booking['name'])
                
#                 # Log before deletion
#                 frappe.logger().info(f"Clearing expired temporary booking: {booking['name']} (expired at {booking['hold_expires_at']})")
                
#                 # Option 1: Mark as Expired (keeps record)
#                 tb_doc.status = 'Expired'
#                 tb_doc.booking_status = 'Expired'
#                 tb_doc.save(ignore_permissions=True)
                
#                 # Also release the held rooms
#                 held_rooms = frappe.db.sql("""
#                     SELECT room_number FROM `tabTemporary Booking Room`
#                     WHERE parent = %s
#                 """, (booking['name'],), as_dict=True)
                
#                 for room in held_rooms:
#                     # Get the room and release the hold
#                     room_doc = frappe.get_doc("Hotel Room", room['room_number'])
#                     room_doc.booking_status = ''
#                     room_doc.hold_expires_at = None
#                     room_doc.save(ignore_permissions=True)
                
#                 expired_count += 1
#                 print(f"  ✓ Cleared: {booking['name']}")
                
#             except Exception as e:
#                 frappe.logger().error(f"Error clearing temporary booking {booking['name']}: {str(e)}")
#                 print(f"  ✗ Error: {booking['name']} - {str(e)}")
        
#         print(f"\nCompleted: {expired_count} temporary bookings cleared")
        
#         # Log summary
#         frappe.logger().info(f"Cleared {expired_count} expired temporary bookings at {current_time}")
        
#         return {
#             "status": "success",
#             "cleared_count": expired_count,
#             "timestamp": current_time
#         }
        
#     except Exception as e:
#         error_msg = f"Error in clear_expired_temporary_bookings: {str(e)}"
#         frappe.logger().error(error_msg)
#         frappe.log_error(frappe.get_traceback(), "Clear Expired Temporary Bookings Error")
        
#         return {
#             "status": "error",
#             "message": error_msg
#         }


# @frappe.whitelist()
# def cleanup_expired_booking_rooms():
#     """
#     Clean up room holds for any temporary bookings that have expired
#     Called as a secondary cleanup job
#     """
    
#     try:
#         current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
#         # Find rooms with expired holds
#         expired_holds = frappe.db.sql("""
#             SELECT DISTINCT room.name, room.booking_status, room.hold_expires_at
#             FROM `tabHotel Room` room
#             WHERE room.booking_status = 'Held'
#             AND room.hold_expires_at IS NOT NULL
#             AND room.hold_expires_at < %s
#         """, (current_time,), as_dict=True)
        
#         print(f"Found {len(expired_holds)} rooms with expired holds")
        
#         for room in expired_holds:
#             try:
#                 room_doc = frappe.get_doc("Hotel Room", room['name'])
#                 room_doc.booking_status = ''
#                 room_doc.hold_expires_at = None
#                 room_doc.save(ignore_permissions=True)
#                 print(f"  ✓ Released hold: {room['name']}")
#             except Exception as e:
#                 print(f"  ✗ Error releasing hold on {room['name']}: {str(e)}")
        
#         return {
#             "status": "success",
#             "rooms_released": len(expired_holds)
#         }
        
#     except Exception as e:
#         frappe.logger().error(f"Error in cleanup_expired_booking_rooms: {str(e)}")
#         return {
#             "status": "error",
#             "message": str(e)
#         }
