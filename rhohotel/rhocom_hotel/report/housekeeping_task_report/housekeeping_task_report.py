import frappe
from datetime import datetime, timedelta
from frappe import _
import json


@frappe.whitelist()
def get_housekeeping_report_with_inventory(start_date=None, end_date=None, employee=None, task_type=None, status=None):
    """
    Generate comprehensive housekeeping report WITH room inventory details.
    
    Includes:
    - Task timing (start, end, duration)
    - Room inventory before task
    - Inventory changes during task
    - Quality inspection results
    - Employee productivity metrics
    - Stock entry tracking
    """
    
    if not start_date:
        start_date = frappe.utils.today()
    if not end_date:
        end_date = frappe.utils.today()
    
    try:
        # Build filter conditions
        filters = {
            'creation': ['>=', start_date],
            'modified': ['<=', end_date]
        }
        
        if employee:
            filters['employee'] = employee
        if task_type:
            filters['task_type'] = task_type
        if status:
            filters['status'] = status
        
        # Fetch all housekeeping tasks
        tasks = frappe.get_list(
            'Housekeeping Task',
            filters=filters,
            fields=[
                'name',
                'room',
                'employee',
                'employee_name',
                'task_type',
                'status',
                'creation',
                'modified',
                'start_time',
                'end_time',
                'stock_entry',
                'quality_passed',
                'inspection_notes',
                'notes'
            ],
            order_by='creation desc',
            limit_page_length=500
        )
        
        task_details = []
        
        for task in tasks:
            task_doc = frappe.get_doc('Housekeeping Task', task['name'])
            
            # ===== TIMING CALCULATIONS =====
            start_time = task_doc.get('start_time')
            end_time = task_doc.get('end_time')
            duration_minutes = None
            duration_formatted = "Not Set"
            
            if start_time and end_time:
                if isinstance(start_time, str):
                    start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                if isinstance(end_time, str):
                    end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
                
                duration = end_time - start_time
                duration_minutes = int(duration.total_seconds() / 60)
                hours = duration_minutes // 60
                mins = duration_minutes % 60
                if hours > 0:
                    duration_formatted = f"{hours}h {mins}m"
                else:
                    duration_formatted = f"{mins}m"
            
            # ===== ROOM INFORMATION =====
            room_info = frappe.get_value(
                'Hotel Room',
                task_doc.room,
                ['room_number', 'room_type', 'floor']
            )
            
            # ===== ROOM INVENTORY BEFORE TASK =====
            inventory_before = []
            inventory_before_summary = {
                'total_items': 0,
                'total_quantity': 0
            }
            
            if task_doc.room_inventory_before:
                for inv in task_doc.room_inventory_before:
                    item_data = {
                        'item': inv.get('item'),
                        'item_name': inv.get('item_name'),
                        'quantity': inv.get('quantity', 0),
                        'uom': inv.get('uom')
                    }
                    inventory_before.append(item_data)
                    inventory_before_summary['total_items'] += 1
                    inventory_before_summary['total_quantity'] += int(inv.get('quantity', 0))
            
            # ===== INVENTORY CHANGES DURING TASK =====
            inventory_changes = []
            inventory_changes_summary = {
                'total_changes': 0,
                'items_added': 0,
                'items_replaced': 0,
                'items_removed': 0,
                'total_added_qty': 0,
                'total_removed_qty': 0
            }
            
            if task_doc.room_inventory_changes:
                for change in task_doc.room_inventory_changes:
                    change_type = change.get('change_type', 'Unknown')
                    quantity_used = int(change.get('quantity_used', 0))
                    
                    change_data = {
                        'item': change.get('item'),
                        'item_name': change.get('item_name'),
                        'quantity_before': change.get('quantity_before', 0),
                        'quantity_after': change.get('quantity_after', 0),
                        'quantity_used': quantity_used,
                        'uom': change.get('uom'),
                        'change_type': change_type
                    }
                    inventory_changes.append(change_data)
                    
                    # Update summary
                    inventory_changes_summary['total_changes'] += 1
                    if change_type == 'Added':
                        inventory_changes_summary['items_added'] += 1
                        inventory_changes_summary['total_added_qty'] += quantity_used
                    elif change_type == 'Replaced':
                        inventory_changes_summary['items_replaced'] += 1
                    elif change_type == 'Removed':
                        inventory_changes_summary['items_removed'] += 1
                        inventory_changes_summary['total_removed_qty'] += quantity_used
            
            # ===== QUALITY INSPECTION =====
            quality_details = frappe.get_list(
                'Quality Inspection - Housekeeping',
                filters={'housekeeping_task': task_doc.name},
                fields=['name', 'inspection_date', 'inspection_time', 'quality_score', 'issues_found'],
                limit_page_length=10
            )
            
            # ===== STOCK ENTRY DETAILS =====
            stock_entry_details = None
            if task_doc.stock_entry:
                try:
                    stock_entry_doc = frappe.get_doc('Stock Entry', task_doc.stock_entry)
                    stock_entry_details = {
                        'stock_entry_id': task_doc.stock_entry,
                        'posting_date': str(stock_entry_doc.posting_date),
                        'warehouse_from': stock_entry_doc.get('from_warehouse'),
                        'warehouse_to': stock_entry_doc.get('to_warehouse'),
                        'total_items': len(stock_entry_doc.items) if stock_entry_doc.items else 0
                    }
                except:
                    pass
            
            # ===== BUILD COMPLETE TASK RECORD =====
            task_detail = {
                'task_id': task_doc.name,
                'room_number': room_info[0] if room_info else 'N/A',
                'room_type': room_info[1] if room_info else 'N/A',
                'floor': room_info[2] if room_info else 'N/A',
                'employee': task_doc.employee,
                'employee_name': task_doc.employee_name,
                'task_type': task_doc.task_type,
                'status': task_doc.status,
                'priority': task_doc.get('priority', 'N/A'),
                'task_created': str(task_doc.creation),
                'task_modified': str(task_doc.modified),
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S') if start_time else 'Not Started',
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else 'Not Completed',
                'duration_minutes': duration_minutes,
                'duration_formatted': duration_formatted,
                'quality_passed': task_doc.quality_passed,
                'inspection_notes': task_doc.inspection_notes,
                'notes': task_doc.notes,
                
                # INVENTORY DATA
                'inventory_before': inventory_before,
                'inventory_before_summary': inventory_before_summary,
                'inventory_changes': inventory_changes,
                'inventory_changes_summary': inventory_changes_summary,
                
                'quality_inspections': quality_details,
                'stock_entry': stock_entry_details
            }
            
            task_details.append(task_detail)
        
        # Calculate summary statistics
        summary = calculate_inventory_summary_statistics(task_details)
        
        return {
            'status': 'success',
            'report_date_range': f"{start_date} to {end_date}",
            'total_tasks': len(task_details),
            'filters_applied': {
                'employee': employee,
                'task_type': task_type,
                'status': status
            },
            'tasks': task_details,
            'summary': summary
        }
    
    except Exception as e:
        frappe.log_error(f"Error generating housekeeping report with inventory: {str(e)}", "Housekeeping Report")
        return {
            'status': 'error',
            'message': f"Error generating report: {str(e)}"
        }


def calculate_inventory_summary_statistics(task_details):
    """
    Calculate comprehensive summary statistics including inventory metrics.
    """
    
    if not task_details:
        return None
    
    # Initialize counters
    completed_tasks = 0
    in_progress_tasks = 0
    pending_tasks = 0
    quality_passed_count = 0
    total_duration_minutes = 0
    
    total_inventory_items_before = 0
    total_inventory_changes = 0
    total_items_added = 0
    total_items_replaced = 0
    total_items_removed = 0
    
    task_type_count = {}
    employee_metrics = {}
    
    # Process each task
    for task in task_details:
        # Task status counts
        if task['status'] == 'Completed':
            completed_tasks += 1
        elif task['status'] == 'In Progress':
            in_progress_tasks += 1
        elif task['status'] == 'Pending':
            pending_tasks += 1
        
        # Quality metrics
        if task['quality_passed']:
            quality_passed_count += 1
        
        # Timing metrics
        if task['duration_minutes']:
            total_duration_minutes += task['duration_minutes']
        
        # Inventory metrics
        inv_before = task['inventory_before_summary']
        inv_changes = task['inventory_changes_summary']
        
        total_inventory_items_before += inv_before['total_items']
        total_inventory_changes += inv_changes['total_changes']
        total_items_added += inv_changes['items_added']
        total_items_replaced += inv_changes['items_replaced']
        total_items_removed += inv_changes['items_removed']
        
        # Task type distribution
        task_type = task['task_type']
        task_type_count[task_type] = task_type_count.get(task_type, 0) + 1
        
        # Employee metrics
        employee = task['employee_name']
        if employee not in employee_metrics:
            employee_metrics[employee] = {
                'total_tasks': 0,
                'completed_tasks': 0,
                'total_duration': 0,
                'quality_passed': 0,
                'avg_duration': 0,
                'inventory_changes_handled': 0,
                'items_handled': 0
            }
        
        emp = employee_metrics[employee]
        emp['total_tasks'] += 1
        if task['status'] == 'Completed':
            emp['completed_tasks'] += 1
        if task['quality_passed']:
            emp['quality_passed'] += 1
        if task['duration_minutes']:
            emp['total_duration'] += task['duration_minutes']
        emp['inventory_changes_handled'] += task['inventory_changes_summary']['total_changes']
        emp['items_handled'] += task['inventory_before_summary']['total_items']
    
    # Calculate averages
    for employee in employee_metrics:
        emp = employee_metrics[employee]
        if emp['total_tasks'] > 0:
            emp['avg_duration'] = round(emp['total_duration'] / emp['total_tasks'], 2)
    
    # Build summary
    summary = {
        'task_statistics': {
            'total_tasks': len(task_details),
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'completion_rate': f"{round((completed_tasks / len(task_details) * 100), 2)}%" if task_details else "0%"
        },
        'quality_statistics': {
            'quality_passed': quality_passed_count,
            'quality_failed': len(task_details) - quality_passed_count,
            'quality_pass_rate': f"{round((quality_passed_count / len(task_details) * 100), 2)}%" if task_details else "0%"
        },
        'timing_statistics': {
            'total_duration_minutes': total_duration_minutes,
            'total_duration_hours': round(total_duration_minutes / 60, 2),
            'average_duration_per_task': f"{round(total_duration_minutes / len(task_details), 2)} min" if task_details else "0"
        },
        'inventory_statistics': {
            'total_items_tracked': total_inventory_items_before,
            'total_changes': total_inventory_changes,
            'avg_changes_per_task': f"{round(total_inventory_changes / len(task_details), 2)}" if task_details else "0",
            'items_added': total_items_added,
            'items_replaced': total_items_replaced,
            'items_removed': total_items_removed,
            'change_rate': f"{round((total_inventory_changes / total_inventory_items_before * 100), 2)}%" if total_inventory_items_before > 0 else "0%"
        },
        'task_type_distribution': task_type_count,
        'employee_productivity': employee_metrics
    }
    
    return summary


# Integration with Frappe Report
def execute(filters=None):
    """
    Execute report for Frappe's Report interface with full inventory details and DURATION columns.
    """
    
    if not filters:
        filters = {}
    
    start_date = filters.get('start_date', frappe.utils.today())
    end_date = filters.get('end_date', frappe.utils.today())
    employee = filters.get('employee')
    task_type = filters.get('task_type')
    status = filters.get('status')
    
    report_data = get_housekeeping_report_with_inventory(
        start_date=start_date,
        end_date=end_date,
        employee=employee,
        task_type=task_type,
        status=status
    )
    
    if report_data['status'] != 'success':
        return [], []
    
    # Define report columns - INCLUDES DURATION COLUMNS
    columns = [
        {
            'label': _('Task ID'),
            'fieldname': 'task_id',
            'fieldtype': 'Link',
            'options': 'Housekeeping Task',
            'width': 100
        },
        {
            'label': _('Room'),
            'fieldname': 'room_number',
            'fieldtype': 'Data',
            'width': 60
        },
        {
            'label': _('Room Type'),
            'fieldname': 'room_type',
            'fieldtype': 'Data',
            'width': 80
        },
        {
            'label': _('Employee'),
            'fieldname': 'employee_name',
            'fieldtype': 'Data',
            'width': 110
        },
        {
            'label': _('Task Type'),
            'fieldname': 'task_type',
            'fieldtype': 'Data',
            'width': 110
        },
        {
            'label': _('Status'),
            'fieldname': 'status',
            'fieldtype': 'Data',
            'width': 90
        },
        {
            'label': _('Start Time'),
            'fieldname': 'start_time',
            'fieldtype': 'Datetime',
            'width': 150
        },
        {
            'label': _('End Time'),
            'fieldname': 'end_time',
            'fieldtype': 'Datetime',
            'width': 150
        },
        {
            'label': _('Duration (min)'),
            'fieldname': 'duration_minutes',
            'fieldtype': 'Int',
            'width': 100
        },
        {
            'label': _('Duration'),
            'fieldname': 'duration_formatted',
            'fieldtype': 'Data',
            'width': 100
        },
        {
            'label': _('Items Before'),
            'fieldname': 'items_before_count',
            'fieldtype': 'Int',
            'width': 90
        },
        {
            'label': _('Changes'),
            'fieldname': 'total_changes',
            'fieldtype': 'Int',
            'width': 70
        },
        {
            'label': _('Added'),
            'fieldname': 'items_added',
            'fieldtype': 'Int',
            'width': 70
        },
        {
            'label': _('Replaced'),
            'fieldname': 'items_replaced',
            'fieldtype': 'Int',
            'width': 80
        },
        {
            'label': _('Removed'),
            'fieldname': 'items_removed',
            'fieldtype': 'Int',
            'width': 80
        },
        {
            'label': _('Quality Passed'),
            'fieldname': 'quality_passed',
            'fieldtype': 'Check',
            'width': 90
        },
        {
            'label': _('Notes'),
            'fieldname': 'notes',
            'fieldtype': 'Text',
            'width': 150
        }
    ]
    
    # Format data rows
    data = []
    for task in report_data['tasks']:
        inv_before = task['inventory_before_summary']
        inv_changes = task['inventory_changes_summary']
        
        data.append({
            'task_id': task['task_id'],
            'room_number': task['room_number'],
            'room_type': task['room_type'],
            'employee_name': task['employee_name'],
            'task_type': task['task_type'],
            'status': task['status'],
            'start_time': task['start_time'],
            'end_time': task['end_time'],
            'duration_minutes': task['duration_minutes'],
            'duration_formatted': task['duration_formatted'],
            'items_before_count': inv_before['total_items'],
            'total_changes': inv_changes['total_changes'],
            'items_added': inv_changes['items_added'],
            'items_replaced': inv_changes['items_replaced'],
            'items_removed': inv_changes['items_removed'],
            'quality_passed': task['quality_passed'],
            'notes': task['notes']
        })
    
    return columns, data