import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date


@frappe.whitelist()
def get_rooms_summary(filters=None):
	"""Return list of rooms with status, maintenance, current_check_in info and reservation/check-out times.
	filters (json string) can include: floor, room_type, status, maintenance, upcoming_checkout_hours
	"""
	import json

	filters = json.loads(filters) if filters else {}
	conds = ["1=1"]
	args = []
	if filters.get("floor"):
		conds.append("room.floor = %s")
		args.append(filters.get("floor"))
	if filters.get("room_type"):
		conds.append("room.room_type = %s")
		args.append(filters.get("room_type"))
	if filters.get("status"):
		conds.append("room.room_status = %s")
		args.append(filters.get("status"))
	if filters.get("maintenance"):
		conds.append("room.maintenance_flag = 1")
	if filters.get("housekeeper_present"):
		conds.append("room.last_keycard_user IS NOT NULL")

	# upcoming checkout window
	upcoming_hours = filters.get("upcoming_checkout_hours")
	if upcoming_hours:
		end = add_to_date(now_datetime(), hours=upcoming_hours)
		conds.append("(ci.expected_check_out_datetime between %s and %s)")
		args.extend([now_datetime(), end])

	query = f"""
		select
			room.name as room,
			room.room_type as room_type,
			room.floor as floor,
			room.room_status as status,
			room.maintenance_flag as maintenance,
			room.last_keycard_user as last_keycard_user,
			room.last_keycard_time as last_keycard_time,
			room.current_check_in as current_check_in,
			ci.guest_name as guest_name,
			ci.expected_check_out_datetime as expected_check_out_datetime,
			r.name as reservation,
			r.reservation_source as reservation_source
		from
			`tabHotel Room` room
		left join
			`tabHotel Room Check In` ci on ci.name = room.current_check_in
		left join
			`tabHotel Room Reservation` r on r.name = ci.reservation
		where {" AND ".join(conds)}
		order by room.floor, room.name
	"""
	rows = frappe.db.sql(query, tuple(args), as_dict=1)
	return rows


@frappe.whitelist()
def make_check_out(checkin_name):
	"""Perform checkout for the given Hotel Room Check In docname.
	Sets actual_check_out_datetime, status and frees up the room.
	"""
	ci = frappe.get_doc("Hotel Room Check In", checkin_name)
	if ci.status == "Checked Out":
		frappe.throw(_("Check-in {0} already checked out").format(checkin_name))
	ci.actual_check_out_datetime = now_datetime()
	ci.status = "Checked Out"
	# placeholder: calculate extra charges here if required
	if not ci.total_charges:
		ci.total_charges = 0.0
	ci.save()

	# update linked room
	if ci.room:
		room = frappe.get_doc("Hotel Room", ci.room)
		room.room_status = "Vacant"
		room.current_check_in = None
		room.save()

	# optionally submit the checkin doc if submittable
	if ci.docstatus == 0 and ci.meta.is_submittable:
		ci.submit()

	return {"success": True, "checkin": ci.name}


@frappe.whitelist()
def get_checkin_invoice_list(check_in):
	"""Return compact list of invoices and totals for a check-in."""
	if not check_in:
		frappe.throw("Check-in not supplied")

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"custom_hotel_room_check_in": check_in},
		fields=["name", "posting_date", "grand_total", "outstanding_amount", "docstatus", "customer"],
		order_by="posting_date desc",
	)

	total_invoiced = sum(i.grand_total or 0 for i in invoices)
	total_outstanding = sum(i.outstanding_amount or 0 for i in invoices)

	return {"invoices": invoices, "total_invoiced": total_invoiced, "total_outstanding": total_outstanding}


@frappe.whitelist()
def collect_payment_for_checkin(check_in, allocations=None, payment_info=None):
	"""Create and submit a Payment Entry for a Hotel Room Check In.

	allocations: JSON string or list of {invoice: name, amount: value}
	payment_info: JSON string or dict with keys: mode_of_payment, paid_amount, reference_no, reference_date, remarks
	Returns: dict with payment_entry name
	"""
	import json

	if not check_in:
		frappe.throw("Check-in not supplied")

	allocations = (
		json.loads(allocations) if allocations and isinstance(allocations, str) else (allocations or [])
	)
	payment_info = (
		json.loads(payment_info) if payment_info and isinstance(payment_info, str) else (payment_info or {})
	)

	company = frappe.db.get_single_value("Global Defaults", "default_company")
	mop = frappe.get_doc("Mode of Payment", payment_info.get("mode_of_payment"))

	if not mop.accounts:
		frappe.throw("Mode of Payment has no accounts configured.")

	mop_account = next((a.default_account for a in mop.accounts if a.company == company), None)

	if not mop_account:
		frappe.throw(f"No account found for Mode of Payment in {company}")

	# avoid duplicate reference numbers
	if payment_info.get("reference_no"):
		existing_pe = frappe.db.get_value("Payment Entry", {"reference_no": payment_info.get("reference_no")})
		if existing_pe:
			frappe.throw("A Payment Entry with this reference number already exists.")

	# Fetch check-in and guest/customer
	ci = frappe.get_doc("Hotel Room Check In", check_in)
	guest = None
	customer = None
	try:
		if ci.guest:
			guest = frappe.get_doc("Hotel Guest", ci.guest)
			customer = guest.customer
	except Exception:
		customer = None

	total_paid = float(payment_info.get("paid_amount") or 0)
	if total_paid <= 0:
		total_paid = sum(float(a.get("amount") or 0) for a in allocations)

	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.party_type = "Customer"
	pe.party = customer or ci.guest or ""
	pe.posting_date = payment_info.get("payment_date") or frappe.utils.today()
	pe.paid_amount = total_paid
	pe.paid_to = mop_account
	pe.received_amount = total_paid
	pe.source_exchange_rate = 1
	pe.target_exchange_rate = 1
	pe.company = company
	pe.mode_of_payment = payment_info.get("mode_of_payment") or payment_info.get("mode") or "Cash"
	if payment_info.get("reference_no"):
		pe.reference_no = payment_info.get("reference_no")
	if payment_info.get("reference_date"):
		pe.reference_date = payment_info.get("reference_date")
	if payment_info.get("remarks"):
		pe.remarks = payment_info.get("remarks")

	# link to check-in for traceability
	pe.custom_hotel_room_check_in = check_in

	# Append references
	for alloc in allocations:
		inv = alloc.get("invoice") or alloc.get("invoice_name") or alloc.get("name")
		requested_amount = float(alloc.get("amount") or 0)
		if not inv or requested_amount <= 0:
			continue

		invoice = frappe.get_doc("Sales Invoice", inv)
		if invoice.docstatus != 1:
			frappe.throw(_("Invoice {0} is not submitted.").format(inv))
		if invoice.custom_hotel_room_check_in != check_in:
			frappe.throw(_("Invoice {0} is not linked to Check In {1}.").format(inv, check_in))

		allocated_amount = min(requested_amount, float(invoice.outstanding_amount or 0))
		if allocated_amount <= 0:
			continue

		pe.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": inv,
				"allocated_amount": allocated_amount,
			},
		)

	try:
		pe.insert(ignore_permissions=True)
		# try to submit if possible
		try:
			pe.submit()
		except Exception:
			# if submission fails due to workflow/accounts, keep as draft but return name
			frappe.log_error(
				frappe.get_traceback(), "Payment Entry submit failed from collect_payment_for_checkin"
			)

		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to create Payment Entry from front desk")
		frappe.throw("Failed to create payment entry")

	return {"payment_entry": pe.name}


@frappe.whitelist()
def collect_payment_and_checkout(check_in, allocations=None, payment_info=None, force_checkout=False):
	"""Collect payment (if any) and perform checkout for a check-in.

	If outstanding invoices remain after payment and force_checkout is False, raise.
	If force_checkout is True, user must have Manager/System Manager role.
	"""
	import json

	if isinstance(force_checkout, str):
		force_checkout = force_checkout.lower() in ("1", "true", "yes")

	# First collect payment if provided
	if allocations or (
		payment_info
		and (
			payment_info.get("paid_amount")
			or (isinstance(payment_info, dict) and payment_info.get("paid_amount"))
		)
	):
		res = collect_payment_for_checkin(check_in, allocations=allocations, payment_info=payment_info)
		payment_entry = res.get("payment_entry")
	else:
		payment_entry = None

	# Re-check outstanding invoices
	invoices = (
		frappe.get_all(
			"Sales Invoice",
			filters={"custom_hotel_room_check_in": check_in, "outstanding_amount": [">", 0]},
			fields=["name", "outstanding_amount"],
		)
		or []
	)
	if invoices and len(invoices) > 0:
		if not force_checkout:
			frappe.throw(
				"Outstanding invoices remain. Collect payment or use force checkout with manager authorization."
			)
		# check roles
		roles = frappe.get_roles(frappe.session.user)
		if "System Manager" not in roles and "Hotel Manager" not in roles:
			frappe.throw("Only a manager can perform a force checkout")

	# perform checkout using existing helper
	check_out_res = make_check_out(check_in)

	return {"payment_entry": payment_entry, "checkout": check_out_res}


@frappe.whitelist()
def create_payment_receipt(payment_entry):
	"""Return a PDF download URL for a Payment Entry using the Payment Receipt print format."""
	if not payment_entry:
		frappe.throw("Payment entry not supplied")

	# Use frappe print format download endpoint
	site_url = frappe.utils.get_url()
	pd_url = f"/api/method/frappe.utils.print_format.download_pdf?doctype=Payment%20Entry&name={payment_entry}&format=Payment%20Receipt"
	return {"print_url": site_url + pd_url}
