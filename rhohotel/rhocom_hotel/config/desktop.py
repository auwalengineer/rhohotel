from frappe import _

def get_data():
	return [
		{
			"module_name": "Rhocom Hotel",
			"color": "#2ecc71",
			"icon": "octicon octicon-home",
			"type": "module",
			"label": _("Rhocom Hotel"),
			"items": [
				{"type": "page", "name": "hotel-setup", "label": _("Setup Wizard"), "description": _("Guided setup for Room Types, Pricing and Packages"), "icon": "octicon octicon-rocket", "color": "#f39c12", "onboard": 1},
				{"type": "doctype", "name": "Hotel Settings", "description": _("Configure hotel defaults and policies"), "icon": "octicon octicon-gear", "color": "#34495e", "onboard": 1},
				{"type": "doctype", "name": "Hotel Room Type", "description": _("Room types and capacities"), "icon": "octicon octicon-list-unordered", "color": "#1abc9c", "onboard": 1},
				{"type": "doctype", "name": "Hotel Room Amenity", "description": _("Room amenities"), "icon": "octicon octicon-star", "color": "#9b59b6"},
				{"type": "doctype", "name": "Hotel Room Package", "description": _("Packages that map items to room types"), "icon": "octicon octicon-package", "color": "#2980b9", "onboard": 1},
				{"type": "doctype", "name": "Hotel Room Pricing", "description": _("Pricing slabs and date ranges"), "icon": "octicon octicon-tag", "color": "#e74c3c", "onboard": 1},
				{"type": "doctype", "name": "Hotel Room Pricing Item", "description": _("Per-item pricing"), "icon": "octicon octicon-credit-card", "color": "#c0392b"},
				{"type": "doctype", "name": "Hotel Floor", "description": _("Hotel floors and layout"), "icon": "octicon octicon-organization", "color": "#16a085"},
				{"type": "doctype", "name": "Hotel Room", "description": _("Rooms and capacities"), "icon": "octicon octicon-device-mobile", "color": "#2c3e50"},
				{"type": "doctype", "name": "Hotel Room Reservation", "description": _("Manage reservations"), "icon": "octicon octicon-calendar", "color": "#27ae60"},
			]
		}
	]
