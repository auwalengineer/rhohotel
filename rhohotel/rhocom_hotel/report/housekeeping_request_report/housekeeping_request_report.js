frappe.query_reports["Housekeeping Request"] = {
    filters: [
        {
            fieldname: "room",
            label: __("Room"),
            fieldtype: "Link",
            options: "Hotel Room",
            get_query: function() {
                return {
                    filters: {
                        "docstatus": 0
                    }
                }
            }
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: [
                "",
                "Pending",
                "Approved",
                "Completed",
                "Cancelled"
            ]
        },
        {
            fieldname: "requested_by",
            label: __("Requested By"),
            fieldtype: "Select",
            options: [
                "",
                "Guest",
                "Front Desk",
                "Room Service",
                "Management"
            ]
        },
        {
            fieldname: "request_date_from",
            label: __("Request Date From"),
            fieldtype: "Date"
        },
        {
            fieldname: "request_date_to",
            label: __("Request Date To"),
            fieldtype: "Date"
        },
        {
            fieldname: "approval_status",
            label: __("Approval Status"),
            fieldtype: "Select",
            options: [
                "",
                "Approved",
                "Pending Approval"
            ]
        }
    ],
    onload: function(report) {
        // Add custom buttons
        report.page.add_action_item(__("Export to Excel"), function() {
            frappe.call({
                method: 'frappe.desk.query_report.export_query_report',
                args: {
                    name: 'Housekeeping Request',
                    filters: report.get_values()
                },
                callback: function() {
                    frappe.msgprint(__('Exported successfully'));
                }
            });
        });

        report.page.add_action_item(__("Bulk Approve"), function() {
            let checked_rows = report.datatable.rowmanager.getCheckedRows();
            if (checked_rows.length === 0) {
                frappe.msgprint(__('Please select at least one request to approve'));
                return;
            }

            frappe.confirm(__('Approve {0} selected request(s)?', [checked_rows.length]), function() {
                let request_ids = checked_rows.map(row => {
                    return report.data[row].name;
                });

                frappe.call({
                    method: 'rhohotel.rhocom_hotel.report.housekeeping_request.housekeeping_request.bulk_approve_requests',
                    args: {
                        request_ids: request_ids
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint({
                                message: __('Successfully approved {0} request(s)', [request_ids.length]),
                                title: __('Bulk Approve Complete'),
                                indicator: 'green'
                            });
                            report.refresh();
                        }
                    }
                });
            });
        });
    },
    formatter: function(value, row, column, data, default_formatter) {
        // Color code the status column
        if (column.fieldname === 'status') {
            if (value === 'Approved') {
                return `<span style="color: green; font-weight: bold;">${value}</span>`;
            } else if (value === 'Pending') {
                return `<span style="color: orange; font-weight: bold;">${value}</span>`;
            } else if (value === 'Completed') {
                return `<span style="color: blue; font-weight: bold;">${value}</span>`;
            } else if (value === 'Cancelled') {
                return `<span style="color: red; font-weight: bold;">${value}</span>`;
            }
        }

        // Show approval status indicator
        if (column.fieldname === 'approval_time') {
            if (value) {
                return `<span style="color: green;">✓ ${frappe.datetime.str_to_user(value)}</span>`;
            } else {
                return `<span style="color: red;">✗ Pending</span>`;
            }
        }

        return default_formatter(value, row, column, data);
    }
};