frappe.listview_settings['Hotel Room Check Out'] = {
    add_fields: ['status'],
    get_indicator: function (doc) {
        if (doc.status === "Completed") {
            return [__("Completed"), "green", "status,=,Completed"];
        } else if (doc.status === "Cancelled") {
            return [__("Cancelled"), "red", "status,=,Cancelled"];
        } else {
            return [__("Draft"), "orange", "status,=,Draft"];
        }
    }
};