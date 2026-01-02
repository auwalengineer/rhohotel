from frappe import _

def get_data():
    return {
        "title": _("Restaurant"),
        "icon": "octicon octicon-file-directory",
        "label": _("Restaurant"),
        "public": 1,
        "items": [
            {
                "label": _("Setup"),
                "items": [
                    {"type": "doctype", "name": "Restaurant Settings", "label": _("Settings")},
                    {"type": "doctype", "name": "Restaurant Location", "label": _("Location")},
                    {"type": "doctype", "name": "Restaurant Menu", "label": _("Menu")},
                    {"type": "doctype", "name": "Restaurant Table", "label": _("Table")},
                ]
            },
            {
                "label": _("Operations"),
                "items": [
                    {"type": "doctype", "name": "Table Reservation", "label": _("Table Reservation")},
                    {"type": "doctype", "name": "Restaurant Order", "label": _("Restaurant Order")},
                    {"type": "doctype", "name": "Kitchen Order Ticket", "label": _("Kitchen Order Ticket")},
                ]
            }
        ]
    }
