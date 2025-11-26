import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime
from frappe.utils import strip_html_tags
        


class MaintenanceRequest(Document):

    def validate(self):
        self.validate_no_duplicate_pending()
        self.validate_required_fields()
        self.validate_request_type()
        self.validate_dates()

    def after_insert(self):
        """Run immediately after creation"""
        self.update_room_maintenance_flag()
        # Create Asset Repair only if approved upon creation
        if self.is_approved_for_repair():
            self.create_asset_repair()
    
    def on_update(self):
        """Triggered on every update"""
        self.set_approval_time()
        self.update_room_maintenance_flag()

        # Only create Asset Repair when it becomes approved and none exists yet
        if self.is_approved_for_repair() and not self.asset_repair:
            self.create_asset_repair()

    # ---------------- VALIDATIONS ----------------
    def validate_no_duplicate_pending(self):
        existing = frappe.db.exists({
            "doctype": "Maintenance Request",
            "asset": self.asset,
            "room": self.room,
            "status": "Pending",
            "name": ["!=", self.name]
        })
        if existing:
            frappe.throw(f"A pending Maintenance Request already exists for this asset in this room ({existing}).")

    def validate_required_fields(self):
        required_fields = ["asset", "room", "issue_type", "request_type", "reported_by", "reported_at"]
        for field in required_fields:
            if not self.get(field):
                frappe.throw(f"{field.replace('_', ' ').title()} is required.")

    def validate_request_type(self):
        if self.request_type == "Repair" and getattr(self, "asset_maintenance", None):
            frappe.throw("Cannot select Asset Maintenance for a Repair request.")
        if self.request_type == "Maintenance" and getattr(self, "asset_repair", None):
            frappe.throw("Cannot select Asset Repair for a Maintenance request.")
    
    def validate_dates(self):
        if self.reported_at:
            reported_at_dt = get_datetime(self.reported_at)
            if reported_at_dt > now_datetime():
                frappe.throw("Reported At cannot be in the future.")

    # ---------------- CORE LOGIC ----------------
    def is_approved_for_repair(self):
        """Helper to check if MR should create an Asset Repair"""
        return (
            self.request_type == "Repair"
            and self.status == "Pending"
            and bool(self.approved)
        )

    def create_asset_repair(self):
        """Create linked Asset Repair record"""
        clean_description = strip_html_tags(self.issue_description) if self.issue_description else ""
        asset_repair_doc = frappe.get_doc({
            "doctype": "Asset Repair",
            "asset": self.asset,
            "failure_date": self.reported_at,
            "repair_status": "Pending",
            "description": clean_description,
            "naming_series": "ACC-ASR-.YYYY.-",
            "maintenance_request": self.name
        })
        asset_repair_doc.insert(ignore_permissions=True)

        # Link to Maintenance Request
        self.db_set('asset_repair', asset_repair_doc.name)
        frappe.db.commit()

    def update_room_maintenance_flag(self):
        """Update Hotel Room maintenance flag based on approval, MR status, and Asset Repair status"""
        if not self.room:
            return

        # Flag should be ON only if:
        # 1. MR is approved AND
        # 2. MR status is Pending AND
        # 3. (No Asset Repair linked OR Asset Repair is still Pending)
        
        flag_should_be_on = False
        
        if self.approved and self.status == "Pending":
            # Check if there's a linked Asset Repair
            if self.asset_repair:
                # Get the Asset Repair status
                asset_repair_status = frappe.db.get_value(
                    "Asset Repair",
                    self.asset_repair,
                    "repair_status"
                )
                # Only turn ON flag if Asset Repair is Pending
                flag_should_be_on = (asset_repair_status == "Pending")
            else:
                # No Asset Repair yet, but MR is approved and pending
                flag_should_be_on = True
        
        new_flag = 1 if flag_should_be_on else 0
        frappe.db.set_value("Hotel Room", self.room, "maintenance_flag", new_flag)
        frappe.db.commit()

    def before_delete(self):
        """Delete linked Asset Repairs when MR is deleted"""
        if self.asset_repair:
            try:
                all_versions = frappe.db.get_list(
                    "Asset Repair",
                    filters={"name": ["like", f"{self.asset_repair}%"]},
                    fields=["name"]
                )
                for ar in all_versions:
                    frappe.db.sql("DELETE FROM `tabAsset Repair` WHERE name = %s", ar.name)
                frappe.db.commit()
            except Exception as e:
                frappe.logger().error(f"Error deleting Asset Repairs: {e}")
                pass

    def set_approval_time(self):
        """Set approval_time only when approved is checked"""
        if self.approved and not self.approval_time:
            self.approval_time = now_datetime()
        elif not self.approved and self.approval_time:
            # Optional: clear it when unapproved
            self.approval_time = None

    # @frappe.whitelist()
    # def approve_request(self):
    #     """Custom method to approve MR by authorized roles only"""
    #     # if 'System Manager' not in frappe.get_roles():
    #     #     frappe.throw("You do not have permission to approve this request.")
        
    #     self.db_set('approved', 1)
    #     self.db_set('approval_time', now_datetime())
        
    #     # Update Hotel Room maintenance flag
    #     self.update_room_maintenance_flag()

    @frappe.whitelist()
    def approve_request(self):
        """Custom method to approve MR by authorized roles only"""
        user_roles = frappe.get_roles()
        if 'System Manager' not in user_roles and 'Hotel Manager' not in user_roles:
            frappe.error_log("You do not have permission to approve this request.")
        
        self.approved = 1
        self.approval_time = now_datetime()
        
        # Update maintenance flag
        self.update_room_maintenance_flag()
        
        # Create Asset Repair if conditions are met
        if self.is_approved_for_repair() and not self.asset_repair:
            self.create_asset_repair()
        
        # Save changes
        self.db_set('approved', 1)
        self.db_set('approval_time', self.approval_time)
        
        frappe.msgprint("Maintenance Request approved successfully")