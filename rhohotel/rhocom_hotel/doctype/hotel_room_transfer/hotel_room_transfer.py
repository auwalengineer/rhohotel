# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class HotelRoomTransfer(Document):
    def before_submit(self):
        self.validate_transfer()
        self.update_check_in()
        self.update_rooms()

    def validate_transfer(self):
        if self.from_room == self.to_room:
            frappe.throw("From Room and To Room cannot be the same.")

        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        if check_in.status != "Checked In":
            frappe.throw("Room transfer is only allowed for active check-ins.")

        to_room_status = frappe.db.get_value("Hotel Room", self.to_room, "status")
        if to_room_status != "Vacant":
            frappe.throw(f"Room {self.to_room} is not vacant.")

    def update_check_in(self):
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        check_in.room_number = self.to_room
        check_in.add_comment("Room Transfer", f"Room transferred from {self.from_room} to {self.to_room} on {self.transfer_datetime}.")
        check_in.save(ignore_permissions=True)

    def update_rooms(self):
        # Update the 'from_room'
        frappe.db.set_value("Hotel Room", self.from_room, "status", "Vacant")
        frappe.db.set_value("Hotel Room", self.from_room, "current_check_in", None)
        frappe.db.set_value("Hotel Room", self.from_room, "current_guest", None)

        # Update the 'to_room'
        check_in = frappe.get_doc("Hotel Room Check In", self.check_in)
        frappe.db.set_value("Hotel Room", self.to_room, "status", "Occupied")
        frappe.db.set_value("Hotel Room", self.to_room, "current_check_in", self.check_in)
        frappe.db.set_value("Hotel Room", self.to_room, "current_guest", check_in.guest)

