import frappe
from frappe.utils import get_datetime, now_datetime
import json


@frappe.whitelist()
def get_room_statistics():
    # This function is already being used by the frontend, so we'll keep it.
    # It's good practice to have all whitelisted methods for a page in its corresponding .py file.
    stats = frappe._dict({
        "vacant": 0,
        "occupied": 0,
        "reserved": 0,
        "dirty": 0,
        "maintenance": 0,
    })
    
    today = frappe.utils.today()

    stats.reserved = frappe.db.count(
        "Hotel Room Reservation",
        filters={
            "from_date": today,
            # Uncomment if needed:
            # "status": "Booked"
        }
    )

    room_stats = frappe.get_all("Hotel Room", fields=["status", "housekeeping_status"], as_list=True)
    for status, housekeeping_status in room_stats:
        if status == "Vacant":
            stats.vacant += 1
        elif status == "Occupied":
            stats.occupied += 1
        elif status == "Maintenance":
            stats.maintenance += 1
        if housekeeping_status == "Dirty":
            stats.dirty += 1

    return stats

@frappe.whitelist()
def get_check_in_list():
	"""
	Returns a list of active check-ins with guest and financial details and contact info.
	"""
	check_ins = frappe.db.sql("""
			SELECT
                ci.name AS check_in_id,
                ci.guest,
                ci.room_number,
                ci.check_in_datetime,
                ci.expected_check_out_datetime,
                COALESCE(inv.total_invoice_amount, 0) AS total_invoice_amount,
                COALESCE(inv.balance, 0) AS balance,
                COALESCE(pay.total_payment_amount, 0) AS total_payment_amount,
                g.email,
                g.phone_number
            FROM `tabHotel Room Check In` ci

            LEFT JOIN `tabHotel Guest` g
                ON ci.guest = g.name

            -- Pre-aggregate invoices
            LEFT JOIN (
                SELECT
                    custom_hotel_room_check_in,
                    SUM(grand_total) AS total_invoice_amount,
                    SUM(outstanding_amount) AS balance
                FROM `tabSales Invoice`
                WHERE docstatus = 1
                GROUP BY custom_hotel_room_check_in
            ) inv ON inv.custom_hotel_room_check_in = ci.name

            -- Pre-aggregate payments
            LEFT JOIN (
                SELECT
                    custom_hotel_room_check_in,
                    SUM(paid_amount) AS total_payment_amount
                FROM `tabPayment Entry`
                WHERE docstatus = 1
                GROUP BY custom_hotel_room_check_in
            ) pay ON pay.custom_hotel_room_check_in = ci.name

            WHERE ci.status = 'Checked In'
            AND ci.docstatus = 1

            ORDER BY ci.room_number;

		""", as_dict=1)

	return check_ins


@frappe.whitelist()
def get_guest_list():
    """
    Returns an aggregated list of all guests with their stay and revenue history.
    """
    guest_list = frappe.db.sql("""
        SELECT
            ci.guest,
            g.market_place,
            COUNT(ci.name) as number_of_stays,
            SUM(si.grand_total) as total_revenue,
            MAX(ci.check_in_datetime) as last_stay
        FROM `tabHotel Room Check In` ci
        LEFT JOIN `tabHotel Guest` g ON ci.guest = g.name
        LEFT JOIN `tabSales Invoice` si ON g.name = si.customer
        WHERE ci.docstatus = 1
        GROUP BY ci.guest
        ORDER BY total_revenue DESC
    """, as_dict=1)
    return guest_list

@frappe.whitelist()
def get_check_out_list():
    """
    Returns a list of check-ins scheduled for checkout today.
    """
    today = frappe.utils.nowdate()
    check_outs = frappe.db.sql("""
    SELECT
        ci.name AS check_in_id,
        ci.guest_name,
        ci.room_number,
        ci.check_in,
        ci.check_in_datetime,
        ci.check_out_datetime,
        COALESCE(SUM(si.grand_total), 0) AS total_invoice_amount,
        COALESCE(SUM(si.outstanding_amount), 0) AS balance,
        COALESCE(SUM(per.paid_amount), 0) AS total_payment_amount,
        g.market_place
    FROM `tabHotel Room Check Out` ci
    LEFT JOIN `tabHotel Guest` g ON ci.guest_name = g.name
    LEFT JOIN `tabSales Invoice` si ON ci.check_in = si.custom_hotel_room_check_in
    LEFT JOIN `tabPayment Entry` per ON ci.check_in = per.custom_hotel_room_check_in
    GROUP BY ci.name
    ORDER BY ci.check_out_datetime DESC
    """, as_dict=1)

    return check_outs

@frappe.whitelist()
def get_reservation_list():
    """
    Returns a list of all hotel room reservations.
    """
    reservations = frappe.get_all(
        "Hotel Room Reservation",
        fields=[
            "name",
            "guest_name",
            "room_number",
            "from_date",
            "to_date",
            "status",
            "payment_status"
        ],
        order_by="creation DESC"
    )
    return reservations

@frappe.whitelist()
def get_rooms(filters=None):
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    else:
        filters = {}

    room_filters = {}
    if filters.get('floor'):
        room_filters['floor'] = filters.get('floor')
    if filters.get('room_type'):
        room_filters['room_type'] = filters.get('room_type')
    if filters.get('status'):
        room_filters['status'] = filters.get('status')
    if filters.get('housekeeping_status'):
        room_filters['housekeeping_status'] = filters.get('housekeeping_status')

    # Handle "Checking Out Today" filter
    if filters.get('checkout_today') and filters.get('today_date'):
        today = filters.get('today_date')
        check_ins_today = frappe.get_all(
            "Hotel Room Check In",
            filters={"expected_check_out_datetime": ["between", [f"{today} 00:00:00", f"{today} 23:59:59"]]},
            pluck="name"
        )
        if check_ins_today:
            room_filters['current_check_in'] = ["in", check_ins_today]
        else:
            # If no check-ins are for today, return no rooms
            return []

    rooms = frappe.get_all(
        "Hotel Room",
        fields=["name", "room_number", "room_type", "floor", "status", "housekeeping_status", "maintenance_flag", "current_check_in", "current_guest"],
        filters=room_filters,
        order_by="room_number"
    )

    # Fetch expected_check_out_datetime for all relevant check-ins in one query
    check_in_ids = [room.get("current_check_in") for room in rooms if room.get("current_check_in")]
    check_in_map = {}
    if check_in_ids:
        check_in_details = frappe.get_all("Hotel Room Check In", filters={"name": ["in", check_in_ids]}, fields=["name", "expected_check_out_datetime", "check_in_datetime"], as_list=1)
        check_in_map = {d[0]: {"expected_check_out": d[1], "check_in": d[2]} for d in check_in_details}

    # Build a clean list of room objects for the frontend
    result = []
    for room in rooms:
        room_obj = room.copy()
        check_in_info = check_in_map.get(room.current_check_in)
        if check_in_info:
            room_obj.expected_check_out_datetime = check_in_info.get("expected_check_out")
            room_obj.check_in_datetime = check_in_info.get("check_in")
        else:
            room_obj.expected_check_out_datetime = None
            room_obj.check_in_datetime = None
        result.append(room_obj)

    return result

@frappe.whitelist()
def get_filtered_rooms(search_text=None, filter_name=None):
	"""
	Search and filter rooms by guest name, room number, or saved filter presets.
	"""
	if not search_text:
		search_text = ""
	
	search_text = search_text.strip()
	
	# Search in rooms and current guests
	rooms = frappe.db.sql("""
		SELECT DISTINCT
			hr.name, hr.room_number, hr.room_type, hr.floor,
			hr.status, hr.housekeeping_status, hr.current_check_in,
			hr.current_guest
		FROM `tabHotel Room` hr
		LEFT JOIN `tabHotel Room Check In` ci ON hr.current_check_in = ci.name
		LEFT JOIN `tabHotel Guest` g ON ci.guest = g.name
		WHERE hr.room_number LIKE %s 
			OR g.name LIKE %s 
			OR g.email LIKE %s
		ORDER BY hr.room_number
	""", [f"%{search_text}%", f"%{search_text}%", f"%{search_text}%"], as_dict=1)
	
	return rooms

@frappe.whitelist()
def get_housekeeping_queue():
	"""
	Returns a queue of rooms needing housekeeping with priority levels.
	Priority: In Progress > Dirty > Inspected > Clean
	"""
	priority_order = {"In Progress": 1, "Dirty": 2, "Inspected": 3, "Clean": 4}
	
	tasks = frappe.get_all(
		"Hotel Room",
		filters={"status": ["in", ["Vacant", "Reserved"]]},
		fields=["name", "room_number", "floor", "room_type", "housekeeping_status"],
		order_by="housekeeping_status ASC"
	)
	
	# Add priority and sort
	for task in tasks:
		task.priority = priority_order.get(task.housekeeping_status, 5)
	
	# Sort by priority then room number
	tasks = sorted(tasks, key=lambda x: (x.priority, x.room_number))
	
	return tasks

@frappe.whitelist()
def get_room_notes(room_name):
	"""
	Get all notes and change log for a specific room.
	"""
	# Get custom notes from Hotel Room doctype (if custom field exists)
	room = frappe.get_doc("Hotel Room", room_name)
	notes_field = getattr(room, "custom_notes", None) or ""
	
	# Get change log from doctype history
	change_log = frappe.db.sql("""
		SELECT modified, modified_by, data
		FROM `tabDocumentation` 
		WHERE ref_doctype = 'Hotel Room' AND ref_name = %s
		ORDER BY modified DESC
		LIMIT 20
	""", [room_name], as_dict=1)
	
	return {
		"notes": notes_field,
		"change_log": change_log
	}

@frappe.whitelist()
def save_room_note(room_name, note_text):
	"""
	Save a quick note for a room.
	"""
	room = frappe.get_doc("Hotel Room", room_name)
	if not hasattr(room, "custom_notes"):
		frappe.throw("Custom notes field not found on Hotel Room")
	
	timestamp = frappe.utils.now_datetime()
	user = frappe.session.user
	note_entry = f"\n[{timestamp}] {user}: {note_text}"
	
	room.custom_notes = (getattr(room, "custom_notes", "") or "") + note_entry
	room.save()
	
	return {"status": "success", "message": "Note saved"}

@frappe.whitelist()
def get_night_audit_data():
	"""
	Returns night audit data: occupancy rate, revenue, no-shows, pending payments.
	"""
	today = frappe.utils.nowdate()
	
	# Get total rooms
	total_rooms = frappe.db.count("Hotel Room")
	
	# Get occupied rooms
	occupied_rooms = frappe.db.count("Hotel Room", {"status": "Occupied"})
	occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
	
	# Get today's revenue
	today_revenue = frappe.db.sql("""
		SELECT COALESCE(SUM(si.grand_total), 0) as total
		FROM `tabSales Invoice` si
		LEFT JOIN `tabHotel Room Check In` ci ON si.custom_hotel_room_check_in = ci.name
		WHERE DATE(si.posting_date) = %s AND si.docstatus = 1
	""", [today], as_dict=1)[0]["total"] or 0
	
	# Get pending payments (outstanding invoices)
	pending_payments = frappe.db.sql("""
		SELECT COALESCE(SUM(si.outstanding_amount), 0) as total
		FROM `tabSales Invoice` si
		LEFT JOIN `tabHotel Room Check In` ci ON si.custom_hotel_room_check_in = ci.name
		WHERE ci.status = 'Checked In' AND si.outstanding_amount > 0
	""", as_dict=1)[0]["total"] or 0
	
	# Get no-shows (reservations that were not checked in)
	no_shows = frappe.db.count("Hotel Room Reservation", {
		"from_date": ["<=", today],
		"to_date": [">=", today],
		"status": ["in", ["Cancelled", "No Show"]]
	})
	
	return {
		"total_rooms": total_rooms,
		"occupied_rooms": occupied_rooms,
		"occupancy_rate": round(occupancy_rate, 2),
		"today_revenue": today_revenue,
		"pending_payments": pending_payments,
		"no_shows": no_shows
	}

@frappe.whitelist()
def get_night_audit_charts_data():
	"""
	Returns data for night audit charts:
	- Revenue by Room Type
	- Daily Sales for the last 7 days
	- Revenue by Market Place
	"""
	today = frappe.utils.nowdate()
	seven_days_ago = frappe.utils.add_to_date(today, days=-6)

	# 1. Revenue by Room Type
	revenue_by_room_type = frappe.db.sql("""
		SELECT
			hr.room_type,
			COALESCE(SUM(si.grand_total), 0) as total_revenue
		FROM `tabSales Invoice` si
		JOIN `tabHotel Room Check In` ci ON si.custom_hotel_room_check_in = ci.name
		JOIN `tabHotel Room` hr ON ci.room_number = hr.name
		WHERE si.docstatus = 1
		GROUP BY hr.room_type
		ORDER BY total_revenue DESC
	""", as_dict=1)

	# 2. Daily Sales for the last 7 days
	daily_sales_data = frappe.db.sql("""
		SELECT
			DATE(posting_date) as sale_date,
			SUM(grand_total) as total_sales
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
		GROUP BY DATE(posting_date)
		ORDER BY sale_date
	""", (seven_days_ago, today), as_dict=1)

	# Create a dictionary for easy lookup
	sales_map = {d['sale_date'].strftime('%Y-%m-%d'): d['total_sales'] for d in daily_sales_data}
	
	# Fill in missing days with 0 sales
	daily_sales = []
	for i in range(7):
		date = frappe.utils.add_to_date(seven_days_ago, days=i)
		date_str = date
		daily_sales.append({
			"date": date,
			"sales": sales_map.get(date_str, 0)
		})

	# 3. Revenue by Market Place
	revenue_by_market_place = frappe.db.sql("""
		SELECT
			g.market_place,
			COALESCE(SUM(si.grand_total), 0) as total_revenue
		FROM `tabSales Invoice` si
		JOIN `tabHotel Room Check In` ci ON si.custom_hotel_room_check_in = ci.name
		JOIN `tabHotel Guest` g ON ci.guest = g.name
		WHERE si.docstatus = 1 AND g.market_place IS NOT NULL AND g.market_place != ''
		GROUP BY g.market_place
		ORDER BY total_revenue DESC
	""", as_dict=1)

	return {
		"revenue_by_room_type": revenue_by_room_type,
		"daily_sales": daily_sales,
		"revenue_by_market_place": revenue_by_market_place
	}

@frappe.whitelist()
def get_rooms_with_payment_status(filters=None):
	"""
	Get rooms with payment/balance information for quick settlement tracking.
	"""
	if filters and isinstance(filters, str):
		filters = json.loads(filters)
	else:
		filters = {}
	
	rooms = frappe.db.sql("""
       SELECT
            ci.name AS check_in_id,
            ci.room_number,
            ci.guest,
            COALESCE(inv.total_invoice, 0) AS total_invoice,
            COALESCE(inv.balance, 0) AS balance,
            COALESCE(inv.total_paid, 0) AS total_paid
        FROM `tabHotel Room Check In` ci

        -- Aggregate active room charges per check-in across Sales and POS invoices.
        LEFT JOIN (
            SELECT
                invoice_data.check_in,
                SUM(invoice_data.total_invoice) AS total_invoice,
                SUM(invoice_data.balance) AS balance,
                SUM(invoice_data.total_invoice - invoice_data.balance) AS total_paid
            FROM (
                SELECT
                    custom_hotel_room_check_in AS check_in,
                    grand_total AS total_invoice,
                    outstanding_amount AS balance
                FROM `tabSales Invoice`
                WHERE docstatus = 1

                UNION ALL

                SELECT
                    custom_hotel_room_check_in AS check_in,
                    grand_total AS total_invoice,
                    outstanding_amount AS balance
                FROM `tabPOS Invoice`
                WHERE docstatus = 1
            ) invoice_data
            GROUP BY invoice_data.check_in
        ) inv ON inv.check_in = ci.name

        WHERE ci.status = 'Checked In'
        AND ci.docstatus = 1

        ORDER BY ci.room_number;

    """, as_dict=1)

	return rooms

@frappe.whitelist()
def get_room_stay_data(from_date, to_date, room_type_filter=None, status_filter=None):
	"""
	Get all room occupancy data for the specified date range.
	Returns rooms with their check-ins and reservations.
	Supports optional filters for room type and stay status.
	"""
	# Build base query with room type filter if provided
	room_filters = []
	if room_type_filter:
		room_filters.append(["room_type", "=", room_type_filter])
	
	rooms = frappe.get_all(
		"Hotel Room",
		fields=["name", "room_number", "room_type", "floor"],
		filters=room_filters if room_filters else None,
		order_by="room_number"
	)
	
	# Get check-ins for the date range
	check_in_conditions = """
		WHERE 
			DATE(ci.check_in_datetime) <= %s AND 
			DATE(ci.expected_check_out_datetime) >= %s AND
			ci.status = 'Checked In'
	"""
	check_in_params = [to_date, from_date]
	
	# Add status filter if specified
	if status_filter == 'reserved':
		check_in_conditions += " AND 1=0"  # Exclude check-ins if only reservations requested
	
	check_ins = frappe.db.sql(f"""
		SELECT
			ci.name,
			ci.room_number,
			ci.guest,
			ci.check_in_datetime,
			ci.expected_check_out_datetime,
			g.name as guest_id
		FROM `tabHotel Room Check In` ci
		LEFT JOIN `tabHotel Guest` g ON ci.guest = g.name
		{check_in_conditions}
		ORDER BY ci.room_number, ci.check_in_datetime
	""", check_in_params, as_dict=1)
	
	# Get reservations for the date range
	reservation_conditions = """
		WHERE
			from_date <= %s AND 
			to_date >= %s AND
			status != 'Cancelled'
	"""
	reservation_params = [to_date, from_date]
	
	# Add status filter if specified
	if status_filter == 'checked-in':
		reservation_conditions += " AND 1=0"  # Exclude reservations if only check-ins requested
	
	reservations = frappe.db.sql(f"""
		SELECT
			name,
			room_number,
			guest_name,
			from_date,
			to_date,
			status
		FROM `tabHotel Room Reservation`
		{reservation_conditions}
		ORDER BY room_number, from_date
	""", reservation_params, as_dict=1)
	
	return {
		"rooms": rooms,
		"check_ins": check_ins,
		"reservations": reservations,
		"from_date": from_date,
		"to_date": to_date
	}

@frappe.whitelist()
def get_default_letterhead():
	"""
	Returns the HTML content of the default letterhead specified in Print Settings.
	"""
	#letterhead_name = frappe.db.get_single_value('Print Settings', 'default_letter_head')
	#if not letterhead_name:
	#	return None
	
	letterhead = frappe.get_doc('Letter Head', 'Frontdesk 1')
	return letterhead.content 










# Add these methods to your rhohotel/rhocom_hotel/page/front_desk/front_desk.py file

@frappe.whitelist()
def get_corporate_reservations():
    """
    Get all corporate reservations with summary information
    Returns: List of corporate reservations with key details
    """
    try:
        reservations = frappe.db.sql("""
            SELECT 
                fdr.name,
                fdr.reservation_number,
                fdr.corporate_guest,
                hg.hotel_guest_name as corporate_guest_name,
                fdr.customer,
                fdr.total_rooms,
                fdr.number_of_nights,
                fdr.from_date,
                fdr.to_date,
                fdr.total_amount,
                fdr.status,
                COUNT(DISTINCT hrr.name) as rooms_with_reservations
            FROM `tabHotel Front Desk Reservation` fdr
            LEFT JOIN `tabHotel Guest` hg ON fdr.corporate_guest = hg.name
            LEFT JOIN `tabHotel Room Reservation` hrr ON fdr.name = hrr.front_desk_reservation
            WHERE fdr.reservation_type = 'Corporate'
            AND fdr.docstatus = 1
            GROUP BY fdr.name
            ORDER BY fdr.creation DESC
        """, as_dict=True)
        
        return reservations
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Corporate Reservations Error")
        return []


@frappe.whitelist()
def get_corporate_reservation_details(reservation_name):
    """
    Get comprehensive details for a corporate reservation including:
    - Full reservation document
    - Room reservations
    - Check-ins
    - Invoices (from BOTH sales_invoice link field AND sales_invoices child table)
    - Payments (if any)
    
    INVOICE FETCHING:
    - Grabs bulk invoice from sales_invoice field (if created)
    - Grabs individual room invoices from sales_invoices child table
    - Deduplicates to avoid showing same invoice twice
    - Merges room details from child table into invoice data
    
    Args:
        reservation_name: Name of the Hotel Front Desk Reservation (e.g., FDR-2025-00318)
    
    Returns:
        Dictionary with all related information including invoices from both sources
    """
    try:
        # STEP 1: Validate reservation exists
        if not frappe.db.exists('Hotel Front Desk Reservation', reservation_name):
            frappe.log_error(f"Reservation not found: {reservation_name}", 
                           "Get Corporate Reservation Details")
            return {
                "success": False,
                "error": f"Reservation {reservation_name} not found",
                "reservation": None,
                "room_reservations": [],
                "checkins": [],
                "invoices": [],
                "payments": []
            }
        
        # STEP 2: Get the full reservation document
        try:
            reservation_doc = frappe.get_doc('Hotel Front Desk Reservation', 
                                            reservation_name)
            reservation = reservation_doc.as_dict()
        except Exception as e:
            frappe.log_error(f"Error fetching reservation: {str(e)}", 
                           "Get Corporate Reservation Details")
            return {
                "success": False,
                "error": f"Could not fetch reservation: {str(e)}",
                "reservation": None,
                "room_reservations": [],
                "checkins": [],
                "invoices": [],
                "payments": []
            }
        
        # STEP 3: Get room reservations (might be empty)
        room_reservations = []
        try:
            room_reservations = frappe.get_all(
                "Hotel Room Reservation",
                filters={"front_desk_reservation": reservation_name},
                fields=["name", "room_number", "guest_name", "status", "rate", 
                       "from_date", "to_date"]
            )
        except Exception as e:
            frappe.log_error(f"Error fetching room reservations: {str(e)}", 
                           "Get Corporate Reservation Details")
            room_reservations = []
        
        # STEP 4: Get check-ins (might be empty - not checked in yet)
        check_ins = []
        try:
            check_ins = frappe.db.sql("""
                SELECT 
                    hrci.name,
                    hrci.room_number,
                    hrci.guest,
                    hrci.check_in_datetime,
                    hrci.expected_check_out_datetime,
                    hrci.status
                FROM `tabHotel Room Check In` hrci
                WHERE hrci.front_desk_reservation = %s
                ORDER BY hrci.check_in_datetime DESC
            """, (reservation_name,), as_dict=True)
        except Exception as e:
            frappe.log_error(f"Error fetching check-ins: {str(e)}", 
                           "Get Corporate Reservation Details")
            check_ins = []
        
        # ✅ STEP 5: Get invoices from BOTH sources
        # Invoices can come from:
        # 1. sales_invoice field (bulk invoice for entire reservation)
        # 2. sales_invoices child table (individual per-room invoices)
        invoices = []
        invoice_names = set()  # Track to avoid duplicates
        
        try:
            # Source 1: Bulk invoice from sales_invoice field
            if reservation.get('sales_invoice'):
                bulk_invoice = frappe.get_all(
                    "Sales Invoice",
                    filters={"name": reservation.get('sales_invoice')},
                    fields=["name", "total", "docstatus", "outstanding_amount", 
                           "posting_date"]
                )
                if bulk_invoice:
                    invoices.extend(bulk_invoice)
                    invoice_names.add(reservation.get('sales_invoice'))
            
            # Source 2: Individual invoices from child table
            if reservation.get('sales_invoices'):  # Check if child table has data
                child_invoices = frappe.get_all(
                    "Hotel Front Desk Reservation Invoice",
                    filters={"parent": reservation_name},
                    fields=["sales_invoice", "room_number", "guest_name", "amount", "created_at"]
                )
                
                if child_invoices:
                    # Get full invoice details for each
                    for child_inv in child_invoices:
                        if child_inv.sales_invoice not in invoice_names:
                            # Fetch full invoice details
                            full_inv = frappe.get_all(
                                "Sales Invoice",
                                filters={"name": child_inv.sales_invoice},
                                fields=["name", "total", "docstatus", "outstanding_amount", 
                                       "posting_date"]
                            )
                            if full_inv:
                                # Merge with child table info
                                full_inv[0].update({
                                    "room_number": child_inv.room_number,
                                    "guest_name": child_inv.guest_name,
                                    "amount": child_inv.amount,
                                    "created_at": child_inv.created_at,
                                    "is_room_invoice": True  # Flag to distinguish
                                })
                                invoices.append(full_inv[0])
                                invoice_names.add(child_inv.sales_invoice)
        
        except Exception as e:
            frappe.log_error(f"Error fetching invoices: {str(e)}", 
                           "Get Corporate Reservation Details")
            invoices = []  # Return empty list, not error
        
        # STEP 6: Get payments (might be empty - no payments made yet)
        # ✅ ONLY QUERY IF INVOICE EXISTS
        payments = []
        try:
            if invoices:  # Only if we have invoices
                # Get payments linked to any of the invoices
                invoice_names_list = list(invoice_names)
                if invoice_names_list:
                    payments = frappe.db.sql("""
                        SELECT DISTINCT
                            pe.name,
                            pe.paid_amount,
                            pe.posting_date,
                            pe.mode_of_payment,
                            pe.status
                        FROM `tabPayment Entry` pe
                        WHERE pe.name IN (
                            SELECT DISTINCT ped.parent
                            FROM `tabPayment Entry Detail` ped
                            WHERE ped.reference_doctype = 'Sales Invoice'
                            AND ped.reference_name IN ({})
                        )
                        ORDER BY pe.posting_date DESC
                    """.format(', '.join(['%s'] * len(invoice_names_list))), 
                    invoice_names_list, as_dict=True)
        except Exception as e:
            frappe.log_error(f"Error fetching payments: {str(e)}", 
                           "Get Corporate Reservation Details")
            payments = []  # Return empty list, not error
        
        # STEP 7: Return all data
        return {
            "success": True,
            "reservation": reservation,
            "room_reservations": room_reservations,
            "checkins": check_ins,
            "invoices": invoices,  # ✅ Now contains invoices from both sources
            "payments": payments
        }
    
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(frappe.get_traceback(), 
                        "Get Corporate Reservation Details Error")
        return {
            "success": False,
            "error": error_msg,
            "reservation": None,
            "room_reservations": [],
            "checkins": [],
            "invoices": [],
            "payments": []
        }

@frappe.whitelist()
def get_hall_bookings():
    try:
        return frappe.db.sql("""
            SELECT
                hb.name,
                hb.hall,
                hb.customer_name,
                hb.start_datetime,
                hb.end_datetime,
                hb.total_hours,
                hb.net_total,
                hb.sales_invoice,
                si.status AS invoice_status
            FROM `tabHall Booking` hb
            LEFT JOIN `tabSales Invoice` si
                ON si.name = hb.sales_invoice
            WHERE hb.docstatus != 2
            ORDER BY hb.start_datetime DESC
        """, as_dict=True)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Get Hall Bookings Error")
        return []
