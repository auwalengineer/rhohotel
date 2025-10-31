frappe.listview_settings['Hotel Room Rate'] = {
    add_fields: ['is_active', 'plan_type', 'days', 'rate_description'],
    get_indicator: function (doc) {
        if (doc.is_active) {
            return [`${doc.plan_type} - ${doc.days} Day(s)`, "green", "is_active,=,1"];
        } else {
            return [__("Inactive"), "red", "is_active,=,0"];
        }
    }
};