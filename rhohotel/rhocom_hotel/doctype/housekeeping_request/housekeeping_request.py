import frappe
from frappe.model.document import Document

class HousekeepingRequest(Document):
    def on_submit(self):
        """
        Just log submission, don't create task yet
        """
        frappe.log_error(
            f"Housekeeping Request {self.name} submitted",
            'Housekeeping Request - Submitted'
        )
    
    def on_cancel(self):
        """
        Cancel the associated task when request is cancelled
        """
        if self.housekeeping_task:
            try:
                task = frappe.get_doc('Housekeeping Task', self.housekeeping_task)
                if task.docstatus == 1:
                    task.amend()
                    task.status = 'Cancelled'
                    task.save()
                    task.submit()
                    frappe.log_error(
                        f"Associated Housekeeping Task {self.housekeeping_task} cancelled",
                        'Housekeeping Request - Task Cancelled'
                    )
            except Exception as e:
                frappe.log_error(f"Error cancelling Housekeeping Task: {str(e)}", 'Housekeeping Request - Error')
    
    def _get_priority_from_request(self):
        """
        Determine task priority based on who requested it
        """
        priority_mapping = {
            'Guest': 'High',
            'Front Desk': 'Medium',
            'Room Service': 'High',
            'Management': 'Medium'
        }
        return priority_mapping.get(self.requested_by, 'Medium')


# @frappe.whitelist()
# def approve_housekeeping_request(request_name):
#     """
#     Approve a housekeeping request, create task, and update its status
#     """
#     try:
#         from frappe.utils import now_datetime
        
#         doc = frappe.get_doc('Housekeeping Request', request_name)
        
#         if not frappe.has_permission('Housekeeping Request', 'write', doc):
#             frappe.throw('You do not have permission to approve this request')
        
#         if doc.status == 'Approved':
#             frappe.msgprint('This request is already approved')
#             return
        
#         # Create Housekeeping Task only when approved
#         try:
#             housekeeping_task = frappe.new_doc('Housekeeping Task')
#             housekeeping_task.room = doc.room
#             housekeeping_task.task_type = 'Guest Request'
#             housekeeping_task.status = 'Assigned'
#             housekeeping_task.priority = _get_priority_from_request(doc)
#             housekeeping_task.notes = doc.request_details or f"Guest Request from {doc.requested_by}: {doc.guest_name}"
            
#             housekeeping_task.insert(ignore_permissions=True)
#             housekeeping_task.submit()
            
#             # Update request with task reference
#             doc.db_set('housekeeping_task', housekeeping_task.name)
            
#         except Exception as e:
#             frappe.log_error(f"Error creating Housekeeping Task: {str(e)}", 'Housekeeping Request - Error')
#             frappe.throw(f"Error creating housekeeping task: {str(e)}")
        
#         # Update status and approval time
#         doc.db_set('status', 'Approved')
#         doc.db_set('approval_time', now_datetime())
        
#         frappe.log_error(
#             f"Housekeeping Request {request_name} approved by {frappe.session.user} at {now_datetime()}",
#             'Housekeeping Request - Approved'
#         )
        
#         return frappe.get_doc('Housekeeping Request', request_name).as_dict()
        
#     except Exception as e:
#         frappe.log_error(f"Error approving Housekeeping Request: {str(e)}", 'Housekeeping Request - Error')
#         frappe.throw(f"Error approving request: {str(e)}")


# @frappe.whitelist()
# def approve_housekeeping_request(request_name):
#     """
#     Approve a housekeeping request, create task, and update its status
#     FIXED: Explicitly loads room inventory after creating task
#     """
#     try:
#         from frappe.utils import now_datetime
        
#         doc = frappe.get_doc('Housekeeping Request', request_name)
        
#         if not frappe.has_permission('Housekeeping Request', 'write', doc):
#             frappe.throw('You do not have permission to approve this request')
        
#         if doc.status == 'Approved':
#             frappe.msgprint('This request is already approved')
#             return
        
#         # Create Housekeeping Task only when approved
#         try:
#             housekeeping_task = frappe.new_doc('Housekeeping Task')
#             housekeeping_task.room = doc.room
#             housekeeping_task.task_type = 'Guest Request'
#             housekeeping_task.status = 'Assigned'
#             housekeeping_task.priority = _get_priority_from_request(doc)
#             housekeeping_task.notes = doc.request_details or f"Guest Request from {doc.requested_by}: {doc.guest_name}"
            
#             housekeeping_task.insert(ignore_permissions=True)
            
#             # Explicitly load room inventory (replicate what the client-side room trigger does)
#             if doc.room:
#                 try:
#                     room_doc = frappe.get_doc('Hotel Room', doc.room)
#                     if hasattr(room_doc, 'room_inventory') and room_doc.room_inventory:
#                         for item in room_doc.room_inventory:
#                             item_doc = frappe.get_doc('Item', item.item)
#                             housekeeping_task.append('room_inventory_before', {
#                                 'item': item.item,
#                                 'quantity_before': item.quantity,
#                                 'uom': item_doc.stock_uom
#                             })
#                         housekeeping_task.save()  # Save the inventory changes
#                 except Exception as e:
#                     frappe.log_error(f"Warning: Could not load room inventory: {str(e)}", 'Housekeeping Request - Warning')
            
#             housekeeping_task.submit()
            
#             # Update request with task reference
#             doc.db_set('housekeeping_task', housekeeping_task.name)
            
#         except Exception as e:
#             frappe.log_error(f"Error creating Housekeeping Task: {str(e)}", 'Housekeeping Request - Error')
#             frappe.throw(f"Error creating housekeeping task: {str(e)}")
        
#         # Update status and approval time
#         doc.db_set('status', 'Approved')
#         doc.db_set('approval_time', now_datetime())
        
#         frappe.log_error(
#             f"Housekeeping Request {request_name} approved by {frappe.session.user} at {now_datetime()}",
#             'Housekeeping Request - Approved'
#         )
        
#         return frappe.get_doc('Housekeeping Request', request_name).as_dict()
        
#     except Exception as e:
#         frappe.log_error(f"Error approving Housekeeping Request: {str(e)}", 'Housekeeping Request - Error')
#         frappe.throw(f"Error approving request: {str(e)}")

@frappe.whitelist()
def approve_housekeeping_request(request_name):
    """
    Approve a housekeeping request, create task, and update its status
    FIXED: Loads inventory only once (no duplication)
    """
    try:
        from frappe.utils import now_datetime
        
        doc = frappe.get_doc('Housekeeping Request', request_name)
        
        if not frappe.has_permission('Housekeeping Request', 'write', doc):
            frappe.throw('You do not have permission to approve this request')
        
        if doc.status == 'Approved':
            frappe.msgprint('This request is already approved')
            return
        
        # Create Housekeeping Task only when approved
        try:
            housekeeping_task = frappe.new_doc('Housekeeping Task')
            housekeeping_task.room = doc.room
            housekeeping_task.task_type = 'Guest Request'
            housekeeping_task.status = 'Assigned'
            housekeeping_task.priority = _get_priority_from_request(doc)
            housekeeping_task.notes = doc.request_details or f"Guest Request from {doc.requested_by}: {doc.guest_name}"
            
            # Load room inventory BEFORE inserting
            if doc.room:
                try:
                    room_doc = frappe.get_doc('Hotel Room', doc.room)
                    if hasattr(room_doc, 'room_inventory') and room_doc.room_inventory:
                        for item in room_doc.room_inventory:
                            item_doc = frappe.get_doc('Item', item.item)
                            housekeeping_task.append('room_inventory_before', {
                                'item': item.item,
                                'quantity_before': item.quantity,
                                'uom': item_doc.stock_uom
                            })
                except Exception as e:
                    frappe.log_error(
                        f"Warning: Could not load room inventory for {doc.room}: {str(e)}", 
                        'Housekeeping Request - Warning'
                    )
            
            # Insert (now with inventory already loaded)
            housekeeping_task.insert(ignore_permissions=True)
            housekeeping_task.submit()
            
            # Update request with task reference
            doc.db_set('housekeeping_task', housekeeping_task.name)
            
        except Exception as e:
            frappe.log_error(f"Error creating Housekeeping Task: {str(e)}", 'Housekeeping Request - Error')
            frappe.throw(f"Error creating housekeeping task: {str(e)}")
        
        # Update status and approval time
        doc.db_set('status', 'Approved')
        doc.db_set('approval_time', now_datetime())
        
        frappe.log_error(
            f"Housekeeping Request {request_name} approved by {frappe.session.user} at {now_datetime()}",
            'Housekeeping Request - Approved'
        )
        
        return frappe.get_doc('Housekeeping Request', request_name).as_dict()
        
    except Exception as e:
        frappe.log_error(f"Error approving Housekeeping Request: {str(e)}", 'Housekeeping Request - Error')
        frappe.throw(f"Error approving request: {str(e)}")


def _get_priority_from_request(doc):
    """Helper function to get priority"""
    priority_mapping = {
        'Guest': 'High',
        'Front Desk': 'Medium',
        'Room Service': 'High',
        'Management': 'Medium'
    }
    return priority_mapping.get(doc.requested_by, 'Medium')

def _get_priority_from_request(doc):
    """Helper function to get priority"""
    priority_mapping = {
        'Guest': 'High',
        'Front Desk': 'Medium',
        'Room Service': 'High',
        'Management': 'Medium'
    }
    return priority_mapping.get(doc.requested_by, 'Medium')