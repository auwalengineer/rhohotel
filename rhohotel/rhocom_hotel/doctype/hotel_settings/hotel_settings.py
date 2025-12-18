# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime



class HotelSettings(Document):
	def validate(self):
		policies = sorted(self.late_checkout_policies, key=lambda x: x.from_hours)

		for i in range(len(policies) - 1):
			if policies[i].to_hours > policies[i + 1].from_hours:
				frappe.throw("Late checkout policies must not overlap.")

# API methods to get default check-in and check-out times
@frappe.whitelist()
def get_default_check_out_time():
	return frappe.get_single('Hotel Settings').default_check_out_time

@frappe.whitelist()
def get_default_check_in_time():
	return frappe.get_single('Hotel Settings').default_check_in_time	

def get_hours_late():
    settings = frappe.get_single("Hotel Settings")

    checkout_time = datetime.strptime(
        str(settings.default_check_out_time), "%H:%M:%S"
    ).time()

    now = datetime.now()

    checkout_dt = datetime.combine(now.date(), checkout_time)

    if now <= checkout_dt:
        return 0.0

    delta = now - checkout_dt
    return round(delta.total_seconds() / 3600, 2)

def get_late_checkout_policy(hours_late):
    settings = frappe.get_single("Hotel Settings")

    if not settings.enable_late_checkout_charges:
        return None

    for row in settings.late_checkout_policies:
        if row.from_hours <= hours_late <= row.to_hours:
            return row

    return None

@frappe.whitelist()
def check_late_checkout(check_in_name = None):
    hours_late = get_hours_late()
    settings = frappe.get_single("Hotel Settings")
    hours_late -= settings.late_checkout_grace_hours


    if hours_late <= 0:
        return {"late": False}

    if hours_late <= 0:
        return {"late": False}

    policy = get_late_checkout_policy(hours_late)

    if not policy:
        return {"late": False}
    
    if check_in_name:
        existing = frappe.db.sql("""
            SELECT sii.name
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si
                ON si.name = sii.parent
            WHERE
                sii.item_code = %s
                AND si.custom_hotel_room_check_in = %s
                AND si.docstatus < 2
            LIMIT 1
        """, (policy.item, check_in_name))

        if existing:
            return {"late": False}


    return {
        "late": True,
        "hours_late": hours_late,
        "policy": {
            "item": policy.item,
            "charge_type": policy.charge_type,
            "amount": policy.charge_amount
        }
    }