import frappe
import frappe
from frappe.utils import nowdate, add_days, cstr
from datetime import datetime
import json
import uuid
import requests
from frappe.utils import flt
from frappe.utils import getdate, get_datetime, date_diff, nowdate, add_days, now_datetime
from datetime import datetime, timedelta


# Import translation function
_ = frappe._


def get_occupancy_rate():
	"""Return current occupancy percentage."""
	return {"value": 82.5, "suffix": "%"}


def get_room_revenue():
	"""Return chart data for last 7 days revenue."""
	return {
		"labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
		"datasets": [{"name": "Revenue", "values": [1200, 1500, 1800, 2000, 2200, 1950, 2500]}],
	}


def get_average_stay_length():
	"""Return average stay length in days."""
	return {"value": 3.2, "suffix": " days"}


def get_maintenance_status_summary():
	"""Return summary of hotel room maintenance statuses."""
	return {
		"labels": ["Active", "Out of Order", "Under Maintenance"],
		"datasets": [{"name": "Room Status", "values": [150, 5, 10]}],
	}


def get_occupancy_history():
	"""Return occupancy history for the last 30 days."""
	labels = [add_days(nowdate(), -i) for i in range(30)][::-1]
	return {
		"labels": labels,
		"datasets": [
			{
				"name": "Occupancy",
				"values": [
					75,
					78,
					80,
					82,
					85,
					88,
					90,
					85,
					82,
					80,
					78,
					75,
					70,
					72,
					75,
					80,
					82,
					85,
					88,
					90,
					92,
					95,
					98,
					100,
					98,
					95,
					92,
					90,
					88,
					85,
				],
			}
		],
	}


def get_average_rate_per_room_type():
	"""Return average rate per room type."""
	return {
		"labels": ["Standard", "Deluxe", "Suite"],
		"datasets": [{"name": "Average Rate", "values": [100, 150, 250]}],
	}


def get_active_rooms_count():
	"""Return number of active rooms per type."""
	return {
		"labels": ["Standard", "Deluxe", "Suite"],
		"datasets": [{"name": "Active Rooms", "values": [80, 50, 20]}],
	}


def get_total_nights_stayed():
	"""Return total nights stayed by a guest."""
	# This would typically be guest-specific, but for a general dashboard,
	# we can show an aggregation or a sample.
	return {"value": 25}


def get_guest_lifetime_value():
	"""Return lifetime value of a guest."""
	return {"value": 5500, "prefix": "$"}


# api url: /api/method/rhohotel.api.get_guest_name_room_number
@frappe.whitelist(allow_guest=True)
def get_guest_name_room_number(room_number):
	guest_name = frappe.db.get_value(
		"Hotel Room Check In", {"room_number": room_number, "status": "Checked In"}, "guest"
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
		as_dict=True,
	)
	return checkin


@frappe.whitelist()
def get_room_rate(room_type, rate_type=None, check_in_date=None):
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
				"clientSecret": "hmd!@yP1Q$3*+%Y8d5WJ",
			},
			headers={"Content-Type": "application/json"},
			timeout=15,  # optional: prevent hanging requests
		)

		# Handle non-200 responses
		if response.status_code != 200:
			frappe.log_error(
				f"✗ Moniepoint Auth Error:\nStatus: {response.status_code}\nResponse: {response.text}",
				"Moniepoint Integration",
			)
			frappe.throw(_("Authentication failed. Please check Moniepoint credentials."))

		data = response.json()
		token = data.get("accessToken")

		if not token:
			frappe.log_error(f"✗ Invalid Response: {data}", "Moniepoint Integration")
			frappe.throw(_("Access token not found in Moniepoint response"))

		frappe.logger().info("✓ Access token obtained successfully")
		return token

	except requests.exceptions.RequestException as e:
		frappe.log_error(f"✗ Moniepoint Authentication Error: {str(e)}", "Moniepoint Integration")
		frappe.throw(_("Failed to authenticate with Moniepoint: {0}").format(str(e)))


# ----------- pay with moniepoint -------------
# @frappe.whitelist()
# def initiate_payment(check_in, terminal_id):
#     # if isinstance(invoice_names, str):
#     #     invoice_names = json.loads(invoice_names)

#     if not check_in:
#         frappe.throw(_("Check in not supplied."))

#     invoice_names = frappe.db.get_all(
#             "Sales Invoice",
#             filters={"custom_hotel_room_check_in": check_in, "outstanding_amount": [">", 0]},
#             pluck="name"
#         )

#     if not invoice_names:
#         frappe.throw(_("No invoices provided for payment."))

#     total_amount = sum(frappe.db.get_value("Sales Invoice", name, "grand_total") for name in invoice_names)

#     # get moniepoint terminal from terminal_id
#     terminal = frappe.get_doc("Moniepoint Terminal", terminal_id)
#     if not terminal:
#         frappe.throw(_("Invalid Moniepoint Terminal."))

#     # Create Payment Session
#     session = frappe.new_doc("Payment Session")
#     session.payment_reference =  frappe.generate_hash(length=10)
#     session.total_amount = total_amount
#     session.hotel_room_check_in = check_in
#     session.posting_date = datetime.now()
#     session.transaction_reference = ""
#     session.terminal_id = terminal.name
#     session.account_number = terminal.account
#     try:
#         session.insert(ignore_permissions=True)
#         frappe.db.commit()
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Error creating Payment Session")
#         frappe.throw(_("Failed to create Payment Session: {0}").format(str(e)))

#     for inv_name in invoice_names:
#         invoice = frappe.new_doc("Payment Session Invoices")
#         invoice.invoice_number = inv_name
#         invoice.payment_session = session.name
#         invoice.insert()
#     frappe.db.commit()


#     client_id, client_secret, terminal_serial, base_url = get_credentials()
#     token = get_access_token()

#     payload = {
#         "terminalSerial": terminal.serial_number,
#         "amount": int(float(total_amount) * 100),
#         "merchantReference": session.payment_reference,
#         "transactionType": "PURCHASE",
#         "paymentMethod": "ANY"
#     }

#     try:


#         response = requests.post(
#             f"{base_url}/v1/transactions",
#             json=payload,
#             headers={
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json"
#             }
#         )

#         # if response.status_code != 200:
#         #     error_msg = response.text
#         #     frappe.logger().error(f"Moniepoint Payment Error - Status: {response.status_code}, Response: {error_msg}")
#         #     session.status = "Failed"
#         #     session.save()
#         #     frappe.throw(_("Payment initiation failed. Please try again."))

#         # Update session status
#         session.status = "Pending"
#         session.save()

#         return session.as_dict()

#     except requests.exceptions.RequestException as e:
#         session.status = "Failed"
#         session.save()
#         frappe.log_error(f"Moniepoint Payment Error: {str(e)}", "Moniepoint Integration")
#         frappe.throw(_("Failed to initiate payment: {0}").format(str(e)))

# -------------- correct working one--------
# @frappe.whitelist()
# def initiate_payment(check_in, terminal_id):
#     if not check_in:
#         frappe.throw(_("Check in not supplied."))

#     invoice_names = frappe.db.get_all(
#         "Sales Invoice",
#         filters={"custom_hotel_room_check_in": check_in, "outstanding_amount": [">", 0]},
#         fields=["name", "grand_total"]
#     )

#     if not invoice_names:
#         frappe.throw(_("No invoices provided for payment."))

#     total_amount = sum(inv.grand_total for inv in invoice_names)

#     # Get moniepoint terminal from terminal_id
#     terminal = frappe.get_doc("Moniepoint Terminal", terminal_id)
#     if not terminal:
#         frappe.throw(_("Invalid Moniepoint Terminal."))

#     # Create Payment Session
#     session = frappe.new_doc("Payment Session")
#     session.payment_reference = frappe.generate_hash(length=10)
#     session.total_amount = total_amount
#     session.hotel_room_check_in = check_in
#     session.posting_date = nowdate()
#     session.transaction_reference = ""
#     session.terminal_id = terminal.name
#     session.account_number = terminal.account

#     # Add invoices as child table rows
#     for inv in invoice_names:
#         session.append("invoices", {
#             "invoice_number": inv.name,
#             "invoice_amount": inv.grand_total
#         })

#     try:
#         session.insert(ignore_permissions=True)
#         frappe.db.commit()
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Error creating Payment Session")
#         frappe.throw(_("Failed to create Payment Session: {0}").format(str(e)))

#     client_id, client_secret, terminal_serial, base_url = get_credentials()
#     token = get_access_token()

#     payload = {
#         "terminalSerial": terminal.serial_number,
#         "amount": int(float(total_amount) * 100),
#         "merchantReference": session.payment_reference,
#         "transactionType": "PURCHASE",
#         "paymentMethod": "ANY"
#     }

#     try:
#         response = requests.post(
#             f"{base_url}/v1/transactions",
#             json=payload,
#             headers={
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json"
#             }
#         )

#         # Update session status
#         session.status = "Pending"
#         session.save()

#         return session.as_dict()

#     except requests.exceptions.RequestException as e:
#         session.status = "Failed"
#         session.save()
#         frappe.log_error(f"Moniepoint Payment Error: {str(e)}", "Moniepoint Integration")
#         frappe.throw(_("Failed to initiate payment: {0}").format(str(e)))


@frappe.whitelist()
def resend_payment_request(payment_session_name):
	try:
		session = frappe.get_doc("Payment Session", payment_session_name)
		if not session:
			frappe.throw(_("Payment Session not found."))

		if session.status != "Pending":
			return {"success": False, "message": "Can only resend a pending payment request."}

		terminal = frappe.get_doc("Moniepoint Terminal", session.terminal_id)
		if not terminal:
			frappe.throw(_("Invalid Moniepoint Terminal linked to the session."))

		token = get_access_token()
		_, _, _, base_url = get_credentials()

		payment_reference = frappe.generate_hash(length=10)

		session.db_set("payment_reference", payment_reference)

		payload = {
			"terminalSerial": terminal.serial_number,
			"amount": int(float(session.total_amount) * 100),
			"merchantReference": payment_reference,
			"transactionType": "PURCHASE",
			"paymentMethod": "ANY",
		}

		response = requests.post(
			f"{base_url}/v1/transactions",
			json=payload,
			headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
		)

		if response.status_code == 200:
			return {"success": True}
		else:
			frappe.log_error(
				f"Moniepoint Resend Error - Status: {response.status_code}, Response: {response.text}",
				"Moniepoint Integration",
			)
			return {"success": False, "message": "Failed to resend payment request."}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error resending payment request")
		return {"success": False, "message": str(e)}


# @frappe.whitelist(allow_guest=True)
# def complete_payment(payment_session):
#     try:
#         session = frappe.get_doc("Payment Session", payment_session)
#         if not session:
#             frappe.msgprint("Payment session not found")
#             return {"success": False, "message": "Payment session not found"}

#         token = get_access_token()
#         _, _, _, base_url = get_credentials()

#         response = requests.get(
#             f"{base_url}/v1/transactions/merchants/{session.payment_reference}",
#             headers={
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json"
#             }
#         )


#         # if response.status != 200:
#         #     error_msg = f"Failed to verify payment: {response.text}"
#         #     frappe.log_error(error_msg, "Moniepoint Integration")
#         #     return {"success": False, "message": error_msg}


#         data = response.json()

#         responseMessage = data.get("responseMessage")
#         status = data.get("status")

#         processingStatus = data.get("processingStatus")


#         # if not processingStatus:
#         #     error_msg = "Payment status not found in response"
#         #     frappe.log_error(error_msg, "Moniepoint Integration")
#         #     #frappe.throw(_("Payment is still pending. Please try again later."))
#         #     return {"success": False, "message": error_msg}

#         if processingStatus == "PROCESSED" and responseMessage == "Transaction Approved":
#             session.db_set("status", "Paid")

#             # Create payment entries for all invoices
#             # Payment Session Invoices
#             invoices = frappe.get_all(
#                 "Payment Session Invoices",
#                 filters={"payment_session": session.name},
#                 pluck="invoice_number"
#             )

#             company = frappe.defaults.get_user_default("Company")

#             default_receivable = frappe.db.get_value("Company",company,"default_receivable_account")

#             for inv in invoices:
#                 invoice = frappe.get_doc("Sales Invoice", inv)

#                 if invoice.docstatus == 1 and invoice.outstanding_amount > 0:
#                     new_payment_entry= frappe.new_doc("Payment Entry")
#                     new_payment_entry.payment_type = "Receive"
#                     new_payment_entry.party_type = "Customer"
#                     new_payment_entry.party =  invoice.customer,
#                     new_payment_entry.paid_from = default_receivable
#                     new_payment_entry.paid_to =  session.account_number
#                     new_payment_entry.paid_amount = invoice.outstanding_amount
#                     new_payment_entry.received_amount = invoice.outstanding_amount
#                     new_payment_entry.custom_hotel_room_check_in= session.hotel_room_check_in
#                     new_payment_entry.reference_no = session.payment_reference
#                     new_payment_entry.reference_date = datetime.now()
#                     new_payment_entry.append("references", {
#                         "reference_doctype": "Sales Invoice",
#                         "reference_name": invoice.name,
#                         "total_amount": invoice.grand_total,
#                         "outstanding_amount": invoice.outstanding_amount,
#                         "allocated_amount": invoice.outstanding_amount
#                     })
#                     new_payment_entry.mode_of_payment = "Moniepoint"

#                     new_payment_entry.insert(ignore_permissions=True)
#                     new_payment_entry.submit()

#             # submit payment session
#             session.submit()
#             return {"success": True, "message": "Payment completed successfully", "name": session.name}
#         else:
#             return {
#                 "success": False,
#                 "message": f"Payment not yet successful. Current status: {status}"
#             }

#     except Exception as e:
#         error_msg = f"Error processing payment: {str(e)}"
#         frappe.log_error(error_msg, "Moniepoint Integration")
#         return {"success": False, "message": error_msg}


#     # if status == "SUCCESS":
#     #     session.db_set("status", "Paid")
#     #     for inv in session.invoices:
#     #         invoice = frappe.get_doc("Sales Invoice", inv.invoice)
#     #         if invoice.docstatus == 1 and invoice.outstanding_amount > 0:
#     #             payment_entry = frappe.get_doc({
#     #                 "doctype": "Payment Entry",
#     #                 "payment_type": "Receive",
#     #                 "party_type": "Customer",
#     #                 "party": invoice.customer,
#     #                 "paid_from": "Debtors - P",
#     #                 "paid_to": "Cash - P",
#     #                 "paid_amount": invoice.grand_total,
#     #                 "received_amount": invoice.grand_total,
#     #                 "references": [{
#     #                     "reference_doctype": "Sales Invoice",
#     #                     "reference_name": invoice.name
#     #                 }],
#     #                 "mode_of_payment": "Moniepoint",
#     #             })
#     #             payment_entry.insert(ignore_permissions=True)
#     #             payment_entry.submit()

#     #     frappe.msgprint(_("Payment confirmed and invoices cleared."))
#     # else:
#     #     frappe.throw(_("Payment not yet successful. Current status: {0}").format(status))


# ---------- latest correct one. ----------
# @frappe.whitelist(allow_guest=True)
# def complete_payment(payment_session):
#     try:
#         session = frappe.get_doc("Payment Session", payment_session)
#         if not session:
#             frappe.msgprint("Payment session not found")
#             return {"success": False, "message": "Payment session not found"}

#         token = get_access_token()
#         _, _, _, base_url = get_credentials()

#         response = requests.get(
#             f"{base_url}/v1/transactions/merchants/{session.payment_reference}",
#             headers={
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json"
#             }
#         )

#         data = response.json()

#         responseMessage = data.get("responseMessage")
#         status = data.get("status")
#         processingStatus = data.get("processingStatus")

#         if processingStatus == "PROCESSED" and responseMessage == "Transaction Approved":
#             session.db_set("status", "Paid")

#             # Get invoices from child table
#             company = frappe.defaults.get_user_default("Company")
#             default_receivable = frappe.db.get_value("Company", company, "default_receivable_account")

#             for invoice_row in session.invoices:
#                 invoice = frappe.get_doc("Sales Invoice", invoice_row.invoice_number)

#                 if invoice.docstatus == 1 and invoice.outstanding_amount > 0:
#                     new_payment_entry = frappe.new_doc("Payment Entry")
#                     new_payment_entry.payment_type = "Receive"
#                     new_payment_entry.party_type = "Customer"
#                     new_payment_entry.party = invoice.customer
#                     new_payment_entry.paid_from = default_receivable
#                     new_payment_entry.paid_to = session.account_number
#                     new_payment_entry.paid_amount = invoice.outstanding_amount
#                     new_payment_entry.received_amount = invoice.outstanding_amount
#                     new_payment_entry.custom_hotel_room_check_in = session.hotel_room_check_in
#                     new_payment_entry.reference_no = session.payment_reference
#                     new_payment_entry.reference_date = nowdate()
#                     new_payment_entry.append("references", {
#                         "reference_doctype": "Sales Invoice",
#                         "reference_name": invoice.name,
#                         "total_amount": invoice.grand_total,
#                         "outstanding_amount": invoice.outstanding_amount,
#                         "allocated_amount": invoice.outstanding_amount
#                     })
#                     new_payment_entry.mode_of_payment = "Moniepoint"

#                     new_payment_entry.insert(ignore_permissions=True)
#                     new_payment_entry.submit()

#             # Submit payment session
#             session.submit()
#             return {"success": True, "message": "Payment completed successfully", "name": session.name}
#         else:
#             return {
#                 "success": False,
#                 "message": f"Payment not yet successful. Current status: {status}"
#             }

#     except Exception as e:
#         error_msg = f"Error processing payment: {str(e)}"
#         frappe.log_error(error_msg, "Moniepoint Integration")
#         return {"success": False, "message": error_msg}


# ----------- latest working ---------
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


# url: /api/method/rhohotel.api.moniepoint_webhook
# public url: /api/method/rhohotel.api.moniepoint_webhook
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
			"Payment Session", {"payment_reference": payment_reference}, "name"
		)

		if not payment_session:
			frappe.log_error(
				f"Moniepoint Webhook: Payment Session not found for reference {payment_reference}",
				"Moniepoint Webhook",
			)
			return {"status": "error", "message": "Payment Session not found"}

		# Update the transaction reference
		frappe.db.set_value(
			"Payment Session", payment_session, "transaction_reference", transaction_reference
		)

		# Complete the payment
		complete_payment(payment_session)

		return {"status": "success"}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Moniepoint Webhook Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_outstanding_invoices(check_in):
	"""Get all outstanding invoices for a check-in with details."""
	if not check_in:
		frappe.throw(_("Check in not supplied."))

	invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={"custom_hotel_room_check_in": check_in, "outstanding_amount": [">", 0], "docstatus": 1},
		fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount"],
	)

	return invoices


@frappe.whitelist()
def initiate_payment(check_in, terminal_id, invoice_allocations):
	"""
	invoice_allocations: JSON string with format:
	[
	    {"invoice_number": "INV-001", "allocated_amount": 10000},
	    {"invoice_number": "INV-002", "allocated_amount": 15000}
	]
	"""
	if not check_in:
		frappe.throw(_("Check in not supplied."))

	# Parse invoice allocations
	if isinstance(invoice_allocations, str):
		invoice_allocations = json.loads(invoice_allocations)

	if not invoice_allocations or len(invoice_allocations) == 0:
		frappe.throw(_("No invoices selected for payment."))

	# Validate allocations and calculate total
	total_amount = 0
	validated_allocations = []

	for allocation in invoice_allocations:
		invoice_number = allocation.get("invoice_number")
		allocated_amount = float(allocation.get("allocated_amount", 0))

		if allocated_amount <= 0:
			continue  # Skip invoices with zero or negative allocation

		# Get invoice details
		invoice = frappe.get_doc("Sales Invoice", invoice_number)

		if invoice.docstatus != 1:
			frappe.throw(_("Invoice {0} is not submitted.").format(invoice_number))

		if allocated_amount > invoice.outstanding_amount:
			frappe.throw(
				_("Allocated amount (₦{0}) exceeds outstanding amount (₦{1}) for invoice {2}").format(
					allocated_amount, invoice.outstanding_amount, invoice_number
				)
			)

		validated_allocations.append(
			{
				"invoice_number": invoice_number,
				"outstanding_amount": invoice.outstanding_amount,
				"allocated_amount": allocated_amount,
			}
		)

		total_amount += allocated_amount

	if total_amount <= 0:
		frappe.throw(_("Total payment amount must be greater than zero."))

	# Get moniepoint terminal
	terminal = frappe.get_doc("Moniepoint Terminal", terminal_id)
	if not terminal:
		frappe.throw(_("Invalid Moniepoint Terminal."))

	# Create Payment Session
	session = frappe.new_doc("Payment Session")
	session.payment_reference = frappe.generate_hash(length=10)
	session.total_amount = total_amount
	session.hotel_room_check_in = check_in
	session.posting_date = nowdate()
	session.transaction_reference = ""
	session.terminal_id = terminal.name
	session.account_number = terminal.account

	try:
		session.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error creating Payment Session")
		frappe.throw(_("Failed to create Payment Session: {0}").format(str(e)))

	# Create Payment Session Invoices records (standalone documents)
	for allocation in validated_allocations:
		invoice_link = frappe.new_doc("Payment Session Invoices")
		invoice_link.payment_session = session.name
		invoice_link.invoice_number = allocation["invoice_number"]
		invoice_link.outstanding_amount = allocation["outstanding_amount"]
		invoice_link.allocated_amount = allocation["allocated_amount"]

		try:
			invoice_link.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(
				f"Error creating Payment Session Invoice link: {str(e)}",
				"Payment Session Invoice Creation Error",
			)
			# Rollback the payment session if invoice link creation fails
			frappe.db.rollback()
			frappe.throw(_("Failed to create payment session invoice link: {0}").format(str(e)))

	frappe.db.commit()

	# Initiate Moniepoint payment
	client_id, client_secret, terminal_serial, base_url = get_credentials()
	token = get_access_token()

	payload = {
		"terminalSerial": terminal.serial_number,
		"amount": int(float(total_amount) * 100),  # Convert to kobo
		"merchantReference": session.payment_reference,
		"transactionType": "PURCHASE",
		"paymentMethod": "ANY",
	}

	try:
		response = requests.post(
			f"{base_url}/v1/transactions",
			json=payload,
			headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
		)

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
			headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
		)

		data = response.json()

		responseMessage = data.get("responseMessage")
		status = data.get("status")
		processingStatus = data.get("processingStatus")

		if processingStatus == "PROCESSED" and responseMessage == "Transaction Approved":
			session.db_set("status", "Paid")

			# Get company and accounts
			company = frappe.defaults.get_user_default("Company")
			default_receivable = frappe.db.get_value("Company", company, "default_receivable_account")

			# Get all Payment Session Invoices for this session
			invoice_allocations = frappe.get_all(
				"Payment Session Invoices",
				filters={"payment_session": session.name},
				fields=["invoice_number", "allocated_amount", "outstanding_amount"],
			)

			# Create payment entries for each allocated invoice
			for allocation in invoice_allocations:
				if allocation.allocated_amount <= 0:
					continue  # Skip if no allocation

				invoice = frappe.get_doc("Sales Invoice", allocation.invoice_number)

				if invoice.docstatus == 1 and invoice.outstanding_amount > 0:
					# Create payment entry for the allocated amount
					new_payment_entry = frappe.new_doc("Payment Entry")
					new_payment_entry.payment_type = "Receive"
					new_payment_entry.party_type = "Customer"
					new_payment_entry.party = invoice.customer
					new_payment_entry.paid_from = default_receivable
					new_payment_entry.paid_to = session.account_number
					new_payment_entry.paid_amount = allocation.allocated_amount
					new_payment_entry.received_amount = allocation.allocated_amount
					new_payment_entry.custom_hotel_room_check_in = session.hotel_room_check_in
					new_payment_entry.reference_no = session.payment_reference
					new_payment_entry.reference_date = nowdate()

					# Allocate to the specific invoice
					new_payment_entry.append(
						"references",
						{
							"reference_doctype": "Sales Invoice",
							"reference_name": invoice.name,
							"total_amount": invoice.grand_total,
							"outstanding_amount": invoice.outstanding_amount,
							"allocated_amount": allocation.allocated_amount,  # Use allocated amount from Payment Session Invoices
						},
					)

					new_payment_entry.mode_of_payment = "Moniepoint"

					try:
						new_payment_entry.insert(ignore_permissions=True)
						new_payment_entry.submit()
					except Exception as e:
						frappe.log_error(
							f"Error creating payment entry for {invoice.name}: {str(e)}",
							"Payment Entry Creation Error",
						)
						# Continue with other invoices even if one fails
						continue

			# Submit payment session
			session.submit()
			return {"success": True, "message": "Payment completed successfully", "name": session.name}
		else:
			return {"success": False, "message": f"Payment not yet successful. Current status: {status}"}

	except Exception as e:
		error_msg = f"Error processing payment: {str(e)}"
		frappe.log_error(error_msg, "Moniepoint Integration")
		return {"success": False, "message": error_msg}


@frappe.whitelist(allow_guest=True)
def add_cors_headers(response=None):
	"""Add CORS headers to allow cross-origin requests."""
	frappe.response.headers.add("Access-Control-Allow-Origin", "*")
	frappe.response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
	frappe.response.headers.add(
		"Access-Control-Allow-Headers", "Content-Type, Authorization, X-Frappe-CSRF-Token"
	)
	frappe.response.headers.add("Access-Control-Allow-Credentials", "true")


# from datetime import datetime
# import frappe
# from frappe import _
# from frappe.utils import getdate, date_diff
# from rhohotel.api import get_room_rate
# import frappe
# from frappe.utils import getdate


# @frappe.whitelist()
# def get_available_rooms(doctype, txt, searchfield, start, page_len, filters):
#     """
#     Frappe set_query method: Returns available rooms for the selected date range.

#     This filters out:
#     1. Rooms with active reservations (not Cancelled/Completed)
#     2. Rooms with checked-in guests
#     3. Rooms with active holds from temporary bookings

#     Usage in HTML/JS:
#         frm.set_query("room_number", function() {
#             return {
#                 query: "rhohotel.methods.get_available_rooms",
#                 filters: {
#                     from_date: frm.doc.from_date,
#                     to_date: frm.doc.to_date,
#                     room_type: frm.doc.room_type
#                 }
#             };
#         });
#     """

#     # Extract dates from filters passed by set_query
#     from_date = filters.get("from_date")
#     to_date = filters.get("to_date")
#     room_type = filters.get("room_type")

#     # Must have both dates
#     if not from_date or not to_date:
#         return []

#     # Validate and convert dates
#     try:
#         from_date_obj = getdate(from_date)
#         to_date_obj = getdate(to_date)

#         if to_date_obj <= from_date_obj:
#             return []

#         from_date_str = from_date_obj.strftime("%Y-%m-%d")
#         to_date_str = to_date_obj.strftime("%Y-%m-%d")
#     except Exception:
#         return []

#     # # Build base filter for operational rooms
#     # room_filters = {
#     #     "operational_status": "In Service",
#     #     "maintenance_flag": 0
#     # }

#     # if room_type:
#     #     room_filters["room_type"] = room_type

#     # Get all eligible rooms
#     all_rooms = frappe.get_all(
#         "Hotel Room",
#         # filters=room_filters,
#         fields=["name"],
#         limit_page_length=None
#     )

#     if not all_rooms:
#         return []

#     room_names = [r["name"] for r in all_rooms]
#     blocked_rooms = set()

#     # ==================================================================
#     # Check 1: Hotel Room Reservation overlaps
#     # ==================================================================
#     try:
#         reservations = frappe.db.sql("""
#             SELECT DISTINCT room_number
#             FROM `tabHotel Room Reservation`
#             WHERE room_number IN ({})
#             AND status NOT IN ('Cancelled', 'Completed')
#             AND from_date < %s
#             AND to_date > %s
#         """.format(", ".join(["%s"] * len(room_names))),
#         tuple(room_names) + (to_date_str, from_date_str),
#         as_dict=True
#         )

#         for res in reservations:
#             blocked_rooms.add(res["room_number"])
#     except Exception as e:
#         frappe.log_error(str(e), "Hotel Room Reservation: Check Overlaps")

#     # ==================================================================
#     # Check 2: Hotel Room Check In overlaps
#     # ==================================================================
#     try:
#         checkins = frappe.db.sql("""
#             SELECT DISTINCT room_number
#             FROM `tabHotel Room Check In`
#             WHERE room_number IN ({})
#             AND status IN ('Draft', 'Checked In')
#             AND DATE(check_in_datetime) < %s
#             AND DATE(expected_check_out_datetime) > %s
#         """.format(", ".join(["%s"] * len(room_names))),
#         tuple(room_names) + (to_date_str, from_date_str),
#         as_dict=True
#         )

#         for ci in checkins:
#             blocked_rooms.add(ci["room_number"])
#     except Exception as e:
#         frappe.log_error(str(e), "Hotel Room Reservation: Check Ins")

#     # ==================================================================
#     # Check 3: Temporary Booking holds (active/not expired)
#     # ==================================================================
#     try:
#         holds = frappe.db.sql("""
#             SELECT DISTINCT tbr.room_number
#             FROM `tabTemporary Booking` tb
#             INNER JOIN `tabTemporary Booking Room` tbr
#                 ON tb.name = tbr.parent
#             WHERE tbr.room_number IN ({})
#             AND tb.status IN ('Hold', 'Payment Link Generated')
#             AND tb.payment_status = 'Pending'
#             AND tb.booking_status = 'Held'
#             AND tb.hold_expires_at > NOW()
#         """.format(", ".join(["%s"] * len(room_names))),
#         tuple(room_names),
#         as_dict=True
#         )

#         for hold in holds:
#             blocked_rooms.add(hold["room_number"])
#     except Exception as e:
#         frappe.log_error(str(e), "Hotel Room Reservation: Temporary Holds")

#     # Filter and return available rooms in Frappe dropdown format
#     available_rooms = [r["name"] for r in all_rooms if r["name"] not in blocked_rooms]

#     # Frappe expects list of lists: [["room1"], ["room2"], ...]
#     return [[room] for room in available_rooms]


@frappe.whitelist()
def get_available_rooms(from_date, to_date, room_type=None):
	"""Get available rooms for selected dates - EXCLUDES HELD ROOMS"""
	try:
		from_date_obj = getdate(from_date)
		to_date_obj = getdate(to_date)

		if to_date_obj <= from_date_obj:
			frappe.throw(_("Check-out date must be after check-in date"))

		filters = {"operational_status": "In Service", "maintenance_flag": 0}

		if room_type:
			filters["room_type"] = room_type

		all_rooms = frappe.get_all(
			"Hotel Room", filters=filters, fields=["name", "room_type", "floor", "capacity"]
		)

		if not all_rooms:
			return []

		room_numbers = [r.name for r in all_rooms]
		requested_check_in = f"{from_date_obj} 12:00:00"
		requested_check_out = f"{to_date_obj} 12:00:00"
		# return all_rooms

		# ✅ CRITICAL FIX #1: Exclude rooms with active holds from Temporary Booking
		current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

		held_rooms = frappe.db.sql(
			"""
            SELECT DISTINCT tbr.room_number
            FROM `tabTemporary Booking` tb
            INNER JOIN `tabTemporary Booking Room` tbr ON tb.name = tbr.parent
            WHERE tbr.room_number IN ({rooms})
            AND tb.status IN ('Hold', 'Payment Link Generated')
            AND tb.payment_status = 'Pending'
            AND tb.booking_status = 'Held'
            AND tb.hold_expires_at > %s
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
			tuple(room_numbers) + (current_time,),
			as_dict=True,
		)

		held_room_list = [r.room_number for r in held_rooms]

		# Exclude overlapping reservations
		overlapping_reservations = frappe.db.sql(
			"""
            SELECT DISTINCT room_number
            FROM `tabHotel Room Reservation`
            WHERE room_number IN ({rooms})
            AND docstatus != 2
            AND status NOT IN ('Cancelled', 'Completed')
            AND NOT (
                TIMESTAMP(DATE(to_date), '12:00:00') <= %s
                OR TIMESTAMP(DATE(from_date), '12:00:00') >= %s
            )
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
			tuple(room_numbers) + (requested_check_in, requested_check_out),
			as_dict=True,
		)

		booked_rooms = [r.room_number for r in overlapping_reservations]

		# Exclude active check-ins
		active_checkins = frappe.db.sql(
			"""
            SELECT DISTINCT room_number
            FROM `tabHotel Room Check In`
            WHERE room_number IN ({rooms})
            AND status IN ('Draft', 'Checked In')
            AND NOT (
                expected_check_out_datetime <= %s
                OR check_in_datetime >= %s
            )
        """.format(rooms=", ".join(["%s"] * len(room_numbers))),
			tuple(room_numbers) + (requested_check_in, requested_check_out),
			as_dict=True,
		)

		checked_in_rooms = [r.room_number for r in active_checkins]

		# ✅ CRITICAL FIX #2: Combine all unavailable rooms
		# Order matters: held_room_list first, then booked, then checked in
		unavailable = set(held_room_list + booked_rooms + checked_in_rooms)
		available_rooms = [r for r in all_rooms if r.name not in unavailable]

		# Calculate pricing for each available room
		for room in available_rooms:
			rate = get_room_rate(room.room_type, check_in_date=str(from_date))
			room["rate_per_night"] = rate
			num_nights = date_diff(to_date_obj, from_date_obj)
			room["total_amount"] = rate * num_nights

		return available_rooms

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Available Rooms Error")
		frappe.throw(_("Error: {0}").format(str(e)))


# Updated rhohotel/api.py method - consolidates only the current invoice

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, get_time, nowtime


@frappe.whitelist()
def create_and_submit_merge_log_for_bill_to_room(pos_invoice_name):
	"""
	Creates and submits a merge log for the Bill to Room invoice that was just saved.

	This method consolidates only the current invoice into a Sales Invoice.
	"""
	try:
		pos_invoice = frappe.get_doc("POS Invoice", pos_invoice_name)

		# Check if this invoice has "Bill to Room" payment
		has_bill_to_room = any(
			p.mode_of_payment and p.mode_of_payment.lower().strip() == "bill to room"
			for p in pos_invoice.payments
		)

		if not has_bill_to_room:
			return None

		# Validate required fields
		if not pos_invoice.customer:
			frappe.throw(_("Customer is required for Bill to Room invoices"))

		if not pos_invoice.custom_hotel_room_check_in:
			return None

		# Check if this invoice is already consolidated
		if pos_invoice.consolidated_invoice:
			return None

		# Create merge log document for ONLY this invoice
		merge_log = frappe.new_doc("POS Invoice Merge Log")
		merge_log.posting_date = getdate(nowdate())
		merge_log.posting_time = get_time(nowtime())
		merge_log.customer = pos_invoice.customer
		merge_log.merge_invoices_based_on = "Customer"
		merge_log.company = pos_invoice.company

		# Add ONLY the current invoice to the merge log
		merge_log.append(
			"pos_invoices",
			{
				"pos_invoice": pos_invoice.name,
				"customer": pos_invoice.customer,
				"posting_date": pos_invoice.posting_date,
				"grand_total": pos_invoice.grand_total,
			},
		)

		# Save the merge log
		merge_log.insert(ignore_permissions=True)
		frappe.db.commit()

		# Submit the merge log (this triggers on_submit which creates Sales Invoice)
		merge_log.submit()
		frappe.db.commit()

		return {
			"success": True,
			"merge_log": merge_log.name,
			"consolidated_invoice": merge_log.consolidated_invoice,
			"invoice_count": 1,
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(message=str(e), title=f"Error creating merge log for {pos_invoice_name}")
		raise
