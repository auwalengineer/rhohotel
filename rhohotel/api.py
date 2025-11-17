import frappe
import frappe
from frappe.utils import nowdate, add_days, cstr
from datetime import datetime
import json
import uuid
import requests
from frappe.utils import flt


# Import translation function
_ = frappe._



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


#api url: /api/method/rhohotel.api.get_guest_name_room_number
@frappe.whitelist(allow_guest=True)
def get_guest_name_room_number(room_number):
    guest_name = frappe.db.get_value(
        "Hotel Room Check In",
        {"room_number": room_number, "status": "Checked In"},
        "guest"
    )
    if guest_name:
        guest_full_name = frappe.db.get_value("Hotel Guest", {"name": guest_name}, "hotel_guest_name")

        if guest_full_name:
            return guest_full_name or ""



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
            # season = frappe.db.get_value("Hotel Season", {
            #     "start_date": ("<=", check_in_date),
            #     "end_date": (">=", check_in_date),
            #     "is_active": 1
            # }, "name")

            # if not season:
            #     return {"error": "No active season found for the selected date."}
        season = "Regular Season"  # Placeholder, implement actual season logic
        # Determine the day type (Weekday/Weekend)
        day_of_week = datetime.strptime(check_in_date, "%Y-%m-%d").weekday()
        day_type = "Weekend" if day_of_week >= 5 else "Weekday" # 5: Saturday, 6: Sunday


        # Fetch the room rate
        rate_amount = frappe.db.get_value("Hotel Room Tariff", {
            "room_type": room_type,
            "day_type": day_type,
            "is_active": 1
        }, "rate_amount")

        if not rate_amount:
            # Fallback to default tariff for the room type
            rate_amount = frappe.db.get_value("Hotel Room Tariff", {
                "room_type": room_type,
                "is_active": 1
            }, "rate_amount")

        return rate_amount or 0

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error fetching room rate")
        return {"error": str(e)}

@frappe.whitelist()
def get_payment_session_status(payment_session):
	# Mocking the status check
	import random
	status = random.choice(["Pending", "Paid"])
	return {"status": status}

def get_credentials():
    settings = frappe.get_single("Moniepoint Settings")
    base_url = settings.base_url or "https://channel.moniepoint.com"
    client_id = settings.client_id
    client_secret = settings.client_secret
    terminal_serial = settings.terminal_serial_number
    if not all([client_id, client_secret, terminal_serial]):
        frappe.throw(_("Please configure Moniepoint credentials in Moniepoint Settings"))
    return client_id, client_secret, terminal_serial, base_url


# def get_access_token():
#     client_id, client_secret, terminal_serial, base_url = get_credentials()
    
#     try:
#         response = requests.post(
#             f"{base_url}/v1/auth",
#             json={
#                 "clientId": client_id,
#                 "clientSecret": client_secret
#             },
#             headers={
#                 "Content-Type": "application/json"
#             }
#         )
        
#         if response.status_code != 200:
#             error_msg = response.text
#             frappe.log_error(
#                 f"Moniepoint Auth Error - Status: {response.status_code}, Response: {error_msg}",
#                 "Moniepoint Integration"
#             )
#             frappe.throw(_("Authentication failed. Please check Moniepoint credentials."))
            
#         data = response.json()
#         token = data.get("accessToken")
        
#         if not token:
#             frappe.throw(_("Access token not found in Moniepoint response"))
            
#         return token
        
#     except requests.exceptions.RequestException as e:
#         frappe.log_error(f"Moniepoint Authentication Error: {str(e)}", "Moniepoint Integration")
#         frappe.throw(_("Failed to authenticate with Moniepoint: {0}").format(str(e)))

def get_access_token():
    client_id, client_secret, terminal_serial, base_url = get_credentials()

    try:

        settings = frappe.get_single("Moniepoint Settings")
        base_url = settings.base_url or "https://channel.moniepoint.com"
        client_id = settings.client_id
        client_secret = settings.client_secret
        response = requests.post(
            f"{base_url}/v1/auth",
            json={
                "clientId": "api-client-11630997-4d5e6dc2-7f77-4b03-be5c-5ababd85e67b",
                "clientSecret": "hmd!@yP1Q$3*+%Y8d5WJ"
            },
            headers={
                "Content-Type": "application/json"
            },
            timeout=15  # optional: prevent hanging requests
        )

        # Handle non-200 responses
        if response.status_code != 200:
            frappe.log_error(
                f"✗ Moniepoint Auth Error:\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text}",
                "Moniepoint Integration"
            )
            frappe.throw(_("Authentication failed. Please check Moniepoint credentials."))

        data = response.json()
        token = data.get("accessToken")

        if not token:
            frappe.log_error(
                f"✗ Invalid Response: {data}",
                "Moniepoint Integration"
            )
            frappe.throw(_("Access token not found in Moniepoint response"))

        frappe.logger().info("✓ Access token obtained successfully")
        return token

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            f"✗ Moniepoint Authentication Error: {str(e)}",
            "Moniepoint Integration"
        )
        frappe.throw(_("Failed to authenticate with Moniepoint: {0}").format(str(e)))

@frappe.whitelist()
def initiate_payment(check_in):
    # if isinstance(invoice_names, str):
    #     invoice_names = json.loads(invoice_names)

    if not check_in:
        frappe.throw(_("Check in not supplied."))

    invoice_names = frappe.db.get_all(
            "Sales Invoice",
            filters={"custom_hotel_room_check_in": check_in, "outstanding_amount": [">", 0]},
            pluck="name"
        )
    
    if not invoice_names:
        frappe.throw(_("No invoices provided for payment."))

    total_amount = sum(frappe.db.get_value("Sales Invoice", name, "grand_total") for name in invoice_names)


    # Create Payment Session
    session = frappe.new_doc("Payment Session")
    session.payment_reference =  frappe.generate_hash(length=10)
    session.total_amount = total_amount
    session.hotel_room_check_in = check_in
    session.posting_date = datetime.now()
    session.transaction_reference = ""

    try:
        session.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error creating Payment Session")
        frappe.throw(_("Failed to create Payment Session: {0}").format(str(e)))

    for inv_name in invoice_names:
        invoice = frappe.new_doc("Payment Session Invoices")
        invoice.invoice_number = inv_name
        invoice.payment_session = session.name
        invoice.insert()
    frappe.db.commit()

    
    # session = frappe.get_doc({
    #     "doctype": "Payment Session",
    #     "posting_date": datetime.now(),
    #     "payment_reference": frappe.generate_hash(length=10),
    #     "status": "Initiated",
    #     "total_amount": total_amount,
    #     "invoices": [{"invoice": name} for name in invoice_names]
    # }).insert(ignore_permissions=True)

    client_id, client_secret, terminal_serial, base_url = get_credentials()
    token = get_access_token()

    payload = {
        "terminalSerial": terminal_serial,
        "amount": int(float(total_amount) * 100),
        "merchantReference": session.payment_reference,
        "transactionType": "PURCHASE",
        "paymentMethod": "ANY"
    }

    try:
        
        
        response = requests.post(
            f"{base_url}/v1/transactions",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        # if response.status_code != 200:
        #     error_msg = response.text
        #     frappe.logger().error(f"Moniepoint Payment Error - Status: {response.status_code}, Response: {error_msg}")
        #     session.status = "Failed"
        #     session.save()
        #     frappe.throw(_("Payment initiation failed. Please try again."))

        # Update session status
        session.status = "Pending"
        session.save()
        
        return session.as_dict()
        
    except requests.exceptions.RequestException as e:
        session.status = "Failed"
        session.save()
        frappe.log_error(f"Moniepoint Payment Error: {str(e)}", "Moniepoint Integration")
        frappe.throw(_("Failed to initiate payment: {0}").format(str(e)))


@frappe.whitelist(allow_guest=True)
def complete_payment(payment_session):
    try:
        session = frappe.get_doc("Payment Session", payment_session)
        if not session:
            frappe.msgprint("Payment session not found")
            return {"success": False, "message": "Payment session not found"}

        token = get_access_token()
        _, _, _, base_url = get_credentials()

        response = requests.get(
            f"{base_url}/v1/transactions/merchants/{session.payment_reference}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )

       

        # if response.status != 200:
        #     error_msg = f"Failed to verify payment: {response.text}"
        #     frappe.log_error(error_msg, "Moniepoint Integration")
        #     return {"success": False, "message": error_msg}
        

        data = response.json()
        
        responseMessage = data.get("responseMessage")
        status = data.get("status")
        
        processingStatus = data.get("processingStatus")

        
        # if not processingStatus:
        #     error_msg = "Payment status not found in response"
        #     frappe.log_error(error_msg, "Moniepoint Integration")
        #     #frappe.throw(_("Payment is still pending. Please try again later."))
        #     return {"success": False, "message": error_msg}
            
        if processingStatus == "PROCESSED" and responseMessage == "Transaction Approved":
            session.db_set("status", "Paid")

            # Create payment entries for all invoices
            # Payment Session Invoices
            invoices = frappe.get_all(
                "Payment Session Invoices",
                filters={"payment_session": session.name},
                pluck="invoice_number"
            )

            for inv in invoices:
                invoice = frappe.get_doc("Sales Invoice", inv)

                if invoice.docstatus == 1 and invoice.outstanding_amount > 0:
                    new_payment_entry= frappe.new_doc("Payment Entry")
                    new_payment_entry.payment_type = "Receive"                
                    new_payment_entry.party_type = "Customer"
                    new_payment_entry.party =  invoice.customer,
                    new_payment_entry.paid_from = "Debtors - P"
                    new_payment_entry.paid_to =  "Cash - P"
                    new_payment_entry.paid_amount = invoice.outstanding_amount
                    new_payment_entry.received_amount = invoice.outstanding_amount
                    new_payment_entry.custom_hotel_room_check_in= session.hotel_room_check_in
                    new_payment_entry.append("references", {
                        "reference_doctype": "Sales Invoice",
                        "reference_name": invoice.name,
                        "total_amount": invoice.grand_total,
                        "outstanding_amount": invoice.outstanding_amount,
                        "allocated_amount": invoice.outstanding_amount
                    })
                    new_payment_entry.mode_of_payment = "Moniepoint"
                
                    new_payment_entry.insert(ignore_permissions=True)
                    new_payment_entry.submit()
            
                return {"success": True, "message": "Payment completed successfully", "name": session.name}
        else:
            return {
                "success": False, 
                "message": f"Payment not yet successful. Current status: {status}"
            }
            
    except Exception as e:
        error_msg = f"Error processing payment: {str(e)}"
        frappe.log_error(error_msg, "Moniepoint Integration")
        return {"success": False, "message": error_msg}


    # if status == "SUCCESS":
    #     session.db_set("status", "Paid")
    #     for inv in session.invoices:
    #         invoice = frappe.get_doc("Sales Invoice", inv.invoice)
    #         if invoice.docstatus == 1 and invoice.outstanding_amount > 0:
    #             payment_entry = frappe.get_doc({
    #                 "doctype": "Payment Entry",
    #                 "payment_type": "Receive",
    #                 "party_type": "Customer",
    #                 "party": invoice.customer,
    #                 "paid_from": "Debtors - P",
    #                 "paid_to": "Cash - P",
    #                 "paid_amount": invoice.grand_total,
    #                 "received_amount": invoice.grand_total,
    #                 "references": [{
    #                     "reference_doctype": "Sales Invoice",
    #                     "reference_name": invoice.name
    #                 }],
    #                 "mode_of_payment": "Moniepoint",
    #             })
    #             payment_entry.insert(ignore_permissions=True)
    #             payment_entry.submit()

    #     frappe.msgprint(_("Payment confirmed and invoices cleared."))
    # else:
    #     frappe.throw(_("Payment not yet successful. Current status: {0}").format(status))

# @frappe.whitelist()
# def complete_payment(payment_session):
# 	payment_session_doc = frappe.get_doc("Payment Session", payment_session)

# 	# Create Payment Entry
# 	pe = frappe.new_doc("Payment Entry")
# 	pe.payment_type = "Receive"
# 	pe.mode_of_payment = "Cash" # This should be configured in settings
# 	pe.party_type = "Customer"
# 	# Assuming all invoices belong to the same customer
# 	invoice = frappe.get_doc("Sales Invoice", payment_session_doc.invoices[0].invoice)
# 	pe.party = invoice.customer
# 	pe.paid_amount = payment_session_doc.total_amount
# 	pe.received_amount = payment_session_doc.total_amount

# 	for inv in payment_session_doc.invoices:
# 		invoice_doc = frappe.get_doc("Sales Invoice", inv.invoice)
# 		pe.append("references", {
# 			"reference_doctype": "Sales Invoice",
# 			"reference_name": inv.invoice,
# 			"total_amount": invoice_doc.grand_total,
# 			"outstanding_amount": invoice_doc.outstanding_amount,
# 			"allocated_amount": invoice_doc.outstanding_amount
# 		})

# 	pe.insert()
# 	pe.submit()

# 	# Update Payment Session
# 	payment_session_doc.status = "Paid"
# 	payment_session_doc.payment_entry = pe.name
# 	payment_session_doc.save()

# 	return pe.as_dict()

#url: /api/method/rhohotel.api.moniepoint_webhook
#public url: /api/method/rhohotel.api.moniepoint_webhook
@frappe.whitelist(allow_guest=True)
def moniepoint_webhook():
    if frappe.request.method != "POST":
        frappe.throw(_("Method not allowed"), frappe.PermissionError)
    # Log the request data for debugging
    webhook_data = frappe.request.data
    frappe.log_error(f"Moniepoint Webhook Received: {webhook_data}", "Moniepoint Webhook")

    try:
        # Parse the JSON data
        data = json.loads(webhook_data)
        event_data = data.get("eventData")
        
        if not event_data:
            frappe.log_error("Moniepoint Webhook: eventData not found", "Moniepoint Webhook")
            return {"status": "error", "message": "eventData not found"}

        # Extract the payment reference
        payment_reference = event_data.get("merchantReference")
        transaction_reference = event_data.get("transactionReference")
        
        if not payment_reference:
            frappe.log_error("Moniepoint Webhook: Payment reference not found", "Moniepoint Webhook")
            return {"status": "error", "message": "Payment reference not found"}

        # Find the corresponding Payment Session
        payment_session = frappe.db.get_value(
            "Payment Session",
            {"payment_reference": payment_reference},
            "name"
        )

        if not payment_session:
            frappe.log_error(f"Moniepoint Webhook: Payment Session not found for reference {payment_reference}", "Moniepoint Webhook")
            return {"status": "error", "message": "Payment Session not found"}

        # Update the transaction reference
        frappe.db.set_value("Payment Session", payment_session, "transaction_reference", transaction_reference)

        # Complete the payment
        complete_payment(payment_session)

        return {"status": "success"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Moniepoint Webhook Error")
        return {"status": "error", "message": str(e)}





























@frappe.whitelist(allow_guest=True)
def add_cors_headers(response=None):
    """Add CORS headers to allow cross-origin requests."""
    frappe.response.headers.add("Access-Control-Allow-Origin", "*")
    frappe.response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    frappe.response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Frappe-CSRF-Token")
    frappe.response.headers.add("Access-Control-Allow-Credentials", "true")