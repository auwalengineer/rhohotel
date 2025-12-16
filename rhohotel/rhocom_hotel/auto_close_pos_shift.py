import frappe
from frappe.utils import now_datetime, nowdate, getdate

def auto_close_pos_shifts():
    """
    Auto-close all open POS Shifts at 7:00 AM
    """

    open_shifts = frappe.get_all(
        "POS Shift",
        filters={
            "status": "Open",
            "docstatus": 1,
            "posting_date": ["<", nowdate()]

        },
        fields=["name"]
    )

    for shift in open_shifts:
        try:
            doc = frappe.get_doc("POS Shift", shift.name)

            doc.status = "Closed"
            doc.closing_time = now_datetime()
            doc.closing_note = "Auto-closed by system at 7:00 AM"
            doc.auto_reconciled = 1
            doc.save(ignore_permissions=True)

        except Exception:
            frappe.log_error(
                title="POS Shift Auto Close Failed",
                message=frappe.get_traceback()
            )

    frappe.db.commit()
