// Housekeeping Task Report - JavaScript
// Adds custom interactions and formatting to the report

frappe.require('assets/frappe/js/frappe/views/ReportView.js');

frappe.views.HousekeepingTaskReport = frappe.views.ReportView.extend({
    init: function(wrapper, ReportName) {
        this._super(wrapper, ReportName);
    },
    
    setup_page: function() {
        this._super();
        this.setup_report_buttons();
    },
    
    setup_report_buttons: function() {
        // Add export buttons
        this.page.add_menu_item(__("Export as PDF"), function() {
            frappe.call({
                method: 'rhohotel.hotel_housekeeping.report.housekeeping_task_report.housekeeping_task_report.export_housekeeping_report_to_pdf',
                args: {
                    start_date: cur_frm ? cur_frm.doc.start_date : null,
                    end_date: cur_frm ? cur_frm.doc.end_date : null
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint(__("PDF generated successfully"));
                    }
                }
            });
        });
        
        this.page.add_menu_item(__("Export as CSV"), function() {
            // CSV export logic
            frappe.msgprint(__("CSV export functionality"));
        });
    }
});

// Custom cell formatting
frappe.listview_settings['Housekeeping Task'] = {
    add_fields: ['status', 'employee_name', 'start_time', 'end_time'],
    
    formatters: {
        'status': function(value) {
            let color = 'gray';
            if (value === 'Completed') {
                color = 'green';
            } else if (value === 'In Progress') {
                color = 'blue';
            } else if (value === 'Pending') {
                color = 'orange';
            }
            return `<span class="indicator ${color}">${value}</span>`;
        }
    },
    
    get_indicator: function(doc) {
        if (doc.status === 'Completed') {
            return [__("Completed"), "green", "status,=," + doc.status];
        } else if (doc.status === 'In Progress') {
            return [__("In Progress"), "blue", "status,=," + doc.status];
        } else if (doc.status === 'Pending') {
            return [__("Pending"), "orange", "status,=," + doc.status];
        }
    }
};

// Report customizations
frappe.provide("frappe.ui.form");

cur_frm.add_fetch("employee", "employee_name", "employee_name");

// Helper functions for report display
function format_duration(minutes) {
    if (!minutes) return 'N/A';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours > 0) {
        return `${hours}h ${mins}m`;
    }
    return `${mins}m`;
}

function format_time(time_string) {
    if (!time_string) return 'Not set';
    return time_string;
}

// Add filter helpers
frappe.pages['housekeeping-task-report'].on_load = function(wrapper) {
    // Add date range filters
    if (wrapper) {
        // Filters will be added by the report framework
    }
};

// Status indicator styling
frappe.ui.form.on('Housekeeping Task', {
    refresh: function(frm) {
        // Update status indicator based on current status
        if (frm.doc.status === 'Completed') {
            frm.set_intro(__("This task has been completed and inspected."), "green");
        } else if (frm.doc.status === 'In Progress') {
            frm.set_intro(__("This task is currently in progress."), "blue");
        } else if (frm.doc.status === 'Pending') {
            frm.set_intro(__("This task is pending assignment."), "orange");
        }
    }
});