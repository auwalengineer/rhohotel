from frappe import _

def get_data():
	return {
		"title": _("Rhocom Hotel"),
		"icon": "octicon octicon-home",
		"label": _("Rhocom Hotel"),
		"items": [
			{"type": "page", "name": "hotel-setup", "label": _("Setup Wizard"), "icon": "octicon octicon-rocket"},
			{
				"label": _("Setup"),
				"items": [
					{"type": "doctype", "name": "Hotel Room Type", "label": _("Room Types")},
					{"type": "doctype", "name": "Hotel Room Pricing", "label": _("Pricing")},
					{"type": "doctype", "name": "Hotel Room Package", "label": _("Packages")}
				]
			},
			{
				"label": _("Operations"),
				"items": [
					{"type": "doctype", "name": "Hotel Room Reservation", "label": _("Reservations")}
				]
			}
		]
	}