import frappe

app_name = "rhohotel"
app_title = "Rhocom Hotel"
app_publisher = "Rhocom Technology Ltd"
app_description = "Rhocom Hotel"
app_email = "engr.auwal@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "rhohotel",
# 		"logo": "/assets/rhohotel/logo.png",
# 		"title": "Rhocom Hotel",
# 		"route": "/rhohotel",
# 		"has_permission": "rhohotel.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/rhohotel/css/rhohotel.css"
# app_include_js = "/assets/rhohotel/js/rhohotel.js"
app_include_js = [
	"/assets/rhohotel/js/pos_room_extension.js",
	"/assets/rhohotel/js/pos_payment.js",
	"/assets/rhohotel/js/pos_payment_override.js",
	"/assets/rhohotel/js/pos_print_invoice_extension.js",
]
# include js, css files in header of web template
# web_include_css = "/assets/rhohotel/css/rhohotel.css"
# web_include_js = "/assets/rhohotel/js/rhohotel.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "rhohotel/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}


doctype_js = {"Sales Invoice": "public/js/sales_invoice.js"}

fixtures = [{"doctype": "Workflow"}, {"doctype": "Workflow State"}, {"doctype": "Workflow Action"}]
# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "rhohotel/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "rhohotel.utils.jinja_methods",
# 	"filters": "rhohotel.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "rhohotel.install.before_install"
# after_install = "rhohotel.install.after_install"
# after_migrate = "rhohotel.rhocom_hotel.patches.add_checkin_room_fields.add_checkin_room_fields"


# Uninstallation
# ------------

# before_uninstall = "rhohotel.uninstall.before_uninstall"
# after_uninstall = "rhohotel.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "rhohotel.utils.before_app_install"
# after_app_install = "rhohotel.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "rhohotel.utils.before_app_uninstall"
# after_app_uninstall = "rhohotel.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "rhohotel.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#


# To show custom pages in the public menu, ensure you have workspace JSON files for each page in `rhohotel/rhocom_hotel/workspace/` or use Desk Page/Workspace UI to add them.
# Remove any non-standard workspace config. Pages will appear if workspace/page JSON exists and permissions allow.
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {"0 11 * * *": ["rhohotel.rhocom_hotel.auto_close_pos_shift.auto_close_pos_shifts"]}
}

# Testing
# -------

# before_tests = "rhohotel.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rhohotel.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "rhohotel.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["rhohotel.utils.before_request"]
# after_request = ["rhohotel.utils.after_request"]

# Job Events
# ----------
# before_job = ["rhohotel.utils.before_job"]
# after_job = ["rhohotel.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"rhohotel.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

doc_events = {
	"Asset Repair": {
		"after_insert": "rhohotel.rhocom_hotel.utils.asset_repair_events.sync_maintenance_request",
		"on_submit": "rhohotel.rhocom_hotel.utils.asset_repair_events.sync_maintenance_request",
		"on_update": "rhohotel.rhocom_hotel.utils.asset_repair_events.sync_maintenance_request",
		"after_amend": "rhohotel.rhocom_hotel.utils.asset_repair_events.sync_maintenance_request",
		"on_cancel": "rhohotel.rhocom_hotel.utils.asset_repair_events.sync_maintenance_request",
	},
}

frappe_csrf_exempt_methods = [
	"rhohotel.search_available_rooms.search_available_rooms",
	"rhohotel.hotel_booking.create_booking",
	"rhohotel.hotel_booking.create_payment_link",
]

frappe.csrf_exempt_methods = frappe_csrf_exempt_methods


after_request = "rhohotel.api.add_cors_headers"

override_doctype_class = {
	"POS Invoice": "rhohotel.rhocom_hotel.pos_invoice.pos_invoice.POSInvoice"
}


# Scheduled Tasks
# scheduler_events = {
#     "cron": {
#         # Run every 5 minutes to check for expired holds
#         "*/5 * * * *": [
#             "rhohotel.hotel_booking.release_expired_holds"
#         ]
#     },
#     "all": [
#         "rhohotel.hotel_booking.release_expired_holds"
#     ]
# }

# background_workers = {
#     'celery': ['rhohotel.background_jobs.clear_expired_temporary_bookings']
# }

# # Scheduled Jobs (every 5 minutes)
# scheduler_events = {
#     "*/5 * * * *": [
#         "rhohotel.background_jobs.clear_expired_temporary_bookings"
#     ],
#     "*/10 * * * *": [
#         "rhohotel.background_jobs.cleanup_expired_booking_rooms"
#     ]
# }


doc_events = {"Sales Invoice": {"validate": "rhohotel.overrides.sales_invoice.validate_sales_invoice"}}
