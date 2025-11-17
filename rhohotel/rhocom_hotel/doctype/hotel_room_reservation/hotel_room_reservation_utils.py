@frappe.whitelist()
def make_room_check_in(source_name, target_doc=None):
	"""Create a new Hotel Room Check In from a Hotel Room Reservation"""
	from frappe.model.mapper import get_mapped_doc

	def set_missing_values(source, target):
		target.check_in_datetime = frappe.utils.now_datetime()
		target.expected_check_out_datetime = frappe.utils.get_datetime(source.to_date)

	doclist = get_mapped_doc("Hotel Room Reservation", source_name, {
		"Hotel Room Reservation": {
			"doctype": "Hotel Room Check In",
			"field_map": {
				"guest_name": "guest_name",
				"name": "reservation",
				"discount": "discount",
				"discount_amount": "discount_amount",
				"net_total": "net_total",
				"grand_total": "grand_total"
			},
			"validation": {
				"docstatus": ["=", 1],
				"status": ["=", "Confirmed"]
			}
		}
	}, target_doc, set_missing_values)

	return doclist