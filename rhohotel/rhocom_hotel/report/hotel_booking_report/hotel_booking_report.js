// Hotel Booking Report - Query File
// File location: rhocom_hotel/rhocom_hotel/report/hotel_booking_report/hotel_booking_report.js

frappe.query_reports["Hotel Booking Report"] = {
	"filters": [
		{
			"fieldname": "booking_number",
			"label": __("Booking Number"),
			"fieldtype": "Link",
			"options": "Hotel Booking",
			"width": "100px"
		},
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": "100px"
		},
		{
			"fieldname": "customer_name",
			"label": __("Customer Name"),
			"fieldtype": "Data",
			"width": "100px"
		},
		{
			"fieldname": "contact_name",
			"label": __("Contact"),
			"fieldtype": "Link",
			"options": "Contact",
			"width": "100px"
		},
		{
			"fieldname": "customer_email",
			"label": __("Customer Email"),
			"fieldtype": "Data",
			"width": "120px"
		},
		{
			"fieldname": "customer_phone",
			"label": __("Customer Phone"),
			"fieldtype": "Data",
			"width": "100px"
		},
		{
			"fieldname": "status",
			"label": __("Booking Status"),
			"fieldtype": "Select",
			"options": "Pending Payment\nConfirmed\nChecked-In\nCompleted\nCancelled",
			"width": "100px"
		},
		{
			"fieldname": "payment_status",
			"label": __("Payment Status"),
			"fieldtype": "Select",
			"options": "Pending\nPaid\nFailed\nRefunded",
			"width": "100px"
		},
		{
			"fieldname": "sales_invoice",
			"label": __("Sales Invoice"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": "100px"
		},
		{
			"fieldname": "transaction_id",
			"label": __("Transaction ID"),
			"fieldtype": "Data",
			"width": "120px"
		},
		{
			"fieldname": "paystack_access_code",
			"label": __("Paystack Access Code"),
			"fieldtype": "Data",
			"width": "150px"
		},
		{
			"fieldname": "from_date_start",
			"label": __("Check-In Date From"),
			"fieldtype": "Date",
			"width": "100px"
		},
		{
			"fieldname": "from_date_end",
			"label": __("Check-In Date To"),
			"fieldtype": "Date",
			"width": "100px"
		},
		{
			"fieldname": "to_date_start",
			"label": __("Check-Out Date From"),
			"fieldtype": "Date",
			"width": "100px"
		},
		{
			"fieldname": "to_date_end",
			"label": __("Check-Out Date To"),
			"fieldtype": "Date",
			"width": "100px"
		},
		{
			"fieldname": "total_rooms_min",
			"label": __("Minimum Rooms"),
			"fieldtype": "Int",
			"width": "80px"
		},
		{
			"fieldname": "total_rooms_max",
			"label": __("Maximum Rooms"),
			"fieldtype": "Int",
			"width": "80px"
		},
		{
			"fieldname": "total_price_min",
			"label": __("Minimum Price"),
			"fieldtype": "Currency",
			"width": "100px"
		},
		{
			"fieldname": "total_price_max",
			"label": __("Maximum Price"),
			"fieldtype": "Currency",
			"width": "100px"
		},
		{
			"fieldname": "check_in_time_start",
			"label": __("Check-In Time From"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "check_in_time_end",
			"label": __("Check-In Time To"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "created_at_start",
			"label": __("Created From"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "created_at_end",
			"label": __("Created To"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "payment_received_at_start",
			"label": __("Payment Received From"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "payment_received_at_end",
			"label": __("Payment Received To"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "hold_expires_at_start",
			"label": __("Hold Expires From"),
			"fieldtype": "Datetime",
			"width": "150px"
		},
		{
			"fieldname": "hold_expires_at_end",
			"label": __("Hold Expires To"),
			"fieldtype": "Datetime",
			"width": "150px"
		}
	],

	"onload": function(report) {
		// Set default filters if needed
		report.page.add_inner_button(__("Refresh"), function() {
			report.refresh();
		});
	},

	"formatter": function(value, row, column, data, default_formatter) {
		if (column.fieldname == "booking_number") {
			value = `<a href="/app/hotel-booking/${data.name}">${value}</a>`;
		} else if (column.fieldname == "customer") {
			value = `<a href="/app/customer/${value}">${value}</a>`;
		} else if (column.fieldname == "sales_invoice") {
			if (value) {
				value = `<a href="/app/sales-invoice/${value}">${value}</a>`;
			}
		} else if (column.fieldname == "total_price") {
			value = frappe.format(value, { fieldtype: "Currency" });
		} else if (column.fieldname.includes("_at")) {
			value = frappe.format(value, { fieldtype: "Datetime" });
		}

		return value || default_formatter(value, row, column, data);
	}
};