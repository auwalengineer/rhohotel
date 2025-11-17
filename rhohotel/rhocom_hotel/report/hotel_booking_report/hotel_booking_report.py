import frappe
from frappe import _
from frappe.model.document import Document
from datetime import datetime, timedelta
from decimal import Decimal


def execute(filters=None):
    """
    Hotel Booking Report - Enhanced Version
    Includes summary statistics and advanced filtering
    """
    if not filters:
        filters = {}
    
    columns = get_columns()
    data = get_data(filters)
    
    # Optional: Add summary section
    if frappe.request and frappe.request.method == "GET":
        frappe.msgprint(f"Total Bookings: {len(data)}", indicator='green')
    
    return columns, data


def get_columns():
    """Define report columns with enhanced formatting"""
    return [
        {
            "label": _("Booking #"),
            "fieldname": "booking_number",
            "fieldtype": "Link",
            "options": "Hotel Booking",
            "width": 120
        },
        {
            "label": _("Customer"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 100
        },
        {
            "label": _("Name"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Email"),
            "fieldname": "customer_email",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("Phone"),
            "fieldname": "customer_phone",
            "fieldtype": "Phone",
            "width": 120
        },
        {
            "label": _("Check-In"),
            "fieldname": "from_date",
            "fieldtype": "Date",
            "width": 110
        },
        {
            "label": _("Check-Out"),
            "fieldname": "to_date",
            "fieldtype": "Date",
            "width": 110
        },
        {
            "label": _("Rooms"),
            "fieldname": "total_rooms",
            "fieldtype": "Int",
            "width": 70
        },
        {
            "label": _("Amount"),
            "fieldname": "total_price",
            "fieldtype": "Currency",
            "width": 110
        },
        {
            "label": _("Book Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Pay Status"),
            "fieldname": "payment_status",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Ref ID"),
            "fieldname": "transaction_id",
            "fieldtype": "Data",
            "width": 140
        },
        {
            "label": _("Invoice"),
            "fieldname": "sales_invoice",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 120
        },
        {
            "label": _("Check-In Time"),
            "fieldname": "check_in_time",
            "fieldtype": "Datetime",
            "width": 150
        },
        {
            "label": _("Check-Out Time"),
            "fieldname": "check_out_time",
            "fieldtype": "Datetime",
            "width": 150
        },
        {
            "label": _("Hold Expires"),
            "fieldname": "hold_expires_at",
            "fieldtype": "Datetime",
            "width": 150
        },
        {
            "label": _("Created"),
            "fieldname": "created_at",
            "fieldtype": "Datetime",
            "width": 150
        },
        {
            "label": _("Payment At"),
            "fieldname": "payment_received_at",
            "fieldtype": "Datetime",
            "width": 150
        }
    ]


def get_data(filters):
    """Fetch hotel booking data with comprehensive filtering"""
    
    # Build filters
    conditions = []
    params = {}
    
    # Text-based filters
    if filters.get("booking_number"):
        conditions.append("hb.booking_number = %(booking_number)s")
        params["booking_number"] = filters.get("booking_number")
    
    if filters.get("customer"):
        conditions.append("hb.customer = %(customer)s")
        params["customer"] = filters.get("customer")
    
    if filters.get("customer_name"):
        conditions.append("hb.customer_name LIKE %(customer_name)s")
        params["customer_name"] = f"%{filters.get('customer_name')}%"
    
    if filters.get("contact_name"):
        conditions.append("hb.contact_name = %(contact_name)s")
        params["contact_name"] = filters.get("contact_name")
    
    if filters.get("status"):
        conditions.append("hb.status = %(status)s")
        params["status"] = filters.get("status")
    
    if filters.get("payment_status"):
        conditions.append("hb.payment_status = %(payment_status)s")
        params["payment_status"] = filters.get("payment_status")
    
    if filters.get("sales_invoice"):
        conditions.append("hb.sales_invoice = %(sales_invoice)s")
        params["sales_invoice"] = filters.get("sales_invoice")
    
    if filters.get("customer_email"):
        conditions.append("hb.customer_email LIKE %(customer_email)s")
        params["customer_email"] = f"%{filters.get('customer_email')}%"
    
    if filters.get("customer_phone"):
        conditions.append("hb.customer_phone LIKE %(customer_phone)s")
        params["customer_phone"] = f"%{filters.get('customer_phone')}%"
    
    if filters.get("transaction_id"):
        conditions.append("hb.transaction_id LIKE %(transaction_id)s")
        params["transaction_id"] = f"%{filters.get('transaction_id')}%"
    
    if filters.get("paystack_access_code"):
        conditions.append("hb.paystack_access_code LIKE %(paystack_access_code)s")
        params["paystack_access_code"] = f"%{filters.get('paystack_access_code')}%"
    
    # Date filters
    if filters.get("from_date_start"):
        conditions.append("hb.from_date >= %(from_date_start)s")
        params["from_date_start"] = filters.get("from_date_start")
    
    if filters.get("from_date_end"):
        conditions.append("hb.from_date <= %(from_date_end)s")
        params["from_date_end"] = filters.get("from_date_end")
    
    if filters.get("to_date_start"):
        conditions.append("hb.to_date >= %(to_date_start)s")
        params["to_date_start"] = filters.get("to_date_start")
    
    if filters.get("to_date_end"):
        conditions.append("hb.to_date <= %(to_date_end)s")
        params["to_date_end"] = filters.get("to_date_end")
    
    # Numeric range filters
    if filters.get("total_rooms_min"):
        conditions.append("hb.total_rooms >= %(total_rooms_min)s")
        params["total_rooms_min"] = int(filters.get("total_rooms_min"))
    
    if filters.get("total_rooms_max"):
        conditions.append("hb.total_rooms <= %(total_rooms_max)s")
        params["total_rooms_max"] = int(filters.get("total_rooms_max"))
    
    if filters.get("total_price_min"):
        conditions.append("hb.total_price >= %(total_price_min)s")
        params["total_price_min"] = float(filters.get("total_price_min"))
    
    if filters.get("total_price_max"):
        conditions.append("hb.total_price <= %(total_price_max)s")
        params["total_price_max"] = float(filters.get("total_price_max"))
    
    # Datetime filters
    if filters.get("check_in_time_start"):
        conditions.append("hb.check_in_time >= %(check_in_time_start)s")
        params["check_in_time_start"] = filters.get("check_in_time_start")
    
    if filters.get("check_in_time_end"):
        conditions.append("hb.check_in_time <= %(check_in_time_end)s")
        params["check_in_time_end"] = filters.get("check_in_time_end")
    
    if filters.get("created_at_start"):
        conditions.append("hb.created_at >= %(created_at_start)s")
        params["created_at_start"] = filters.get("created_at_start")
    
    if filters.get("created_at_end"):
        conditions.append("hb.created_at <= %(created_at_end)s")
        params["created_at_end"] = filters.get("created_at_end")
    
    if filters.get("payment_received_at_start"):
        conditions.append("hb.payment_received_at >= %(payment_received_at_start)s")
        params["payment_received_at_start"] = filters.get("payment_received_at_start")
    
    if filters.get("payment_received_at_end"):
        conditions.append("hb.payment_received_at <= %(payment_received_at_end)s")
        params["payment_received_at_end"] = filters.get("payment_received_at_end")
    
    if filters.get("hold_expires_at_start"):
        conditions.append("hb.hold_expires_at >= %(hold_expires_at_start)s")
        params["hold_expires_at_start"] = filters.get("hold_expires_at_start")
    
    if filters.get("hold_expires_at_end"):
        conditions.append("hb.hold_expires_at <= %(hold_expires_at_end)s")
        params["hold_expires_at_end"] = filters.get("hold_expires_at_end")
    
    # Build WHERE clause
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # SQL query
    query = f"""
        SELECT
            hb.name,
            hb.booking_number,
            hb.customer,
            hb.customer_name,
            hb.contact_name,
            hb.from_date,
            hb.to_date,
            hb.customer_email,
            hb.customer_phone,
            hb.total_rooms,
            hb.total_price,
            hb.status,
            hb.payment_status,
            hb.transaction_id,
            hb.paystack_access_code,
            hb.sales_invoice,
            hb.check_in_time,
            hb.check_out_time,
            hb.hold_expires_at,
            hb.created_at,
            hb.payment_received_at
        FROM
            `tabHotel Booking` hb
        WHERE
            {where_clause}
        ORDER BY
            hb.creation DESC
    """
    
    # Execute query
    data = frappe.db.sql(query, params, as_dict=True)
    
    return data


def get_summary_statistics(data):
    """Calculate summary statistics from report data"""
    if not data:
        return {}
    
    total_bookings = len(data)
    total_revenue = sum(row.get('total_price', 0) for row in data if row.get('total_price'))
    total_rooms = sum(row.get('total_rooms', 0) for row in data if row.get('total_rooms'))
    
    paid_bookings = len([row for row in data if row.get('payment_status') == 'Paid'])
    confirmed_bookings = len([row for row in data if row.get('status') == 'Confirmed'])
    
    avg_price = total_revenue / total_bookings if total_bookings > 0 else 0
    avg_rooms = total_rooms / total_bookings if total_bookings > 0 else 0
    
    return {
        'total_bookings': total_bookings,
        'total_revenue': total_revenue,
        'total_rooms': total_rooms,
        'paid_bookings': paid_bookings,
        'confirmed_bookings': confirmed_bookings,
        'avg_price': avg_price,
        'avg_rooms': avg_rooms,
        'payment_rate': (paid_bookings / total_bookings * 100) if total_bookings > 0 else 0
    }