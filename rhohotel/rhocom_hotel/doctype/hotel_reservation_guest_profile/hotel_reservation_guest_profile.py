# Hotel Reservation Guest Profile - Backend API
# File: rhohotel/rhohotel/hotel_reservation_guest_profile.py

import frappe
from frappe.utils import nowdate, getdate
from datetime import datetime
import json


from frappe.model.document import Document


class HotelReservationGuestProfile(Document):
	pass

@frappe.whitelist()
def create_guest_profile(hotel_reservation, first_name, last_name, email=None, phone=None, 
                         adults=1, children=0, special_requests=None, dietary_requirements=None,
                         id_type=None, id_number=None, address_line1=None, city=None, country=None):
    """
    Create a Hotel Reservation Guest Profile for a guest.
    
    This is called when guest details are collected for check-in.
    
    Args:
        hotel_reservation (str): Hotel Room Reservation name/ID
        first_name (str): Guest first name
        last_name (str): Guest last name
        email (str): Guest email
        phone (str): Guest phone
        adults (int): Number of adults (default 1)
        children (int): Number of children (default 0)
        special_requests (str): Special requests
        dietary_requirements (str): Dietary requirements
        id_type (str): Type of ID (Passport, License, etc.)
        id_number (str): ID number
        address_line1 (str): Address
        city (str): City
        country (str): Country
    
    Returns:
        dict: Created profile details
    """
    
    try:
        # Get reservation details
        reservation = frappe.get_doc("Hotel Room Reservation", hotel_reservation)
        
        if not reservation:
            raise frappe.ValidationError(f"Hotel Room Reservation {hotel_reservation} not found")
        
        # Check if profile already exists for this reservation
        existing_profile = frappe.db.get_value(
            "Hotel Reservation Guest Profile",
            {"hotel_reservation": hotel_reservation}
        )
        
        if existing_profile:
            # Update existing profile
            profile = frappe.get_doc("Hotel Reservation Guest Profile", existing_profile)
        else:
            # Create new profile
            profile = frappe.get_doc({
                "doctype": "Hotel Reservation Guest Profile",
                "hotel_reservation": hotel_reservation,
            })
        
        # Set/Update fields
        profile.first_name = first_name
        profile.last_name = last_name
        profile.email = email or ""
        profile.phone = phone or ""
        profile.adults = adults
        profile.children = children
        profile.special_requests = special_requests or ""
        profile.dietary_requirements = dietary_requirements or "None"
        profile.id_type = id_type or ""
        profile.id_number = id_number or ""
        profile.address_line1 = address_line1 or ""
        profile.city = city or ""
        profile.country = country or ""
        
        # Get details from reservation
        profile.room_number = reservation.room_number
        profile.check_in_date = reservation.from_date
        profile.check_out_date = reservation.to_date
        profile.booking_number = reservation.booking_number or ""
        profile.payment_status = reservation.payment_status or "Pending"
        
        # Get guest count from booking
        if reservation.booking_number:
            booking_details = frappe.db.get_value(
                "Hotel Booking",
                reservation.booking_number,
                ["total_rooms", "total_price"]
            )
            if booking_details:
                profile.guest_count = booking_details[0]
                profile.paid_amount = booking_details[1]
        
        # Link to Contact if exists
        if email:
            contact = frappe.db.get_value(
                "Contact",
                {"email_id": email}
            )
            if contact:
                profile.contact_link = contact
        
        # Link to Customer if exists
        if email:
            customer = frappe.db.get_value(
                "Customer",
                {"email_id": email}
            )
            if customer:
                profile.customer_link = customer
        
        profile.created_at = datetime.now()
        profile.created_by_user = frappe.session.user
        
        profile.save()
        frappe.db.commit()
        
        return {
            "success": True,
            "profile_id": profile.name,
            "message": f"Guest profile created for {first_name} {last_name}"
        }
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.log_error(f"Error creating guest profile: {str(e)}")
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def auto_create_guest_profile(hotel_reservation):
    """
    Automatically create guest profile from reservation data.
    Called after reservation is created and before check-in.
    
    Args:
        hotel_reservation (str): Hotel Room Reservation name/ID
    
    Returns:
        dict: Created profile
    """
    
    try:
        reservation = frappe.get_doc("Hotel Room Reservation", hotel_reservation)
        
        # Create profile with basic info from reservation
        profile = frappe.get_doc({
            "doctype": "Hotel Reservation Guest Profile",
            "hotel_reservation": hotel_reservation,
            "first_name": reservation.guest_name.split()[0] if reservation.guest_name else "Guest",
            "last_name": reservation.guest_name.split()[1] if reservation.guest_name and len(reservation.guest_name.split()) > 1 else "",
            "room_number": reservation.room_number,
            "check_in_date": reservation.from_date,
            "check_out_date": reservation.to_date,
            "booking_number": reservation.booking_number or "",
            "payment_status": reservation.payment_status or "Pending",
            "adults": 1,
            "children": 0,
            "created_at": datetime.now(),
            "created_by_user": frappe.session.user,
        })
        
        profile.insert()
        frappe.db.commit()
        
        return {
            "success": True,
            "profile_id": profile.name
        }
    
    except Exception as e:
        frappe.log_error(f"Error auto-creating guest profile: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_guest_profile_on_checkin(profile_id, check_in_time=None):
    """
    Update guest profile when guest checks in.
    
    Args:
        profile_id (str): Hotel Reservation Guest Profile ID
        check_in_time (str): Check-in timestamp (optional, defaults to now)
    
    Returns:
        dict: Updated profile
    """
    
    try:
        profile = frappe.get_doc("Hotel Reservation Guest Profile", profile_id)
        
        if profile.is_checked_in:
            raise frappe.ValidationError("Guest already checked in")
        
        profile.is_checked_in = 1
        profile.check_in_time = check_in_time or datetime.now()
        profile.save()
        frappe.db.commit()
        
        # Send notification to housekeeping
        send_housekeeping_notification(profile, "Check-In")
        
        return {
            "success": True,
            "message": f"{profile.first_name} {profile.last_name} checked in"
        }
    
    except Exception as e:
        frappe.log_error(f"Error checking in guest: {str(e)}")
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def update_guest_profile_on_checkout(profile_id, check_out_time=None):
    """
    Update guest profile when guest checks out.
    
    Args:
        profile_id (str): Hotel Reservation Guest Profile ID
        check_out_time (str): Check-out timestamp (optional, defaults to now)
    
    Returns:
        dict: Updated profile
    """
    
    try:
        profile = frappe.get_doc("Hotel Reservation Guest Profile", profile_id)
        
        if not profile.is_checked_in:
            raise frappe.ValidationError("Guest not checked in yet")
        
        if profile.is_checked_out:
            raise frappe.ValidationError("Guest already checked out")
        
        profile.is_checked_out = 1
        profile.check_out_time = check_out_time or datetime.now()
        profile.save()
        frappe.db.commit()
        
        # Send notification to housekeeping
        send_housekeeping_notification(profile, "Check-Out")
        
        # Update room status
        update_room_status_after_checkout(profile.room_number)
        
        return {
            "success": True,
            "message": f"{profile.first_name} {profile.last_name} checked out"
        }
    
    except Exception as e:
        frappe.log_error(f"Error checking out guest: {str(e)}")
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def get_guest_profile_by_reservation(hotel_reservation):
    """
    Get guest profile for a specific reservation.
    
    Args:
        hotel_reservation (str): Hotel Room Reservation ID
    
    Returns:
        dict: Guest profile data
    """
    
    try:
        profile_name = frappe.db.get_value(
            "Hotel Reservation Guest Profile",
            {"hotel_reservation": hotel_reservation}
        )
        
        if profile_name:
            profile = frappe.get_doc("Hotel Reservation Guest Profile", profile_name)
            return {
                "success": True,
                "profile": profile.as_dict()
            }
        else:
            return {
                "success": False,
                "message": "No guest profile found for this reservation"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def get_guest_profiles_for_checkin(date=None):
    """
    Get all guest profiles that need check-in for a specific date.
    
    Args:
        date (str): Date to check (format YYYY-MM-DD, defaults to today)
    
    Returns:
        list: Guest profiles pending check-in
    """
    
    try:
        if not date:
            date = nowdate()
        
        profiles = frappe.db.get_list(
            "Hotel Reservation Guest Profile",
            filters={
                "check_in_date": date,
                "is_checked_in": 0,
                "is_checked_out": 0
            },
            fields=["name", "first_name", "last_name", "room_number", "email", "phone", "adults", "children"],
            order_by="created_at asc"
        )
        
        return {
            "success": True,
            "count": len(profiles),
            "profiles": profiles
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def get_guest_profiles_for_checkout(date=None):
    """
    Get all guest profiles that need check-out for a specific date.
    
    Args:
        date (str): Date to check (format YYYY-MM-DD, defaults to today)
    
    Returns:
        list: Guest profiles pending check-out
    """
    
    try:
        if not date:
            date = nowdate()
        
        profiles = frappe.db.get_list(
            "Hotel Reservation Guest Profile",
            filters={
                "check_out_date": date,
                "is_checked_in": 1,
                "is_checked_out": 0
            },
            fields=["name", "first_name", "last_name", "room_number", "email", "phone"],
            order_by="created_at asc"
        )
        
        return {
            "success": True,
            "count": len(profiles),
            "profiles": profiles
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def send_housekeeping_notification(profile, event_type):
    """
    Send notification to housekeeping team on check-in/check-out.
    
    Args:
        profile: Hotel Reservation Guest Profile doc
        event_type: "Check-In" or "Check-Out"
    """
    
    try:
        # Get housekeeping role users
        users = frappe.db.get_list(
            "User",
            filters={"roles": "Hotel Housekeeping"}
        )
        
        if users:
            message = f"""
            <h4>{event_type} Notification</h4>
            <p><strong>Guest:</strong> {profile.first_name} {profile.last_name}</p>
            <p><strong>Room:</strong> {profile.room_number}</p>
            <p><strong>Event:</strong> {event_type}</p>
            <p><strong>Special Requests:</strong> {profile.special_requests or 'None'}</p>
            <p><strong>Dietary Requirements:</strong> {profile.dietary_requirements or 'None'}</p>
            <p><strong>Mobility Assistance:</strong> {profile.mobility_assistance or 'No'}</p>
            """
            
            for user in users:
                frappe.sendmail(
                    recipients=[user.email],
                    subject=f"Guest {event_type} - Room {profile.room_number}",
                    message=message
                )
    
    except Exception as e:
        frappe.log_error(f"Error sending housekeeping notification: {str(e)}")


def update_room_status_after_checkout(room_number):
    """
    Update room status to Vacant and mark for housekeeping after check-out.
    
    Args:
        room_number (str): Room number
    """
    
    try:
        room = frappe.get_doc("Hotel Room", room_number)
        room.status = "Vacant"
        room.booking_status = "Available"
        room.housekeeping_status = "Dirty"  # Mark for cleaning
        room.save()
        frappe.db.commit()
    
    except Exception as e:
        frappe.log_error(f"Error updating room status: {str(e)}")


# ============================================================================
# AUTO-CREATE GUEST PROFILE TRIGGER
# ============================================================================

def auto_create_on_reservation_creation(doc, method=None):
    """
    Automatically create guest profile when Hotel Room Reservation is created.
    
    Add this to Hotel Room Reservation DocType:
    doc_events:
        after_insert: rhohotel.rhohotel.hotel_reservation_guest_profile.auto_create_on_reservation_creation
    """
    
    try:
        if doc.doctype == "Hotel Room Reservation" and not doc.get("__islocal"):
            # Auto-create guest profile
            auto_create_guest_profile(doc.name)
    
    except Exception as e:
        frappe.log_error(f"Error in auto_create_on_reservation_creation: {str(e)}")


def update_guest_profile_on_payment(doc, method=None):
    """
    Update guest profile when payment is confirmed.
    
    Add this to Hotel Booking DocType:
    doc_events:
        before_save: rhohotel.rhohotel.hotel_reservation_guest_profile.update_guest_profile_on_payment
    """
    
    try:
        if doc.doctype == "Hotel Booking" and doc.payment_status == "Paid":
            # Update all associated guest profiles with customer link
            if doc.customer:
                reservations = frappe.get_all(
                    "Hotel Room Reservation",
                    filters={"booking_number": doc.booking_number},
                    fields=["name"]
                )
                
                for res in reservations:
                    profile = frappe.db.get_value(
                        "Hotel Reservation Guest Profile",
                        {"hotel_reservation": res.name}
                    )
                    
                    if profile:
                        profile_doc = frappe.get_doc("Hotel Reservation Guest Profile", profile)
                        profile_doc.customer_link = doc.customer
                        profile_doc.payment_status = "Paid"
                        profile_doc.save()
    
    except Exception as e:
        frappe.log_error(f"Error in update_guest_profile_on_payment: {str(e)}")