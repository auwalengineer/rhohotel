# Copyright (c) 2025, Rhocom Technology Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class HotelRoomTariff(Document):
    def validate(self):
        self.validate_tariff()
        
    def validate_tariff(self):
        """Ensure no duplicate tariff exists for the same combination"""
        filters = {
            'room_type': self.room_type,
            'rate_type': self.rate_type,
            'hotel_season': self.hotel_season,
            'name': ['!=', self.name]
        }
        
        if frappe.db.exists('Hotel Room Tariff', filters):
            frappe.throw("A tariff already exists for this combination of Room Type, Rate Type, and Season")
            
    @frappe.whitelist()
    def get_amount(room_type, rate_type, hotel_season):
        """Get tariff amount for given combination"""
        tariff = frappe.get_all(
            'Hotel Room Tariff',
            filters={
                'room_type': room_type,
                'rate_type': rate_type,
                'hotel_season': hotel_season,
                'is_active': 1
            },
            fields=['rate_amount'],
            limit=1
        )

        if not tariff:
            tariff = frappe.get_all(
                'Hotel Room Tariff',
                filters={
                    'room_type': room_type,
                    'is_active': 1,
                    'is_default': 1
                },
                fields=['rate_amount'],
                limit=1
            )
        
        return tariff[0].rate_amount if tariff else 0