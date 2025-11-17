# """
# Housekeeping Task with Room Inventory and Stock Management Integration
# FIXED VERSION - Uses minimal required Stock Entry fields only
# """

# import frappe
# from frappe.model.document import Document
# from frappe import utils
# from frappe.utils import now, nowtime, today, getdate


# class HousekeepingTask(Document):
#     """
#     Housekeeping Task with integrated room inventory tracking and 
#     automatic stock entry generation for material issues.
#     """
    
#     def validate(self):
#         """Validation on save"""
#         self.capture_initial_inventory()
#         self.validate_inventory_changes()

#     def on_update(self):
#         # Update room to clear if status is 'Completed'
#         if self.status == "Completed":
#             room = frappe.get_doc("Hotel Room", self.room)
#             room.housekeeping_status = "Clean"
#             room.save()
#             frappe.publish_realtime('rhohotel_front_desk_update')
    
#     # def before_submit(self):
#     #     """Actions before submission"""
#     #     self.set_actual_times()
    
#     def on_submit(self):
#         """Actions after submission - create stock entry and update inventory"""
#         self.create_stock_entry()
#         self.update_room_inventory()
    
#     def capture_initial_inventory(self):
#         """
#         Capture room inventory snapshot when task is created/updated.
#         This is read-only and auto-populated when room is selected.
#         """
#         if not self.room:
#             return
        
#         # Only auto-load if not already loaded
#         if self.room_inventory_before:
#             return
        
#         try:
#             room = frappe.get_doc('Hotel Room', self.room)
            
#             # Check if room has inventory tracking
#             if not hasattr(room, 'room_inventory') or not room.room_inventory:
#                 return
            
#             # Clear and repopulate inventory snapshot
#             self.room_inventory_before = []
            
#             for inv_item in room.room_inventory:
#                 item_doc = frappe.get_doc('Item', inv_item.item)
#                 self.append('room_inventory_before', {
#                     'item': inv_item.item,
#                     'quantity_before': inv_item.quantity,
#                     'uom': item_doc.stock_uom
#                 })
        
#         except frappe.DoesNotExistError:
#             frappe.log_error(
#                 f"Room {self.room} not found when loading inventory",
#                 "Housekeeping Task"
#             )
#         except Exception as e:
#             frappe.log_error(f"Error loading room inventory: {str(e)}", "Housekeeping Task")
    
#     def validate_inventory_changes(self):
#         """
#         Comprehensive validation for inventory changes.
#         Throws errors for critical issues, warnings for non-critical issues.
#         """
#         if not self.room_inventory_changes:
#             return
        
#         # Get warehouse first (needed for stock validation)
#         warehouse = frappe.db.get_single_value("Hotel Settings", "consumable_warehouse")
#         if not warehouse:
#             frappe.throw("Warehouse is not configured in Hotel Settings")
        
#         if not frappe.db.exists("Warehouse", warehouse):
#             frappe.throw(f"Warehouse '{warehouse}' does not exist in system")
        
#         # Store validation errors to show all at once
#         validation_errors = []
#         validation_warnings = []
        
#         for idx, change in enumerate(self.room_inventory_changes, 1):
#             # ===== CRITICAL VALIDATIONS (Block submission) =====
            
#             # 1. Item code required
#             if not change.item:
#                 validation_errors.append(f"Row {idx}: Item code is required")
#                 continue
            
#             # 2. Item must exist
#             if not frappe.db.exists('Item', change.item):
#                 validation_errors.append(f"Row {idx}: Item '{change.item}' does not exist")
#                 continue
            
#             # 3. Quantity must be positive
#             if not change.quantity_changed or change.quantity_changed <= 0:
#                 validation_errors.append(f"Row {idx}: Quantity must be greater than 0")
#                 continue
            
#             # 4. Change type is required
#             if not change.change_type or change.change_type not in ["Added", "Replaced", "Removed"]:
#                 validation_errors.append(f"Row {idx}: Invalid change type '{change.change_type}'")
#                 continue
            
#             # Get item details
#             item = frappe.get_doc('Item', change.item)
            
#             # ===== WAREHOUSE VALIDATION (Critical for Added/Replaced) =====
            
#             if change.change_type in ["Added", "Replaced"]:
#                 # For Added/Replaced, we MUST have stock available
#                 available_qty = frappe.db.get_value(
#                     "Stock Ledger Entry",
#                     {
#                         "warehouse": warehouse, 
#                         "item_code": change.item,
#                         "is_cancelled": 0
#                     },
#                     "sum(actual_qty)",
#                 ) or 0
                
#                 if available_qty <= 0:
#                     validation_errors.append(
#                         f"Row {idx}: Item '{change.item}' has 0 quantity in warehouse '{warehouse}'. "
#                         f"Cannot {change.change_type.lower()} items that don't exist in stock."
#                     )
#                 elif available_qty < change.quantity_changed:
#                     validation_errors.append(
#                         f"Row {idx}: Insufficient stock for '{change.item}'. "
#                         f"Available: {available_qty}, Requested: {change.quantity_changed}"
#                     )
            
#             # ===== NON-CRITICAL VALIDATIONS (Warnings) =====
            
#             # 5. Item is not stock item (warning)
#             if not item.is_stock_item:
#                 validation_warnings.append(
#                     f"Row {idx}: '{change.item}' is not marked as a stock item. "
#                     "Stock tracking may not work as expected."
#                 )
            
#             # 6. Check if item is disabled (warning)
#             if item.disabled:
#                 validation_warnings.append(
#                     f"Row {idx}: Item '{change.item}' is disabled. "
#                     "Consider using an active item."
#                 )
            
#             # 7. Set UOM from item if not set
#             if not change.uom:
#                 change.uom = item.stock_uom
        
#         # ===== THROW ALL VALIDATION ERRORS AT ONCE =====
#         if validation_errors:
#             error_message = "Cannot submit Housekeeping Task due to the following errors:\n\n"
#             error_message += "\n".join([f"❌ {err}" for err in validation_errors])
#             frappe.throw(error_message, title="Validation Failed")
        
#         # ===== SHOW WARNINGS (but allow submission) =====
#         if validation_warnings:
#             warning_message = "Warnings (task will still be submitted):\n\n"
#             warning_message += "\n".join([f"⚠️ {warn}" for warn in validation_warnings])
#             frappe.msgprint(warning_message, indicator="yellow", title="Validation Warnings")
    
#     # def set_actual_times(self):
#     #     """
#     #     Set actual start/end times if not already set.
#     #     Used for audit trail and stock entry posting time.
#     #     """
#     #     current_time = now()
        
#     #     if not self.actual_start_time:
#     #         self.actual_start_time = current_time
        
#     #     if not self.actual_end_time:
#     #         self.actual_end_time = current_time
    
#     def create_stock_entry(self):
#         """
#         Create Material Issue Stock Entry from inventory changes.
        
#         COMPULSORY FIELDS ONLY:
#         - stock_entry_type: Required by Stock Entry DocType
#         - company: Required by Stock Entry DocType (get from system default)
#         - from_warehouse: Source warehouse (where items come from)
#         - items: Table with item_code, qty
        
#         Notes:
#         - Gets company from system default (frappe.defaults.get_default("company"))
#         - Leaves posting_date, posting_time blank (auto-filled by Frappe)
#         - Leaves to_warehouse blank (indicates consumption/issue)
#         - Only includes Added/Replaced items (Removed items skipped)
#         """
        
#         if not self.room_inventory_changes:
#             return
        
#         # Get warehouse from task
#         warehouse = frappe.db.get_single_value("Hotel Settings", "consumable_warehouse")
#         if not warehouse:
#             frappe.throw("Warehouse is required to create stock entry")
        
#         # Validate warehouse exists
#         if not frappe.db.exists("Warehouse", warehouse):
#             frappe.throw(f"Warehouse '{warehouse}' does not exist")
        
#         # Filter items to issue (only Added or Replaced)
#         items_to_issue = []
        
#         for change in self.room_inventory_changes:
#             # Only process Added and Replaced items
#             if change.change_type in ["Added", "Replaced"]:
#                 item_code = change.item
                
#                 if not item_code:
#                     frappe.throw(f"Row {change.idx}: Item is required")
                
#                 if not change.quantity_changed or change.quantity_changed <= 0:
#                     frappe.throw(f"Row {change.idx}: Quantity must be greater than 0")
                
#                 # VALIDATE: Item exists
#                 item_doc = frappe.db.get_value(
#                     "Item",
#                     item_code,
#                     ["is_stock_item", "stock_uom"],
#                     as_dict=True
#                 )
                
#                 if not item_doc:
#                     frappe.throw(f"Item '{item_code}' does not exist")
                
#                 if not item_doc.get("is_stock_item"):
#                     frappe.msgprint(
#                         f"Row {change.idx}: Warning - '{item_code}' is not a stock item.",
#                         indicator="yellow",
#                         title="Non-Stock Item"
#                     )
                
#                 # VALIDATE: Check available quantity
#                 available_qty = frappe.db.get_value(
#                     "Stock Ledger Entry",
#                     {
#                         "warehouse": warehouse, 
#                         "item_code": item_code,
#                         "is_cancelled": 0
#                     },
#                     "sum(actual_qty)",
#                 ) or 0
                
#                 if available_qty < change.quantity_changed:
#                     frappe.msgprint(
#                         f"Row {change.idx}: Only {available_qty} units available, issuing {change.quantity_changed}.",
#                         indicator="yellow",
#                         title="Low Stock"
#                     )
                
#                 items_to_issue.append({
#                     "item_code": item_code,
#                     "qty": change.quantity_changed,
#                     "uom": item_doc.get("stock_uom", "Nos")
#                 })
        
#         if not items_to_issue:
#             frappe.msgprint("No items to issue (only Added/Replaced items are included)")
#             return
        
#         try:
#             # Get Stock Entry Type - Material Issue
#             stock_entry_type = frappe.db.get_value(
#                 "Stock Entry Type",
#                 {"purpose": "Material Issue"},
#                 "name"
#             )
            
#             if not stock_entry_type:
#                 frappe.throw(
#                     "Stock Entry Type 'Material Issue' does not exist. "
#                     "Please create it first."
#                 )
            
#             # ===== CREATE STOCK ENTRY WITH ONLY COMPULSORY FIELDS =====
#             stock_entry = frappe.new_doc("Stock Entry")
            
#             # COMPULSORY FIELDS
#             stock_entry.stock_entry_type = stock_entry_type
#             stock_entry.company = frappe.db.get_default("company")  # Get from system
#             stock_entry.from_warehouse = warehouse
            
#             # Optional but useful for reference
#             stock_entry.remarks = f"Housekeeping Task: {self.name} - Room {self.room}"
            
#             # NOTE: NOT setting these - let Frappe auto-fill:
#             # - posting_date (defaults to Today)
#             # - posting_time (defaults to Now)
#             # - to_warehouse (left blank for consumption/issue)
            
#             # ===== ADD ITEMS =====
#             for item in items_to_issue:
#                 stock_entry.append("items", {
#                     "item_code": item["item_code"],
#                     "qty": item["qty"],
#                     "s_warehouse": warehouse,
#                     "uom": item["uom"],
#                 })
            
#             # ===== SAVE AND SUBMIT =====
#             stock_entry.insert(ignore_permissions=True)
#             stock_entry.submit()
            
#             # Link stock entry back to task
#             self.stock_entry = stock_entry.name
#             frappe.db.set_value("Housekeeping Task", self.name, "stock_entry", stock_entry.name)
            
#             frappe.msgprint(
#                 f"✓ Stock Entry {stock_entry.name} created with {len(items_to_issue)} item(s)",
#                 indicator="green",
#                 title="Stock Entry Created"
#             )
            
#         except frappe.ValidationError as ve:
#             frappe.log_error(frappe.get_traceback(), "Stock Entry Validation Error")
#             frappe.msgprint(
#                 f"Validation error: {str(ve)}. Please create manually.",
#                 indicator="yellow",
#                 title="Stock Entry Error"
#             )
#         except Exception as e:
#             frappe.log_error(frappe.get_traceback(), "Stock Entry Creation Error")
#             frappe.msgprint(
#                 f"Error: {str(e)}. Please create manually.",
#                 indicator="yellow",
#                 title="Stock Entry Error"
#             )

    
#     def update_room_inventory(self):
#         """
#         Update room inventory after housekeeping task completion.
        
#         This updates the Hotel Room's inventory table based on the
#         changes recorded in this task:
#         - Added items are added to room inventory
#         - Replaced items replace existing quantities
#         - Removed items are decreased from inventory
#         """
#         try:
#             room = frappe.get_doc('Hotel Room', self.room)
            
#             if not hasattr(room, 'room_inventory'):
#                 frappe.msgprint(
#                     f"Room {self.room} does not have inventory tracking",
#                     indicator='yellow',
#                     title="Room Update Warning"
#                 )
#                 return
            
#             # Process each inventory change
#             for change in self.room_inventory_changes:
#                 # Find existing item in room inventory
#                 inv_item = None
#                 for item in room.room_inventory:
#                     if item.item == change.item:
#                         inv_item = item
#                         break
                
#                 if change.change_type == 'Added':
#                     # Add to existing or create new
#                     if inv_item:
#                         inv_item.quantity += change.quantity_changed
#                     else:
#                         room.append('room_inventory', {
#                             'item': change.item,
#                             'quantity': change.quantity_changed
#                         })
                
#                 elif change.change_type == 'Replaced':
#                     # Set to new quantity
#                     if inv_item:
#                         inv_item.quantity = change.quantity_changed
#                     else:
#                         room.append('room_inventory', {
#                             'item': change.item,
#                             'quantity': change.quantity_changed
#                         })
                
#                 elif change.change_type == 'Removed':
#                     # Decrease quantity
#                     if inv_item:
#                         inv_item.quantity = max(0, inv_item.quantity - change.quantity_changed)
            
#             # Save room with updated inventory
#             room.save(ignore_permissions=True)
            
#             frappe.msgprint(
#                 f"Room inventory updated successfully",
#                 indicator='green',
#                 title="Room Updated"
#             )
        
#         except Exception as e:
#             frappe.log_error(
#                 f"Error updating room inventory: {str(e)}",
#                 "Housekeeping Task - Room Update"
#             )
#             frappe.msgprint(
#                 f"Warning: Could not update room inventory: {str(e)}",
#                 indicator='yellow',
#                 title="Room Update Error"
#             )


# @frappe.whitelist()
# def load_room_inventory(room):
#     """
#     Fetch current room inventory to populate room_inventory_before table.
#     Called from client-side when room is selected.
    
#     Returns:
#         List of inventory items in the room
#     """
#     if not room:
#         return []
    
#     try:
#         room_doc = frappe.get_doc('Hotel Room', room)
#         inventory = []
        
#         if hasattr(room_doc, 'room_inventory') and room_doc.room_inventory:
#             for item in room_doc.room_inventory:
#                 item_doc = frappe.get_doc('Item', item.item)
#                 inventory.append({
#                     'item': item.item,
#                     'quantity_before': item.quantity,
#                     'uom': item_doc.stock_uom
#                 })
        
#         return inventory
    
#     except frappe.DoesNotExistError:
#         frappe.throw(f"Room '{room}' not found")
#     except Exception as e:
#         frappe.log_error(f"Error loading room inventory: {str(e)}", "Load Room Inventory")
#         frappe.throw(f"Error loading inventory: {str(e)}")


# @frappe.whitelist()
# def get_item_details(item_code):
#     """
#     Fetch item details (UOM, valuation rate, etc.)
#     Called from client-side when adding inventory changes.
    
#     Args:
#         item_code: Item code to fetch details for
    
#     Returns:
#         Dictionary with item details
#     """
#     try:
#         item = frappe.get_doc('Item', item_code)
#         return {
#             'uom': item.stock_uom,
#             'is_stock_item': item.is_stock_item
#         }
#     except frappe.DoesNotExistError:
#         frappe.throw(f"Item '{item_code}' not found")
#     except Exception as e:
#         frappe.log_error(f"Error fetching item details: {str(e)}", "Get Item Details")
#         frappe.throw(f"Error fetching item details: {str(e)}")







"""
Housekeeping Task with Room Inventory and Stock Management Integration
FIXED VERSION - Prevents duplicate inventory loading
"""

import frappe
from frappe.model.document import Document
from frappe import utils
from frappe.utils import now, nowtime, today, getdate


class HousekeepingTask(Document):
    """
    Housekeeping Task with integrated room inventory tracking and 
    automatic stock entry generation for material issues.
    """
    
    def validate(self):
        """Validation on save"""
        # Don't auto-capture inventory here - only validate existing changes
        self.validate_inventory_changes()

    def on_update(self):
        # Update room to clear if status is 'Completed'
        if self.status == "Completed":
            room = frappe.get_doc("Hotel Room", self.room)
            room.housekeeping_status = "Clean"
            room.save()
            frappe.publish_realtime('rhohotel_front_desk_update')

            # if self.docstatus == 1:
            #     if not self.stock_entry:
            #         self.create_stock_entry()
            #         self.update_room_inventory()

            #         frappe.msgprint(
            #             msg=f"✅ Housekeeping Task '{self.name}' for Room {self.room} is now completed. "
            #                 f"Stock and inventory updated automatically.",
            #             title="Task Completed",
            #             indicator="green"
            #         )
    def on_update_after_submit(self):
        # Run only when status is changed to 'Completed' after submission
        if self.status == "Completed" and not self.stock_entry:
            # Update room housekeeping status
            room = frappe.get_doc("Hotel Room", self.room)
            room.housekeeping_status = "Clean"
            room.save(ignore_permissions=True)
            frappe.publish_realtime('rhohotel_front_desk_update')

            # Create stock entry and update inventory
            self.create_stock_entry()
            self.update_room_inventory()

            frappe.msgprint(
                msg=f"✅ Housekeeping Task '{self.name}' for Room {self.room}' is now completed. "
                    f"Stock and inventory updated automatically.",
                title="Task Completed",
                indicator="green"
            )

    def before_save(self):
    # Prevent any modification if already completed
        if self.docstatus == 1 and self.status == "Completed":
            frappe.throw("This housekeeping task has been completed and can no longer be modified.")


    
    # def on_submit(self):
    #     """Actions after submission - create stock entry and update inventory"""
    #     self.create_stock_entry()
    #     self.update_room_inventory()
    
    def validate_inventory_changes(self):
        """
        Comprehensive validation for inventory changes.
        Throws errors for critical issues, warnings for non-critical issues.
        """
        if not self.room_inventory_changes:
            return
        
        # Get warehouse first (needed for stock validation)
        warehouse = frappe.db.get_single_value("Hotel Settings", "consumable_warehouse")
        if not warehouse:
            frappe.throw("Warehouse is not configured in Hotel Settings")
        
        if not frappe.db.exists("Warehouse", warehouse):
            frappe.throw(f"Warehouse '{warehouse}' does not exist in system")
        
        # Store validation errors to show all at once
        validation_errors = []
        validation_warnings = []
        
        for idx, change in enumerate(self.room_inventory_changes, 1):
            # ===== CRITICAL VALIDATIONS (Block submission) =====
            
            # 1. Item code required
            if not change.item:
                validation_errors.append(f"Row {idx}: Item code is required")
                continue
            
            # 2. Item must exist
            if not frappe.db.exists('Item', change.item):
                validation_errors.append(f"Row {idx}: Item '{change.item}' does not exist")
                continue
            
            # 3. Quantity must be positive
            if not change.quantity_changed or change.quantity_changed <= 0:
                validation_errors.append(f"Row {idx}: Quantity must be greater than 0")
                continue
            
            # 4. Change type is required
            if not change.change_type or change.change_type not in ["Added", "Replaced", "Removed"]:
                validation_errors.append(f"Row {idx}: Invalid change type '{change.change_type}'")
                continue
            
            # Get item details
            item = frappe.get_doc('Item', change.item)
            
            # ===== WAREHOUSE VALIDATION (Critical for Added/Replaced) =====
            
            if change.change_type in ["Added", "Replaced"]:
                # For Added/Replaced, we MUST have stock available
                available_qty = frappe.db.get_value(
                    "Stock Ledger Entry",
                    {
                        "warehouse": warehouse, 
                        "item_code": change.item,
                        "is_cancelled": 0
                    },
                    "sum(actual_qty)",
                ) or 0
                
                if available_qty <= 0:
                    validation_errors.append(
                        f"Row {idx}: Item '{change.item}' has 0 quantity in warehouse '{warehouse}'. "
                        f"Cannot {change.change_type.lower()} items that don't exist in stock."
                    )
                elif available_qty < change.quantity_changed:
                    validation_errors.append(
                        f"Row {idx}: Insufficient stock for '{change.item}'. "
                        f"Available: {available_qty}, Requested: {change.quantity_changed}"
                    )
            
            # ===== NON-CRITICAL VALIDATIONS (Warnings) =====
            
            # 5. Item is not stock item (warning)
            if not item.is_stock_item:
                validation_warnings.append(
                    f"Row {idx}: '{change.item}' is not marked as a stock item. "
                    "Stock tracking may not work as expected."
                )
            
            # 6. Check if item is disabled (warning)
            if item.disabled:
                validation_warnings.append(
                    f"Row {idx}: Item '{change.item}' is disabled. "
                    "Consider using an active item."
                )
            
            # 7. Set UOM from item if not set
            if not change.uom:
                change.uom = item.stock_uom
        
        # ===== THROW ALL VALIDATION ERRORS AT ONCE =====
        if validation_errors:
            error_message = "Cannot submit Housekeeping Task due to the following errors:\n\n"
            error_message += "\n".join([f"❌ {err}" for err in validation_errors])
            frappe.throw(error_message, title="Validation Failed")
        
        # ===== SHOW WARNINGS (but allow submission) =====
        if validation_warnings:
            warning_message = "Warnings (task will still be submitted):\n\n"
            warning_message += "\n".join([f"⚠️ {warn}" for warn in validation_warnings])
            frappe.msgprint(warning_message, indicator="yellow", title="Validation Warnings")
    
    def create_stock_entry(self):
        """
        Create Material Issue Stock Entry from inventory changes.
        
        COMPULSORY FIELDS ONLY:
        - stock_entry_type: Required by Stock Entry DocType
        - company: Required by Stock Entry DocType (get from system default)
        - from_warehouse: Source warehouse (where items come from)
        - items: Table with item_code, qty
        
        Notes:
        - Gets company from system default (frappe.defaults.get_default("company"))
        - Leaves posting_date, posting_time blank (auto-filled by Frappe)
        - Leaves to_warehouse blank (indicates consumption/issue)
        - Only includes Added/Replaced items (Removed items skipped)
        """
        
        if not self.room_inventory_changes:
            return
        
        # Get warehouse from task
        warehouse = frappe.db.get_single_value("Hotel Settings", "consumable_warehouse")
        if not warehouse:
            frappe.throw("Warehouse is required to create stock entry")
        
        # Validate warehouse exists
        if not frappe.db.exists("Warehouse", warehouse):
            frappe.throw(f"Warehouse '{warehouse}' does not exist")
        
        # Filter items to issue (only Added or Replaced)
        items_to_issue = []
        
        for change in self.room_inventory_changes:
            # Only process Added and Replaced items
            if change.change_type in ["Added", "Replaced"]:
                item_code = change.item
                
                if not item_code:
                    frappe.throw(f"Row {change.idx}: Item is required")
                
                if not change.quantity_changed or change.quantity_changed <= 0:
                    frappe.throw(f"Row {change.idx}: Quantity must be greater than 0")
                
                # VALIDATE: Item exists
                item_doc = frappe.db.get_value(
                    "Item",
                    item_code,
                    ["is_stock_item", "stock_uom"],
                    as_dict=True
                )
                
                if not item_doc:
                    frappe.throw(f"Item '{item_code}' does not exist")
                
                if not item_doc.get("is_stock_item"):
                    frappe.msgprint(
                        f"Row {change.idx}: Warning - '{item_code}' is not a stock item.",
                        indicator="yellow",
                        title="Non-Stock Item"
                    )
                
                # VALIDATE: Check available quantity
                available_qty = frappe.db.get_value(
                    "Stock Ledger Entry",
                    {
                        "warehouse": warehouse, 
                        "item_code": item_code,
                        "is_cancelled": 0
                    },
                    "sum(actual_qty)",
                ) or 0
                
                if available_qty < change.quantity_changed:
                    frappe.msgprint(
                        f"Row {change.idx}: Only {available_qty} units available, issuing {change.quantity_changed}.",
                        indicator="yellow",
                        title="Low Stock"
                    )
                
                items_to_issue.append({
                    "item_code": item_code,
                    "qty": change.quantity_changed,
                    "uom": item_doc.get("stock_uom", "Nos")
                })
        
        if not items_to_issue:
            frappe.msgprint("No items to issue (only Added/Replaced items are included)")
            return
        
        try:
            # Get Stock Entry Type - Material Issue
            stock_entry_type = frappe.db.get_value(
                "Stock Entry Type",
                {"purpose": "Material Issue"},
                "name"
            )
            
            if not stock_entry_type:
                frappe.throw(
                    "Stock Entry Type 'Material Issue' does not exist. "
                    "Please create it first."
                )
            
            # ===== CREATE STOCK ENTRY WITH ONLY COMPULSORY FIELDS =====
            stock_entry = frappe.new_doc("Stock Entry")
            
            # COMPULSORY FIELDS
            stock_entry.stock_entry_type = stock_entry_type
            stock_entry.company = frappe.db.get_default("company")  # Get from system
            stock_entry.from_warehouse = warehouse
            
            # Optional but useful for reference
            stock_entry.remarks = f"Housekeeping Task: {self.name} - Room {self.room}"
            
            # NOTE: NOT setting these - let Frappe auto-fill:
            # - posting_date (defaults to Today)
            # - posting_time (defaults to Now)
            # - to_warehouse (left blank for consumption/issue)
            
            # ===== ADD ITEMS =====
            for item in items_to_issue:
                stock_entry.append("items", {
                    "item_code": item["item_code"],
                    "qty": item["qty"],
                    "s_warehouse": warehouse,
                    "uom": item["uom"],
                })
            
            # ===== SAVE AND SUBMIT =====
            stock_entry.insert(ignore_permissions=True)
            stock_entry.submit()
            
            # Link stock entry back to task
            self.stock_entry = stock_entry.name
            frappe.db.set_value("Housekeeping Task", self.name, "stock_entry", stock_entry.name)
            
            frappe.msgprint(
                f"✓ Stock Entry {stock_entry.name} created with {len(items_to_issue)} item(s)",
                indicator="green",
                title="Stock Entry Created"
            )
            
        except frappe.ValidationError as ve:
            frappe.log_error(frappe.get_traceback(), "Stock Entry Validation Error")
            frappe.msgprint(
                f"Validation error: {str(ve)}. Please create manually.",
                indicator="yellow",
                title="Stock Entry Error"
            )
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Stock Entry Creation Error")
            frappe.msgprint(
                f"Error: {str(e)}. Please create manually.",
                indicator="yellow",
                title="Stock Entry Error"
            )

    
    def update_room_inventory(self):
        """
        Update room inventory after housekeeping task completion.
        
        This updates the Hotel Room's inventory table based on the
        changes recorded in this task:
        - Added items are added to room inventory
        - Replaced items replace existing quantities
        - Removed items are decreased from inventory
        """
        try:
            room = frappe.get_doc("Hotel Room", self.room)
            
            if not hasattr(room, 'room_inventory'):
                frappe.msgprint(
                    f"Room {self.room} does not have inventory tracking",
                    indicator='yellow',
                    title="Room Update Warning"
                )
                return
            
            # Process each inventory change
            for change in self.room_inventory_changes:
                # Find existing item in room inventory
                inv_item = None
                for item in room.room_inventory:
                    if item.item == change.item:
                        inv_item = item
                        break
                
                if change.change_type == 'Added':
                    # Add to existing or create new
                    if inv_item:
                        inv_item.quantity += change.quantity_changed
                    else:
                        room.append('room_inventory', {
                            'item': change.item,
                            'quantity': change.quantity_changed
                        })
                
                elif change.change_type == 'Replaced':
                    # Set to new quantity
                    if inv_item:
                        inv_item.quantity = change.quantity_changed
                    else:
                        room.append('room_inventory', {
                            'item': change.item,
                            'quantity': change.quantity_changed
                        })
                
                elif change.change_type == 'Removed':
                    # Decrease quantity
                    if inv_item:
                        inv_item.quantity = max(0, inv_item.quantity - change.quantity_changed)
            
            # Save room with updated inventory
            room.save(ignore_permissions=True)
            
            frappe.msgprint(
                f"Room inventory updated successfully",
                indicator='green',
                title="Room Updated"
            )
        
        except Exception as e:
            frappe.log_error(
                f"Error updating room inventory: {str(e)}",
                "Housekeeping Task - Room Update"
            )
            frappe.msgprint(
                f"Warning: Could not update room inventory: {str(e)}",
                indicator='yellow',
                title="Room Update Error"
            )


@frappe.whitelist()
def load_room_inventory(room):
    """
    Fetch current room inventory to populate room_inventory_before table.
    Called from client-side when room is selected.
    
    Returns:
        List of inventory items in the room
    """
    if not room:
        return []
    
    try:
        room_doc = frappe.get_doc('Hotel Room', room)
        inventory = []
        
        if hasattr(room_doc, 'room_inventory') and room_doc.room_inventory:
            for item in room_doc.room_inventory:
                item_doc = frappe.get_doc('Item', item.item)
                inventory.append({
                    'item': item.item,
                    'quantity_before': item.quantity,
                    'uom': item_doc.stock_uom
                })
        
        return inventory
    
    except frappe.DoesNotExistError:
        frappe.throw(f"Room '{room}' not found")
    except Exception as e:
        frappe.log_error(f"Error loading room inventory: {str(e)}", "Load Room Inventory")
        frappe.throw(f"Error loading inventory: {str(e)}")


@frappe.whitelist()
def get_item_details(item_code):
    """
    Fetch item details (UOM, valuation rate, etc.)
    Called from client-side when adding inventory changes.
    
    Args:
        item_code: Item code to fetch details for
    
    Returns:
        Dictionary with item details
    """
    try:
        item = frappe.get_doc('Item', item_code)
        return {
            'uom': item.stock_uom,
            'is_stock_item': item.is_stock_item
        }
    except frappe.DoesNotExistError:
        frappe.throw(f"Item '{item_code}' not found")
    except Exception as e:
        frappe.log_error(f"Error fetching item details: {str(e)}", "Get Item Details")
        frappe.throw(f"Error fetching item details: {str(e)}")











#checklist items




# ============================================================
# ADD THESE METHODS TO YOUR EXISTING housekeeping_task.py
# ============================================================

# Add these to the HousekeepingTask class (after your existing methods):

    def validate_all_mandatory_items_completed(self):
        """Before submit, check all mandatory items are completed"""
        if not self.checklist_items:
            frappe.throw(_("Cannot submit task without checklist items"))
        
        incomplete_mandatory = []
        
        for item in self.checklist_items:
            if item.is_mandatory and not item.is_completed:
                incomplete_mandatory.append(item.item_description)
        
        if incomplete_mandatory:
            frappe.throw(
                _("Cannot submit. The following mandatory items are not completed:<br><br>{0}").format(
                    "<br>".join(["• " + item for item in incomplete_mandatory])
                ),
                title=_("Incomplete Mandatory Items")
            )
    
    def validate_status_completed(self):
        """Status must be Completed before submitting"""
        if self.status != "Completed":
            frappe.throw(_("Status must be 'Completed' before submitting"))


# Add these standalone @frappe.whitelist() methods at the end of the file:

@frappe.whitelist()
def get_template_items(template):
    """Fetch checklist items from a template"""
    if not template:
        return []
    
    # Validate template exists
    if not frappe.db.exists("Task Checklist Template", template):
        frappe.throw(_("Template {0} does not exist").format(template))
    
    # Check if template is active
    is_active = frappe.db.get_value("Task Checklist Template", template, "is_active")
    if not is_active:
        frappe.msgprint(
            _("Warning: Template '{0}' is not active").format(template),
            indicator='orange'
        )
    
    items = frappe.get_all(
        "Checklist Template Item",
        filters={"parent": template},
        fields=["item_description", "is_mandatory", "sequence", "estimated_time"],
        order_by="sequence asc"
    )
    
    if not items:
        frappe.msgprint(
            _("Template '{0}' has no checklist items").format(template),
            indicator='orange'
        )
    
    return items


@frappe.whitelist()
def get_suggested_template(room, task_type):
    """Suggest a template based on room type and task type"""
    if not room or not task_type:
        return None
    
    try:
        # Validate room exists
        if not frappe.db.exists("Hotel Room", room):
            frappe.throw(_("Room {0} does not exist").format(room))
        
        # Get room's hotel room type
        room_doc = frappe.get_doc("Hotel Room", room)
        room_type = room_doc.hotel_room_type
        
        if not room_type:
            frappe.msgprint(
                _("Room {0} does not have a room type assigned").format(room),
                indicator='orange'
            )
            # Try to find template without room type filter
            return get_template_without_room_type(task_type)
        
        # Find matching template with exact room type and task type
        templates = frappe.get_all(
            "Task Checklist Template",
            filters={
                "room_typ": room_type,
                "task_type": task_type,
                "is_active": 1
            },
            fields=["name", "template_name"],
            limit=1
        )
        
        if templates:
            return templates[0].name
        
        # If no exact match, try without room type (generic template)
        frappe.msgprint(
            _("No specific template found for room type '{0}'. Trying generic template.").format(room_type),
            indicator='blue'
        )
        return get_template_without_room_type(task_type)
        
    except Exception as e:
        frappe.log_error(f"Error suggesting template: {str(e)}")
        return None


def get_template_without_room_type(task_type):
    """Get generic template without room type filter"""
    templates = frappe.get_all(
        "Task Checklist Template",
        filters={
            "task_type": task_type,
            "is_active": 1,
            "room_typ": ["in", ["", None]]  # Templates without specific room type
        },
        fields=["name"],
        limit=1
    )
    
    if templates:
        return templates[0].name
    
    # If still nothing, get any active template with matching task type
    templates = frappe.get_all(
        "Task Checklist Template",
        filters={
            "task_type": task_type,
            "is_active": 1
        },
        fields=["name"],
        limit=1
    )
    
    if templates:
        return templates[0].name
    
    return None