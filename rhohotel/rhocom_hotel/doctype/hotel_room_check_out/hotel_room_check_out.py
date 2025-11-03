# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, get_datetime, add_to_date

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
        # Use session and tariff for main room charge
        room_charge = 0
        if check_in.room_type and check_in.rate_type and check_in.hotel_session:
            tariff = frappe.get_all(
                "Hotel Room Tariff",
                filters={
                    "room_type": check_in.room_type,
                    "rate_type": check_in.rate_type,
                    "hotel_session": check_in.hotel_session,
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
        frappe.publish_realtime('rhohotel_front_desk_update')

    def update_check_in(self):
        """Update check-in status"""
        frappe.db.set_value("Hotel Room Check In", self.check_in, {
            "status": "Checked Out",
            "docstatus": 2  # Cancel the check-in
        })

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
    return {"invoices": invoices, "payments": payments}
