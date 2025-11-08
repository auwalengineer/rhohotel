import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

class MaintenanceRequest(Document):

    def validate(self):
        self.validate_no_duplicate_pending()
        self.validate_required_fields()
        self.validate_request_type()
        self.validate_dates()

    def after_insert(self):
        if self.request_type == "Repair" and self.status == "Pending":
            self.create_asset_repair()

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

    def create_asset_repair(self):
        asset_repair_doc = frappe.get_doc({
            "doctype": "Asset Repair",
            "asset": self.asset,
            "failure_date": self.reported_at,
            "repair_status": "Pending",
            "description": self.issue_description,
            "naming_series": "ACC-ASR-.YYYY.-",
            "maintenance_request": self.name
        })
        asset_repair_doc.insert(ignore_permissions=True)

        # Store the AR name as text
        self.db_set('asset_repair', asset_repair_doc.name)
        frappe.db.commit()
    
    def before_delete(self):
        """Delete all linked Asset Repairs before MR is deleted"""
        if self.asset_repair:
            try:
                # Find all versions of this Asset Repair (original + amendments)
                all_versions = frappe.db.get_list(
                    "Asset Repair",
                    filters={"name": ["like", f"{self.asset_repair}%"]},
                    fields=["name"]
                )
                
                frappe.logger().info(f"Deleting {len(all_versions)} Asset Repairs")
                
                # Delete all versions using SQL (bypass validation)
                for ar in all_versions:
                    frappe.db.sql(
                        "DELETE FROM `tabAsset Repair` WHERE name = %s",
                        ar.name
                    )
                
                frappe.db.commit()
                frappe.logger().info(f"Deleted {len(all_versions)} Asset Repairs for MR {self.name}")
                
            except Exception as e:
                frappe.logger().error(f"Error deleting Asset Repairs: {e}")
                # Don't block deletion on error
                pass