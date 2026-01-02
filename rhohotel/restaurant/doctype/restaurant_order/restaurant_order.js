// Copyright (c) 2024, Rhocom and contributors
// For license information, please see license.txt

frappe.ui.form.on("Restaurant Order", {
	refresh: function(frm) {
		frm.trigger("calculate_total");
	},
	items_on_form_rendered: function(frm) {
		frm.trigger("calculate_total");
	}
});

frappe.ui.form.on("Restaurant Order Item", {
	quantity: function(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		row.amount = row.quantity * row.rate;
		frm.refresh_field("items");
		frm.trigger("calculate_total");
	},
	rate: function(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		row.amount = row.quantity * row.rate;
		frm.refresh_field("items");
		frm.trigger("calculate_total");
	},
	item: function(frm, cdt, cdn) {
		frm.trigger("calculate_total");
	}
});
