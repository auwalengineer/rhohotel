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

    def calculate_total(self):
        """Calculate total amount including additional charges and session-based room charges"""
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        # Use session and tariff for main room charge
        room_charge = 0
        if check_in.room_type and check_in.rate_type and check_in.session_type:
            tariff = frappe.get_all(
                "Hotel Room Tariff",
                filters={
                    "room_type": check_in.room_type,
                    "rate_type": check_in.rate_type,
                    "session_type": check_in.session_type,
                    "is_active": 1
                },
                fields=["amount"],
                limit=1
            )
            if tariff:
                room_charge = tariff[0].amount
        self.total_amount = room_charge + sum(charge.amount for charge in self.additional_charges)

    def on_submit(self):
        """Update related records on checkout"""
        self.status = "Completed"
        self.update_check_in()
        self.update_room()

    def update_check_in(self):
        """Update check-in status"""
        frappe.db.set_value("Hotel Room Check In", self.check_in, {
            "status": "Checked Out",
            "docstatus": 2  # Cancel the check-in
        })

    def update_room(self):
        """Update room status and trigger housekeeping"""
        frappe.db.set_value("Hotel Room", self.room, {
            "status": "Vacant",
            "housekeeping_status": "Dirty",
            "current_key_card": ""
        })

    def on_cancel(self):
        """Revert changes when checkout is cancelled"""
        if self.docstatus == 2:  # Only if cancelled
            check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
            if check_in.docstatus == 2:  # If check-in was cancelled
                check_in.docstatus = 1
                check_in.status = "Checked In"
                check_in.db_update()

            frappe.db.set_value("Hotel Room", self.room, {
                "status": "Occupied",
                "housekeeping_status": "Clean",
                "current_key_card": check_in.key_card_number
            })