import frappe
from frappe import _
from frappe.utils import nowdate, add_days
from datetime import datetime
import json


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
        season = frappe.db.get_value("Hotel Season", {
            "start_date": ("<=", check_in_date),
            "end_date": (">=", check_in_date),
            "is_active": 1
        }, "name")

        if not season:
            return {"error": "No active season found for the selected date."}

        # Determine the day type (Weekday/Weekend)
        day_of_week = datetime.strptime(check_in_date, "%Y-%m-%d").weekday()
        day_type = "Weekend" if day_of_week >= 5 else "Weekday" # 5: Saturday, 6: Sunday


        # Fetch the room rate
        rate_amount = frappe.db.get_value("Hotel Room Tariff", {
            "room_type": room_type,
            "rate_type": rate_type,
            "season": season,
            "day_type": day_type,
            "is_active": 1
        }, "rate_amount")

        return rate_amount or 16000

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error fetching room rate")
        return {"error": str(e)}


# @frappe.whitelist()
# def initiate_payment(invoice_names):
# 	# invoice_names is a list of sales invoice names
# 	if isinstance(invoice_names, str):
# 		invoice_names = json.loads(invoice_names)

# 	import uuid
# 	# Calculate total outstanding amount
# 	total_amount = 0
	
# 	valid_invoices = [inv for inv in invoice_names if inv]

# 	for inv_name in valid_invoices:
# 		outstanding_amount = frappe.db.get_value("Sales Invoice", inv_name, "outstanding_amount")
# 		total_amount += outstanding_amount or 0

# 	# Mock Moniepoint API call
# 	payment_reference = "MON-" + str(uuid.uuid4())

# 	# Create Payment Session
# 	payment_session = frappe.new_doc("Payment Session")
# 	payment_session.payment_reference = payment_reference
# 	payment_session.total_amount = total_amount
# 	for inv_name in valid_invoices:
# 		payment_session.append("invoices", {
# 			"invoice": inv_name
# 		})
# 	payment_session.insert()

# 	return payment_session.as_dict()

@frappe.whitelist()
def initiate_payment(invoice_names):
    # Parse the invoices list
    if isinstance(invoice_names, str):
        invoice_names = json.loads(invoice_names)

    total_amount = 0
    for inv in invoice_names:
        outstanding = frappe.db.get_value("Sales Invoice", inv, "outstanding_amount") or 0
        total_amount += outstanding

    # Create local Payment Session
    payment_session = frappe.new_doc("Payment Session")
    payment_session.total_amount = total_amount
    payment_session.status = "Pending"
    payment_session.insert(ignore_permissions=True)

    # Build Moniepoint payload
    payload = {
        "merchantId": frappe.db.get_single_value("Moniepoint Settings", "merchant_id"),
        "terminalId": frappe.db.get_single_value("Moniepoint Settings", "terminal_id"),
        "amount": total_amount,
        "currency": "NGN",
        "reference": payment_session.name,
        "callbackUrl": frappe.utils.get_url("/api/method/rhohotel.api.moniepoint_callback"),
        "description": f"Hotel payment for {len(invoice_names)} invoice(s)"
    }

    # Send to Moniepoint (mock or real endpoint)
    import requests
    res = requests.post("https://api.moniepoint.com/pos/payment/request", json=payload, timeout=10)
    response = res.json()

    if response.get("status") == "SUCCESS":
        payment_session.payment_reference = response.get("paymentReference")
        payment_session.save()
        return {"message": "Payment pushed to terminal", "session": payment_session.name}
    else:
        frappe.throw(response.get("message", "Failed to initiate Moniepoint payment"))


@frappe.whitelist()
def get_payment_session_status(payment_session):
	# Mocking the status check
	import random
	status = random.choice(["Pending", "Paid"])
	return {"status": status}

@frappe.whitelist()
def complete_payment(payment_session):
	payment_session_doc = frappe.get_doc("Payment Session", payment_session)

	# Create Payment Entry
	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.mode_of_payment = "Cash" # This should be configured in settings
	pe.party_type = "Customer"
	# Assuming all invoices belong to the same customer
	invoice = frappe.get_doc("Sales Invoice", payment_session_doc.invoices[0].invoice)
	pe.party = invoice.customer
	pe.paid_amount = payment_session_doc.total_amount
	pe.received_amount = payment_session_doc.total_amount

	for inv in payment_session_doc.invoices:
		invoice_doc = frappe.get_doc("Sales Invoice", inv.invoice)
		pe.append("references", {
			"reference_doctype": "Sales Invoice",
			"reference_name": inv.invoice,
			"total_amount": invoice_doc.grand_total,
			"outstanding_amount": invoice_doc.outstanding_amount,
			"allocated_amount": invoice_doc.outstanding_amount
		})

	pe.insert()
	pe.submit()

	# Update Payment Session
	payment_session_doc.status = "Paid"
	payment_session_doc.payment_entry = pe.name
	payment_session_doc.save()

	return pe.as_dict()


# api url: /api/method/rhohotel.api.moniepoint_callback
@frappe.whitelist(allow_guest=True)
def moniepoint_callback():
    import hmac, hashlib

    data = frappe.request.get_data(as_text=True)
    received_signature = frappe.get_request_header("X-Moniepoint-Signature")

    # Verify signature
    secret = frappe.db.get_single_value("Moniepoint Settings", "callback_secret")
    computed_signature = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()

    if received_signature != computed_signature:
        frappe.log_error("Invalid Moniepoint callback signature", "Moniepoint Callback")
        frappe.local.response["http_status_code"] = 401
        return {"status": "error", "message": "Invalid signature"}

    payload = frappe.parse_json(data)
    reference = payload.get("reference")
    status = payload.get("status")

    session = frappe.get_doc("Payment Session", reference)
    if status == "SUCCESS":
        # Create Payment Entry
        create_payment_entry(session)
        session.status = "Paid"
    else:
        session.status = "Failed"

    session.save()
    frappe.db.commit()
    return {"status": "ok"}



def create_payment_entry(session):
    """Create a Payment Entry when payment is confirmed from Moniepoint."""
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.mode_of_payment = "POS"
    first_invoice = frappe.get_doc("Sales Invoice", session.invoices[0].invoice)
    pe.party_type = "Customer"
    pe.party = first_invoice.customer
    pe.paid_amount = session.total_amount
    pe.received_amount = session.total_amount

    for inv in session.invoices:
        invoice_doc = frappe.get_doc("Sales Invoice", inv.invoice)
        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice_doc.name,
            "total_amount": invoice_doc.grand_total,
            "outstanding_amount": invoice_doc.outstanding_amount,
            "allocated_amount": invoice_doc.outstanding_amount
        })

    pe.insert()
    pe.submit()

