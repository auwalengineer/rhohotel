
# Copyright (c) 2025, Rhocom and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class HotelGuest(Document):
    def before_save(self):
        if not self.customer:
            self.create_customer()

    def create_customer(self):
        if not frappe.db.exists("Customer", {"custom_guest_id": self.name}):
            customer = frappe.new_doc("Customer")
            customer.customer_name = self.hotel_guest_name
            # Set other customer fields as needed
            customer.custom_guest_id = self.name
            customer.insert()
            self.customer = customer.name
