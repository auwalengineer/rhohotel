"""
Hotel Booking - REFACTORED WITH TEMPORARY BOOKING
Handles multi-room bookings with temporary hold before payment.

Location: rhohotel/rhohotel/hotel_booking_v2.py

KEY CHANGES:
- Step 1: Create TEMPORARY BOOKING (holds all data)
- Step 2: Generate Paystack payment link
- Step 3: On successful payment → Convert to Customer, Invoice, Reservations
- NO documents created until payment confirmed
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
    get_room_tariff,
    generate_secure_booking_number,
    create_or_get_item
)


# ════════════════════════════════════════════════════════════════════════════
# STEP 1: CREATE TEMPORARY BOOKING (NO PERMANENT DOCS YET)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def create_booking(from_date, to_date, rooms, customer_email=None, customer_phone=None, customer_name=None):
    """
    Create a TEMPORARY booking - holds all data without creating Customer/Invoice.
    
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
        
        # === VALIDATE ROOMS & CALCULATE PRICE ===
        temp_rooms = []
        total_price = 0
        
        for room_number in rooms:
            room = validate_room_for_booking(room_number, from_str, to_str)
            tariff = get_room_tariff(room.get("room_type"), from_str)
            
            if not tariff:
                raise frappe.ValidationError(f"No tariff for {room.get('room_type')}")
            
            rate_amount = float(tariff.get("rate_amount", 0))
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
    ✅ Includes public_key for frontend integration
    """
    try:
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
# STEP 3: PAYSTACK WEBHOOK - CONVERT TEMPORARY TO PERMANENT
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def paystack_webhook():
    """
    Paystack Webhook: Payment successful → Convert temporary booking to permanent.
    
    Workflow:
    1. Verify payment with Paystack
    2. Get temporary booking
    3. Create Customer
    4. Create Sales Invoice
    5. Create Hotel Room Reservations
    6. Create Guest Profiles
    7. Delete temporary booking (or mark as converted)
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
        
        # === GET TEMPORARY BOOKING ===
        try:
            temp_booking = frappe.get_doc("Temporary Booking", {"booking_number": booking_number})
        except frappe.DoesNotExistError:
            frappe.log_error(f"Temp booking {booking_number} not found", "Paystack Webhook")
            return {"status": "error", "message": "Booking not found"}
        
        # === PROCESS SUCCESSFUL PAYMENT ===
        if event == "charge.success" and status == "success":
            
            # Verify amount
            if amount != temp_booking.total_price:
                frappe.log_error(
                    f"Amount mismatch: {amount} vs {temp_booking.total_price}",
                    "Paystack Webhook"
                )
                temp_booking.payment_status = "Failed"
                temp_booking.save(ignore_permissions=True)
                frappe.db.commit()
                return {"status": "error", "message": "Amount mismatch"}
            
            # === ELEVATE PRIVILEGES ===
            current_user = frappe.session.user
            frappe.set_user("Administrator")
            
            try:
                # ✅ STEP 1: CREATE CUSTOMER
                customer_doc = frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": temp_booking.guest_name,
                    "customer_type": "Individual",
                    "email_id": temp_booking.guest_email or "",
                    "mobile_no": temp_booking.guest_phone or "",
                    "status": "Active",
                    "booking_reference": booking_number,
                }).insert(ignore_permissions=True)
                customer_id = customer_doc.name
                
                frappe.logger().info(f"✅ Created Customer {customer_id}")
                
                # ✅ STEP 2: CREATE CONTACT
                contact_name = None
                if temp_booking.guest_email:
                    parts = temp_booking.guest_name.split(' ', 1)
                    contact_doc = frappe.get_doc({
                        "doctype": "Contact",
                        "first_name": parts[0],
                        "last_name": parts[1] if len(parts) > 1 else "",
                        "email_id": temp_booking.guest_email,
                        "phone": temp_booking.guest_phone or "",
                    }).insert(ignore_permissions=True)
                    contact_name = contact_doc.name
                    frappe.logger().info(f"✅ Created Contact {contact_name}")
                
                # ✅ STEP 3: CREATE SALES INVOICE
                invoice_items = []
                for room in temp_booking.rooms:
                    item_code = create_or_get_item(
                        room["room_number"],
                        room["room_type"],
                        None
                    )
                    invoice_items.append({
                        "item_code": item_code,
                        "item_name": room["room_number"],
                        "qty": room["num_nights"],
                        "rate": room["rate_per_night"],
                        "description": f"Room {room['room_number']} - {room['num_nights']} night(s)"
                    })
                
                sales_invoice = frappe.get_doc({
                    "doctype": "Sales Invoice",
                    "customer": customer_id,
                    "contact_email": temp_booking.guest_email or "",
                    "posting_date": nowdate(),
                    "due_date": nowdate(),
                    "items": invoice_items
                }).insert(ignore_permissions=True)
                
                frappe.logger().info(f"✅ Created Sales Invoice {sales_invoice.name}")
                
                # ✅ STEP 4: CREATE HOTEL ROOM RESERVATIONS + GUEST PROFILES
                guest_profiles = []
                
                for room in temp_booking.rooms:
                    reservation_items = [{
                        "item": room["room_number"],
                        "room_type": room["room_type"],
                        "rate_type": room.get("rate_type", "Standard"),
                        "season_type": room.get("season_type", ""),
                        "qty": room["num_nights"],
                        "rate": room["rate_per_night"],
                        "amount": room["total_price"]
                    }]
                    
                    # Create Hotel Room Reservation
                    reservation = frappe.get_doc({
                        "doctype": "Hotel Room Reservation",
                        "room_number": room["room_number"],
                        "from_date": temp_booking.check_in_date,
                        "to_date": temp_booking.check_out_date,
                        "guest_name": temp_booking.guest_name,
                        "customer": customer_id,
                        "status": "Booked",
                        "payment_status": "Paid",
                        "booking_number": booking_number,
                        "hold_expires_at": None,
                        "sales_invoice": sales_invoice.name,
                        "items": reservation_items,
                        "net_total": room["total_price"],
                    }).insert(ignore_permissions=True)
                    
                    # Submit reservation
                    reservation.flags.ignore_permissions = True
                    reservation.submit()
                    
                    frappe.logger().info(f"✅ Created & submitted Reservation {reservation.name}")
                    
                    # Create Guest Profile
                    guest_profile = frappe.get_doc({
                        "doctype": "Hotel Reservation Guest Profile",
                        "profile_id": f"PROF-{booking_number}-{room['room_number']}",
                        "reservation_reference": reservation.name,
                        "hotel_reservation": reservation.name,
                        "booking_number": booking_number,
                        "first_name": temp_booking.guest_name.split()[0] if temp_booking.guest_name else "Guest",
                        "last_name": temp_booking.guest_name.split()[1] if temp_booking.guest_name and len(temp_booking.guest_name.split()) > 1 else "",
                        "email": temp_booking.guest_email or "",
                        "phone": temp_booking.guest_phone or "",
                        "room_number": room["room_number"],
                        "check_in_date": temp_booking.check_in_date,
                        "check_out_date": temp_booking.check_out_date,
                        "payment_status": "Paid",
                        "adults": 1,
                        "children": 0,
                        "contact_link": contact_name,
                        "customer_link": customer_id,
                        "created_at": datetime.now(),
                        "created_by_user": frappe.session.user,
                    }).insert(ignore_permissions=True)
                    
                    guest_profiles.append(guest_profile.name)
                    frappe.logger().info(f"✅ Created Guest Profile {guest_profile.name}")
                    
                    # Update room status
                    room_doc = frappe.get_doc("Hotel Room", room["room_number"])
                    room_doc.booking_status = "Reserved"
                    room_doc.current_booking_number = None
                    room_doc.hold_expires_at = None
                    room_doc.save(ignore_permissions=True)
                
                # ✅ STEP 5: SUBMIT SALES INVOICE (background job)
                if sales_invoice:
                    frappe.enqueue(
                        'rhohotel.hotel_booking_v2.submit_invoice_background',
                        invoice_id=sales_invoice.name,
                        booking_number=booking_number,
                        queue='long'
                    )
                
                # ✅ STEP 6: UPDATE TEMPORARY BOOKING STATUS
                temp_booking.status = "Payment Completed"
                temp_booking.payment_status = "Paid"
                temp_booking.payment_received_at = datetime.now()
                temp_booking.save(ignore_permissions=True)
                
                # ✅ STEP 7: SEND CONFIRMATION EMAIL
                send_booking_confirmation_email(
                    temp_booking.guest_name,
                    temp_booking.guest_email,
                    booking_number,
                    temp_booking.check_in_date,
                    temp_booking.check_out_date,
                    temp_booking.total_price,
                    [room["room_number"] for room in temp_booking.rooms]
                )
                
                frappe.db.commit()
                
                frappe.logger().info(f"✅ Booking {booking_number} fully converted from temporary")
                return {
                    "status": "success",
                    "message": "Booking confirmed",
                    "booking_number": booking_number
                }
            
            finally:
                frappe.set_user(current_user)
        
        else:
            # Payment failed
            temp_booking.payment_status = "Failed"
            temp_booking.status = "Cancelled"
            temp_booking.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.logger().warning(f"❌ Payment failed for {booking_number}")
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


# ════════════════════════════════════════════════════════════════════════════
# EMAIL & BACKGROUND JOBS
# ════════════════════════════════════════════════════════════════════════════

def send_booking_confirmation_email(guest_name, guest_email, booking_number, check_in, check_out, total_price, rooms):
    """Send booking confirmation email."""
    try:
        rooms_list = "\n".join([f"- Room {r}" for r in rooms])
        
        frappe.sendmail(
            recipients=[guest_email],
            subject=f"Booking Confirmed - {booking_number}",
            message=f"""
            <h3>Booking Confirmed!</h3>
            <p><strong>Booking:</strong> {booking_number}</p>
            <p><strong>Guest:</strong> {guest_name}</p>
            <p><strong>Check-in:</strong> {check_in}</p>
            <p><strong>Check-out:</strong> {check_out}</p>
            <p><strong>Paid:</strong> ₦{total_price:,.2f}</p>
            <p><strong>Rooms:</strong><pre>{rooms_list}</pre></p>
            <p>Thank you!</p>
            """,
            now=True
        )
    except Exception as e:
        frappe.log_error(f"Email error: {str(e)}")


def submit_invoice_background(invoice_id, booking_number):
    """Submit Sales Invoice and create Payment Entry after payment."""
    try:
        frappe.logger().info(f"[BG] Submitting invoice {invoice_id}")
        
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        
        try:
            # Load and submit invoice
            inv = frappe.get_doc("Sales Invoice", invoice_id)
            
            if inv.docstatus == 0:
                inv.flags.ignore_permissions = True
                inv.submit()
                frappe.db.commit()
                frappe.logger().info(f"✅ Invoice {invoice_id} submitted")
            
            # Create Payment Entry
            mode_of_payment = frappe.db.get_value("Mode of Payment", {"name": "Paystack"}, "name")
            if not mode_of_payment:
                frappe.logger().error("Mode of Payment 'Paystack' not found")
                frappe.set_user(current_user)
                return
            
            paid_to = frappe.db.get_value(
                "Mode of Payment Account",
                {"parent": "Paystack", "company": inv.company},
                "default_account"
            )
            
            if not paid_to:
                frappe.logger().error("No Default Account for Paystack")
                frappe.set_user(current_user)
                return
            
            paid_from = inv.debit_to
            if not paid_from:
                frappe.logger().error("Invoice missing debit_to")
                frappe.set_user(current_user)
                return
            
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
                "paid_amount": inv.grand_total,
                "received_amount": inv.grand_total,
                "reference_no": booking_number,
                "reference_date": frappe.utils.today(),
                "remarks": f"Paystack payment for booking {booking_number}"
            })
            
            pe.append("references", {
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice_id,
                "total_amount": inv.grand_total,
                "outstanding_amount": 0,
                "allocated_amount": inv.grand_total
            })
            
            pe.flags.ignore_permissions = True
            pe.flags.ignore_mandatory = False
            pe.flags.ignore_account_permission = True
            
            pe.insert(ignore_permissions=True)
            pe.submit()
            frappe.db.commit()
            
            frappe.logger().info(f"✅ Payment Entry {pe.name} created & submitted")
        
        finally:
            frappe.set_user(current_user)
    
    except Exception as e:
        tb = frappe.get_traceback()
        frappe.log_error(tb, f"Invoice Submit Error - {invoice_id}")
        frappe.logger().error(f"❌ Error: {e}")


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
                tb.save(ignore_permissions=True)
                
                # Release associated rooms
                rooms_held = frappe.get_all(
                    "Hotel Room",
                    filters={
                        "current_booking_number": temp_booking["booking_number"],
                        "booking_status": "Held"
                    },
                    fields=["name"]
                )
                
                for room in rooms_held:
                    room_doc = frappe.get_doc("Hotel Room", room.name)
                    room_doc.booking_status = "Available"
                    room_doc.current_booking_number = None
                    room_doc.hold_expires_at = None
                    room_doc.save(ignore_permissions=True)
                    released_count += 1
                    frappe.logger().info(f"✅ Released room {room.name}")
                
                frappe.logger().info(f"✅ Expired temp booking {temp_booking['booking_number']}")
            
            except Exception as e:
                frappe.logger().error(f"Error with {temp_booking['booking_number']}: {str(e)}")
                continue
        
        frappe.db.commit()
        frappe.logger().info(f"🎯 Released {released_count} rooms from expired holds")
        return {"success": True, "released": released_count}
    
    except Exception as e:
        frappe.log_error(str(e), "Hold Release Error")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def manual_release_expired_holds():
    """Manual trigger for hold release."""
    return release_expired_holds()