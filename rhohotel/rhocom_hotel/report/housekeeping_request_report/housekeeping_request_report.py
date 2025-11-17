import frappe
from frappe.utils import getdate

def execute(filters=None):
    """
    Execute the Housekeeping Request report with filters
    """
    if not filters:
        filters = {}
    
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data


def get_columns():
    """
    Define report columns
    """
    return [
        {
            "label": "Request ID",
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Housekeeping Request",
            "width": 120
        },
        {
            "label": "Room",
            "fieldname": "room",
            "fieldtype": "Link",
            "options": "Hotel Room",
            "width": 100
        },
        {
            "label": "Guest Name",
            "fieldname": "guest_name",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "Request Date",
            "fieldname": "request_date",
            "fieldtype": "Date",
            "width": 120
        },
        {
            "label": "Requested By",
            "fieldname": "requested_by",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": "Request Details",
            "fieldname": "request_details",
            "fieldtype": "Data",
            "width": 250
        },
        {
            "label": "Housekeeping Task",
            "fieldname": "housekeeping_task",
            "fieldtype": "Link",
            "options": "Housekeeping Task",
            "width": 150
        },
        {
            "label": "Approval Time",
            "fieldname": "approval_time",
            "fieldtype": "DateTime",
            "width": 150
        },
        {
            "label": "Created On",
            "fieldname": "creation",
            "fieldtype": "DateTime",
            "width": 150
        }
    ]


def get_data(filters):
    """
    Fetch data based on applied filters
    """
    # Build the WHERE clause dynamically
    conditions = []
    
    # Room filter
    if filters.get('room'):
        conditions.append(f"hr.room = '{frappe.db.escape(filters.get('room'))}'")
    
    # Status filter
    if filters.get('status'):
        conditions.append(f"hr.status = '{frappe.db.escape(filters.get('status'))}'")
    
    # Requested By filter
    if filters.get('requested_by'):
        conditions.append(f"hr.requested_by = '{frappe.db.escape(filters.get('requested_by'))}'")
    
    # Request Date From filter
    if filters.get('request_date_from'):
        conditions.append(f"DATE(hr.request_date) >= '{frappe.db.escape(filters.get('request_date_from'))}'")
    
    # Request Date To filter
    if filters.get('request_date_to'):
        conditions.append(f"DATE(hr.request_date) <= '{frappe.db.escape(filters.get('request_date_to'))}'")
    
    # Approval Status filter
    if filters.get('approval_status') == 'Approved':
        conditions.append("hr.approval_time IS NOT NULL")
    elif filters.get('approval_status') == 'Pending Approval':
        conditions.append("hr.approval_time IS NULL AND hr.status != 'Cancelled'")
    
    # Build the WHERE clause
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # Execute the query
    query = f"""
        SELECT
            hr.name,
            hr.room,
            hr.guest_name,
            hr.request_date,
            hr.requested_by,
            hr.status,
            hr.request_details,
            hr.housekeeping_task,
            hr.approval_time,
            hr.creation
        FROM
            `tabHousekeeping Request` hr
        WHERE
            {where_clause}
        ORDER BY
            hr.creation DESC
    """
    
    data = frappe.db.sql(query, as_dict=True)
    
    # Format the data
    formatted_data = []
    for row in data:
        formatted_data.append({
            "name": row.get('name'),
            "room": row.get('room'),
            "guest_name": row.get('guest_name'),
            "request_date": row.get('request_date'),
            "requested_by": row.get('requested_by'),
            "status": row.get('status'),
            "request_details": row.get('request_details')[:100] if row.get('request_details') else '',  # Truncate for display
            "housekeeping_task": row.get('housekeeping_task'),
            "approval_time": row.get('approval_time'),
            "creation": row.get('creation')
        })
    
    return formatted_data


@frappe.whitelist()
def bulk_approve_requests(request_ids):
    """
    Bulk approve multiple housekeeping requests
    """
    from frappe.utils import now_datetime
    
    if isinstance(request_ids, str):
        import json
        request_ids = json.loads(request_ids)
    
    approved_count = 0
    failed_count = 0
    errors = []
    
    for request_id in request_ids:
        try:
            doc = frappe.get_doc('Housekeeping Request', request_id)
            
            if not frappe.has_permission('Housekeeping Request', 'write', doc):
                failed_count += 1
                errors.append(f"{request_id}: Permission denied")
                continue
            
            if doc.status == 'Approved':
                continue  # Skip already approved
            
            # Create Housekeeping Task if not exists
            if not doc.housekeeping_task:
                try:
                    housekeeping_task = frappe.new_doc('Housekeeping Task')
                    housekeeping_task.room = doc.room
                    housekeeping_task.task_type = 'Guest Request'
                    housekeeping_task.status = 'Assigned'
                    housekeeping_task.priority = _get_priority_from_request(doc)
                    housekeeping_task.notes = doc.request_details or f"Guest Request from {doc.requested_by}: {doc.guest_name}"
                    
                    housekeeping_task.insert(ignore_permissions=True)
                    housekeeping_task.submit()
                    
                    doc.db_set('housekeeping_task', housekeeping_task.name)
                except Exception as e:
                    failed_count += 1
                    errors.append(f"{request_id}: Error creating task - {str(e)}")
                    continue
            
            # Update status and approval time
            doc.db_set('status', 'Approved')
            doc.db_set('approval_time', now_datetime())
            
            approved_count += 1
            
            frappe.log_error(
                f"Housekeeping Request {request_id} bulk approved by {frappe.session.user}",
                'Housekeeping Request - Bulk Approved'
            )
            
        except Exception as e:
            failed_count += 1
            errors.append(f"{request_id}: {str(e)}")
    
    result_message = f"Successfully approved {approved_count} request(s)"
    if failed_count > 0:
        result_message += f". Failed: {failed_count}"
        if errors:
            result_message += f"\nErrors:\n" + "\n".join(errors[:5])  # Show first 5 errors
    
    frappe.msgprint(result_message)
    
    return {
        "approved": approved_count,
        "failed": failed_count,
        "errors": errors
    }


def _get_priority_from_request(doc):
    """
    Determine task priority based on who requested it
    """
    priority_mapping = {
        'Guest': 'High',
        'Front Desk': 'Medium',
        'Room Service': 'High',
        'Management': 'Medium'
    }
    return priority_mapping.get(doc.requested_by, 'Medium')