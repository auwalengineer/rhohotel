# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class HotelRoomRate(Document):
    def validate(self):
        self.validate_days()
        
    def validate_days(self):
        """Ensure number of days is valid"""
        if self.days < 1:
            frappe.throw("Number of days must be at least 1")
            
        if self.plan_type == "Hourly" and self.days > 1:
            frappe.throw("For hourly rates, number of days should be 1")