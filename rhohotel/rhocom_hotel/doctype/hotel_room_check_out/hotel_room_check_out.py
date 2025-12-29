# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, get_datetime, add_to_date
import requests
import base64


class HotelRoomCheckOut(Document):
    def validate(self):
        self.validate_check_in()
        self.calculate_stay_duration()
        self.handle_late_checkout()
        self.calculate_total()

    def validate_check_in(self):
        """Ensure check-in exists and is valid for checkout"""
        if not frappe.db.exists("Hotel Room Check In", self.check_in):
            frappe.throw(_("Check In {0} does not exist").format(self.check_in))

        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        if check_in.status != "Checked In":
            frappe.throw(_("Check In {0} is not in 'Checked In' status").format(self.check_in))

        if get_datetime(self.check_out_datetime) < get_datetime(check_in.check_in_datetime):
            frappe.throw(_("Check-out time cannot be before check-in time"))

    def calculate_stay_duration(self):
        """Calculate actual stay duration"""
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        hours = time_diff_in_hours(self.check_out_datetime, check_in.check_in_datetime)
        days = int(hours / 24)
        remaining_hours = hours % 24

        self.actual_stay_duration = f"{days} days, {int(remaining_hours)} hours"

    def handle_late_checkout(self):
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        self.late_checkout = check_in.late_checkout
        if self.late_checkout:
            hotel_settings = frappe.get_single("Hotel Settings")
            if hotel_settings.enable_late_check_out:
                self.late_checkout_charges = hotel_settings.late_check_out_charges
            else:
                self.late_checkout_charges = 0
        else:
            self.late_checkout_charges = 0

    def calculate_total(self):
        """Calculate total amount including additional charges and session-based room charges"""
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        # Use season and tariff for main room charge
        room_charge = 0
        if check_in.room_type and check_in.rate_type and check_in.hotel_season:
            tariff = frappe.get_all(
                "Hotel Room Tariff",
                filters={
                    "room_type": check_in.room_type,
                    "rate_type": check_in.rate_type,
                    #"hotel_season": check_in.hotel_season,
                    "is_active": 1
                },
                fields=["amount"],
                limit=1
            )
            if tariff:
                room_charge = tariff[0].amount
        self.total_amount = room_charge + sum(charge.amount for charge in self.additional_charges)
        if self.late_checkout:
            self.total_amount += self.late_checkout_charges

    def on_submit(self):
        """Update related records on checkout"""
        self.status = "Completed"
        self.update_check_in()
        self.update_room()
        self.update_reservation()  
        self.create_housekeeping_task()
        self.submit()
        frappe.publish_realtime('rhohotel_front_desk_update')

    def update_check_in(self):
        """Update check-in status"""
        frappe.db.set_value("Hotel Room Check In", self.check_in, {
            "status": "Checked Out"        
        })
        
    def update_reservation(self):
        """Update reservation status if linked"""
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        if check_in.reservation:
            reservation = frappe.get_doc("Hotel Room Reservation", check_in.reservation)
            reservation.status = "Completed"
            reservation.db_update()
        

    # create house keeping task on checkout
    def create_housekeeping_task(self):
        # check_out = frappe.get_doc("Hotel Room Check Out", self.name)
        task = frappe.new_doc("Housekeeping Task")
        task.room = self.room_number
        task.task_type = "Checkout Cleaning"
        task.status = "Pending"
        #task.description = f"Clean room {check_out.room_number} after checkout."
        task.insert(ignore_permissions=True)
        


    # update room status to Vacant and housekeeping to Dirty
    def update_room(self):
        """Update room status and trigger housekeeping"""
        frappe.db.set_value("Hotel Room", self.room_number, {
            "status": "Vacant",
            "housekeeping_status": "Dirty",
            "current_key_card": "",
            "current_check_in": "",
            "current_guest": "",
        })

    # revert changes if checkout is cancelled
    def on_cancel(self):
        """Revert changes when checkout is cancelled"""
        if self.docstatus == 2:  # Only if cancelled
            check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
            if check_in.docstatus == 2:  # If check-in was cancelled
                check_in.docstatus = 1
                check_in.status = "Checked In"
                check_in.db_update()

            frappe.db.set_value("Hotel Room", self.room_number, {
                "status": "Occupied",
                "housekeeping_status": "Clean",
                "current_key_card": check_in.key_card_number
            })
        frappe.publish_realtime('rhohotel_front_desk_update')

    def on_update(self):
        """Publish update to front desk"""
        frappe.publish_realtime('rhohotel_front_desk_update')


@frappe.whitelist()
def get_linked_documents(check_in):
    invoices = frappe.get_all("Sales Invoice", filters={"custom_hotel_room_check_in": check_in}, fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount"])
    payments = frappe.get_all("Payment Entry", filters={"custom_hotel_room_check_in": check_in}, fields=["name", "party", "posting_date", "paid_amount"])

    total_outstanding_amount = sum(invoice.outstanding_amount for invoice in invoices)

    check_in_doc = frappe.get_doc("Hotel Room Check In", check_in)
    guest_doc = frappe.get_doc("Hotel Guest", check_in_doc.guest)
    guest_email = guest_doc.email

    return {"invoices": invoices, "payments": payments, "total_outstanding_amount": total_outstanding_amount, "guest_email": guest_email}



@frappe.whitelist()
def initiate_monnify_payment(check_in_docname, check_out_docname, amount, guest_email, guest_name):
    hotel_settings = frappe.get_single("Hotel Settings")
    api_key = hotel_settings.monnify_api_key
    secret_key = hotel_settings.monnify_secret_key

    if not (api_key and secret_key):
        frappe.throw(_("Monnify API Key and Secret Key not set in Hotel Settings."))

    # Monnify API Base URL (use sandbox for testing, production for live)
    base_url = "https://sandbox.monnify.com" # Or "https://api.monnify.com" for production

    # Authenticate and get access token
    auth_string = f"{api_key}:{secret_key}"
    encoded_auth_string = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_auth_string}"
    }
    
    # Get access token
    try:
        token_response = requests.post(f"{base_url}/api/v1/auth/login", headers=headers)
        token_response.raise_for_status()
        access_token = token_response.json().get("responseBody", {}).get("accessToken")
    except requests.exceptions.RequestException as e:
        frappe.throw(_(f"Monnify authentication failed: {e}"))

    if not access_token:
        frappe.throw(_("Failed to get Monnify access token."))

    # Initiate transaction
    transaction_ref = frappe.generate_hash(length=20) # Generate a unique transaction reference
    
    payload = {
        "amount": amount,
        "customerName": guest_name,
        "customerEmail": guest_email,
        "paymentReference": transaction_ref,
        "paymentDescription": f"Payment for Hotel Room Check In: {check_in_docname}",
        "currencyCode": "NGN", # Assuming NGN, user can configure later
        "contractCode": "YOUR_CONTRACT_CODE", # User needs to provide this
        "redirectUrl": frappe.get_site_url(f"/api/method/rhohotel.rhocom_hotel.doctype.hotel_room_check_out.hotel_room_check_out.monnify_payment_callback"),
        "metadata": {
            "check_in_docname": check_in_docname,
            "check_out_docname": check_out_docname
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        init_response = requests.post(f"{base_url}/api/v1/merchant/transactions/init-transaction", json=payload, headers=headers)
        init_response.raise_for_status()
        response_data = init_response.json().get("responseBody", {})
        payment_page_url = response_data.get("checkoutUrl")
        transaction_reference = response_data.get("transactionReference")

        if not payment_page_url:
            frappe.throw(_("Failed to get Monnify payment page URL."))

        return {"payment_url": payment_page_url, "transaction_reference": transaction_reference}

    except requests.exceptions.RequestException as e:
        frappe.throw(_(f"Monnify transaction initiation failed: {e}"))


@frappe.whitelist(allow_guest=True)
def monnify_payment_callback(transactionReference, paymentStatus, amountPaid, customerEmail, check_in_docname, check_out_docname):
    # Verify the transaction status with Monnify
    hotel_settings = frappe.get_single("Hotel Settings")
    api_key = hotel_settings.monnify_api_key
    secret_key = hotel_settings.monnify_secret_key

    if not (api_key and secret_key):
        frappe.throw(_("Monnify API Key and Secret Key not set in Hotel Settings."))

    base_url = "https://sandbox.monnify.com" # Or "https://api.monnify.com" for production

    auth_string = f"{api_key}:{secret_key}"
    encoded_auth_string = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_auth_string}"
    }
    
    try:
        token_response = requests.post(f"{base_url}/api/v1/auth/login", headers=headers)
        token_response.raise_for_status()
        access_token = token_response.json().get("responseBody", {}).get("accessToken")
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Monnify authentication failed in callback: {e}")
        frappe.redirect("/payment-failed") # Redirect to a payment failed page

    if not access_token:
        frappe.log_error("Failed to get Monnify access token in callback.")
        frappe.redirect("/payment-failed")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        verify_response = requests.get(f"{base_url}/api/v1/merchant/transactions/reference/{transactionReference}", headers=headers)
        verify_response.raise_for_status()
        response_data = verify_response.json().get("responseBody", {})
        
        if response_data.get("paymentStatus") == "PAID":
            # Payment successful, create Payment Entry in ERPNext
            payment_entry = frappe.new_doc("Payment Entry")
            payment_entry.payment_type = "Receive"
            payment_entry.party_type = "Customer"

            # Get customer from Hotel Guest
            check_in_doc = frappe.get_doc("Hotel Room Check In", check_in_docname)
            guest_doc = frappe.get_doc("Hotel Guest", check_in_doc.guest)
            payment_entry.party = guest_doc.customer
            payment_entry.paid_amount = amountPaid
            payment_entry.received_amount = amountPaid
            payment_entry.mode_of_payment = "Monnify" # Or a specific Monnify payment method
            payment_entry.reference_no = transactionReference
            payment_entry.reference_date = frappe.utils.nowdate()
            payment_entry.custom_hotel_room_check_in = check_in_docname

            # Link to Sales Invoices
            invoices = frappe.get_all("Sales Invoice", filters={"custom_hotel_room_check_in": check_in_docname, "outstanding_amount": [">", 0]}, fields=["name", "outstanding_amount"])
            
            for invoice in invoices:
                payment_entry.append("references", {
                    "doctype": "Sales Invoice",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": invoice.name,
                    "bill_no": invoice.name,
                    "due_amount": invoice.outstanding_amount,
                    "allocated_amount": min(amountPaid, invoice.outstanding_amount) # Allocate payment
                })
                amountPaid -= min(amountPaid, invoice.outstanding_amount)
                if amountPaid <= 0:
                    break

            payment_entry.insert(ignore_permissions=True)
            payment_entry.submit()

            # Update Hotel Room Check Out payment status
            frappe.db.set_value("Hotel Room Check Out", check_out_docname, "payment_status", "Paid")

            frappe.redirect("/payment-success") # Redirect to a payment success page
        else:
            frappe.log_error(f"Monnify payment not successful for transaction {transactionReference}. Status: {response_data.get('paymentStatus')}")
            frappe.redirect("/payment-failed")

    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Monnify transaction verification failed in callback: {e}")
        frappe.redirect("/payment-failed")