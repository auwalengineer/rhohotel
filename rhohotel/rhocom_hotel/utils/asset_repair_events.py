import frappe

def sync_maintenance_request(doc, method=None):
    """Sync Asset Repair status to Maintenance Request and update room flag"""
    
    # Get the Maintenance Request from the custom field
    if not doc.maintenance_request:
        frappe.logger().warning(
            f"No maintenance_request set on Asset Repair {doc.name}"
        )
        return
    
    mr_name = doc.maintenance_request
    
    # Determine status based on Asset Repair status
    status = "Pending"
    completion_date = None

    if doc.docstatus == 2:  # Cancelled
        status = "Cancelled"
    elif doc.docstatus == 1 and hasattr(doc, 'repair_status'):
        if doc.repair_status == "Completed":
            status = "Completed"
            completion_date = doc.completion_date
        elif doc.repair_status == "Cancelled":
            status = "Cancelled"
        else:
            status = "Pending"
    
    # Update the Maintenance Request
    frappe.db.set_value(
        "Maintenance Request", 
        mr_name, 
        {
            "status": status,
            "completion_date": completion_date
        }
    )
    
    frappe.logger().info(
        f"Synced Asset Repair {doc.name} to MR {mr_name}: status={status}"
    )
    
    # NOW UPDATE THE ROOM MAINTENANCE FLAG
    # Get the MR doc and call update_room_maintenance_flag
    mr_doc = frappe.get_doc("Maintenance Request", mr_name)
    mr_doc.update_room_maintenance_flag()
    
    frappe.logger().info(
        f"Updated room maintenance flag for MR {mr_name} after Asset Repair sync"
    )