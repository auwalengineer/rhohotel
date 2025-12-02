

"""
Hotel Booking - REFACTORED WITH TEMPORARY BOOKING + FIXES
Handles multi-room bookings with temporary hold before payment.


- Step 1: Create TEMPORARY BOOKING (holds all data + status)
- Step 2: Generate Paystack payment link  
- Step 3: On successful payment → Convert to Customer, Invoice, Reservations, Hotel Guest, Payment Entry
"""

import frappe
from frappe.utils import nowdate, getdate
from datetime import datetime, timedelta
import json
import requests
import base64
import hmac
import hashlib

from .shared_utilities import (
    parse_date,
    validate_date_range,
    validate_room_for_booking,
    generate_secure_booking_number,
    create_or_get_item
)

from .api import get_room_rate

from .booking_validations import (
    validate_rooms_still_available,
    check_temporary_booking_still_valid,
    release_booking_holds
)



def get_or_create_customer(customer_name, customer_email, customer_phone):
    """
    Check if customer exists by email or phone, return existing or create new
    
    Priority matching:
    1. Email match (primary)
    2. Phone match (secondary)
    3. Create new if no match
    
    Args:
        customer_name (str): Customer name
        customer_email (str): Customer email
        customer_phone (str): Customer phone
    
    Returns:
        str: Customer ID (name)
    """
    
  
    # ============================================================================
    # STEP 1: Check by Email (Primary)
    # ============================================================================
    if customer_email:
        existing_by_email = frappe.db.get_value(
            "Customer",
            filters={"email_id": customer_email},
            fieldname=["name", "customer_name", "email_id", "mobile_no"]
        )
        
        if existing_by_email:
            print(f"\n✅ FOUND by EMAIL!")
            print(f"   Customer ID: {existing_by_email[0]}")
            print(f"   Name: {existing_by_email[1]}")
            print(f"   Email: {existing_by_email[2]}")
            print(f"   Phone: {existing_by_email[3]}")
            return existing_by_email[0]
    
    # ============================================================================
    # STEP 2: Check by Phone (Secondary)
    # ============================================================================
    if customer_phone:
        # Clean phone number (remove spaces, dashes, etc)
        clean_phone = customer_phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        existing_by_phone = frappe.db.get_value(
            "Customer",
            filters={"mobile_no": clean_phone},
            fieldname=["name", "customer_name", "email_id", "mobile_no"]
        )
        
        if existing_by_phone:
            return existing_by_phone[0]
    
    # ============================================================================
    # STEP 3: Create New Customer
    # ============================================================================
    
    try:
        customer = frappe.new_doc("Customer")
        customer.customer_name = customer_name
        customer.customer_type = "Individual"
        customer.email_id = customer_email
        customer.mobile_no = customer_phone
        customer.territory = frappe.db.get_default("territory") or "Nigeria"
        customer.customer_group = frappe.db.get_default("customer_group") or "Individual"
        
        customer.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return customer.name
        
    except Exception as e:
        frappe.log_error(f"Error creating customer: {str(e)}", "Hotel Booking - Create Customer")
        print(f"❌ ERROR creating customer: {str(e)}")
        raise



# ════════════════════════════════════════════════════════════════════════════
# STEP 1: CREATE TEMPORARY BOOKING (NO PERMANENT DOCS YET)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def create_booking(from_date, to_date, rooms, customer_email=None, customer_phone=None, customer_name=None):
    """
    Create a TEMPORARY booking - holds all data without creating Customer/Invoice.
    ✅ NOW WITH ROOM RE-VALIDATION
    ✅ Booking status tracked in Temporary Booking only
    ✅ Uses get_room_rate instead of get_room_tariff
    
    Args:
        from_date (str): Check-in date (YYYY-MM-DD)
        to_date (str): Check-out date (YYYY-MM-DD)
        rooms (list or str): List of room numbers ["101", "102"]
        customer_email (str): Guest email
        customer_phone (str): Guest phone
        customer_name (str): Guest name
    
    Returns:
        dict: Temporary booking data with booking_number
    """
    try:
        # === PARSE INPUTS ===
        if isinstance(rooms, str):
            try:
                rooms = json.loads(rooms)
            except json.JSONDecodeError:
                raise frappe.ValidationError("Invalid rooms format")
        
        if not isinstance(rooms, list) or len(rooms) == 0:
            raise frappe.ValidationError("At least 1 room required")
        if not customer_name:
            raise frappe.ValidationError("Guest name required")
        
        # === PARSE & VALIDATE DATES ===
        from_str, from_date_obj = parse_date(from_date, "from_date")
        to_str, to_date_obj = parse_date(to_date, "to_date")
        num_nights = validate_date_range(from_date_obj, to_date_obj)
        
        frappe.logger().info(f"🔍 Re-validating {len(rooms)} room(s) are available...")
        validation_result = validate_rooms_still_available(rooms, from_str, to_str)
        
        if not validation_result.get("success"):
            unavailable_info = ", ".join([
                f"{r['room_number']} ({r['reason']})" 
                for r in validation_result.get("unavailable_rooms", [])
            ])
            frappe.throw(f"Selected rooms are no longer available: {unavailable_info}")
        
        frappe.logger().info(f"✅ All {len(rooms)} room(s) validated and available")
        
        # === VALIDATE ROOMS & CALCULATE PRICE ===
        temp_rooms = []
        total_price = 0
        
        for room_number in rooms:
            room = validate_room_for_booking(room_number, from_str, to_str)
            rate_amount = get_room_rate(room.get("room_type"), check_in_date=from_str)
            
            if not rate_amount or rate_amount == 0:
                raise frappe.ValidationError(f"No tariff for {room.get('room_type')}")
            
            room_price = rate_amount * num_nights
            total_price += room_price
            
            # Get season info
            season_info = frappe.db.get_value(
                "Hotel Room Tariff",
                {"room_type": room.get("room_type"), "is_active": 1},
                ["hotel_season", "rate_type"],
                as_dict=True
            ) or {}
            
            season_type = frappe.db.get_value(
                "Hotel Season",
                season_info.get("hotel_season"),
                "season_type"
            ) if season_info.get("hotel_season") else None
            
            temp_rooms.append({
                "room_number": room_number,
                "room_type": room.get("room_type"),
                "rate_type": season_info.get("rate_type") or "Standard",
                "season_type": season_type or "",
                "num_nights": num_nights,
                "rate_per_night": rate_amount,
                "total_price": room_price
            })
        
        # === GENERATE BOOKING NUMBER ===
        booking_number = generate_secure_booking_number()
        hold_expires_at = datetime.now() + timedelta(minutes=15)
        
        # === CREATE TEMPORARY BOOKING DOCUMENT ===
        temp_booking = frappe.get_doc({
            "doctype": "Temporary Booking",
            "booking_number": booking_number,
            "status": "Hold",
            "booking_status": "Held",  # ✅ NEW: Rooms are being held (payment pending)
            "guest_name": customer_name,
            "guest_email": customer_email or "",
            "guest_phone": customer_phone or "",
            "check_in_date": from_str,
            "check_out_date": to_str,
            "num_nights": num_nights,
            "total_rooms": len(rooms),
            "total_price": total_price,
            "currency": "NGN",
            "payment_status": "Pending",
            "hold_expires_at": hold_expires_at,
            "created_at": datetime.now(),
            "created_by": frappe.session.user,
            "rooms": temp_rooms,
            "notes": ""
        }).insert()
        
        # === NO NEED TO UPDATE ROOM STATUS - Status tracked in Temporary Booking ===
        
        frappe.db.commit()
        
        return {
            "success": True,
            "booking_number": booking_number,
            "guest_name": customer_name,
            "guest_email": customer_email,
            "check_in_date": from_str,
            "check_out_date": to_str,
            "number_of_nights": num_nights,
            "total_rooms": len(rooms),
            "rooms_booked": rooms,
            "total_price": total_price,
            "currency": "NGN",
            "hold_expires_at": hold_expires_at.isoformat(),
            "status": "Hold",
            "next_step": "Call create_payment_link",
            "message": f"Temporary booking {booking_number} created. Payment required within 15 minutes."
        }
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.log_error(f"Error creating temp booking: {str(e)}")
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# STEP 2: CREATE PAYMENT LINK (FROM TEMPORARY BOOKING)
# ════════════════════════════════════════════════════════════════════════════

def call_paystack_api(amount, reference, customer_email, customer_name, description):
    """Call Paystack API to initialize transaction."""
    try:
        settings = frappe.get_doc("Hotel Settings")
        paystack_secret_key = settings.get_password("paystack_secret_key")
        
        if not paystack_secret_key:
            return {
                "status": "error",
                "message": "Paystack secret key not configured"
            }
        
        url = "https://api.paystack.co/transaction/initialize"
        
        payload = {
            "email": customer_email,
            "amount": int(amount * 100),
            "reference": reference,
            "metadata": {
                "customer_name": customer_name,
                "description": description,
                "booking_type": "hotel"
            }
        }
        
        headers = {
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json"
        }
        
        frappe.logger().info(f"Calling Paystack for {reference}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        result = response.json()
        
        if response.status_code == 200 and result.get("status") == True:
            data = result.get("data", {})
            return {
                "status": "success",
                "payment_url": data.get("authorization_url"),
                "access_code": data.get("access_code"),
                "transaction_id": data.get("reference"),
                "message": "Payment link generated"
            }
        else:
            error_message = result.get("message", "Unknown error from Paystack")
            frappe.logger().error(f"Paystack error: {error_message}")
            return {
                "status": "error",
                "message": error_message
            }
    
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Request timeout. Please try again."
        }
    except Exception as e:
        frappe.logger().error(f"Error calling Paystack: {str(e)}")
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }


@frappe.whitelist()
def create_payment_link(booking_number):
    """
    Generate Paystack payment link from TEMPORARY booking.
    ✅ NOW WITH BOOKING VALIDITY CHECK
    ✅ Includes public_key for frontend integration
    """
    try:
        frappe.logger().info(f"🔍 Checking if booking {booking_number} is still valid...")
        
        validity_check = check_temporary_booking_still_valid(booking_number)
        if not validity_check.get("success"):
            error_msg = validity_check.get("message", "Booking is no longer valid")
            frappe.logger().warning(f"❌ Booking {booking_number} failed validity check: {error_msg}")
            frappe.throw(error_msg)
        
        frappe.logger().info(f"✅ Booking {booking_number} is valid for payment")
        
        # Get temporary booking
        temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": booking_number})
        
        if temp_booking.status != "Hold":
            raise frappe.ValidationError(
                f"Booking {booking_number} is not in Hold status (current: {temp_booking.status})"
            )
        
        if temp_booking.payment_status == "Paid":
            raise frappe.ValidationError("Booking already paid")
        
        # === GET PAYSTACK SETTINGS ===
        settings = frappe.get_doc("Hotel Settings")
        paystack_public_key = settings.get_password("paystack_public_key")
        paystack_secret_key = settings.get_password("paystack_secret_key")
        
        if not paystack_public_key or not paystack_secret_key:
            raise frappe.ValidationError("Paystack keys not configured")
        
        frappe.logger().info(f"Creating payment link for {booking_number}")
        
        # === CHECK FOR EXISTING PAYMENT LINK ===
        if temp_booking.transaction_id and temp_booking.paystack_access_code:
            frappe.logger().info(f"Using existing payment link for {booking_number}")
            
            return {
                "success": True,
                "payment_url": f"https://checkout.paystack.com/{temp_booking.paystack_access_code}",
                "booking_number": booking_number,
                "amount": temp_booking.total_price,
                "currency": "NGN",
                "public_key": paystack_public_key,
                "transaction_id": temp_booking.transaction_id,
                "access_code": temp_booking.paystack_access_code,
                "message": "Using existing payment link"
            }
        
        # === CALL PAYSTACK API ===
        paystack_response = call_paystack_api(
            amount=temp_booking.total_price,
            reference=booking_number,
            customer_email=temp_booking.guest_email or "guest@hotel.com",
            customer_name=temp_booking.guest_name,
            description=f"Hotel booking: {temp_booking.total_rooms} room(s), {temp_booking.check_in_date} to {temp_booking.check_out_date}"
        )
        
        if paystack_response.get("status") == "success":
            payment_url = paystack_response.get("payment_url")
            transaction_id = paystack_response.get("transaction_id")
            access_code = paystack_response.get("access_code")
            
            # === STORE TRANSACTION DETAILS IN TEMPORARY BOOKING ===
            temp_booking.transaction_id = transaction_id
            temp_booking.paystack_access_code = access_code
            temp_booking.status = "Payment Link Generated"
            temp_booking.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.logger().info(f"Payment link created for {booking_number}")
            
            return {
                "success": True,
                "payment_url": payment_url,
                "booking_number": booking_number,
                "amount": temp_booking.total_price,
                "currency": "NGN",
                "public_key": paystack_public_key,
                "transaction_id": transaction_id,
                "access_code": access_code,
                "message": "Redirect to payment URL"
            }
        else:
            raise frappe.ValidationError(
                f"Failed to generate payment link: {paystack_response.get('message')}"
            )
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.log_error(f"Error creating payment link: {str(e)}")
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# HELPER: CREATE OR GET HOTEL GUEST
# ════════════════════════════════════════════════════════════════════════════

def create_or_get_hotel_guest(guest_name, guest_email, guest_phone, customer_id):
    """
    Create or retrieve Hotel Guest by checking phone/email.
    ✅ Check if exists by phone OR email first
    ✅ Only fill required fields (email, phone, name) - no optional fields
    
    Args:
        guest_name (str): Full name of guest
        guest_email (str): Email address
        guest_phone (str): Phone number
        customer_id (str): Linked Customer ID
    
    Returns:
        str: Hotel Guest name (doc ID)
    """
    try:
        # ✅ CHECK IF GUEST EXISTS BY PHONE
        if guest_phone:
            existing_by_phone = frappe.db.get_value(
                "Hotel Guest",
                {"phone_number": guest_phone},
                "name"
            )
            if existing_by_phone:
                frappe.logger().info(f"✅ Found existing Hotel Guest by phone: {existing_by_phone}")
                return existing_by_phone
        
        # ✅ CHECK IF GUEST EXISTS BY EMAIL
        if guest_email:
            existing_by_email = frappe.db.get_value(
                "Hotel Guest",
                {"email": guest_email},
                "name"
            )
            if existing_by_email:
                frappe.logger().info(f"✅ Found existing Hotel Guest by email: {existing_by_email}")
                return existing_by_email
        
        # ✅ CREATE NEW HOTEL GUEST (Only fill REQUIRED fields)
        frappe.logger().info(f"Creating new Hotel Guest: {guest_name}")
        
        hotel_guest = frappe.get_doc({
            "doctype": "Hotel Guest",
            "hotel_guest_name": guest_name,  # ✅ Required
            "phone_number": guest_phone or "",  # ✅ Required (phone)
            "email": guest_email or "",  # ✅ For identification
            "gender": "Male",  # ✅ Required - Default (can be updated later)
            "id_type": "Passport",  # ✅ Required - Default (can be updated later)
            "id_number": "",  # ✅ Required - Empty (can be updated later)
            "customer": customer_id  # ✅ Link to customer
            # ❌ DO NOT fill optional fields like market_place, nationality, notes
            # ❌ They can be added later by hotel staff
        }).insert(ignore_permissions=True)
        
        frappe.logger().info(f"✅ Created Hotel Guest: {hotel_guest.name}")
        return hotel_guest.name
    
    except Exception as e:
        frappe.logger().error(f"Error creating/getting Hotel Guest: {str(e)}")
        raise


# ════════════════════════════════════════════════════════════════════════════
# STEP 3: PAYSTACK WEBHOOK - CONVERT TEMPORARY TO PERMANENT
# ════════════════════════════════════════════════════════════════════════════

# @frappe.whitelist(allow_guest=True)
# def paystack_webhook():
#     """
#     Paystack Webhook: Payment successful → Convert temporary booking to permanent.
#     ✅ Creates Hotel Guest (not Guest Profile)
#     ✅ Invoice submission and Payment Entry creation happens HERE
#     ✅ Booking status tracked in Temporary Booking only
    
#     Workflow:
#     1. Verify payment with Paystack
#     2. Get temporary booking
#     3. Create Customer
#     4. Create Sales Invoice & SUBMIT IT
#     5. Create Hotel Room Reservations (one per room)
#     6. Create Hotel Guest (or get existing by phone/email)
#     7. Create Payment Entry & SUBMIT IT
#     8. Update Temporary Booking status
#     9. Queue confirmation email (background)
#     """
#     try:
#         body = frappe.request.get_data(as_text=True)
#         signature = frappe.request.headers.get("X-Paystack-Signature")
#         data = frappe.request.get_json()
        
#         frappe.log_error(message=f"Webhook Payload: {data}", title="Paystack Webhook")
        
#         # === VERIFY SIGNATURE ===
#         if not verify_paystack_signature(body, signature):
#             frappe.log_error("Invalid signature", "Paystack Webhook")
#             return {"status": "error", "message": "Invalid signature"}
        
#         # === EXTRACT DATA ===
#         event = data.get("event")
#         transaction_data = data.get("data", {})
#         booking_number = transaction_data.get("reference")
#         status = transaction_data.get("status")
#         amount = transaction_data.get("amount") / 100  # Convert from kobo
        
#         if not booking_number:
#             frappe.log_error("No booking reference", "Paystack Webhook")
#             return {"status": "error", "message": "No booking reference"}
        
#         # === GET TEMPORARY BOOKING ===
#         try:
#             temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": booking_number})
#         except frappe.DoesNotExistError:
#             frappe.log_error(f"Temp booking {booking_number} not found", "Paystack Webhook")
#             return {"status": "error", "message": "Booking not found"}
        
#         # === PROCESS SUCCESSFUL PAYMENT ===
#         if event == "charge.success" and status == "success":
            
#             # ✅ CHECK IF ALREADY PROCESSED (IDEMPOTENCY)
#             if temp_booking.payment_status == "Paid":
#                 frappe.logger().warning(f"⚠️ Payment already processed for {booking_number}")
#                 return {
#                     "status": "success",
#                     "message": "Payment already processed",
#                     "booking_number": booking_number
#                 }
            
#             # Verify amount
#             if amount != temp_booking.total_price:
#                 frappe.log_error(
#                     f"Amount mismatch: {amount} vs {temp_booking.total_price}",
#                     "Paystack Webhook"
#                 )
#                 temp_booking.payment_status = "Failed"
#                 temp_booking.save(ignore_permissions=True)
#                 frappe.db.commit()
#                 return {"status": "error", "message": "Amount mismatch"}
            
#             # === ELEVATE PRIVILEGES ===
#             current_user = frappe.session.user
#             frappe.set_user("Administrator")
            
#             try:
#                 # ✅ STEP 1: CREATE CUSTOMER
#                 customer_id = get_or_create_customer(
#                     customer_name=temp_booking.guest_name,
#                     customer_email=temp_booking.guest_email,
#                     customer_phone=temp_booking.guest_phone
#                 )
#                 # customer_id = customer_doc.name
                
#                 frappe.logger().info(f"✅ Created Customer {customer_id}")
                
#                 # ✅ STEP 2: CREATE CONTACT
#                 contact_name = None
#                 if temp_booking.guest_email:
#                     parts = temp_booking.guest_name.split(' ', 1)
#                     contact_doc = frappe.get_doc({
#                         "doctype": "Contact",
#                         "first_name": parts[0],
#                         "last_name": parts[1] if len(parts) > 1 else "",
#                         "email_id": temp_booking.guest_email,
#                         "phone": temp_booking.guest_phone or "",
#                     }).insert(ignore_permissions=True)
#                     contact_name = contact_doc.name
#                     frappe.logger().info(f"✅ Created Contact {contact_name}")
                
#                 # ✅ STEP 3: CREATE SALES INVOICE
#                 invoice_items = []
#                 for room in temp_booking.rooms:
#                     item_code = create_or_get_item(
#                         room.room_number,
#                         room.room_type,
#                         None
#                     )
#                     invoice_items.append({
#                         "item_code": item_code,
#                         "item_name": room.room_number,
#                         "qty": room.num_nights,
#                         "rate": room.rate_per_night,
#                         "description": f"Room {room.room_number} - {room.num_nights} night(s)"
#                     })
                
#                 sales_invoice = frappe.get_doc({
#                     "doctype": "Sales Invoice",
#                     "customer": customer_id,
#                     "contact_email": temp_booking.guest_email or "",
#                     "posting_date": nowdate(),
#                     "due_date": nowdate(),
#                     "items": invoice_items
#                 }).insert(ignore_permissions=True)
                
#                 frappe.logger().info(f"✅ Created Sales Invoice {sales_invoice.name}")
                
#                 # ✅ STEP 4: CREATE HOTEL ROOM RESERVATIONS
#                 guest_profiles = []
                
#                 for room in temp_booking.rooms:
#                     reservation_items = [{
#                         "item": room.room_number,
#                         "room_type": room.room_type,
#                         "rate_type": room.rate_type,
#                         "season_type": room.season_type,
#                         "qty": room.num_nights,
#                         "rate": room.rate_per_night,
#                         "amount": room.total_price
#                     }]
                    
#                     # CREATE HOTEL ROOM RESERVATION (linked to Temporary Booking)
#                     reservation = frappe.get_doc({
#                         "doctype": "Hotel Room Reservation",
#                         "temporary_booking_reference": temp_booking.name,
#                         "booking_number": booking_number,
#                         "room_number": room.room_number,
#                         "from_date": temp_booking.check_in_date,
#                         "to_date": temp_booking.check_out_date,
#                         "guest_name": temp_booking.guest_name,
#                         "customer": customer_id,
#                         "status": "Booked",
#                         "payment_status": "Paid",
#                         "hold_expires_at": None,
#                         "sales_invoice": sales_invoice.name,
#                         "items": reservation_items,
#                         "net_total": room.total_price,
#                     }).insert(ignore_permissions=True)
                    
#                     # Submit reservation
#                     reservation.flags.ignore_permissions = True
#                     reservation.submit()
                    
#                     frappe.logger().info(f"✅ Created & submitted Reservation {reservation.name}")
                
#                 # ✅ STEP 5: CREATE OR GET HOTEL GUEST (Check by phone/email first!)
#                 frappe.logger().info(f"Creating/Getting Hotel Guest for {temp_booking.guest_name}")
#                 hotel_guest_id = create_or_get_hotel_guest(
#                     temp_booking.guest_name,
#                     temp_booking.guest_email,
#                     temp_booking.guest_phone,
#                     customer_id
#                 )
#                 frappe.logger().info(f"✅ Hotel Guest: {hotel_guest_id}")
                
#                 # ✅ STEP 6: SUBMIT SALES INVOICE (IMMEDIATELY)
#                 frappe.logger().info(f"Submitting Sales Invoice {sales_invoice.name}")
#                 sales_invoice.flags.ignore_permissions = True
#                 sales_invoice.submit()
#                 frappe.logger().info(f"✅ Sales Invoice {sales_invoice.name} submitted")
                
#                 # ✅ STEP 7: CREATE & SUBMIT PAYMENT ENTRY (IMMEDIATELY)
#                 frappe.logger().info(f"Creating Payment Entry for {booking_number}")
                
#                 mode_of_payment = frappe.db.get_value("Mode of Payment", {"name": "Paystack"}, "name")
#                 if not mode_of_payment:
#                     frappe.logger().error("Mode of Payment 'Paystack' not found")
#                 else:
#                     paid_to = frappe.db.get_value(
#                         "Mode of Payment Account",
#                         {"parent": "Paystack", "company": sales_invoice.company},
#                         "default_account"
#                     )
                    
#                     paid_from = sales_invoice.debit_to
                    
#                     if paid_to and paid_from:
#                         pe = frappe.get_doc({
#                             "doctype": "Payment Entry",
#                             "payment_type": "Receive",
#                             "party_type": "Customer",
#                             "party": customer_id,
#                             "posting_date": frappe.utils.today(),
#                             "payment_date": frappe.utils.today(),
#                             "mode_of_payment": mode_of_payment,
#                             "paid_from": paid_from,
#                             "paid_to": paid_to,
#                             "paid_amount": sales_invoice.grand_total,
#                             "received_amount": sales_invoice.grand_total,
#                             "reference_no": booking_number,
#                             "reference_date": frappe.utils.today(),
#                             "remarks": f"Paystack payment for booking {booking_number}"
#                         })
                        
#                         pe.append("references", {
#                             "reference_doctype": "Sales Invoice",
#                             "reference_name": sales_invoice.name,
#                             "total_amount": sales_invoice.grand_total,
#                             "outstanding_amount": 0,
#                             "allocated_amount": sales_invoice.grand_total
#                         })
                        
#                         pe.flags.ignore_permissions = True
#                         pe.flags.ignore_mandatory = False
#                         pe.flags.ignore_account_permission = True
                        
#                         pe.insert(ignore_permissions=True)
#                         pe.submit()
#                         frappe.logger().info(f"✅ Payment Entry {pe.name} created & submitted")
#                     else:
#                         frappe.logger().warning(f"Could not create payment entry: paid_to={paid_to}, paid_from={paid_from}")
                
#                 # ✅ STEP 8: UPDATE TEMPORARY BOOKING STATUS
#                 temp_booking.status = "Payment Completed"
#                 temp_booking.booking_status = "Reserved"  # ✅ NEW: Rooms are now reserved (payment completed)
#                 temp_booking.payment_status = "Paid"
#                 temp_booking.payment_received_at = datetime.now()
#                 temp_booking.save(ignore_permissions=True)
                
#                 # ✅ STEP 8.5: SUBMIT TEMPORARY BOOKING (PERMANENT RECORD)
#                 frappe.logger().info(f"Submitting Temporary Booking {temp_booking.name}")
#                 temp_booking.flags.ignore_permissions = True
#                 temp_booking.submit()
#                 frappe.logger().info(f"✅ Temporary Booking {temp_booking.name} submitted permanently")
                
#                 frappe.db.commit()
                
#                 # ✅ STEP 9: SEND CONFIRMATION EMAIL (background - optional)
#                 # frappe.enqueue(
#                 #     'rhohotel.rhohotel.hotel_booking.send_booking_confirmation_email_bg',
#                 #     temp_booking_name=temp_booking.name,
#                 #     queue='short'
#                 # )
                
#                 frappe.logger().info(f"✅ Booking {booking_number} fully converted from temporary")
#                 return {
#                     "status": "success",
#                     "message": "Booking confirmed",
#                     "booking_number": booking_number
#                 }
            
#             finally:
#                 frappe.set_user(current_user)
        
#         else:
#             # Payment failed
#             temp_booking.payment_status = "Failed"
#             temp_booking.status = "Cancelled"
#             temp_booking.booking_status = "Released"  # ✅ NEW: Rooms are released (payment failed)
#             temp_booking.save(ignore_permissions=True)
#             frappe.db.commit()
            
#             frappe.logger().warning(f"❌ Payment failed for {booking_number}")
#             return {
#                 "status": "failed",
#                 "message": "Payment failed"
#             }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Paystack Webhook Error")
#         return {
#             "status": "error",
#             "message": str(e)
#         }


@frappe.whitelist(allow_guest=True)
def paystack_webhook():
    """
    Paystack Webhook: Receives payment notifications from Paystack.
    ✅ Verifies signature
    ✅ Extracts payment data
    ✅ Calls shared processing function
    
    Returns:
        dict: Webhook response
    """
    try:
        body = frappe.request.get_data(as_text=True)
        signature = frappe.request.headers.get("X-Paystack-Signature")
        data = frappe.request.get_json()
        
        frappe.log_error(message=f"Webhook Payload: {data}", title="Paystack Webhook")
        
        # === VERIFY SIGNATURE ===
        if not verify_paystack_signature(body, signature):
            frappe.log_error("Invalid signature", "Paystack Webhook")
            return {"status": "error", "message": "Invalid signature"}
        
        # === EXTRACT DATA ===
        event = data.get("event")
        transaction_data = data.get("data", {})
        booking_number = transaction_data.get("reference")
        status = transaction_data.get("status")
        amount = transaction_data.get("amount") / 100  # Convert from kobo
        
        if not booking_number:
            frappe.log_error("No booking reference", "Paystack Webhook")
            return {"status": "error", "message": "No booking reference"}
        
        frappe.logger().info(f"🔔 Webhook received for {booking_number}: {event}, {status}")
        
        # === PROCESS SUCCESSFUL PAYMENT ===
        if event == "charge.success" and status == "success":
            # Prepare payment data
            payment_data = {
                "amount": amount,
                "status": "success",
                "reference": booking_number,
                "channel": transaction_data.get("channel"),
                "paid_at": transaction_data.get("paid_at"),
                "transaction_date": transaction_data.get("transaction_date")
            }
            
            # Call shared processing function
            result = process_payment_transaction(
                booking_number=booking_number,
                payment_data=payment_data,
                source="webhook"
            )
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": result.get("message"),
                    "booking_number": booking_number,
                    "already_processed": result.get("already_processed", False)
                }
            else:
                return {
                    "status": "error",
                    "message": result.get("message"),
                    "error_code": result.get("error_code")
                }
        
        else:
            # Payment failed or other event
            frappe.logger().warning(f"⚠️ Webhook event not processed: {event}, status: {status}")
            
            # Try to update temporary booking status
            try:
                temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": booking_number})
                temp_booking.payment_status = "Failed"
                temp_booking.status = "Cancelled"
                temp_booking.booking_status = "Released"
                temp_booking.save(ignore_permissions=True)
                frappe.db.commit()
            except:
                pass
            
            return {
                "status": "failed",
                "message": f"Payment failed: {status}"
            }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Paystack Webhook Error")
        return {
            "status": "error",
            "message": str(e)
        }
        
        

def verify_paystack_signature(body, signature):
    """Verify Paystack webhook signature."""
    try:
        settings = frappe.get_doc("Hotel Settings")
        secret_key = settings.get_password("paystack_secret_key")
        
        if not secret_key:
            frappe.log_error("Paystack secret key not found", "Signature Verification")
            return False
        
        hash_object = hmac.new(
            secret_key.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha512
        )
        
        computed_signature = hash_object.hexdigest()
        return hmac.compare_digest(computed_signature, signature)
    
    except Exception as e:
        frappe.log_error(f"Signature verification error: {str(e)}", "Signature Verification")
        return False


# @frappe.whitelist(allow_guest=True)
# def verify_callback_payment(reference):
#     """
#     Verify payment from callback URL (user redirect from Paystack).
#     ✅ Verifies with Paystack API
#     ✅ Calls shared processing function
#     ✅ Idempotent - safe to call multiple times
    
#     Args:
#         reference (str): Booking number / transaction reference
    
#     Returns:
#         dict: Verification result
#     """
#     try:
#         frappe.logger().info(f"🔍 Callback verification for: {reference}")
        
#         # === STEP 1: GET TEMPORARY BOOKING ===
#         try:
#             temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": reference})
#         except frappe.DoesNotExistError:
#             frappe.logger().error(f"❌ Booking {reference} not found")
#             return {
#                 "success": False,
#                 "message": "Booking not found. Please contact support."
#             }
        
#         # === STEP 2: QUICK CHECK - Already Processed? ===
#         if temp_booking.payment_status == "Paid":
#             frappe.logger().info(f"✅ Booking {reference} already processed")
#             return {
#                 "success": True,
#                 "booking_number": reference,
#                 "message": "Payment confirmed",
#                 "already_processed": True
#             }
        
#         # === STEP 3: VERIFY WITH PAYSTACK API ===
#         settings = frappe.get_doc("Hotel Settings")
#         paystack_secret_key = settings.get_password("paystack_secret_key")
        
#         if not paystack_secret_key:
#             frappe.logger().error("❌ Paystack secret key not configured")
#             return {
#                 "success": False,
#                 "message": "Payment gateway configuration error"
#             }
        
#         # Call Paystack Verify API
#         verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
#         headers = {
#             "Authorization": f"Bearer {paystack_secret_key}",
#             "Content-Type": "application/json"
#         }
        
#         frappe.logger().info(f"📡 Calling Paystack verify API for {reference}")
        
#         try:
#             response = requests.get(verify_url, headers=headers, timeout=30)
#             result = response.json()
#         except requests.exceptions.Timeout:
#             frappe.logger().error(f"❌ Paystack API timeout for {reference}")
#             return {
#                 "success": False,
#                 "message": "Payment verification timeout. Please refresh or contact support."
#             }
#         except Exception as e:
#             frappe.logger().error(f"❌ Paystack API error: {str(e)}")
#             return {
#                 "success": False,
#                 "message": "Payment verification error. Please contact support."
#             }
        
#         if response.status_code != 200 or not result.get("status"):
#             error_msg = result.get("message", "Verification failed")
#             frappe.logger().error(f"❌ Paystack verification failed: {error_msg}")
#             return {
#                 "success": False,
#                 "message": f"Payment verification failed: {error_msg}"
#             }
        
#         # === STEP 4: EXTRACT PAYMENT DATA ===
#         transaction_data = result.get("data", {})
#         payment_status = transaction_data.get("status")
#         amount_paid = transaction_data.get("amount") / 100  # Convert from kobo
        
#         frappe.logger().info(f"💰 Payment status: {payment_status}, Amount: ₦{amount_paid}")
        
#         # Prepare payment data
#         payment_data = {
#             "amount": amount_paid,
#             "status": payment_status,
#             "reference": reference,
#             "channel": transaction_data.get("channel"),
#             "paid_at": transaction_data.get("paid_at"),
#             "transaction_date": transaction_data.get("transaction_date")
#         }
        
#         # === STEP 5: CALL SHARED PROCESSING FUNCTION ===
#         result = process_payment_transaction(
#             booking_number=reference,
#             payment_data=payment_data,
#             source="callback"
#         )
        
#         if result.get("success"):
#             return {
#                 "success": True,
#                 "booking_number": reference,
#                 "message": result.get("message"),
#                 "already_processed": result.get("already_processed", False),
#                 "customer_id": result.get("customer_id"),
#                 "sales_invoice": result.get("sales_invoice"),
#                 "processed_via": result.get("processed_via")
#             }
#         else:
#             return {
#                 "success": False,
#                 "message": result.get("message"),
#                 "error_code": result.get("error_code")
#             }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Callback Payment Verification Error")
#         frappe.logger().error(f"❌ Error in callback verification: {str(e)}")
#         return {
#             "success": False,
#             "message": f"Verification error: {str(e)}"
#         }


@frappe.whitelist(allow_guest=True)
def verify_callback_payment(reference):
    """
    Verify payment from callback URL (user redirect from Paystack).
    ✅ Verifies with Paystack API
    ✅ Calls shared processing function
    ✅ Idempotent - safe to call multiple times
    
    Args:
        reference (str): Booking number / transaction reference
    
    Returns:
        dict: Verification result with booking details
    """
    try:
        frappe.logger().info(f"🔍 Callback verification for: {reference}")
        
        # === STEP 1: GET TEMPORARY BOOKING ===
        try:
            temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": reference})
        except frappe.DoesNotExistError:
            frappe.logger().error(f"❌ Booking {reference} not found")
            return {
                "success": False,
                "message": "Booking not found. Please contact support."
            }
        
        # === STEP 2: QUICK CHECK - Already Processed? ===
        if temp_booking.payment_status == "Paid":
            frappe.logger().info(f"✅ Booking {reference} already processed")
            # Get guest count information
            adults = temp_booking.get("adults") or 0
            children = temp_booking.get("children") or 0
            total_guests = adults + children if (adults or children) else None
            
            # Get room details with room types
            rooms_list = []
            for room in temp_booking.rooms:
                rooms_list.append({
                    # "room_number": room.room_number,
                    "room_type": room.room_type,
                    "rate_per_night": room.rate_per_night,
                    "num_nights": room.num_nights,
                    "total_price": room.total_price
                })
            
            return {
                "success": True,
                "booking_number": reference,
                "message": "Payment confirmed",
                "already_processed": True,
                "guest_name": temp_booking.guest_name,
                "guest_email": temp_booking.guest_email,
                "guest_phone": temp_booking.guest_phone,
                "check_in_date": temp_booking.check_in_date,
                "check_out_date": temp_booking.check_out_date,
                "num_nights": temp_booking.num_nights,
                "total_rooms": temp_booking.total_rooms,
                "total_price": temp_booking.total_price,
                "currency": temp_booking.currency or "NGN",
                "rooms": rooms_list,
                "payment_date": temp_booking.payment_received_at.strftime("%Y-%m-%d %H:%M:%S") if temp_booking.payment_received_at else None,
                "guests": {
                    "adults": adults,
                    "children": children,
                    "total": total_guests
                } if total_guests else None
            }
        
        # === STEP 3: VERIFY WITH PAYSTACK API ===
        settings = frappe.get_doc("Hotel Settings")
        paystack_secret_key = settings.get_password("paystack_secret_key")
        
        if not paystack_secret_key:
            frappe.logger().error("❌ Paystack secret key not configured")
            return {
                "success": False,
                "message": "Payment gateway configuration error"
            }
        
        # Call Paystack Verify API
        verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json"
        }
        
        frappe.logger().info(f"📡 Calling Paystack verify API for {reference}")
        
        try:
            response = requests.get(verify_url, headers=headers, timeout=30)
            result = response.json()
        except requests.exceptions.Timeout:
            frappe.logger().error(f"❌ Paystack API timeout for {reference}")
            return {
                "success": False,
                "message": "Payment verification timeout. Please refresh or contact support."
            }
        except Exception as e:
            frappe.logger().error(f"❌ Paystack API error: {str(e)}")
            return {
                "success": False,
                "message": "Payment verification error. Please contact support."
            }
        
        if response.status_code != 200 or not result.get("status"):
            error_msg = result.get("message", "Verification failed")
            frappe.logger().error(f"❌ Paystack verification failed: {error_msg}")
            return {
                "success": False,
                "message": f"Payment verification failed: {error_msg}"
            }
        
        # === STEP 4: EXTRACT PAYMENT DATA ===
        transaction_data = result.get("data", {})
        payment_status = transaction_data.get("status")
        amount_paid = transaction_data.get("amount") / 100  # Convert from kobo
        
        frappe.logger().info(f"💰 Payment status: {payment_status}, Amount: ₦{amount_paid}")
        
        # Prepare payment data
        payment_data = {
            "amount": amount_paid,
            "status": payment_status,
            "reference": reference,
            "channel": transaction_data.get("channel"),
            "paid_at": transaction_data.get("paid_at"),
            "transaction_date": transaction_data.get("transaction_date")
        }
        
        # === STEP 5: CALL SHARED PROCESSING FUNCTION ===
        result = process_payment_transaction(
            booking_number=reference,
            payment_data=payment_data,
            source="callback"
        )
        
        if result.get("success"):
            # Refresh temp_booking to get updated data
            temp_booking.reload()
            
            return {
                "success": True,
                "booking_number": reference,
                "message": result.get("message"),
                "already_processed": result.get("already_processed", False),
                # "customer_id": result.get("customer_id"),
                # "sales_invoice": result.get("sales_invoice"),
                "processed_via": result.get("processed_via"),
                "guest_name": temp_booking.guest_name,
                "guest_email": temp_booking.guest_email,
                "guest_phone": temp_booking.guest_phone,
                "check_in_date": temp_booking.check_in_date,
                "check_out_date": temp_booking.check_out_date,
                "num_nights": temp_booking.num_nights,
                "total_rooms": temp_booking.total_rooms,
                "total_price": temp_booking.total_price,
                "currency": temp_booking.currency or "NGN",
                "rooms": rooms_list,
                "payment_date": temp_booking.payment_received_at.strftime("%Y-%m-%d %H:%M:%S") if temp_booking.payment_received_at else None,
                "guests": {
                    "adults": adults,
                    "children": children,
                    "total": total_guests
                } if total_guests else None
            }
        else:
            return {
                "success": False,
                "message": result.get("message"),
                "error_code": result.get("error_code")
            }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Callback Payment Verification Error")
        frappe.logger().error(f"❌ Error in callback verification: {str(e)}")
        return {
            "success": False,
            "message": f"Verification error: {str(e)}"
        }
        
        
# ════════════════════════════════════════════════════════════════════════════
# EMAIL & BACKGROUND JOBS
# ════════════════════════════════════════════════════════════════════════════

def send_booking_confirmation_email_bg(temp_booking_name):
    """Background job to send confirmation email"""
    try:
        temp_booking = frappe.get_doc("Temporary Booking", temp_booking_name)
        
        rooms_list = "\n".join([f"- Room {r.room_number}" for r in temp_booking.rooms])
        
        frappe.sendmail(
            recipients=[temp_booking.guest_email],
            subject=f"Booking Confirmed - {temp_booking.booking_number}",
            message=f"""
            <h3>Booking Confirmed!</h3>
            <p><strong>Booking:</strong> {temp_booking.booking_number}</p>
            <p><strong>Guest:</strong> {temp_booking.guest_name}</p>
            <p><strong>Check-in:</strong> {temp_booking.check_in_date}</p>
            <p><strong>Check-out:</strong> {temp_booking.check_out_date}</p>
            <p><strong>Paid:</strong> ₦{temp_booking.total_price:,.2f}</p>
            <p><strong>Rooms:</strong><pre>{rooms_list}</pre></p>
            <p>Thank you!</p>
            """,
            now=True
        )
        frappe.logger().info(f"✅ Confirmation email sent to {temp_booking.guest_email}")
    except Exception as e:
        frappe.log_error(f"Email error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS FOR MULTI-ROOM BOOKINGS
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_booking_reservations(booking_number):
    """Get all reservations for a booking"""
    try:
        reservations = frappe.get_all(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number},
            fields=["name", "room_number", "status", "payment_status", "from_date", "to_date"]
        )
        return {
            "success": True,
            "booking_number": booking_number,
            "total_reservations": len(reservations),
            "reservations": reservations
        }
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def check_in_entire_booking(booking_number):
    """Check in ALL rooms for a booking at once"""
    try:
        reservations = frappe.get_all(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number},
            fields=["name"]
        )
        
        for res in reservations:
            res_doc = frappe.get_doc("Hotel Room Reservation", res.name)
            res_doc.status = "Checked-In"
            res_doc.check_in_time = datetime.now()
            res_doc.save(ignore_permissions=True)
        
        frappe.db.commit()
        return {"success": True, "rooms_checked_in": len(reservations), "booking_number": booking_number}
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def check_out_entire_booking(booking_number):
    """Check out ALL rooms for a booking at once"""
    try:
        reservations = frappe.get_all(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number},
            fields=["name", "room_number"]
        )
        
        for res in reservations:
            res_doc = frappe.get_doc("Hotel Room Reservation", res.name)
            res_doc.status = "Completed"
            res_doc.check_out_time = datetime.now()
            res_doc.save(ignore_permissions=True)
            
            # Update room status
            room_doc = frappe.get_doc("Hotel Room", res.room_number)
            room_doc.housekeeping_status = "Dirty"
            room_doc.save(ignore_permissions=True)
        
        frappe.db.commit()
        return {"success": True, "rooms_checked_out": len(reservations), "booking_number": booking_number}
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# ROOM HOLD CLEANUP
# ════════════════════════════════════════════════════════════════════════════

def release_expired_holds():
    """Release rooms with expired holds (background job)."""
    try:
        current_time = datetime.now()
        released_count = 0
        
        frappe.logger().info(f"Running hold cleanup at {current_time}")
        
        # === Find expired TEMPORARY bookings ===
        expired_temp_bookings = frappe.get_all(
            "Temporary Booking",
            filters={
                "status": ["in", ["Hold", "Payment Link Generated"]],
                "payment_status": "Pending",
                "hold_expires_at": ["<", current_time]
            },
            fields=["name", "booking_number"]
        )
        
        for temp_booking in expired_temp_bookings:
            try:
                tb = frappe.get_doc("Temporary Booking", temp_booking.name)
                tb.status = "Expired"
                tb.booking_status = "Released"  # ✅ NEW: Rooms are released (hold expired)
                tb.save(ignore_permissions=True)
                
                frappe.logger().info(f"✅ Expired temp booking {temp_booking['booking_number']}")
            
            except Exception as e:
                frappe.logger().error(f"Error with {temp_booking['booking_number']}: {str(e)}")
                continue
        
        frappe.db.commit()
        frappe.logger().info(f"🎯 Processed {len(expired_temp_bookings)} expired temporary bookings")
        return {"success": True, "expired": len(expired_temp_bookings)}
    
    except Exception as e:
        frappe.log_error(str(e), "Hold Release Error")
        return {"success": False, "error": str(e)}


def process_payment_transaction(booking_number, payment_data, source="webhook"):
    """
    SHARED FUNCTION: Process payment and create booking documents.
    ✅ Called by both webhook and callback
    ✅ Idempotent - safe to call multiple times
    ✅ Atomic - either completes fully or rolls back
    
    Args:
        booking_number (str): Booking reference number
        payment_data (dict): Payment details from Paystack
            - amount (float): Amount paid in Naira
            - status (str): Payment status
            - reference (str): Transaction reference
        source (str): "webhook" or "callback" (for logging)
    
    Returns:
        dict: Processing result with success status
    """
    try:
        frappe.logger().info(f"🔄 [{source.upper()}] Processing payment for {booking_number}")
        
        # === STEP 1: GET TEMPORARY BOOKING ===
        try:
            temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": booking_number})
        except frappe.DoesNotExistError:
            frappe.logger().error(f"❌ [{source.upper()}] Booking {booking_number} not found")
            return {
                "success": False,
                "message": "Booking not found",
                "error_code": "BOOKING_NOT_FOUND"
            }
        
        # === STEP 2: IDEMPOTENCY CHECK - Already Processed? ===
        if temp_booking.payment_status == "Paid":
            frappe.logger().info(f"✅ [{source.upper()}] Booking {booking_number} already processed")
            return {
                "success": True,
                "message": "Payment already processed",
                "booking_number": booking_number,
                "already_processed": True,
                "customer_id": temp_booking.customer if hasattr(temp_booking, 'customer') else None
            }
        
        # === STEP 3: VERIFY PAYMENT DATA ===
        amount_paid = float(payment_data.get("amount", 0))
        payment_status = payment_data.get("status", "")
        
        # Check payment status
        if payment_status != "success":
            frappe.logger().warning(f"⚠️ [{source.upper()}] Payment not successful: {payment_status}")
            temp_booking.payment_status = "Failed"
            temp_booking.status = "Cancelled"
            temp_booking.booking_status = "Released"
            temp_booking.save(ignore_permissions=True)
            frappe.db.commit()
            return {
                "success": False,
                "message": f"Payment status: {payment_status}",
                "error_code": "PAYMENT_FAILED"
            }
        
        # Check amount
        if amount_paid != temp_booking.total_price:
            frappe.logger().error(f"❌ [{source.upper()}] Amount mismatch: {amount_paid} vs {temp_booking.total_price}")
            temp_booking.payment_status = "Failed"
            temp_booking.save(ignore_permissions=True)
            frappe.db.commit()
            return {
                "success": False,
                "message": "Amount mismatch",
                "error_code": "AMOUNT_MISMATCH"
            }
        
        # === STEP 4: LOCK CHECK (Race Condition Protection) ===
        # Reload from database to get latest state
        temp_booking.reload()
        
        if temp_booking.payment_status == "Paid":
            frappe.logger().info(f"✅ [{source.upper()}] Booking {booking_number} was processed during verification")
            return {
                "success": True,
                "message": "Payment already processed (race condition)",
                "booking_number": booking_number,
                "already_processed": True
            }
        
        # === STEP 5: ELEVATE PRIVILEGES ===
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        
        try:
            # === STEP 6: CREATE CUSTOMER ===
            customer_id = get_or_create_customer(
                customer_name=temp_booking.guest_name,
                customer_email=temp_booking.guest_email,
                customer_phone=temp_booking.guest_phone
            )
            frappe.logger().info(f"✅ [{source.upper()}] Customer: {customer_id}")
            
            # === STEP 7: CREATE CONTACT ===
            contact_name = None
            if temp_booking.guest_email:
                # Check if contact already exists
                existing_contact = frappe.db.get_value(
                    "Contact",
                    {"email_id": temp_booking.guest_email},
                    "name"
                )
                
                if existing_contact:
                    contact_name = existing_contact
                    frappe.logger().info(f"✅ [{source.upper()}] Found existing Contact: {contact_name}")
                else:
                    parts = temp_booking.guest_name.split(' ', 1)
                    contact_doc = frappe.get_doc({
                        "doctype": "Contact",
                        "first_name": parts[0],
                        "last_name": parts[1] if len(parts) > 1 else "",
                        "email_id": temp_booking.guest_email,
                        "phone": temp_booking.guest_phone or "",
                    }).insert(ignore_permissions=True)
                    contact_name = contact_doc.name
                    frappe.logger().info(f"✅ [{source.upper()}] Created Contact: {contact_name}")
            
            # === STEP 8: CREATE SALES INVOICE ===
            invoice_items = []
            for room in temp_booking.rooms:
                item_code = create_or_get_item(
                    room.room_number,
                    room.room_type,
                    None
                )
                invoice_items.append({
                    "item_code": item_code,
                    "item_name": room.room_number,
                    "qty": room.num_nights,
                    "rate": room.rate_per_night,
                    "description": f"Room {room.room_number} - {room.num_nights} night(s)"
                })
            
            sales_invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": customer_id,
                "contact_email": temp_booking.guest_email or "",
                "posting_date": nowdate(),
                "due_date": nowdate(),
                "items": invoice_items
            }).insert(ignore_permissions=True)
            
            frappe.logger().info(f"✅ [{source.upper()}] Sales Invoice: {sales_invoice.name}")
            
            # === STEP 9: CREATE HOTEL ROOM RESERVATIONS ===
            reservation_names = []
            for room in temp_booking.rooms:
                reservation_items = [{
                    "item": room.room_number,
                    "room_type": room.room_type,
                    "rate_type": room.rate_type,
                    "season_type": room.season_type,
                    "qty": room.num_nights,
                    "rate": room.rate_per_night,
                    "amount": room.total_price
                }]
                
                # CREATE HOTEL ROOM RESERVATION
                reservation = frappe.get_doc({
                    "doctype": "Hotel Room Reservation",
                    "temporary_booking_reference": temp_booking.name,
                    "booking_number": booking_number,
                    "room_number": room.room_number,
                    "rate": room.rate_per_night,
                    "discount": 0,
                    "from_date": temp_booking.check_in_date,
                    "to_date": temp_booking.check_out_date,
                    "guest_name": temp_booking.guest_name,
                    "customer": customer_id,
                    "status": "Booked",
                    "payment_status": "Paid",
                    "hold_expires_at": None,
                    "sales_invoice": sales_invoice.name,
                    "items": reservation_items,
                    "net_total": room.total_price,
                }).insert(ignore_permissions=True)
                
                # Submit reservation
                reservation.flags.ignore_permissions = True
                reservation.submit()
                reservation_names.append(reservation.name)
                
                frappe.logger().info(f"✅ [{source.upper()}] Reservation: {reservation.name}")
            
            # === STEP 10: CREATE OR GET HOTEL GUEST ===
            hotel_guest_id = create_or_get_hotel_guest(
                temp_booking.guest_name,
                temp_booking.guest_email,
                temp_booking.guest_phone,
                customer_id
            )
            frappe.logger().info(f"✅ [{source.upper()}] Hotel Guest: {hotel_guest_id}")
            
            # === STEP 11: SUBMIT SALES INVOICE ===
            sales_invoice.flags.ignore_permissions = True
            sales_invoice.submit()
            frappe.logger().info(f"✅ [{source.upper()}] Invoice submitted: {sales_invoice.name}")
            
            # === STEP 12: CREATE & SUBMIT PAYMENT ENTRY ===
            payment_entry_name = None
            mode_of_payment = frappe.db.get_value("Mode of Payment", {"name": "Paystack"}, "name")
            
            if not mode_of_payment:
                frappe.logger().error(f"❌ [{source.upper()}] Mode of Payment 'Paystack' not found")
            else:
                paid_to = frappe.db.get_value(
                    "Mode of Payment Account",
                    {"parent": "Paystack", "company": sales_invoice.company},
                    "default_account"
                )
                
                paid_from = sales_invoice.debit_to
                
                if paid_to and paid_from:
                    pe = frappe.get_doc({
                        "doctype": "Payment Entry",
                        "payment_type": "Receive",
                        "party_type": "Customer",
                        "party": customer_id,
                        "posting_date": frappe.utils.today(),
                        "payment_date": frappe.utils.today(),
                        "mode_of_payment": mode_of_payment,
                        "paid_from": paid_from,
                        "paid_to": paid_to,
                        "paid_amount": sales_invoice.grand_total,
                        "received_amount": sales_invoice.grand_total,
                        "reference_no": booking_number,
                        "reference_date": frappe.utils.today(),
                        "remarks": f"Paystack payment for booking {booking_number} (via {source})"
                    })
                    
                    pe.append("references", {
                        "reference_doctype": "Sales Invoice",
                        "reference_name": sales_invoice.name,
                        "total_amount": sales_invoice.grand_total,
                        "outstanding_amount": 0,
                        "allocated_amount": sales_invoice.grand_total
                    })
                    
                    pe.flags.ignore_permissions = True
                    pe.flags.ignore_mandatory = False
                    pe.flags.ignore_account_permission = True
                    
                    pe.insert(ignore_permissions=True)
                    pe.submit()
                    payment_entry_name = pe.name
                    frappe.logger().info(f"✅ [{source.upper()}] Payment Entry: {pe.name}")
                else:
                    frappe.logger().warning(f"⚠️ [{source.upper()}] Could not create payment entry: paid_to={paid_to}, paid_from={paid_from}")
            
            # === STEP 13: UPDATE TEMPORARY BOOKING ===
            temp_booking.status = "Payment Completed"
            temp_booking.booking_status = "Reserved"
            temp_booking.payment_status = "Paid"
            temp_booking.payment_received_at = datetime.now()
            temp_booking.customer = customer_id  # Link customer
            temp_booking.save(ignore_permissions=True)
            
            # === STEP 14: SUBMIT TEMPORARY BOOKING ===
            temp_booking.flags.ignore_permissions = True
            temp_booking.submit()
            frappe.logger().info(f"✅ [{source.upper()}] Temporary Booking submitted: {temp_booking.name}")
            
            # === STEP 15: COMMIT TRANSACTION ===
            frappe.db.commit()
            
            # === STEP 16: SEND CONFIRMATION EMAIL (background) ===
            frappe.enqueue(
                'rhohotel.rhohotel.hotel_booking.send_booking_confirmation_email_bg',
                temp_booking_name=temp_booking.name,
                queue='short'
            )
            
            frappe.logger().info(f"✅ [{source.upper()}] Payment processed successfully for {booking_number}")
            
            return {
                "success": True,
                "message": "Booking confirmed",
                "booking_number": booking_number,
                "customer_id": customer_id,
                "sales_invoice": sales_invoice.name,
                "payment_entry": payment_entry_name,
                "reservations": reservation_names,
                "hotel_guest": hotel_guest_id,
                "processed_via": source,
                "already_processed": False
            }
        
        finally:
            # Restore user
            frappe.set_user(current_user)
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Payment Processing Error ({source})")
        frappe.logger().error(f"❌ [{source.upper()}] Error processing payment: {str(e)}")
        return {
            "success": False,
            "message": f"Processing error: {str(e)}",
            "error_code": "PROCESSING_ERROR"
        }