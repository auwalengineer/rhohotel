// // Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// // For license information, please see license.txt

// frappe.ui.form.on("Hotel Room", {
// 	room_type: function (frm) {
// 		if (frm.doc.room_type) {
// 			frappe.model.with_doc("Hotel Room Type", frm.doc.room_type, () => {
// 				let hotel_room_type = frappe.get_doc(
// 					"Hotel Room Type",
// 					frm.doc.room_type
// 				);

// 				// reset the amenities
// 				frm.doc.amenities = [];

// 				for (let amenity of hotel_room_type.amenities) {
// 					let d = frm.add_child("amenities");
// 					d.item = amenity.item;
// 				}
// 				frm.refresh_field("amenities");
// 			});
// 		}
// 	},
// });


// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hotel Room", {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Housekeeping Request"), () => {
				frappe.new_doc("Housekeeping Request", {
					room: frm.doc.name,
				});
			}, __("Create"));
		}
	},
	room_type: function (frm) {
		if (frm.doc.room_type) {

			// get room capacity from room type
			frappe.model.with_doc("Hotel Room Type", frm.doc.room_type, () => {
				let hotel_room_type = frappe.get_doc(
					"Hotel Room Type",
					frm.doc.room_type
				);
				frm.set_value("capacity", hotel_room_type.capacity);
			});

			frappe.model.with_doc("Hotel Room Type", frm.doc.room_type, () => {
				let hotel_room_type = frappe.get_doc(
					"Hotel Room Type",
					frm.doc.room_type
				);



				// Reset and populate amenities
				frm.doc.amenities = [];
				for (let amenity of hotel_room_type.amenities) {
					let d = frm.add_child("amenities");
					d.item = amenity.item;
				}
				frm.refresh_field("amenities");

				// Reset and populate room inventory from standard_inventory
				if (hotel_room_type.standard_inventory && hotel_room_type.standard_inventory.length > 0) {
					frm.doc.room_inventory = [];
					for (let inventory_item of hotel_room_type.standard_inventory) {
						let d = frm.add_child("room_inventory");
						d.item = inventory_item.item;
						d.quantity = inventory_item.quantity;
					}
					frm.refresh_field("room_inventory");
				}
			});
		}
	},


});