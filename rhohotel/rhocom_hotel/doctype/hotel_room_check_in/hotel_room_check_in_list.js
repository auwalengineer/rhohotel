frappe.listview_settings['Hotel Room Check In'] = {
    add_fields: ["status"],
    get_indicator: function (doc) {
        return [__(doc.status), {
            "Draft": "orange",
            "Checked In": "green",
            "Checked Out": "blue",
            "Cancelled": "red"
        }[doc.status], "status,=," + doc.status];
    }
};