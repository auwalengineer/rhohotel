# Path: rhocom_hotel/rhocom_hotel/report/maintenance_request_report/maintenance_request_report.py

import frappe
from frappe.utils import flt

def execute(filters=None):
    if not filters:
        filters = {}
    
    conditions = []
    values = {}
    
    if filters.get("room"):
        conditions.append("room = %(room)s")
        values["room"] = filters["room"]
    if filters.get("asset"):
        conditions.append("asset = %(asset)s")
        values["asset"] = filters["asset"]
    if filters.get("request_type"):
        conditions.append("request_type = %(request_type)s")
        values["request_type"] = filters["request_type"]
    if filters.get("status"):
        conditions.append("status = %(status)s")
        values["status"] = filters["status"]
    if filters.get("from_date"):
        conditions.append("reported_at >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("reported_at <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    
    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    data = frappe.db.sql(f"""
        SELECT
            name,
            room,
            asset,
            request_type,
            issue_type,
            priority,
            status,
            reported_by,
            reported_at,
            completion_date,
            asset_repair
        FROM `tabMaintenance Request`
        {where_clause}
        ORDER BY reported_at DESC
    """, values, as_dict=True)
    
    columns = [
        {"fieldname": "name", "label": "Request ID", "fieldtype": "Data", "width": 120},
        {"fieldname": "room", "label": "Room", "fieldtype": "Link", "options": "Hotel Room", "width": 120},
        {"fieldname": "asset", "label": "Asset", "fieldtype": "Link", "options": "Asset", "width": 150},
        {"fieldname": "request_type", "label": "Request Type", "fieldtype": "Data", "width": 120},
        {"fieldname": "issue_type", "label": "Issue Type", "fieldtype": "Data", "width": 120},
        {"fieldname": "priority", "label": "Priority", "fieldtype": "Data", "width": 100},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100},
        {"fieldname": "reported_by", "label": "Reported By", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "reported_at", "label": "Reported At", "fieldtype": "Datetime", "width": 150},
        {"fieldname": "completion_date", "label": "Completion Date", "fieldtype": "Datetime", "width": 150},
        {"fieldname": "asset_repair", "label": "Asset Repair", "fieldtype": "Link", "options": "Asset Repair", "width": 150},
    ]
    
    return columns, data
