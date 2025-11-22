"""
Hotel Booking - Booking & Payment Module (REFACTORED)
Handles multi-room bookings with SINGLE primary guest name
Location: rhohotel/rhohotel/hotel_booking.py

KEY CHANGES:
- Removed 'guests' parameter - now uses single 'customer_name' for all rooms
- All rooms in booking are under ONE primary guest
- Cleaner function signature and better UX
"""

import frappe
from frappe.utils import nowdate, getdate
from datetime import datetime, timedelta
import json
import requests
import base64
import hmac
import hashlib

# Import shared utilities
from .shared_utilities import (
    parse_date,
    validate_date_range,
    validate_room_for_booking,
    get_room_tariff,
    generate_secure_booking_number,
    create_or_get_item
)


# ════════════════════════════════════════════════════════════════════════════
# MAIN BOOKING FUNCTION - SINGLE PRIMARY GUEST
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def create_booking(from_date, to_date, rooms, customer_email=None, customer_phone=None, customer_name=None):
    """
    Create a multi-room booking with ONE primary guest name for all rooms.
    
    Args:
        from_date (str): Check-in date (YYYY-MM-DD)
        to_date (str): Check-out date (YYYY-MM-DD)
        rooms (list or str): List of room numbers ["101", "102", "103"]
        customer_email (str): Primary guest email
        customer_phone (str): Primary guest phone  
        customer_name (str): Primary guest name (used for ALL rooms)
    
    Workflow:
    1. Create/Get Customer (status = "Pending")
    2. Create Contact
    3. Create Hotel Booking (with REAL customer)
    4. Create Hotel Room Reservations (all use same primary guest)
    5. Create Guest Profiles (all reference primary guest)
    6. Create Sales Invoice
    7. Hold rooms for 15 minutes
    
    Example Call:
        create_booking(
            from_date="2025-12-01",
            to_date="2025-12-03",
            rooms=["101", "102", "103"],
            customer_name="John Doe",
            customer_email="john@example.com",
            customer_phone="+2341234567890"
        )
    """
    try:
        # === PARSE INPUTS ===
        if isinstance(rooms, str):
            try:
                rooms = json.loads(rooms)
            except json.JSONDecodeError:
                raise frappe.ValidationError("Invalid rooms format. Must be JSON array or list.")

        # === VALIDATE INPUTS ===
        if not isinstance(rooms, list) or len(rooms) == 0:
            raise frappe.ValidationError("At least 1 room must be provided")
        if not customer_name:
            raise frappe.ValidationError("Primary guest name (customer_name) is required")

        # === PARSE & VALIDATE DATES ===
        from_str, from_date_obj = parse_date(from_date, "from_date")
        to_str, to_date_obj = parse_date(to_date, "to_date")
        num_nights = validate_date_range(from_date_obj, to_date_obj)

        # === VALIDATE ROOMS & CALCULATE PRICE ===
        room_reservations = []
        total_price = 0
        invoice_items = []

        for room_number in rooms:
            # Validate room availability
            room = validate_room_for_booking(room_number, from_str, to_str)
            tariff = get_room_tariff(room.get("room_type"), from_str)
            
            if not tariff:
                raise frappe.ValidationError(f"No tariff found for {room.get('room_type')}")

            room_price = float(tariff.get("rate_amount", 0)) * num_nights
            total_price += room_price

            room_reservations.append({
                "room_number": room_number,
                "room_type": room.get("room_type"),
                "price": room_price
            })

            # Create invoice item for this room
            item_code = create_or_get_item(room_number, room.get("room_type"), room.get("erpnext_item"))
            invoice_items.append({
                "item_code": item_code,
                "item_name": room_number,
                "qty": num_nights,
                "rate": float(tariff.get("rate_amount", 0)),
                "description": f"Room {room_number} - {num_nights} night(s) from {from_str} to {to_str}"
            })

        # === GENERATE BOOKING NUMBER ===
        booking_number = generate_secure_booking_number()

        # === CREATE/GET CUSTOMER ===
        customer_id = None
        is_repeat_customer = False

        if customer_email:
            # Check if customer already exists
            existing = frappe.db.get_value("Customer", {"email_id": customer_email})
            if existing:
                customer_id = existing
                is_repeat_customer = True
            else:
                customer_doc = frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "customer_type": "Individual",
                    "email_id": customer_email,
                    "mobile_no": customer_phone or "",
                    "status": "Pending",
                    "booking_reference": booking_number,
                }).insert()
                customer_id = customer_doc.name
        else:
            # Create customer without email (anonymous booking)
            customer_doc = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_type": "Individual",
                "email_id": "",
                "mobile_no": customer_phone or "",
                "status": "Pending",
                "booking_reference": booking_number,
            }).insert()
            customer_id = customer_doc.name

        # === CREATE/UPDATE CONTACT ===
        contact_name = None
        if customer_email:
            existing = frappe.db.get_value("Contact", {"email_id": customer_email})
            if existing:
                # Update existing contact
                contact_doc = frappe.get_doc("Contact", existing)
                if customer_phone: 
                    contact_doc.phone = customer_phone
                parts = customer_name.split(' ', 1)
                contact_doc.first_name = parts[0]
                contact_doc.last_name = parts[1] if len(parts) > 1 else ""
                contact_doc.save()
                contact_name = existing
            else:
                # Create new contact
                parts = customer_name.split(' ', 1)
                contact_doc = frappe.get_doc({
                    "doctype": "Contact",
                    "first_name": parts[0],
                    "last_name": parts[1] if len(parts) > 1 else "",
                    "email_id": customer_email,
                    "phone": customer_phone or "",
                }).insert()
                contact_name = contact_doc.name

        # === CREATE SALES INVOICE ===
        sales_invoice = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": customer_id,
            "contact_email": customer_email or "",
            "posting_date": nowdate(),
            "due_date": nowdate(),
            "items": invoice_items
        }).insert()

        # === CREATE HOTEL BOOKING ===
        hold_expires_at = datetime.now() + timedelta(minutes=15)
        booking = frappe.get_doc({
            "doctype": "Hotel Booking",
            "booking_number": booking_number,
            "customer": customer_id,
            "customer_name": customer_name,
            "customer_email": customer_email or "",
            "customer_phone": customer_phone or "",
            "contact_name": contact_name,
            "from_date": from_str,
            "to_date": to_str,
            "total_rooms": len(rooms),
            "total_price": total_price,
            "status": "Pending Payment",
            "payment_status": "Pending",
            "sales_invoice": sales_invoice.name,
            "hold_expires_at": hold_expires_at,
            "created_at": datetime.now(),
        }).insert()

        # === CREATE RESERVATIONS + GUEST PROFILES ===
        booking_reservations = []
        guest_profiles = []

        for data in room_reservations:
            tariff = get_room_tariff(data["room_type"], from_str)
            season_info = frappe.db.get_value(
                "Hotel Room Tariff",
                {"room_type": data["room_type"], "is_active": 1},
                ["hotel_season", "rate_type"], 
                as_dict=True
            ) or {}
            season_type = frappe.db.get_value(
                "Hotel Season", 
                season_info.get("hotel_season"), 
                "season_type"
            ) if season_info.get("hotel_season") else None

            reservation_items = [{
                "item": data["room_number"],
                "room_type": data["room_type"],
                "rate_type": season_info.get("rate_type") or "Standard",
                "season_type": season_type or "",
                "qty": num_nights,
                "rate": float(tariff.get("rate_amount", 0)),
                "amount": data["price"]
            }]

            # ✅ Create Hotel Room Reservation
            reservation = frappe.get_doc({
                "doctype": "Hotel Room Reservation",
                "room_number": data["room_number"],
                "from_date": from_str,
                "to_date": to_str,
                "guest_name": customer_name,  # ✅ PRIMARY GUEST NAME
                "customer": customer_id,
                "status": "Pending Payment",
                "payment_status": "Pending",
                "booking_number": booking.name,  # ✅ Use booking.name (internal ID)
                "hold_expires_at": hold_expires_at,
                "sales_invoice": sales_invoice.name,
                "items": reservation_items,
                "net_total": data["price"],
            }).insert()

            # ✅ Create Guest Profile (linked to primary guest)
            guest_profile = frappe.get_doc({
                "doctype": "Hotel Reservation Guest Profile",
                "profile_id": f"PROF-{booking_number}-{data['room_number']}",
                "reservation_reference": reservation.name,
                "hotel_reservation": reservation.name,  # ✅ Link to Hotel Room Reservation
                "booking_number": booking_number,  # ✅ For reference
                "first_name": customer_name.split()[0] if customer_name else "Guest",
                "last_name": customer_name.split()[1] if customer_name and len(customer_name.split()) > 1 else "Guest",
                "email": customer_email or "",
                "phone": customer_phone or "",
                "room_number": data["room_number"],
                "check_in_date": from_str,
                "check_out_date": to_str,
                "payment_status": "Pending",
                "adults": 1,
                "children": 0,
                "contact_link": contact_name,
                "customer_link": customer_id,
                "created_at": datetime.now(),
                "created_by_user": frappe.session.user,
            }).insert()

            booking_reservations.append({
                "reservation_id": reservation.name,
                "room_number": data["room_number"],
                "guest_name": customer_name,  # ✅ PRIMARY GUEST
                "price": data["price"],
                "guest_profile_id": guest_profile.name
            })
            guest_profiles.append(guest_profile.name)

        # === HOLD ROOMS ===
        for room_number in rooms:
            room = frappe.get_doc("Hotel Room", room_number)
            room.booking_status = "Held"
            room.current_booking_number = booking_number
            room.hold_expires_at = hold_expires_at
            room.save()

        frappe.db.commit()

        return {
            "success": True,
            "booking_number": booking_number,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "is_repeat_customer": is_repeat_customer,
            "customer_status": "Pending",
            "sales_invoice_id": sales_invoice.name,
            "from_date": from_str,
            "to_date": to_str,
            "number_of_nights": num_nights,
            "total_rooms": len(rooms),
            "rooms_booked": rooms,
            "reservations": booking_reservations,
            "guest_profiles": guest_profiles,
            "total_price": total_price,
            "currency": "NGN",
            "status": "Pending Payment",
            "hold_expires_at": hold_expires_at.isoformat(),
            "customer_created": True,
            "next_step": "Call create_payment_link",
            "message": f"Booking {booking_number} created for {customer_name}. Payment required within 15 minutes."
        }

    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.log_error(f"Error creating booking: {str(e)}")
        frappe.throw(f"Error creating booking: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# PAYSTACK API CALL - GENERATES PAYMENT LINK
# ════════════════════════════════════════════════════════════════════════════

def call_paystack_api(amount, reference, customer_email, customer_name, description):
    """
    Call Paystack API to initialize transaction and get payment link.
    
    Args:
        amount (float): Payment amount in NGN
        reference (str): Unique reference (booking number)
        customer_email (str): Customer email
        customer_name (str): Customer name
        description (str): Payment description
    
    Returns:
        dict: API response with payment_url, access_code, and transaction_id
    """
    
    try:
        # Get Paystack secret key
        settings = frappe.get_doc("Hotel Settings")
        paystack_secret_key = settings.get_password("paystack_secret_key")
        
        if not paystack_secret_key:
            frappe.logger().error("Paystack secret key not configured")
            return {
                "status": "error",
                "message": "Paystack secret key not configured"
            }
        
        # Paystack API endpoint
        url = "https://api.paystack.co/transaction/initialize"
        
        # Prepare payload (amount in kobo - multiply by 100)
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
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json"
        }
        
        frappe.logger().info(f"Calling Paystack API with reference: {reference}")
        
        # Make request
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        result = response.json()
        
        frappe.logger().info(f"Paystack response: {result.get('status')}")
        
        # Check if successful
        if response.status_code == 200 and result.get("status") == True:
            data = result.get("data", {})
            return {
                "status": "success",
                "payment_url": data.get("authorization_url"),
                "access_code": data.get("access_code"),
                "transaction_id": data.get("reference"),
                "message": "Payment link generated successfully"
            }
        else:
            # Error from Paystack
            error_message = result.get("message", "Unknown error from Paystack")
            frappe.logger().error(f"Paystack error: {error_message}")
            return {
                "status": "error",
                "message": error_message
            }
    
    except requests.exceptions.Timeout:
        frappe.logger().error("Paystack API timeout")
        return {
            "status": "error",
            "message": "Request timeout. Please try again."
        }
    except requests.exceptions.ConnectionError:
        frappe.logger().error("Paystack API connection error")
        return {
            "status": "error",
            "message": "Connection error. Please check your internet connection."
        }
    except Exception as e:
        frappe.logger().error(f"Error calling Paystack API: {str(e)}")
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }


# ════════════════════════════════════════════════════════════════════════════
# CREATE PAYMENT LINK (WITH public_key IN RESPONSE)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def create_payment_link(booking_number):
    """
    Create Paystack payment link for a booking.
    ✅ Includes public_key in response for frontend Paystack integration.
    
    Args:
        booking_number (str): Booking number
    
    Returns:
        dict: Payment URL, public_key, and booking details
    """
    
    try:
        # Get booking by booking_number field
        booking_name = frappe.db.get_value("Hotel Booking", {"booking_number": booking_number}, "name")
        if not booking_name:
            raise frappe.ValidationError(f"Booking {booking_number} not found")
        
        booking = frappe.get_doc("Hotel Booking", booking_name)
        
        if booking.status != "Pending Payment":
            raise frappe.ValidationError(
                f"Booking {booking_number} is not pending payment (status: {booking.status})"
            )
        
        if booking.payment_status == "Paid":
            raise frappe.ValidationError("Booking already paid")
        
        # ✅ GET PAYSTACK SETTINGS FIRST (needed for all responses)
        settings = frappe.get_doc("Hotel Settings")
        paystack_public_key = settings.get_password("paystack_public_key")
        paystack_secret_key = settings.get_password("paystack_secret_key")
        
        if not paystack_public_key or not paystack_secret_key:
            raise frappe.ValidationError("Paystack keys not configured in Hotel Settings")
        
        frappe.logger().info(f"Creating payment link for booking {booking_number}")
        
        # ✅ CHECK IF TRANSACTION ALREADY EXISTS (avoid duplicates)
        if booking.transaction_id and booking.paystack_access_code:
            frappe.logger().info(f"Payment link already exists for {booking_number}")
            
            # Return existing payment link WITH public_key
            return {
                "success": True,
                "payment_url": f"https://checkout.paystack.com/{booking.paystack_access_code}",
                "booking_number": booking_number,
                "amount": booking.total_price,
                "currency": "NGN",
                "public_key": paystack_public_key,  # ✅ INCLUDE THIS!
                "transaction_id": booking.transaction_id,
                "access_code": booking.paystack_access_code,
                "message": "Using existing payment link"
            }
        
        # Call Paystack API to initialize transaction
        paystack_response = call_paystack_api(
            amount=booking.total_price,
            reference=booking_number,
            customer_email=booking.customer_email or "guest@hotel.com",
            customer_name=booking.customer_name or "Guest",
            description=f"Hotel booking: {booking.total_rooms} room(s), {booking.from_date} to {booking.to_date}"
        )
        
        if paystack_response.get("status") == "success":
            payment_url = paystack_response.get("payment_url")
            transaction_id = paystack_response.get("transaction_id")
            access_code = paystack_response.get("access_code")
            
            # Store transaction details in booking
            booking.transaction_id = transaction_id
            booking.paystack_access_code = access_code
            booking.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.logger().info(f"Payment link created for {booking_number}")
            
            # Return new payment link WITH public_key
            return {
                "success": True,
                "payment_url": payment_url,
                "booking_number": booking_number,
                "amount": booking.total_price,
                "currency": "NGN",
                "public_key": paystack_public_key,  # ✅ INCLUDE THIS!
                "transaction_id": transaction_id,
                "access_code": access_code,
                "message": "Redirect to payment URL to complete payment"
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
# PAYSTACK WEBHOOK - PAYMENT VERIFICATION (FIXED)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def paystack_webhook():
    """
    Paystack Webhook: Verify payment and activate booking.
    FIXED: Properly submit Hotel Room Reservations after payment
    """
    try:
        # Get raw body for signature verification
        body = frappe.request.get_data(as_text=True)
        signature = frappe.request.headers.get("X-Paystack-Signature")
        
        data = frappe.request.get_json()

        frappe.log_error(message=f"Paystack Webhook Payload: {data}", title="Paystack Webhook")
        
        # Verify webhook signature
        if not verify_paystack_signature(body, signature):
            frappe.log_error("Invalid Paystack signature", "Paystack Webhook")
            return {"status": "error", "message": "Invalid signature"}
        
        # Get transaction details
        event = data.get("event")
        transaction_data = data.get("data", {})
        booking_number = transaction_data.get("reference")
        status = transaction_data.get("status")
        amount = transaction_data.get("amount") / 100  # Convert from kobo to NGN
        
        if not booking_number:
            frappe.log_error("No booking reference in webhook", "Paystack Webhook")
            return {"status": "error", "message": "No booking reference"}
        
        # Get booking
        booking_name = frappe.db.get_value("Hotel Booking", {"booking_number": booking_number}, "name")
        if not booking_name:
            frappe.log_error(f"Booking {booking_number} not found", "Paystack Webhook")
            return {"status": "error", "message": "Booking not found"}
        
        booking = frappe.get_doc("Hotel Booking", booking_name)
        
        # Process successful payment
        if event == "charge.success" and status == "success":
            
            # Verify amount matches
            if amount != booking.total_price:
                frappe.log_error(
                    f"Amount mismatch: {amount} vs {booking.total_price}",
                    "Paystack Webhook"
                )
                booking.payment_status = "Failed"
                booking.save(ignore_permissions=True)
                frappe.db.commit()
                return {"status": "error", "message": "Amount mismatch"}
            
            # Elevate privileges for webhook processing
            current_user = frappe.session.user
            frappe.set_user("Administrator")
            
            try:
                # Activate customer
                if booking.customer:
                    customer = frappe.get_doc("Customer", booking.customer)
                    customer.disabled = 0  # Enable customer
                    customer.save(ignore_permissions=True)
                
                # Update booking
                booking.status = "Confirmed"
                booking.payment_status = "Paid"
                booking.payment_received_at = datetime.now()
                booking.save(ignore_permissions=True)

                reservations = frappe.get_all(
                    "Hotel Room Reservation",
                    {"booking_number": booking_name},
                    ["name", "room_number"]
                )
                
                # ✅ FIXED: Submit Hotel Room Reservations (don't just save)
                for res in reservations:
                    res_doc = frappe.get_doc("Hotel Room Reservation", res.name)
                    
                    # Only submit if in draft state
                    if res_doc.docstatus == 0:
                        res_doc.status = "Booked"
                        res_doc.payment_status = "Paid"
                        res_doc.hold_expires_at = None
                        
                        # ✅ SUBMIT the document (not just save)
                        res_doc.flags.ignore_permissions = True
                        res_doc.submit()
                        frappe.logger().info(f"✅ Submitted reservation {res_doc.name}")
                    else:
                        # If already submitted, update
                        res_doc.status = "Booked"
                        res_doc.payment_status = "Paid"
                        res_doc.hold_expires_at = None
                        res_doc.flags.ignore_permissions = True
                        res_doc.save()
                        frappe.logger().info(f"✅ Updated reservation {res_doc.name}")
                    
                    # Update guest profile
                    gp = frappe.db.get_value("Hotel Reservation Guest Profile", {"hotel_reservation": res.name})
                    if gp:
                        gp_doc = frappe.get_doc("Hotel Reservation Guest Profile", gp)
                        gp_doc.payment_status = "Paid"
                        gp_doc.save(ignore_permissions=True)
                    
                    # Update room
                    room_doc = frappe.get_doc("Hotel Room", res.room_number)
                    room_doc.booking_status = "Reserved"
                    room_doc.save(ignore_permissions=True)
                
                # Queue invoice submission as a background job
                if booking.sales_invoice:
                    frappe.enqueue(
                        'rhohotel.hotel_booking.submit_invoice_background',
                        invoice_id=booking.sales_invoice,
                        booking_number=booking_number,
                        queue='long'
                    )
                
                # Send confirmation email
                send_booking_confirmation_email(booking)
                
                frappe.db.commit()
                
                frappe.logger().info(f"✅ Booking {booking_number} confirmed via Paystack")
                return {
                    "status": "success",
                    "message": "Booking confirmed",
                    "booking_number": booking_number
                }
            
            finally:
                # Restore original user
                frappe.set_user(current_user)
        
        else:
            # Payment failed
            booking.payment_status = "Failed"
            booking.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.logger().warning(f"❌ Payment failed for booking {booking_number}")
            return {
                "status": "failed",
                "message": "Payment failed"
            }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Paystack Webhook Error")
        return {
            "status": "error",
            "message": str(e)
        }

        
def verify_paystack_signature(body, signature):
    """
    Verify Paystack webhook signature using SHA512.
    
    Args:
        body (str): Raw request body
        signature (str): X-Paystack-Signature header
    
    Returns:
        bool: True if signature is valid
    """
    try:
        settings = frappe.get_doc("Hotel Settings")
        secret_key = settings.get_password("paystack_secret_key")
        
        if not secret_key:
            frappe.log_error("Paystack secret key not found", "Signature Verification")
            return False
        
        # Create hash using SHA512
        hash_object = hmac.new(
            secret_key.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha512
        )
        
        computed_signature = hash_object.hexdigest()
        
        # Compare signatures (timing-safe comparison)
        return hmac.compare_digest(computed_signature, signature)
    
    except Exception as e:
        frappe.log_error(f"Signature verification error: {str(e)}", "Signature Verification")
        return False


# ════════════════════════════════════════════════════════════════════════════
# VERIFY PAYMENT MANUALLY (optional endpoint)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def verify_payment(reference):
    """
    Manually verify payment status from Paystack.
    
    Args:
        reference (str): Booking number / Paystack reference
    
    Returns:
        dict: Payment status
    """
    try:
        settings = frappe.get_doc("Hotel Settings")
        secret_key = settings.get_password("paystack_secret_key")
        
        if not secret_key:
            raise frappe.ValidationError("Paystack secret key not configured")
        
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json"
        }
        
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        
        response = requests.get(url, headers=headers, timeout=30)
        result = response.json()
        
        if response.status_code == 200 and result.get("status") == True:
            transaction = result.get("data", {})
            
            return {
                "success": True,
                "reference": transaction.get("reference"),
                "amount": transaction.get("amount") / 100,  # Convert from kobo
                "status": transaction.get("status"),
                "paid_at": transaction.get("paid_at"),
                "customer": transaction.get("customer", {})
            }
        else:
            return {
                "success": False,
                "message": result.get("message", "Unknown error")
            }
    
    except Exception as e:
        frappe.log_error(f"Verification error: {str(e)}")
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# EMAIL, CHECK-IN, CHECK-OUT, ETC.
# ════════════════════════════════════════════════════════════════════════════

def send_booking_confirmation_email(booking):
    try:
        rooms = "\n".join([f"- Room {r.room_number}" for r in
                          frappe.get_all("Hotel Room Reservation", {"booking_number": booking.booking_number},
                                         ["room_number"])])
        frappe.sendmail(
            recipients=[booking.customer_email],
            subject=f"Booking Confirmed - {booking.booking_number}",
            message=f"""
            <h3>Booking Confirmed!</h3>
            <p><strong>Booking:</strong> {booking.booking_number}</p>
            <p><strong>Guest:</strong> {booking.customer_name}</p>
            <p><strong>Check-in:</strong> {booking.from_date}</p>
            <p><strong>Check-out:</strong> {booking.to_date}</p>
            <p><strong>Paid:</strong> ₦{booking.total_price:,.2f}</p>
            <p><strong>Rooms:</strong><pre>{rooms}</pre></p>
            <p>Thank you!</p>
            """,
            now=True
        )
    except Exception as e:
        frappe.log_error(f"Email error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# CHECK-IN / CHECK-OUT FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def check_in_booking(booking_number):
    """Check in entire booking."""
    try:
        booking = frappe.get_doc("Hotel Booking", booking_number)
        
        if booking.status == "Checked-In":
            raise frappe.ValidationError("Already checked in")
        
        if booking.status != "Confirmed":
            raise frappe.ValidationError(f"Status: {booking.status}")
        
        booking.status = "Checked-In"
        booking.check_in_time = datetime.now()
        booking.save()
        
        # ✅ FIXED: Use 'booking_number' field
        reservations = frappe.get_all(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number},
            fields=["name"]
        )
        
        for res in reservations:
            res_doc = frappe.get_doc("Hotel Room Reservation", res.name)
            res_doc.status = "Checked-In"
            res_doc.check_in_time = datetime.now()
            res_doc.save()
            
            guest_profile = frappe.db.get_value(
                "Hotel Reservation Guest Profile",
                {"hotel_reservation": res.name}
            )
            
            if guest_profile:
                gp_doc = frappe.get_doc("Hotel Reservation Guest Profile", guest_profile)
                gp_doc.is_checked_in = 1
                gp_doc.check_in_time = datetime.now()
                gp_doc.save()
            
            room = frappe.get_doc("Hotel Room", res_doc.room_number)
            room.status = "Occupied"
            room.booking_status = "Occupied"
            room.save()
        
        frappe.db.commit()
        
        return {"success": True, "booking_number": booking_number, "status": "Checked-In"}
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def check_out_booking(booking_number):
    """Check out entire booking."""
    try:
        booking = frappe.get_doc("Hotel Booking", booking_number)
        
        if booking.status == "Completed":
            raise frappe.ValidationError("Already checked out")
        
        if booking.status not in ["Confirmed", "Checked-In"]:
            raise frappe.ValidationError(f"Cannot checkout from {booking.status}")
        
        booking.status = "Completed"
        booking.check_out_time = datetime.now()
        booking.save()
        
        # ✅ FIXED: Use 'booking_number' field
        reservations = frappe.get_all(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number},
            fields=["name"]
        )
        
        for res in reservations:
            res_doc = frappe.get_doc("Hotel Room Reservation", res.name)
            res_doc.status = "Completed"
            res_doc.check_out_time = datetime.now()
            res_doc.save()
            
            guest_profile = frappe.db.get_value(
                "Hotel Reservation Guest Profile",
                {"hotel_reservation": res.name}
            )
            
            if guest_profile:
                gp_doc = frappe.get_doc("Hotel Reservation Guest Profile", guest_profile)
                gp_doc.is_checked_out = 1
                gp_doc.check_out_time = datetime.now()
                gp_doc.save()
            
            room = frappe.get_doc("Hotel Room", res_doc.room_number)
            room.status = "Vacant"
            room.booking_status = "Available"
            room.housekeeping_status = "Dirty"
            room.save()
        
        frappe.db.commit()
        
        return {"success": True, "booking_number": booking_number, "status": "Completed"}
    
    except frappe.ValidationError as e:
        frappe.throw(str(e))
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# BOOKING MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_booking_details(booking_number):
    """Get booking details."""
    try:
        # Get the booking first to get the doc name
        booking_doc = frappe.get_doc("Hotel Booking", booking_number)
        
        # ✅ FIXED: Use 'booking_number' field
        reservations = frappe.db.get_list(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number},
            fields=["name", "room_number", "guest_name", "from_date", "to_date", "status"]
        )
        
        if not reservations:
            raise frappe.ValidationError("Not found")
        
        return {
            "booking_number": booking_number,
            "customer": booking_doc.customer,
            "customer_name": booking_doc.customer_name,
            "from_date": booking_doc.from_date,
            "to_date": booking_doc.to_date,
            "total_rooms": len(reservations),
            "total_price": booking_doc.total_price,
            "status": booking_doc.status,
            "reservations": reservations
        }
    
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


@frappe.whitelist()
def cancel_booking(booking_number):
    """Cancel booking."""
    try:
        booking = frappe.get_doc("Hotel Booking", booking_number)
        
        if booking.status == "Cancelled":
            raise frappe.ValidationError("Already cancelled")
        
        booking.status = "Cancelled"
        booking.save()
        
        # ✅ FIXED: Use 'booking_number' field
        reservations = frappe.get_all(
            "Hotel Room Reservation",
            filters={"booking_number": booking_number, "status": ["!=", "Cancelled"]},
            fields=["name", "room_number"]
        )
        
        for res in reservations:
            res_doc = frappe.get_doc("Hotel Room Reservation", res.name)
            res_doc.status = "Cancelled"
            res_doc.save()
            
            room = frappe.get_doc("Hotel Room", res.room_number)
            room.booking_status = "Available"
            room.status = "Vacant"
            room.save()
        
        frappe.db.commit()
        
        return {"success": True, "booking_number": booking_number}
    
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# GUEST PROFILE MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_guest_profiles_for_checkin(date=None):
    """Get guest profiles for check-in."""
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
            fields=["name", "first_name", "last_name", "room_number", "email", "phone", "hotel_reservation"],
            order_by="created_at asc"
        )
        
        return {"success": True, "count": len(profiles), "date": date, "profiles": profiles}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_guest_profile_details(profile_id, **kwargs):
    """Update guest profile."""
    try:
        profile = frappe.get_doc("Hotel Reservation Guest Profile", profile_id)
        
        allowed_fields = [
            "email", "phone", "date_of_birth", "gender", "nationality",
            "id_type", "id_number", "address_line1", "city", "state",
            "special_requests", "dietary_requirements", "adults", "children"
        ]
        
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                setattr(profile, field, value)
        
        profile.save()
        frappe.db.commit()
        
        return {"success": True, "profile_id": profile.name}
    
    except Exception as e:
        frappe.throw(f"Error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ════════════════════════════════════════════════════════════════════════════


def submit_invoice_background(invoice_id, booking_number):
    """
    Background job to submit Sales Invoice and automatically
    create a Payment Entry after successful Paystack payment.
    FIXED: Properly set paid_amount and received_amount
    """
    try:
        frappe.logger().info(f"[BG Job] Starting: Submit + Payment for Invoice {invoice_id}")

        # 🔥 Elevate privilege for entire operation
        current_user = frappe.session.user
        frappe.set_user("Administrator")

        # 1️⃣ LOAD & SUBMIT INVOICE
        inv = frappe.get_doc("Sales Invoice", invoice_id)

        if inv.docstatus == 0:
            inv.flags.ignore_permissions = True
            inv.submit()
            frappe.db.commit()
            frappe.logger().info(f"✅ Invoice {invoice_id} submitted.")

        # 2️⃣ FETCH PAYMENT SETTINGS
        mode_of_payment = frappe.db.get_value("Mode of Payment", {"name": "Paystack"}, "name")
        if not mode_of_payment:
            frappe.logger().error("❌ Mode of Payment 'Paystack' not found.")
            frappe.set_user(current_user)
            return

        paid_to = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": "Paystack", "company": inv.company},
            "default_account"
        )

        if not paid_to:
            frappe.logger().error("❌ No Default Account under Mode of Payment Account for 'Paystack'.")
            frappe.set_user(current_user)
            return

        paid_from = inv.debit_to
        if not paid_from:
            frappe.logger().error("❌ Invoice missing debit_to account.")
            frappe.set_user(current_user)
            return

        # 3️⃣ BUILD PAYMENT ENTRY
        # FIX: Set BOTH paid_amount and received_amount to invoice grand_total
        pe = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": inv.customer,
            "posting_date": frappe.utils.today(),
            "payment_date": frappe.utils.today(),
            "mode_of_payment": mode_of_payment,
            "paid_from": paid_from,
            "paid_to": paid_to,
            "paid_amount": inv.grand_total,      # ✅ REQUIRED: Set this
            "received_amount": inv.grand_total,  # ✅ Set this to same value
            "reference_no": booking_number,
            "reference_date": frappe.utils.today(),
            "remarks": f"Paystack payment for booking {booking_number}"
        })

        # APPLY PAYMENT TO INVOICE
        # ✅ outstanding_amount = 0 means invoice is FULLY PAID
        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice_id,
            "total_amount": inv.grand_total,
            "outstanding_amount": 0,              # ✅ Must be 0 for full payment
            "allocated_amount": inv.grand_total
        })

        pe.flags.ignore_permissions = True
        pe.flags.ignore_mandatory = False  # Let validation run to catch issues
        pe.flags.ignore_account_permission = True

        # 4️⃣ INSERT & SUBMIT PAYMENT ENTRY
        pe.insert(ignore_permissions=True)
        pe.submit()
        frappe.db.commit()

        frappe.logger().info(f"✅ Payment Entry {pe.name} created & submitted successfully.")
        frappe.logger().info(f"   Paid Amount: {pe.paid_amount}")
        frappe.logger().info(f"   Received Amount: {pe.received_amount}")

        # 🔥 Restore original user
        frappe.set_user(current_user)

    except Exception as e:
        tb = frappe.get_traceback()
        frappe.log_error(tb, f"Invoice Submit Error - {invoice_id}")
        frappe.logger().error(f"❌ Error processing invoice {invoice_id}: {e}")
        frappe.logger().error(tb)

        # Restore user even in error
        try:
            frappe.set_user(current_user)
        except:
            pass












# # ════════════════════════════════════════════════════════════════════════════
# # BACKGROUND JOB - RELEASE EXPIRED HOLDS
# # ════════════════════════════════════════════════════════════════════════════
# def release_expired_holds():
#     """
#     Background job to release rooms where hold has expired without payment.
#     Updates statuses but does NOT delete documents.
#     """
#     try:
#         current_time = datetime.now()
        
#         # Find expired bookings
#         expired_bookings = frappe.get_all(
#             "Hotel Booking",
#             filters={
#                 "status": "Pending Payment",
#                 "payment_status": "Pending", 
#                 "hold_expires_at": ["<", current_time]
#             },
#             fields=["name", "booking_number", "customer"]
#         )
        
#         if not expired_bookings:
#             frappe.logger().info("No expired holds to release")
#             return {"success": True, "released": 0}
        
#         released_count = 0
        
#         for booking in expired_bookings:
#             try:
#                 frappe.logger().info(f"Releasing expired hold for booking {booking.booking_number}")
                
#                 # Update booking status - use "Failed" instead of "Timeout"
#                 booking_doc = frappe.get_doc("Hotel Booking", booking.name)
#                 booking_doc.status = "Cancelled"
#                 booking_doc.payment_status = "Failed"  # ✅ FIXED: Use "Failed" instead of "Timeout"
#                 booking_doc.save(ignore_permissions=True)
                
#                 # Get all reservations for this booking
#                 reservations = frappe.get_all(
#                     "Hotel Room Reservation", 
#                     filters={"booking_number": booking.name},
#                     fields=["name", "room_number"]
#                 )
                
#                 for reservation in reservations:
#                     # Update reservation status - use "Failed" instead of "Timeout"
#                     res_doc = frappe.get_doc("Hotel Room Reservation", reservation.name)
#                     res_doc.status = "Cancelled"
#                     res_doc.payment_status = "Failed"  # ✅ FIXED: Use "Failed" instead of "Timeout"
#                     res_doc.hold_expires_at = None
                    
#                     # Only cancel if in draft state, otherwise just update
#                     if res_doc.docstatus == 0:
#                         res_doc.save(ignore_permissions=True)
#                     else:
#                         res_doc.flags.ignore_permissions = True
#                         res_doc.save()
                    
#                     # Update guest profile - use "Failed" instead of "Timeout"
#                     guest_profiles = frappe.get_all(
#                         "Hotel Reservation Guest Profile",
#                         filters={"hotel_reservation": reservation.name},
#                         fields=["name"]
#                     )
                    
#                     for profile in guest_profiles:
#                         gp_doc = frappe.get_doc("Hotel Reservation Guest Profile", profile.name)
#                         gp_doc.payment_status = "Failed"  # ✅ FIXED: Use "Failed" instead of "Timeout"
#                         gp_doc.save(ignore_permissions=True)
                    
#                     # Release the room
#                     room_doc = frappe.get_doc("Hotel Room", reservation.room_number)
#                     room_doc.booking_status = "Available"
#                     room_doc.current_booking_number = None
#                     room_doc.hold_expires_at = None
#                     room_doc.save(ignore_permissions=True)
                
#                 released_count += 1
#                 frappe.logger().info(f"✅ Released expired hold for booking {booking.booking_number}")
                
#             except Exception as e:
#                 # ✅ FIXED: Shorter error message for logging
#                 error_msg = f"Hold release error for {booking.booking_number}: {str(e)[:50]}"
#                 frappe.log_error(title="Hold Release Error", message=error_msg)
#                 continue
        
#         frappe.db.commit()
        
#         frappe.logger().info(f"🎯 Released {released_count} expired holds")
#         return {"success": True, "released": released_count}
        
#     except Exception as e:
#         # ✅ FIXED: Shorter error message for logging
#         error_msg = f"Background job error: {str(e)[:50]}"
#         frappe.log_error(title="Background Job Error", message=error_msg)
#         return {"success": False, "error": str(e)}

        

# @frappe.whitelist()
# def manual_release_expired_holds():
#     """Manual trigger for testing hold release"""
#     return release_expired_holds()








# ════════════════════════════════════════════════════════════════════════════
# BACKGROUND JOB - RELEASE EXPIRED HOLDS (ENHANCED)
# ════════════════════════════════════════════════════════════════════════════
def release_expired_holds():
    """
    Enhanced background job to release rooms where hold has expired without payment.
    Also cleans up orphaned rooms stuck in Held status.
    """
    try:
        current_time = datetime.now()
        released_count = 0
        
        print(f"🕒 Background job running at: {current_time}")
        
        # === STRATEGY 1: Release via expired bookings ===
        expired_bookings = frappe.get_all(
            "Hotel Booking",
            filters={
                "status": "Pending Payment",
                "payment_status": "Pending", 
                "hold_expires_at": ["<", current_time]
            },
            fields=["name", "booking_number", "customer"]
        )
        
        print(f"Found {len(expired_bookings)} expired bookings")
        
        for booking in expired_bookings:
            try:
                print(f"Processing expired booking: {booking.booking_number}")
                
                # Update booking status
                booking_doc = frappe.get_doc("Hotel Booking", booking.name)
                booking_doc.status = "Cancelled"
                booking_doc.payment_status = "Failed"
                booking_doc.save(ignore_permissions=True)
                
                # Get all reservations for this booking
                reservations = frappe.get_all(
                    "Hotel Room Reservation", 
                    filters={"booking_number": booking.name},
                    fields=["name", "room_number"]
                )
                
                print(f"Found {len(reservations)} reservations for booking {booking.booking_number}")
                
                for reservation in reservations:
                    # Update reservation status
                    res_doc = frappe.get_doc("Hotel Room Reservation", reservation.name)
                    res_doc.status = "Cancelled"
                    res_doc.payment_status = "Failed"
                    res_doc.hold_expires_at = None
                    
                    if res_doc.docstatus == 0:
                        res_doc.save(ignore_permissions=True)
                    else:
                        res_doc.flags.ignore_permissions = True
                        res_doc.save()
                    
                    # Update guest profile
                    guest_profiles = frappe.get_all(
                        "Hotel Reservation Guest Profile",
                        filters={"hotel_reservation": reservation.name},
                        fields=["name"]
                    )
                    
                    for profile in guest_profiles:
                        gp_doc = frappe.get_doc("Hotel Reservation Guest Profile", profile.name)
                        gp_doc.payment_status = "Failed"
                        gp_doc.save(ignore_permissions=True)
                    
                    # ⭐️ CRITICAL: Release the room with proper error handling
                    try:
                        room_doc = frappe.get_doc("Hotel Room", reservation.room_number)
                        room_doc.booking_status = "Available"
                        room_doc.current_booking_number = None
                        room_doc.hold_expires_at = None
                        room_doc.save(ignore_permissions=True)
                        print(f"✅ Released room {reservation.room_number}")
                        released_count += 1
                    except Exception as room_error:
                        print(f"❌ Failed to release room {reservation.room_number}: {str(room_error)}")
                        # Continue with other rooms even if one fails
                        continue
                
                print(f"✅ Completed booking {booking.booking_number}")
                
            except Exception as e:
                error_msg = f"Error with {booking.booking_number}: {str(e)[:50]}"
                print(f"❌ {error_msg}")
                frappe.log_error(title="Hold Release Error", message=error_msg)
                continue
        
        # === STRATEGY 2: Clean up orphaned held rooms (SAFETY NET) ===
        print("Checking for orphaned held rooms...")
        all_held_rooms = frappe.get_all(
            "Hotel Room",
            filters={"booking_status": "Held"},
            fields=["name", "current_booking_number", "hold_expires_at"]
        )
        
        print(f"Found {len(all_held_rooms)} held rooms in system")
        
        for room in all_held_rooms:
            try:
                room_doc = frappe.get_doc("Hotel Room", room.name)
                
                # Check if this room should be released
                should_release = False
                
                # Case 1: Hold time expired
                if room.hold_expires_at and room.hold_expires_at < current_time:
                    should_release = True
                    print(f"Room {room.name}: hold expired")
                
                # Case 2: No booking number
                elif not room.current_booking_number:
                    should_release = True
                    print(f"Room {room.name}: no booking number")
                
                # Case 3: Booking doesn't exist or is cancelled
                elif room.current_booking_number:
                    booking_exists = frappe.db.exists("Hotel Booking", {"booking_number": room.current_booking_number})
                    if not booking_exists:
                        should_release = True
                        print(f"Room {room.name}: booking doesn't exist")
                    else:
                        booking_status = frappe.db.get_value("Hotel Booking", {"booking_number": room.current_booking_number}, "status")
                        if booking_status == "Cancelled":
                            should_release = True
                            print(f"Room {room.name}: booking is cancelled")
                
                # Release the room if any condition is met
                if should_release and room_doc.booking_status == "Held":
                    room_doc.booking_status = "Available"
                    room_doc.current_booking_number = None
                    room_doc.hold_expires_at = None
                    room_doc.save(ignore_permissions=True)
                    print(f"✅ Released orphaned room: {room.name}")
                    released_count += 1
                    
            except Exception as e:
                error_msg = f"Error with room {room.name}: {str(e)[:50]}"
                print(f"❌ {error_msg}")
                continue
        
        frappe.db.commit()
        
        print(f"🎯 Released {released_count} rooms total")
        return {"success": True, "released": released_count}
        
    except Exception as e:
        error_msg = f"Background job error: {str(e)[:50]}"
        print(f"❌ {error_msg}")
        frappe.log_error(title="Background Job Error", message=error_msg)
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def manual_release_expired_holds():
    """Manual trigger for testing hold release"""
    return release_expired_holds()

# ════════════════════════════════════════════════════════════════════════════
# IMMEDIATE ROOM CLEANUP FUNCTION
# ════════════════════════════════════════════════════════════════════════════
@frappe.whitelist()
def force_release_all_held_rooms():
    """Force release ALL held rooms immediately"""
    try:
        held_rooms = frappe.get_all(
            "Hotel Room",
            filters={"booking_status": "Held"},
            fields=["name", "current_booking_number", "hold_expires_at"]
        )
        
        print(f"Force releasing {len(held_rooms)} held rooms")
        
        for room in held_rooms:
            room_doc = frappe.get_doc("Hotel Room", room.name)
            room_doc.booking_status = "Available"
            room_doc.current_booking_number = None
            room_doc.hold_expires_at = None
            room_doc.save(ignore_permissions=True)
            print(f"✅ Force released: {room.name}")
        
        frappe.db.commit()
        return {"success": True, "released": len(held_rooms)}
    
    except Exception as e:
        return {"success": False, "error": str(e)}