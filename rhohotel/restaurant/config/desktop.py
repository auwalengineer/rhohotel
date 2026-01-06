from frappe import _
def get_data():
    return [
        {
            "name": "Restaurant",
            "label": _("Restaurant Dashboard"),
            "icon": "octicon octicon-file-directory",
            "type": "workspace",
            "public": 1,
            "color": "grey",
        }
    ]