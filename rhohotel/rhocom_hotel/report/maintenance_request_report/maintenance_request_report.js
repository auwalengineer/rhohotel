frappe.query_reports["Maintenance Request Report"] = {
    onload: function(report) {
        console.log("Maintenance Request Report Loaded");
    },
    filters: [
        {
            fieldname: "request_type",
            label: "Request Type",
            fieldtype: "Select",
            options: "\nRepair\nMaintenance",
            onchange: function() {
                frappe.query_report.refresh();
            }
        }
    ]
};
