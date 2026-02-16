frappe.pages["front-desk"].on_page_load = function (wrapper) {
	new FrontDesk(wrapper);

	// Load DataTables and Buttons extension CSS and JS if not already loaded
	if (!$.fn.dataTable) {
		// Core CSS
		const dtLink = document.createElement("link");
		dtLink.rel = "stylesheet";
		dtLink.href = "https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css";
		document.head.appendChild(dtLink);

		// Buttons CSS
		const dtButtonsLink = document.createElement("link");
		dtButtonsLink.rel = "stylesheet";
		dtButtonsLink.href =
			"https://cdn.datatables.net/buttons/2.4.1/css/buttons.dataTables.min.css";
		document.head.appendChild(dtButtonsLink);

		// Core JS
		const dtScript = document.createElement("script");
		dtScript.src = "https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js";
		document.head.appendChild(dtScript);

		// Buttons JS and dependencies
		const scriptsToLoad = [
			"https://cdn.datatables.net/buttons/2.4.1/js/dataTables.buttons.min.js",
			"https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js",
			"https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.2.7/pdfmake.min.js",
			"https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.2.7/vfs_fonts.js",
			"https://cdn.datatables.net/buttons/2.4.1/js/buttons.html5.min.js",
			"https://cdn.datatables.net/buttons/2.4.1/js/buttons.print.min.js",
		];
		scriptsToLoad.forEach((src) => frappe.require(src));
	}

	frappe.require([
		"assets/frappe/js/lib/chart.umd.min.js",
		"assets/frappe/js/frappe-charts.min.js",
	]);

	// Add CSS for blinking animation and uniform card heights
	const style = document.createElement("style");
	style.innerHTML = `
		@keyframes blinker {
			50% {
				opacity: 0.3;
			}
		}
		.blink-me {
			animation: blinker 1.5s linear infinite;
		}
		.room-grid .room-card {
			display: flex;
			flex-direction: column;
		}
		.room-grid .room-card .card {
			height: 100%;
			display: flex;
			flex-direction: column;
		}
		.room-grid .room-card .card-body {
			display: flex;
			flex-direction: column;
			height: 100%;
		}
		.room-grid .room-card .card-text {
			flex-grow: 1;
		}
		.dataTables_wrapper {
			margin-top: 1rem;
		}
		.dataTables_filter input {
			margin-left: 0.5rem;
		}
		table.dataTable tbody tr {
			cursor: pointer;
		}
		table.dataTable thead th {
			background-color: #f5f5f5;
		}
		.stay-timeline-header {
			display: grid;
			grid-template-columns: 150px 1fr;
			gap: 1rem;
			font-weight: bold;
			padding: 1rem;
			background-color: #f9f9f9;
			border-bottom: 2px solid #ddd;
			border-radius: 4px 4px 0 0;
		}
		.stay-row {
			display: grid;
			grid-template-columns: 150px 1fr;
			gap: 1rem;
			align-items: center;
			padding: 0.75rem 1rem;
			border-bottom: 1px solid #eee;
		}
		.stay-row:hover {
			background-color: #fafafa;
		}
		.room-label {
			font-weight: 600;
			padding: 0.5rem;
			background-color: #f9f9f9;
			border-radius: 4px;
		}
		.date-column {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			min-width: 80px;
			gap: 0.25rem;
		}
		.date-header {
			font-weight: bold;
			font-size: 0.85rem;
			text-align: center;
			padding: 0.5rem 0.25rem;
			background-color: #f0f0f0;
		}
		.stay-bar {
			height: 32px;
			background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
			border-radius: 4px;
			display: flex;
			align-items: center;
			justify-content: center;
			color: white;
			font-size: 0.7rem;
			font-weight: bold;
			width: 100%;
			max-width: 78px;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			padding: 0 0.25rem;
			cursor: pointer;
			transition: all 0.2s ease;
		}
		.stay-bar:hover {
			box-shadow: 0 2px 8px rgba(0,0,0,0.2);
			transform: scale(1.05);
		}
		.stay-bar-continuous {
			height: 40px;
			border-radius: 4px;
			display: flex;
			align-items: center;
			justify-content: center;
			color: white;
			font-size: 0.75rem;
			font-weight: bold;
			padding: 0.5rem;
			cursor: pointer;
			transition: all 0.2s ease;
		}
		.stay-bar-continuous:hover {
			box-shadow: 0 4px 12px rgba(0,0,0,0.25);
			transform: translateY(-2px);
		}
		.stay-bar-text {
			word-wrap: break-word;
			overflow-wrap: break-word;
			white-space: normal;
			text-align: center;
			line-height: 1.2;
		}
		.empty-day {
			height: 40px;
			background-color: #e8f5e9;
			border-radius: 4px;
			width: 100%;
			max-width: 78px;
		}
		.stay-timeline-container {
			overflow-x: auto;
			border: 1px solid #ddd;
			border-radius: 4px;
			background-color: #fff;
		}
		.timeline-dates {
			display: flex;
			gap: 0.25rem;
		}

        /* Front Desk & Modal UI improvements */
        .frappe-card-head h4, .frappe-card-head h5 {
            margin: 0;
            font-weight: 700;
            color: #333;
        }

        .invoices-container .table {
            margin-bottom: 0;
        }

        .invoices-container .frappe-card {
            border-radius: 8px;
            box-shadow: 0 6px 20px rgba(20,23,26,0.06);
        }

        .invoices-container .frappe-card-body {
            padding: 1rem;
        }

        .invoices-container .inv-checkbox {
            width: 18px;
            height: 18px;
        }

        .invoices-container input.form-control {
            height: 36px;
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid #e6e6e6;
        }

        .invoices-container .btn {
            border-radius: 6px;
            padding: 6px 10px;
        }

        /* Emphasize totals */
        .invoices-container .totals {
            display:flex;
            justify-content:space-between;
            align-items:center;
            margin-top:0.75rem;
            font-weight:600;
        }

        /* Controls layout to avoid floating/overlap */
        .invoices-container .controls-row {
            display:flex;
            gap:0.5rem;
            align-items:center;
            flex-wrap:wrap;
            margin-top:0.5rem;
        }

        .invoices-container .control-left {
            flex:1 1 280px;
            display:flex;
            gap:0.5rem;
            align-items:center;
            flex-wrap:wrap;
        }

        .invoices-container .control-right {
            flex:0 0 auto;
            display:flex;
            gap:0.5rem;
            align-items:center;
            flex-wrap:wrap;
        }

        .invoices-container .table-responsive {
            width:100%;
            overflow:auto;
        }

        .invoices-container .btn { z-index: 1 }

        /* Responsive tweaks */
        @media (max-width: 700px) {
            .invoices-container .frappe-card-body { padding: 0.75rem; }
            .invoices-container .btn { padding: 6px 8px; font-size: 13px }
            .room-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
        }

        /* Room modal: enforce two-column layout for Current Check-in Details and Room Details */
        .frappe-dialog .modal-body .col-md-6 {
            width: 50%;
            float: left;
            box-sizing: border-box;
            padding-right: 0.75rem;
            padding-bottom: 0.5rem;
        }

        .frappe-dialog .modal-body .col-md-12 {
            width: 100%;
            float: none;
        }

        /* Ensure form controls inside columns fill available width */
        .frappe-dialog .modal-body .col-md-6 .form-control,
        .frappe-dialog .modal-body .col-md-6 .frappe-control {
            width: 100%;
        }
	`;
	document.head.appendChild(style);
};

class FrontDesk {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: "Front Desk",
			single_column: true,
		});

		this.rooms = [];
		this.filters = {};
		this.current_view = "room_view";

		this.letterhead_html = null;

		// Fetch letterhead first, then render the page
		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_default_letterhead",
			callback: (r) => {
				if (r.message) {
					this.letterhead_html = r.message;
				}
				// Now initialize the rest of the page
				this.make_stats_area();
				this.make_view_switcher();
				this.make_filters();
				this.make_view_containers();
				this.switch_view(this.current_view); // Initial render
				this.start_clock();
				this.start_timer_updates();
			},
		});

		// Realtime updates
		frappe.realtime.on("rhohotel_front_desk_update", () => {
			this.refresh();
		});
	}

	make_stats_area() {
		const $header = $(`<div class="front-desk-header"></div>`).prependTo(
			this.page.main.parent(),
		);

		const $top_bar = $(
			`<div class="d-flex justify-content-between align-items-center p-3"></div>`,
		).appendTo($header);

		this.$clock = $(`<div class="clock-widget"></div>`).appendTo($top_bar);
		this.$clock.css({
			"font-size": "1.5rem",
			"font-weight": "bold",
		});

		this.$user_display = $(
			`<div>Welcome, <strong>${frappe.session.user_fullname}</strong></div>`,
		).appendTo($top_bar);
		this.$user_display.css({
			"font-size": "1.2rem",
		});

		this.$stats = $('<div class="room-stats"></div>').appendTo($header);
		this.$stats.css({
			display: "grid",
			"grid-template-columns": "repeat(auto-fill, minmax(200px, 1fr))",
			gap: "1rem",
			padding: "1rem",
		});
	}

	make_view_switcher() {
		const $view_switcher_container = $(
			`<div class="front-desk-view-switcher-container" style="padding: 1rem 1rem 0;"></div>`,
		).insertAfter(this.page.main.parent().find(".front-desk-header"));
		this.$view_switcher = $(
			`<div class="btn-group" role="group" style="flex-wrap: wrap;"></div>`,
		).appendTo($view_switcher_container);

		const views = [
			{ name: "room_view", label: "Room View", icon: "th" },
			{ name: "check_in_view", label: "Check-ins", icon: "sign-in" },
			{ name: "check_out_view", label: "Check-outs", icon: "sign-out" },
			{ name: "reservation_view", label: "Reservations", icon: "calendar-check-o" },
			{
				name: "corporate_reservations_view",
				label: "Corporate Reservations",
				icon: "building",
			},
			{ name: "hall_booking_view", label: "Hall Bookings", icon: "university" },
			{ name: "available_rooms_view", label: "Available Rooms", icon: "bed" },
			{ name: "guest_list_view", label: "Guests", icon: "users" },
			{ name: "housekeeping_view", label: "Housekeeping", icon: "tasks" },
			{ name: "payments_view", label: "Payments", icon: "money" },
			{ name: "room_stay_report", label: "Room Stay Report", icon: "calendar" },
			{ name: "night_audit_view", label: "Night Audit", icon: "bar-chart" },
		];

		views.forEach((view) => {
			const button = $(`
                <button type="button" class="btn btn-default" data-view="${view.name}">
                    <i class="fa fa-${view.icon}"></i> ${view.label}
                </button>
            `).appendTo(this.$view_switcher);

			button.on("click", () => {
				this.switch_view(view.name);
			});
		});
	}

	make_view_containers() {
		this.$room_grid = $(
			`<div class="room-grid view-container" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; padding: 1rem 0;"></div>`,
		).appendTo(this.page.main);
	}

	make_filters() {
		const fields = [
			{
				fieldtype: "Data",
				label: "Search Room/Guest",
				fieldname: "search_text",
				placeholder: "Room number, guest name or email...",
				change: () => this.perform_search(),
			},
			{
				fieldtype: "Link",
				label: "Floor",
				fieldname: "floor",
				options: "Hotel Floor",
				change: () => this.refresh_rooms(),
			},
			{
				fieldtype: "Link",
				label: "Room Type",
				fieldname: "room_type",
				options: "Hotel Room Type",
				change: () => this.refresh_rooms(),
			},
			{
				fieldtype: "Select",
				label: "Status",
				fieldname: "status",
				options: "\nVacant\nOccupied\nReserved\nMaintenance",
				change: () => this.refresh_rooms(),
			},
			{
				fieldtype: "Select",
				label: "Housekeeping",
				fieldname: "housekeeping_status",
				options: "\nClean\nDirty\nInspected\nIn Progress",
				change: () => this.refresh_rooms(),
			},
			{
				fieldtype: "Check",
				label: "Checking Out Today",
				fieldname: "checkout_today",
				change: () => this.refresh_rooms(),
			},
		];

		fields.forEach((df) => {
			this.page.add_field(df);
		});
	}

	perform_search() {
		const search_text = this.page.get_form_values().search_text;
		if (search_text && search_text.length > 0) {
			this.$room_grid.empty();
			this.$room_grid.html(`<div class="text-muted">Searching...</div>`);
			frappe.call({
				method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_filtered_rooms",
				args: { search_text: search_text },
				callback: (r) => {
					const rooms = r.message || [];
					this.$room_grid.empty();
					if (rooms.length === 0) {
						this.$room_grid.html(
							`<div class="text-muted">No rooms found matching "${search_text}"</div>`,
						);
					} else {
						rooms.forEach((room) => {
							const $card = this.get_room_card(room);
							$card.on("click", () => this.show_room_actions(room));
							this.$room_grid.append($card);
						});
					}
				},
			});
		} else {
			this.refresh_rooms();
		}
	}

	get_room_card(room) {
		const status_colors = {
			Vacant: "green",
			Occupied: "blue",
			Reserved: "orange-color", // Use a valid CSS variable
			Maintenance: "red",
		};

		const housekeeping_icons = {
			Clean: "check",
			Dirty: "trash",
			Inspected: "eye",
			"In Progress": "refresh",
		};

		const status_color = status_colors[room.status] || "gray";
		const housekeeping_icon = housekeeping_icons[room.housekeeping_status] || "question";

		return $(
			`<div class="room-card" data-name="${room.name}">${this.get_card_content(room, status_color, housekeeping_icon)}</div>`,
		);
	}

	get_card_content(room, status_color, housekeeping_icon) {
		let card_style = `border-left: 3px solid var(--${status_color});`;
		let checkout_warning_style = "";
		let overdue_html = "";

		if (room.status === "Occupied" && room.expected_check_out_datetime) {
			const now = moment();
			const checkout_time = moment(room.expected_check_out_datetime);
			const diff_minutes = checkout_time.diff(now, "minutes");

			if (diff_minutes < 0) {
				// Checkout time has passed
				checkout_warning_style = "background-color: #ef9a9a;"; // A darker, but not pure, red
				const overstay_duration = moment.duration(now.diff(checkout_time)).humanize();
				overdue_html = `<div class="mt-2 text-danger blink-me overdue-message">
                        <strong>Overdue by ${overstay_duration}</strong>
                    </div>`;
			} else if (diff_minutes <= 60) {
				// Checkout is within the next hour
				checkout_warning_style = "background-color: #ffcdd2;"; // A lighter red
			}
		}

		return `
                <div class="card" style="${card_style} ${checkout_warning_style}">
                    <div class="card-body">
                        <h5 class="card-title">
                            ${room.room_number}
                           
                            <span class="float-right">
                                <i class="fa fa-${housekeeping_icon}"
                                   title="${room.housekeeping_status}"></i>
                            </span>
                        </h5>
                        <div class="card-text">
                            <div>${room.room_type}</div>
                            <div class="text-muted">${room.floor || ""}</div>
                            ${
								room.current_guest
									? `
                                <div class="mt-2">
                                    <strong>Guest:</strong> ${room.current_guest}<br>
                                    <small>Checkout: ${room.expected_check_out_datetime ? frappe.datetime.str_to_user(room.expected_check_out_datetime) : "N/A"}</small>
                                </div>
                                <div class="overdue-container">${overdue_html}</div>
                            `
									: ""
							}
                            ${
								room.upcoming_guest
									? `
                                <div class="mt-2">
                                    <strong>Reserved:</strong> ${room.upcoming_guest}<br>
                                    <small>Check-in: ${room.check_in_date ? frappe.datetime.str_to_user(room.check_in_date) : "N/A"}</small>
                                </div>
                            `
									: ""
							}
                            ${
								room.maintenance_request
									? `
                                <div class="mt-2 text-danger">
                                    <i class="fa fa-tools"></i> Under maintenance
                                </div>
                            `
									: ""
							}
                        </div>
                    </div>
                </div>`;
	}

	get_stat_card(label, value, icon, color, route_options = null) {
		const $card = $(
			`<div class="stat-card">
                <div class="card" style="background-color: var(--${color}-100)">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <h5 class="card-title">${value}</h5>
                                <p class="card-text text-muted">${label}</p>
                            </div>
                            <div class="avatar avatar-lg" style="background-color: var(--${color}-200)">
                                <i class="fa fa-${icon} fa-2x" style="color: var(--${color}-600)"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`,
		);

		if (route_options) {
			$card.on("click", () => {
				if (label === "Reserved Today") {
					frappe.set_route("List", "Hotel Room Reservation", {
						from_date: frappe.datetime.get_today(),
					});
				} else {
					frappe.set_route("List", "Hotel Room", route_options);
				}
			});
			$card.css("cursor", "pointer");
		}
		return $card;
	}

	refresh() {
		this.render_current_view();
	}

	switch_view(view_name) {
		this.current_view = view_name;

		// Update button styles
		this.$view_switcher.find("button").removeClass("btn-primary").addClass("btn-default");
		this.$view_switcher
			.find(`button[data-view="${view_name}"]`)
			.removeClass("btn-default")
			.addClass("btn-primary");

		this.render_current_view();
	}

	render_current_view() {
		this.page.main.find(".view-container").hide();
		const $filter_area = this.page.main.find(".page-form");

		if (this.current_view === "room_view") {
			$filter_area.show();
			this.$room_grid.show();
			this.refresh_stats();
			this.refresh_rooms();
		} else if (this.current_view === "check_in_view") {
			$filter_area.hide();
			this.refresh_stats();
			this.render_check_in_view();
		} else if (this.current_view === "guest_list_view") {
			$filter_area.hide();
			this.refresh_stats();
			this.render_guest_list_view();
		} else if (this.current_view === "check_out_view") {
			$filter_area.hide();
			this.refresh_stats();
			this.render_check_out_view();
		} else if (this.current_view === "reservation_view") {
			$filter_area.hide();
			this.refresh_stats();
			this.render_reservation_view();
		} else if (this.current_view === "housekeeping_view") {
			$filter_area.hide();
			this.render_housekeeping_view();
		} else if (this.current_view === "payments_view") {
			$filter_area.hide();
			this.refresh_stats();
			this.render_payments_view();
		} else if (this.current_view === "room_stay_report") {
			$filter_area.hide();
			this.render_room_stay_report();
		} else if (this.current_view === "night_audit_view") {
			$filter_area.hide();
			this.render_night_audit_view();
		} else if (this.current_view === "corporate_reservations_view") {
			$filter_area.hide();
			this.refresh_stats();
			this.render_corporate_reservations_view();
		} else if (this.current_view === "hall_booking_view") {
			$filter_area.hide();
			this.render_hall_booking_view();
		} else if (this.current_view === "available_rooms_view") {
			$filter_area.hide();
			this.render_available_rooms_view();
		} else {
			$filter_area.hide();
			this.refresh_stats(); // Stats are always visible
			let $view = this.page.main.find(`[data-view-name="${this.current_view}"]`);
			if (!$view.length) {
				$view = $(
					`<div class="view-container" data-view-name="${this.current_view}" style="padding: 1rem 0;"></div>`,
				).appendTo(this.page.main);
			}
			$view.show();
			this.render_placeholder_view($view);
		}
	}

	render_placeholder_view($container) {
		const view_name = $container.data("view-name");
		const titles = {
			check_in_view: "Check-in List",
			guest_list_view: "Guest List",
			check_out_view: "Check-out List",
		};
		$container.html(`
            <div class="frappe-card">
                <div class="frappe-card-head"><h4>${titles[view_name] || "View"}</h4></div>
                <div class="frappe-card-body">
                    <p class="text-muted">This view is under construction. The list of ${view_name.split("_")[0]}s will appear here.</p>
                </div>
            </div>`);
	}

	render_check_in_view() {
		let $view = this.page.main.find(`[data-view-name="check_in_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="check_in_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Check-ins...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_check_in_list",
			callback: (r) => {
				const check_ins = r.message;
				let table_content;

				if (!check_ins || check_ins.length === 0) {
					table_content = `<p class="text-muted">No guests are currently checked in.</p>`;
					$view.html(
						`<div class="frappe-card"><div class="frappe-card-body">${table_content}</div></div>`,
					);
				} else {
					const rows = check_ins
						.map(
							(ci) => `
                        <tr>
                            <td><a href="/app/hotel-room-check-in/${ci.check_in_id}">${ci.check_in_id}</a></td>
                            <td><a href="/app/hotel-guest/${ci.guest}">${ci.guest}</a></td>
                            <td>${ci.room_number}</td>
                            <td>${frappe.datetime.str_to_user(ci.check_in_datetime)}</td>
                            <td>${frappe.datetime.str_to_user(ci.expected_check_out_datetime)}</td>
                            <td class="text-right">${frappe.format(ci.total_invoice_amount, { fieldtype: "Currency" })}</td>
                            <td class="text-right">${frappe.format(ci.total_payment_amount, { fieldtype: "Currency" })}</td>
                            <td class="text-right">${frappe.format(ci.balance, { fieldtype: "Currency" })}</td>
                            <td class="text-center">
                                ${ci.phone_number ? `<a href="tel:${ci.phone_number}" title="${ci.phone_number}" class="btn btn-xs btn-default"><i class="fa fa-phone"></i></a>` : ""}
                                ${ci.email_id ? `<a href="mailto:${ci.email_id}" title="${ci.email_id}" class="btn btn-xs btn-default"><i class="fa fa-envelope"></i></a>` : ""}
                            </td>
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="check_in_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Check-in ID</th>
                                    <th>Guest</th>
                                    <th>Room</th>
                                    <th>Check-in</th>
                                    <th>Expected Check-out</th>
                                    <th class="text-right">Total Invoice</th>
                                    <th class="text-right">Total Payment</th>
                                    <th class="text-right">Balance</th>
                                    <th class="text-center">Contact</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

					$view.html(
						`<div class="frappe-card"><div class="frappe-card-body">${table_content}</div></div>`,
					);

					// Initialize DataTable
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#check_in_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									order: [[3, "asc"]], // Order by Check-in datetime ascending
									language: {
										search: "Filter:",
										lengthMenu: "Show _MENU_ entries",
									},
									dom: "Bfrtip",
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	render_guest_list_view() {
		let $view = this.page.main.find(`[data-view-name="guest_list_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="guest_list_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Guest List...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_guest_list",
			callback: (r) => {
				const guests = r.message;
				let table_content;

				if (!guests || guests.length === 0) {
					table_content = `<p class="text-muted">No guest history found.</p>`;
				} else {
					const rows = guests
						.map(
							(g) => `
                        <tr>
                            <td><a href="/app/hotel-guest/${g.guest}">${g.guest}</a></td>
                            <td class="text-center">${g.number_of_stays}</td>
                            <td class="text-right">${frappe.format(g.total_revenue, { fieldtype: "Currency" })}</td>
                            <td>${g.market_place || ""}</td>
                            <td>${frappe.datetime.str_to_user(g.last_stay)}</td>
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="guest_list_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Guest</th>
                                    <th class="text-center">Number of Stays</th>
                                    <th class="text-right">Total Revenue</th>
                                    <th>Market Place</th>
                                    <th>Last Stay</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;
				}

				const card_header = `<div class="frappe-card-head"><h4>Guest List</h4></div>`;
				const card_body = `<div class="frappe-card-body">${table_content}</div>`;
				$view.html(`<div class="frappe-card">${card_header}${card_body}</div>`);

				// Initialize DataTable
				if (guests && guests.length > 0) {
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#guest_list_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									dom: "Bfrtip",
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	render_check_out_view() {
		let $view = this.page.main.find(`[data-view-name="check_out_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="check_out_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading today's check-outs...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_check_out_list",
			callback: (r) => {
				const check_outs = r.message;
				let table_content;

				if (!check_outs || check_outs.length === 0) {
					table_content = `<p class="text-muted">No guests are scheduled to check out today.</p>`;
					const card_header = `<div class="frappe-card-head"><h4>Check-out List</h4></div>`;
					const card_body = `<div class="frappe-card-body">${table_content}</div>`;
					$view.html(`<div class="frappe-card">${card_header}${card_body}</div>`);
				} else {
					const rows = check_outs
						.map(
							(co) => `
                        <tr>
                            <td><a href="/app/hotel-guest/${co.guest}">${co.guest_name}</a></td>
                            <td>${co.room_number}</td>
                            <td>${frappe.datetime.str_to_user(co.check_in_datetime)}</td>
                            <td>${frappe.datetime.str_to_user(co.check_out_datetime)}</td>
                            <td class="text-right">${frappe.format(co.balance, { fieldtype: "Currency" })}</td>
                            <td>
                                <a href="/app/hotel-room-check-in/${co.check_in}" class="btn btn-xs btn-default">View Check-in</a>
                            </td>
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="check_out_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Guest</th>
                                    <th>Room</th>
                                    <th>Check-in Time</th>
                                    <th>Check-out Time</th>
                                    <th class="text-right">Balance</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

					const card_header = `<div class="frappe-card-head"><h4>Check-out List</h4></div>`;
					const card_body = `<div class="frappe-card-body">${table_content}</div>`;
					$view.html(`<div class="frappe-card">${card_header}${card_body}</div>`);

					// Initialize DataTable
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#check_out_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									order: [[3, "asc"]],
									dom: "Bfrtip",
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	render_reservation_view() {
		let $view = this.page.main.find(`[data-view-name="reservation_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="reservation_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Reservations...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_reservation_list",
			callback: (r) => {
				const reservations = r.message;
				let table_content;

				if (!reservations || reservations.length === 0) {
					table_content = `<p class="text-muted">No reservations found.</p>`;
					$view.html(`<div class="frappe-card"><div class="frappe-card-head">
                        <h4>Reservations</h4>
                        
                        </div><div class="frappe-card-body">${table_content}</div></div>`);
				} else {
					const rows = reservations
						.map(
							(res) => `
                        <tr>
                            <td><a href="/app/hotel-room-reservation/${res.name}">${res.name}</a></td>
                            <td>${res.guest_name}</td>
                            <td><a href="/app/hotel-room/${res.room_number}">${res.room_number}</a></td>
                            <td>${frappe.datetime.str_to_user(res.from_date)}</td>
                            <td>${frappe.datetime.str_to_user(res.to_date)}</td>
                            <td>${res.status}</td>
                           
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="reservation_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Reservation ID</th>
                                    <th>Guest</th>
                                    <th>Room</th>
                                    <th>From Date</th>
                                    <th>To Date</th>
                                    <th>Status</th>
                                   
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

					$view.html(`<div class="frappe-card"><div class="frappe-card-head">
                        <h4>Reservations</h4>
                        <a href="/app/hotel-room-reservation/new" class="btn btn-primary btn-sm">New Reservation</a>
                        </div><div class="frappe-card-body">${table_content}</div></div>`);

					// Initialize DataTable
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#reservation_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									dom: "Bfrtip",
									order: [[3, "asc"]],
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	fetch_and_display_available_rooms(checkInDate, checkOutDate, roomType, $container) {
		$container.html(
			`<div class="text-muted text-center" style="padding: 2rem;">Loading available rooms...</div>`,
		);

		frappe.call({
			method: "rhohotel.api.get_available_rooms",
			args: {
				from_date: checkInDate,
				to_date: checkOutDate,
				room_type: roomType || null,
			},
			callback: (r) => {
				if (!r.message || r.message.length === 0) {
					$container.html(`
                        <div class="alert alert-info" style="text-align: center; padding: 2rem;">
                            <i class="fa fa-info-circle"></i>
                            <p>No rooms available for the selected dates and room type.</p>
                        </div>
                    `);
					return;
				}

				const rooms = r.message;
				const numNights = moment(checkOutDate).diff(moment(checkInDate), "days");

				// Group rooms by room type for better organization
				const roomsByType = {};
				rooms.forEach((room) => {
					if (!roomsByType[room.room_type]) {
						roomsByType[room.room_type] = [];
					}
					roomsByType[room.room_type].push(room);
				});

				let html = `<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem;">`;

				Object.keys(roomsByType).forEach((roomType) => {
					roomsByType[roomType].forEach((room) => {
						html += `
                            <div class="available-room-card" style="border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: all 0.3s ease; cursor: pointer;" data-room="${room.name}">
                                <div style="background:black; color: white; padding: 1rem; color:white;">
                                    <h4 style="margin: 0; font-size: 1.5rem; font-weight: bold; color:white !important;">${room.name}</h4>
                                    <p style="margin: 0.25rem 0 0 0; font-size: 0.9rem; opacity: 0.9;">${room.room_type}</p>
                                </div>
                                <div style="padding: 1.5rem;">
                                   

                                    <div style="margin-bottom: 1rem; display: flex; justify-content: space-between;">
                                        <div>
                                            <p style="font-size: 0.85rem; color: #666; margin: 0 0 0.5rem 0;">Floor</p>
                                            <p style="font-weight: 600; margin: 0;">${room.floor || "N/A"}</p>
                                        </div>

                                        <div style="text-align: right;">
                                            <p style="font-size: 0.85rem; color: #666; margin: 0 0 0.5rem 0;">Capacity</p>
                                            <p style="font-weight: 600; margin: 0;">${room.capacity || "N/A"} guests</p>
                                        </div>
                                    </div>


                                    
                                    <hr style="margin: 1rem 0; border: none; border-top: 1px solid #eee;">
                                   <div style="display:flex; justify-content: space-between; margin-bottom: 1rem;">
                                        <p style="font-size: 0.85rem; color: #666; margin: 0 0 0.5rem 0;">Price per night</p>
                                        <h5 style="margin: 0; font-size: 1.3rem; color: #black; font-weight: bold;">${frappe.format(room.rate_per_night, { fieldtype: "Currency" })}</h5>
                                    </div>
                                    <div style="background-color: #f5f5f5; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem;">
                                        <p style="font-size: 0.85rem; color: #666; margin: 0 0 0.25rem 0;">Total (${numNights} nights)</p>
                                        <h5 style="margin: 0; font-size: 1.1rem; font-weight: bold; color: #2c3e50;">${frappe.format(room.total_amount, { fieldtype: "Currency" })}</h5>
                                    </div>
                                    <button class="btn btn-default btn-block view-room-btn" data-room="${room.name}" style="width: 100%; padding: 0.75rem; border-radius: 4px;">
                                        <i class="fa fa-info-circle"></i> Room Details
                                    </button>
                                </div>
                            </div>
                        `;
					});
				});

				html += `</div>`;

				// Add summary info at the top
				const summaryHtml = `
                    <div style="background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 1rem; border-radius: 4px; margin-bottom: 1.5rem;">
                        <p style="margin: 0; color: #1976d2; font-weight: 600;">
                            <i class="fa fa-check-circle"></i> 
                            ${rooms.length} room(s) available for ${numNights} night(s) (${moment(checkInDate).format("MMM DD")} - ${moment(checkOutDate).format("MMM DD")})
                        </p>
                    </div>
                `;

				$container.html(summaryHtml + html);

				// Bind book room buttons
				$container.find(".book-room-btn").on("click", function () {
					const roomNumber = $(this).data("room");
					const room = rooms.find((r) => r.name === roomNumber);
					if (room) {
						frappe.new_doc("Hotel Room Check In", {
							room_number: room.name,
							check_in_date: checkInDate,
						});
					}
				});

				// Bind view room details buttons
				$container.find(".view-room-btn").on("click", function () {
					const roomNumber = $(this).data("room");
					frappe.set_route("Form", "Hotel Room", roomNumber);
				});

				// Add hover effect
				$container
					.find(".available-room-card")
					.on("mouseenter", function () {
						$(this).css("box-shadow", "0 8px 16px rgba(0,0,0,0.15)");
						$(this).css("transform", "translateY(-4px)");
					})
					.on("mouseleave", function () {
						$(this).css("box-shadow", "0 2px 4px rgba(0,0,0,0.1)");
						$(this).css("transform", "translateY(0)");
					});
			},
			error: (err) => {
				$container.html(`
                    <div class="alert alert-danger">
                        <i class="fa fa-exclamation-circle"></i> Error loading available rooms. Please try again.
                    </div>
                `);
				console.error(err);
			},
		});
	}

	render_available_rooms_view() {
		let $view = this.page.main.find(`[data-view-name="available_rooms_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="available_rooms_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();

		// Get today's date and add 1 day as default
		const today = frappe.datetime.get_today();
		const tomorrow = frappe.datetime.add_days(today, 1);

		// Create filter HTML
		const filterHtml = `
            <div class="available-rooms-filters" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; padding: 1.5rem; background-color: #f9f9f9; border-radius: 8px; border: 1px solid #e0e0e0;">
                <div>
                    <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem;">Check-in Date</label>
                    <input type="date" id="available_check_in_date" value="${today}" style="padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box; font-size: 1rem;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem;">Check-out Date</label>
                    <input type="date" id="available_check_out_date" value="${tomorrow}" style="padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box; font-size: 1rem;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem;">Room Type</label>
                    <select id="available_room_type_filter" style="padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box; font-size: 1rem;">
                        <option value="">All Room Types</option>
                    </select>
                </div>
                <div style="display: flex; align-items: flex-end; gap: 0.75rem;">
                    <button id="available_rooms_search" class="btn btn-primary" style="flex: 1; padding: 0.75rem;">
                        <i class="fa fa-search"></i> Search Available Rooms
                    </button>
                </div>
            </div>
        `;

		// Set initial HTML with filters and empty results container
		$view.html(`
            <div class="frappe-card">
                <div class="frappe-card-head">
                    <h4>Available Rooms</h4>
                </div>
                <div class="frappe-card-body">
                    ${filterHtml}
                    <div id="available_rooms_container"></div>
                </div>
            </div>
        `);

		// Populate room types
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Hotel Room Type",
				fields: ["name"],
				limit_page_length: 0,
			},
			callback: (r) => {
				if (r.message) {
					const roomTypeSelect = $view.find("#available_room_type_filter");
					r.message.forEach((rt) => {
						roomTypeSelect.append(`<option value="${rt.name}">${rt.name}</option>`);
					});
				}
			},
		});

		// Bind search button
		$view.find("#available_rooms_search").on("click", () => {
			const checkInDate = $view.find("#available_check_in_date").val();
			const checkOutDate = $view.find("#available_check_out_date").val();
			const roomType = $view.find("#available_room_type_filter").val();

			if (!checkInDate || !checkOutDate) {
				frappe.msgprint(__("Please select both check-in and check-out dates"));
				return;
			}

			if (checkOutDate <= checkInDate) {
				frappe.msgprint(__("Check-out date must be after check-in date"));
				return;
			}

			this.fetch_and_display_available_rooms(
				checkInDate,
				checkOutDate,
				roomType,
				$view.find("#available_rooms_container"),
			);
		});

		// Auto-search on date/room type change
		$view
			.find(
				"#available_check_in_date, #available_check_out_date, #available_room_type_filter",
			)
			.on("change", () => {
				$view.find("#available_rooms_search").click();
			});
	}

	refresh_stats() {
		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_room_statistics",
			callback: (r) => {
				this.$stats.empty();
				const stats = r.message;
				this.$stats.append(
					this.get_stat_card("Vacant Rooms", stats.vacant, "bed", "green", {
						status: "Vacant",
					}),
				);
				this.$stats.append(
					this.get_stat_card("Occupied Rooms", stats.occupied, "user", "blue", {
						status: "Occupied",
					}),
				);
				this.$stats.append(
					this.get_stat_card("Reserved Today", stats.reserved, "calendar", "orange", {
						status: "Reserved",
					}),
				);
				this.$stats.append(
					this.get_stat_card("Dirty Rooms", stats.dirty, "trash", "yellow", {
						housekeeping_status: "Dirty",
					}),
				);
				this.$stats.append(
					this.get_stat_card("In Maintenance", stats.maintenance, "wrench", "red", {
						status: "Maintenance",
					}),
				);
			},
		});
	}

	refresh_rooms() {
		const filters = this.page.get_form_values();
		this.filters = filters;

		// If checkout_today is checked, add today's date to the filters
		if (filters.checkout_today) {
			filters.today_date = frappe.datetime.get_today();
		}

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_rooms",
			args: { filters: filters },
			callback: (r) => {
				const rooms = r.message;
				this.rooms = rooms; // Store rooms for real-time updates
				this.$room_grid.empty();

				if (rooms.length === 0) {
					this.$room_grid.html(
						'<p class="text-muted text-center" style="padding: 2rem 0;">No rooms found.</p>',
					);
					return;
				}

				rooms.forEach((room) => {
					const $card = this.get_room_card(room);
					this.$room_grid.append($card);

					$card.click(() => {
						this.show_room_actions(room);
					});
				});
			},
		});
	}

	start_clock() {
		setInterval(() => {
			this.$clock.text(frappe.datetime.now_datetime());
		}, 1000);
	}

	start_timer_updates() {
		setInterval(() => {
			this.update_room_card_timers();
		}, 60 * 1000); // Run every minute
	}

	update_room_card_timers() {
		if (!this.rooms || this.rooms.length === 0) return;

		const now = moment();

		this.rooms.forEach((room) => {
			if (room.status === "Occupied" && room.expected_check_out_datetime) {
				const $card = this.$room_grid.find(`.room-card[data-name="${room.name}"] .card`);
				if (!$card.length) return;

				const checkout_time = moment(room.expected_check_out_datetime);
				const diff_minutes = checkout_time.diff(now, "minutes");

				let new_style = "";
				let overdue_html = "";

				if (diff_minutes < 0) {
					new_style = "background-color: #ef9a9a;"; // Darker red
					const overstay_duration = moment.duration(now.diff(checkout_time)).humanize();
					overdue_html = `<div class="mt-2 text-danger blink-me overdue-message"><strong>Overdue by ${overstay_duration}</strong></div>`;
				} else if (diff_minutes <= 60) {
					new_style = "background-color: #ffcdd2;"; // Lighter red
				}

				$card.css(
					"background-color",
					new_style ? new_style.split(":")[1].replace(";", "") : "",
				);
				$card.find(".overdue-container").html(overdue_html);
			}
		});
	}

	show_room_actions(room) {
		const self = this;
		const actions = [];

		if (room.status === "Vacant" && room.housekeeping_status === "Clean") {
			actions.push({
				label: `New Check-in`,
				action: () =>
					frappe.new_doc("Hotel Room Check In", { room_number: room.room_number }),
			});
		}

		if (room.status === "Occupied") {
			actions.push({
				label: "Check-out",
				action: () => {
					frappe.call({
						method: "rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out",
						args: {
							source_name: room.current_check_in,
						},
						callback: (r) => {
							if (r.message) {
								frappe.set_route("Form", "Hotel Room Check Out", r.message.name);
							}
						},
					});
				},
			});
			if (room.current_check_in) {
				actions.push({
					label: "Open Check-in",
					action: () =>
						frappe.set_route("Form", "Hotel Room Check In", room.current_check_in),
				});
			}
		}

		if (room.status === "Reserved") {
			// Action to create check-in from reservation
		}

		actions.push({
			label: "Maintenance Request",
			action: () => frappe.new_doc("Maintenance Request", { room: room.name }),
		});

		actions.push({
			label: "Housekeeping Request",
			action: () =>
				frappe.new_doc("Housekeeping Request", {
					room: room.name,
					request_date: frappe.datetime.get_today(),
					requested_by: "Front Desk",
				}),

		// Add quick action to mark room as clean
		
		});

        if (room.housekeeping_status !== 'Clean') {
			actions.push({
				label: 'Mark as Clean',
				action: () => {
					frappe.call({
						method: 'frappe.client.set_value',
						args: {
							doctype: 'Hotel Room',
							name: room.name,
							fieldname: 'housekeeping_status',
							value: 'Clean'
						},
						callback: (r) => {
							frappe.msgprint(__('Room marked as Clean'));
							// notify other users and refresh UI
							frappe.publish_realtime('rhohotel_front_desk_update');
							this.refresh();
						}
					});
				}
			});
		}

		actions.push({
			label: "Make Reservation",
			action: () =>
				frappe.new_doc("Hotel Room Reservation", { room_number: room.room_number }),
		});

		actions.push({
			label: "Room Details",
			action: () => frappe.set_route("Form", "Hotel Room", room.name),
		});

		const dialog_fields = [];

        dialog_fields.push(
			{
				fieldtype: "Section Break",
				label: "Room Details",
			},

			// Row 1 - Column 1
			{
				fieldtype: "Data",
				label: "Room Type",
				default: room.room_type,
				read_only: 1,
			},

			// Row 1 - Column 2
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Data",
				label: "Floor",
				default: room.floor,
				read_only: 1,
			},

			// Row 2
			{
				fieldtype: "Section Break",
			},

			// Row 2 - Column 1
			{
				fieldtype: "Data",
				label: "Status",
				default: room.status,
				read_only: 1,
			},

			// Row 2 - Column 2
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Data",
				label: "Housekeeping",
				default: room.housekeeping_status,
				read_only: 1,
			},
		);

		if (room.status === "Occupied") {
			dialog_fields.push({
				fieldtype: "Section Break",
				label: "Current Check-in Details",
			});

			// First column
			dialog_fields.push({
				fieldtype: "Data",
				label: "Guest",
				default: room.current_guest,
				read_only: 1,
			});

			dialog_fields.push({
				fieldtype: "Data",
				label: "Check-in Time",
				default: room.check_in_datetime
					? frappe.datetime.str_to_user(room.check_in_datetime)
					: "N/A",
				read_only: 1,
			});

			// 👇 THIS is what you were missing
			dialog_fields.push({
				fieldtype: "Column Break",
			});

			// Second column
			dialog_fields.push({
				fieldtype: "Data",
				label: "Expected Check-out",
				default: room.expected_check_out_datetime
					? frappe.datetime.str_to_user(room.expected_check_out_datetime)
					: "N/A",
				read_only: 1,
			});

			// Invoices section
			if (room.current_check_in) {
				dialog_fields.push({
					fieldtype: "Section Break",
				});

				dialog_fields.push({
					fieldtype: "HTML",
					fieldname: "invoices_html",
					options: `<div id="invoices_container_${room.current_check_in}" class="invoices-container">
                        Loading invoices...
                      </div>`,
				});
			}
		}

		

		// Add a section for actions at the bottom
		dialog_fields.push({
			fieldtype: "Section Break",
			label: "Actions",
		});

		dialog_fields.push({
			fieldtype: "HTML",
			fieldname: "actions_html",
			options: this.get_actions_html(actions),
		});

		const dialog = new frappe.ui.Dialog({
			title: `Room ${room.room_number}`,
			fields: dialog_fields,
			size: "large",
		});

		// Bind click events for action buttons
		actions.forEach((act, index) => {
			dialog.$wrapper.find(`[data-action-index="${index}"]`).on("click", () => {
				act.action();
				dialog.hide();
			});
		});

		dialog.show();

		// If occupied and has a check-in, load invoices and render payment form
		if (room.status === "Occupied" && room.current_check_in) {
			const container_selector = `#invoices_container_${room.current_check_in}`;
			const $invContainer = dialog.$wrapper.find(container_selector);
			if ($invContainer.length) {
				$invContainer.html('<div class="text-muted">Loading invoices...</div>');

				frappe.call({
					method: "rhohotel.rhocom_hotel.api.front_desk.get_checkin_invoice_list",
					args: { check_in: room.current_check_in },
					callback: (r) => {
						const data = r.message || {
							invoices: [],
							total_invoiced: 0,
							total_outstanding: 0,
						};
						const invoices = data.invoices || [];

						const invoice_rows = invoices
							.map((inv) => {
								return `<tr data-invoice="${inv.name}">
                                <td><input type="checkbox" class="inv-checkbox" data-name="${inv.name}" data-outstanding="${inv.outstanding_amount}"></td>
                                <td><a href="/app/sales-invoice/${inv.name}" target="_blank">${inv.name}</a></td>
                                <td>${frappe.format(inv.grand_total, { fieldtype: "Currency" })}</td>
                                <td>${frappe.format(inv.outstanding_amount, { fieldtype: "Currency" })}</td>
                            </tr>`;
							})
							.join("");

						const invoices_table = `
                            <div class="frappe-card">
                                <div class="frappe-card-head"><h5>Invoices</h5></div>
                                <div class="frappe-card-body">
                                    <div class="table-responsive">
                                        <table class="table table-sm table-bordered">
                                            <thead>
                                                <tr><th style="width:32px;"></th><th>Invoice</th><th class="text-right">Total</th><th class="text-right">Outstanding</th></tr>
                                            </thead>
                                            <tbody>
                                                ${invoice_rows || '<tr><td colspan="4" class="text-muted text-center">No invoices found</td></tr>'}
                                            </tbody>
                                        </table>
                                    </div>
                                    <div class="controls-row">
                                        <div class="control-left">
                                            <label style="margin:0; font-weight:600;">Mode</label>
                                            <select id="modal_payment_mode_${room.current_check_in}" class="form-control" style="width:160px;">
                                                <option value="Cash">Cash</option>
                                                <option value="Card">Card</option>
                                                <option value="Bank">Bank Transfer</option>
                                            </select>
                                            <label style="margin:0 0 0 8px; font-weight:600;">Amount</label>
                                            <input id="modal_payment_amount_${room.current_check_in}" class="form-control" style="width:140px;" />
                                            <input id="modal_payment_ref_${room.current_check_in}" class="form-control" placeholder="Reference (optional)" style="width:200px;" />
                                        </div>
                                        <div class="control-right">
                                            <button class="btn btn-primary btn-sm" id="pay_selected_${room.current_check_in}"><i class="fa fa-credit-card"></i> Pay Selected</button>
                                            <button class="btn btn-success btn-sm" id="pay_all_${room.current_check_in}"><i class="fa fa-check"></i> Pay All</button>
                                            <button class="btn btn-danger btn-sm" id="checkout_${room.current_check_in}"><i class="fa fa-sign-out"></i> Checkout</button>
                                        </div>
                                    </div>
                                    <div class="totals">Total invoiced: ${frappe.format(data.total_invoiced || 0, { fieldtype: "Currency" })} <span>Outstanding: ${frappe.format(data.total_outstanding || 0, { fieldtype: "Currency" })}</span></div>
                                </div>
                            </div>
                        `;

						$invContainer.html(invoices_table);

						// helper to compute selected total
						function compute_selected_total() {
							let total = 0;
							$invContainer.find(".inv-checkbox:checked").each(function () {
								total += parseFloat($(this).data("outstanding") || 0);
							});
							return total;
						}

						// update amount when checkboxes change
						$invContainer.on("change", ".inv-checkbox", function () {
							const total = compute_selected_total();
							$invContainer
								.find(`#modal_payment_amount_${room.current_check_in}`)
								.val(frappe.format(total, { fieldtype: "Currency" }));
						});

						// Pay Selected
						$invContainer
							.find(`#pay_selected_${room.current_check_in}`)
							.on("click", function () {
								const allocations = [];
								$invContainer.find(".inv-checkbox:checked").each(function () {
									allocations.push({
										invoice: $(this).data("name"),
										amount: $(this).data("outstanding"),
									});
								});
								if (allocations.length === 0) {
									frappe.msgprint(__("Please select at least one invoice"));
									return;
								}
								const amountVal = $invContainer
									.find(`#modal_payment_amount_${room.current_check_in}`)
									.val();
								const payment_info = {
									mode_of_payment: $invContainer
										.find(`#modal_payment_mode_${room.current_check_in}`)
										.val(),
									paid_amount: amountVal,
									reference_no: $invContainer
										.find(`#modal_payment_ref_${room.current_check_in}`)
										.val(),
								};

								frappe.call({
									method: "rhohotel.rhocom_hotel.api.front_desk.collect_payment_for_checkin",
									args: {
										check_in: room.current_check_in,
										allocations: JSON.stringify(allocations),
										payment_info: JSON.stringify(payment_info),
									},
									callback: (res) => {
										frappe.msgprint(__("Payment recorded"));
										// open receipt if available
										const pe = res.message && res.message.payment_entry;
										if (pe) {
											frappe.call({
												method: "rhohotel.rhocom_hotel.api.front_desk.create_payment_receipt",
												args: { payment_entry: pe },
												callback: (r2) => {
													if (r2.message && r2.message.print_url) {
														window.open(
															r2.message.print_url,
															"_blank",
														);
													}
												},
											});
										}
										self.refresh();
										dialog.hide();
									},
								});
							});

						// Pay All
						$invContainer
							.find(`#pay_all_${room.current_check_in}`)
							.on("click", function () {
								const allocations = invoices.map((inv) => ({
									invoice: inv.name,
									amount: inv.outstanding_amount,
								}));
								if (allocations.length === 0) {
									frappe.msgprint(__("No outstanding invoices to pay"));
									return;
								}
								const total = allocations.reduce((s, a) => s + (a.amount || 0), 0);
								const payment_info = {
									mode_of_payment: $invContainer
										.find(`#modal_payment_mode_${room.current_check_in}`)
										.val(),
									paid_amount: total,
									reference_no: $invContainer
										.find(`#modal_payment_ref_${room.current_check_in}`)
										.val(),
								};

								frappe.call({
									method: "rhohotel.rhocom_hotel.api.front_desk.collect_payment_for_checkin",
									args: {
										check_in: room.current_check_in,
										allocations: JSON.stringify(allocations),
										payment_info: JSON.stringify(payment_info),
									},
									callback: (res) => {
										frappe.msgprint(__("Payment recorded"));
										const pe = res.message && res.message.payment_entry;
										if (pe) {
											frappe.call({
												method: "rhohotel.rhocom_hotel.api.front_desk.create_payment_receipt",
												args: { payment_entry: pe },
												callback: (r2) => {
													if (r2.message && r2.message.print_url) {
														window.open(
															r2.message.print_url,
															"_blank",
														);
													}
												},
											});
										}
										self.refresh();
										dialog.hide();
									},
								});
							});

						// Checkout (attempt to collect outstanding then checkout)
						$invContainer
							.find(`#checkout_${room.current_check_in}`)
							.on("click", function () {
								// attempt pay all then checkout in one call
								const allocations = invoices.map((inv) => ({
									invoice: inv.name,
									amount: inv.outstanding_amount,
								}));
								const total = allocations.reduce((s, a) => s + (a.amount || 0), 0);
								const payment_info = {
									mode_of_payment: $invContainer
										.find(`#modal_payment_mode_${room.current_check_in}`)
										.val(),
									paid_amount: total,
									reference_no: $invContainer
										.find(`#modal_payment_ref_${room.current_check_in}`)
										.val(),
								};

								frappe.call({
									method: "rhohotel.rhocom_hotel.api.front_desk.collect_payment_and_checkout",
									args: {
										check_in: room.current_check_in,
										allocations: JSON.stringify(allocations),
										payment_info: JSON.stringify(payment_info),
										force_checkout: false,
									},
									callback: (res) => {
										frappe.msgprint(__("Checkout completed"));
										self.refresh();
										dialog.hide();
									},
									error: (err) => {
										// If error due to outstanding and user wants force checkout, show confirm
										const msg =
											(err &&
												err.responseJSON &&
												err.responseJSON.message) ||
											"Checkout failed";
										frappe.confirm(
											msg + "<br/><br/>Force checkout (manager)?",
											() => {
												// on confirm, call with force_checkout true (caller must have manager role)
												frappe.call({
													method: "rhohotel.rhocom_hotel.api.front_desk.collect_payment_and_checkout",
													args: {
														check_in: room.current_check_in,
														allocations: JSON.stringify(allocations),
														payment_info: JSON.stringify(payment_info),
														force_checkout: true,
													},
													callback: (res2) => {
														frappe.msgprint(
															__("Force checkout completed"),
														);
														self.refresh();
														dialog.hide();
													},
												});
											},
										);
									},
								});
							});
					},
				});
			}
		}
	}

	get_actions_html(actions) {
		const buttons_html = actions
			.map((act, index) => {
				const icon_map = {
					"New Check-in": "sign-in",
					"Check-out": "sign-out",
					"Open Check-in": "folder-open",
					"Maintenance Request": "wrench",
					"Housekeeping Request": "tasks",
					"Mark as Clean": "check",
					"Room Details": "info-circle",
				};

				const button_color_map = {
					"New Check-in": "btn-primary",
					"Check-out": "btn-danger",
					"Open Check-in": "btn-info",
					"Maintenance Request": "btn-warning",
					"Housekeeping Request": "btn-success",
					"Mark as Clean": "btn-success",
					"Room Details": "btn-default",
				};

				const icon = icon_map[act.label] || "hand-pointer-o";
				const color = button_color_map[act.label] || "btn-default";

				return `
            <button class="btn btn-sm ${color}" data-action-index="${index}" style="margin: 0.25rem;">
                <i class="fa fa-${icon}"></i> ${act.label}
            </button>
        `;
			})
			.join("");

		return `
        <div style="display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.5rem;">
            ${buttons_html}
        </div>
    `;
	}

	render_housekeeping_view() {
		let $view = this.page.main.find(`[data-view-name="housekeeping_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="housekeeping_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Housekeeping Queue...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_housekeeping_queue",
			callback: (r) => {
				const tasks = r.message;
				let table_content;

				if (!tasks || tasks.length === 0) {
					table_content = `<p class="text-muted">All rooms are clean!</p>`;
					$view.html(
						`<div class="frappe-card"><div class="frappe-card-head"><h4>Housekeeping Queue</h4></div><div class="frappe-card-body">${table_content}</div></div>`,
					);
				} else {
					const priority_icons = {
						"In Progress": "spinner fa-spin",
						Dirty: "trash",
						Inspected: "eye",
						Clean: "check",
					};

					const rows = tasks
						.map(
							(task) => `
                        <tr>
                            <td><strong>${task.room_number}</strong></td>
                            <td>${task.floor || "-"}</td>
                            <td>${task.room_type}</td>
                            <td>
                                <span style="padding: 0.25rem 0.75rem; background-color: ${task.priority <= 2 ? "#ffe0e0" : "#e8f5e9"}; border-radius: 4px;">
                                    <i class="fa fa-${priority_icons[task.housekeeping_status] || "question"}"></i> ${task.housekeeping_status}
                                </span>
                            </td>
                            <td class="text-right">
                                <a href="/app/hotel-room/${task.name}" class="btn btn-xs btn-default">View</a>
                            </td>
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="housekeeping_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Room</th>
                                    <th>Floor</th>
                                    <th>Type</th>
                                    <th>Status</th>
                                    <th class="text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

					$view.html(
						`<div class="frappe-card"><div class="frappe-card-head"><h4>Housekeeping Queue</h4></div><div class="frappe-card-body">${table_content}</div></div>`,
					);

					// Initialize DataTable
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#housekeeping_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									dom: "Bfrtip",
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	render_corporate_reservations_view() {
		let $view = this.page.main.find(`[data-view-name="corporate_reservations_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="corporate_reservations_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Corporate Reservations...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_corporate_reservations",
			callback: (r) => {
				const reservations = r.message || [];
				let table_content;

				if (reservations.length === 0) {
					table_content = `<p class="text-muted">No corporate reservations found.</p>`;
					$view.html(
						`<div class="frappe-card"><div class="frappe-card-head"><h4>Corporate Reservations</h4></div><div class="frappe-card-body">${table_content}</div></div>`,
					);
				} else {
					const rows = reservations
						.map(
							(res) => `
                        <tr data-reservation="${res.name}">
                            <td><strong><a href="#" class="corp-res-link" data-name="${res.name}">${res.name}</a></strong></td>
                            <td><a href="/app/hotel-guest/${res.corporate_guest}">${res.corporate_guest_name}</a></td>
                            <td>${res.customer || "N/A"}</td>
                            <td>${res.total_rooms}</td>
                            <td>${res.number_of_nights} nights</td>
                            <td>${frappe.datetime.str_to_user(res.from_date)}</td>
                            <td>${frappe.datetime.str_to_user(res.to_date)}</td>
                            <td class="text-right">${frappe.format(res.total_amount, { fieldtype: "Currency" })}</td>
                            <td>
                                <span class="badge ${res.status === "Checked In" ? "badge-success" : res.status === "Checked Out" ? "badge-secondary" : "badge-info"}">${res.status}</span>
                            </td>
                            <td class="text-center">
                                <button class="btn btn-xs btn-default view-corp-res" data-name="${res.name}" title="View Details">
                                    <i class="fa fa-eye"></i>
                                </button>
                            </td>
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="corporate_reservations_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Reservation ID</th>
                                    <th>Corporate Guest</th>
                                    <th>Customer</th>
                                    <th>Rooms</th>
                                    <th>Duration</th>
                                    <th>Check-in</th>
                                    <th>Check-out</th>
                                    <th class="text-right">Total Amount</th>
                                    <th>Status</th>
                                    <th class="text-center">Actions</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

					$view.html(`<div class="frappe-card"><div class="frappe-card-head">
                        <h4>Corporate Reservations</h4>
                        <a href="/app/hotel-front-desk-reservation/new" class="btn btn-primary btn-sm">New Reservation</a>
                        </div><div class="frappe-card-body">${table_content}</div></div>`);

					// Bind view buttons
					$view.find(".view-corp-res").on("click", (e) => {
						e.preventDefault();
						const res_name = $(e.currentTarget).data("name");
						this.show_corporate_reservation_details(res_name);
					});

					// Bind reservation name links
					$view.find(".corp-res-link").on(
						"click",
						function (e) {
							e.preventDefault();
							const res_name = $(this).data("name");
							this.show_corporate_reservation_details(res_name);
						}.bind(this),
					);

					// Initialize DataTable
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#corporate_reservations_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: false,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									language: {
										search: "Filter:",
										lengthMenu: "Show _MENU_ entries",
									},
									dom: "Bfrtip",
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	// show_corporate_reservation_details(reservation_name) {
	//     /**
	//      * Shows detailed modal for corporate reservation with:
	//      * - Full reservation details
	//      * - Room status overview
	//      * - Invoices and payments
	//      * - Bulk action buttons
	//      */

	//     frappe.call({
	//         method: 'frappe.client.get',
	//         args: {
	//             doctype: 'Hotel Front Desk Reservation',
	//             name: reservation_name
	//         },
	//         callback: (r) => {
	//             if (!r.message) return;

	//             const reservation = r.message;

	//             // Fetch related data
	//             frappe.call({
	//                 method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_corporate_reservation_details',
	//                 args: {
	//                     reservation_name: reservation_name
	//                 },
	//                 callback: (r2) => {
	//                     const details = r2.message;

	//                     this.show_corporate_res_modal(reservation, details);
	//                 }
	//             });
	//         }
	//     });
	// }
	show_corporate_reservation_details(reservation_name) {
		/**
		 * Shows detailed modal for a corporate reservation
		 */

		if (!reservation_name) {
			frappe.msgprint(__("No reservation selected"));
			return;
		}

		frappe.show_alert({
			message: __("Loading reservation details..."),
			indicator: "blue",
		});

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_corporate_reservation_details",
			args: {
				reservation_name: reservation_name,
			},
			callback: (r) => {
				if (r.message && r.message.success) {
					const reservation = r.message.reservation;
					const details = r.message;
					this.show_corporate_res_modal(reservation, details);
				} else if (r.message && r.message.error) {
					frappe.msgprint({
						title: __("Error"),
						indicator: "red",
						message: __("Error: " + r.message.error),
					});
				} else {
					frappe.msgprint(__("No data found"));
				}
			},
			error: (err) => {
				frappe.msgprint(__("Failed to load reservation details"));
				console.error(err);
			},
		});
	}

	show_corporate_res_modal(reservation, details) {
		/**
		 * Display comprehensive corporate reservation modal
		 * with all details and bulk action buttons
		 */

		if (!reservation || !reservation.name) {
			frappe.msgprint(__("Invalid reservation data"));
			return;
		}

		// Extract data
		const room_reservations = details.room_reservations || [];
		const invoices = details.invoices || [];
		const payments = details.payments || [];

		// Build the modal content
		let modal_content = `
        <div style="padding: 0;">
            
            <!-- HEADER CARD -->
            <div class="corporate-res-header" style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            ">
                <div class="row">
                    <div class="col-md-6">
                        <h5>${reservation.name}</h5>
                        <p style="font-size: 12px; opacity: 0.9;">Reservation ID</p>
                    </div>
                    <div class="col-md-6">
                        <h5>${frappe.format(reservation.total_amount, { fieldtype: "Currency" })}</h5>
                        <p style="font-size: 12px; opacity: 0.9;">Total Amount</p>
                    </div>
                </div>
                <div class="row" style="margin-top: 15px;">
                    <div class="col-md-6">
                        <p><strong>${reservation.total_rooms || 0}</strong> Rooms</p>
                    </div>
                    <div class="col-md-6">
                        <span class="badge badge-success">${reservation.status || "Active"}</span>
                    </div>
                </div>
            </div>
            
            <!-- GUEST INFO -->
            <div class="guest-info" style="margin-bottom: 25px;">
                <h6 style="border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 15px;">
                    📋 Guest Information
                </h6>
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Corporate Guest:</strong></p>
                        <p>${reservation.primary_guest_name || "-"}</p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>Customer:</strong></p>
                        <p>${reservation.customer || "-"}</p>
                    </div>
                </div>
                <div class="row" style="margin-top: 10px;">
                    <div class="col-md-6">
                        <p><strong>Check-in:</strong> ${frappe.datetime.str_to_user(reservation.from_date) || "-"}</p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>Check-out:</strong> ${frappe.datetime.str_to_user(reservation.to_date) || "-"}</p>
                    </div>
                </div>
            </div>
            

            <!-- ROOMS TABLE -->
            <div class="rooms-section" style="margin-bottom: 25px;">
                <h6 style="border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 15px;">
                    🛏️ Rooms (${(reservation.rooms || []).length})
                </h6>
                <div class="table-responsive">
                    <table class="table table-sm table-bordered">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th>Room</th>
                                <th>Type</th>
                                <th>Guest</th>
                                <th class="text-right">Rate</th>
                                <th class="text-right">Total</th>
                                <th>Status</th>
                                <th class="text-center">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${(reservation.rooms || [])
								.map((room, idx) => {
									const checkin = details.checkins.find(
										(c) => c.room_number === room.room_number,
									);

									let status_badge = "";
									let action_button = "";

									if (checkin && checkin.status === "Checked In") {
										status_badge =
											'<span class="badge badge-success">✓ Checked In</span>';
										action_button = "—"; // No action button for already checked in
									} else if (checkin && checkin.status === "Checked Out") {
										status_badge =
											'<span class="badge badge-secondary">Checked Out</span>';
										action_button = "—"; // No action button for checked out
									} else {
										status_badge =
											'<span class="badge badge-info">Booked</span>';
										// ✅ Show check-in button only for booked rooms
										action_button = `
                                        <button class="btn btn-xs btn-primary check-in-room-btn" 
                                                data-room-idx="${idx}" 
                                                data-room-number="${room.room_number}"
                                                title="Check in this room">
                                            <i class="fa fa-sign-in"></i> Check In
                                        </button>
                                    `;
									}

									return `
                                    <tr>
                                        <td><strong>${room.room_number || "-"}</strong></td>
                                        <td>${room.room_type || "-"}</td>
                                        <td>${room.guest_name || "—"}</td>
                                        <td class="text-right">${frappe.format(room.rate_per_night || 0, { fieldtype: "Currency" })}</td>
                                        <td class="text-right">${frappe.format(room.room_total || 0, { fieldtype: "Currency" })}</td>
                                        <td class="text-center">${status_badge}</td>
                                        <td class="text-center">${action_button}</td>
                                    </tr>
                                `;
								})
								.join("")}
                        </tbody>
                    </table>
                </div>
                ${(reservation.rooms || []).length === 0 ? '<p style="color: #999;">No rooms assigned</p>' : ""}
            </div>


        
            <!-- INVOICES -->
            <div class="invoices-section" style="margin-bottom: 25px;">
                <h6 style="border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 15px;">
                    📄 Invoices (${invoices.length})
                </h6>
                
                <!-- Summary if multiple invoices exist -->
                ${
					invoices.length > 1
						? `
                    <div style="background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 10px 15px; border-radius: 4px; margin-bottom: 15px;">
                        <strong style="color: #1976d2;">
                            ${invoices.filter((inv) => inv.is_room_invoice).length} room invoice(s) + ${invoices.filter((inv) => !inv.is_room_invoice).length} bulk invoice(s)
                        </strong>
                    </div>
                `
						: ""
				}
                
                <div class="table-responsive">
                    <table class="table table-sm table-bordered">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th>Invoice ID</th>
                                <th>Type</th>
                                <th class="text-right">Amount</th>
                                <th>Outstanding</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${
								invoices.length > 0
									? invoices
											.map((inv) => {
												// Determine invoice type
												let invoice_type = "Bulk";
												let room_badge = "";

												if (inv.is_room_invoice) {
													invoice_type = "Room";
													room_badge = `<br/><small style="color: #666;">Room: <strong>${inv.room_number}</strong></small>`;
												}

												// Determine status badge color
												let status_color = "badge-secondary";
												if (inv.docstatus === 1) {
													status_color = "badge-success";
												} else if (inv.docstatus === 2) {
													status_color = "badge-danger";
												}

												return `
                                    <tr>
                                        <td>
                                            <strong><a href="/app/sales-invoice/${inv.name}" target="_blank">${inv.name}</a></strong>
                                            ${room_badge}
                                        </td>
                                        <td>
                                            <span class="badge ${invoice_type === "Room" ? "badge-info" : "badge-primary"}">
                                                ${invoice_type}
                                            </span>
                                        </td>
                                        <td class="text-right">${frappe.format(inv.total || inv.amount || 0, { fieldtype: "Currency" })}</td>
                                        <td class="text-right">${frappe.format(inv.outstanding_amount || 0, { fieldtype: "Currency" })}</td>
                                        <td>
                                            <span class="badge ${status_color}">
                                                ${inv.docstatus === 1 ? "Submitted" : inv.docstatus === 2 ? "Cancelled" : "Draft"}
                                            </span>
                                        </td>
                                        <td class="text-center">
                                            <a href="/app/sales-invoice/${inv.name}" class="btn btn-xs btn-default" target="_blank">
                                                <i class="fa fa-external-link"></i> View
                                            </a>
                                        </td>
                                    </tr>
                                `;
											})
											.join("")
									: '<tr><td colspan="6" class="text-muted text-center">No invoices created yet</td></tr>'
							}
                        </tbody>
                    </table>
                </div>
                
                <!-- Summary footer -->
                ${
					invoices.length > 0
						? `
                    <div style="background-color: #f5f5f5; padding: 10px 15px; border-radius: 4px; margin-top: 10px; display: flex; justify-content: space-between;">
                        <div>
                            <strong>Total Invoiced:</strong>
                            ${frappe.format(
								invoices.reduce(
									(sum, inv) => sum + (inv.total || inv.amount || 0),
									0,
								),
								{ fieldtype: "Currency" },
							)}
                        </div>
                        <div>
                            <strong>Total Outstanding:</strong>
                            ${frappe.format(
								invoices.reduce(
									(sum, inv) => sum + (inv.outstanding_amount || 0),
									0,
								),
								{ fieldtype: "Currency" },
							)}
                        </div>
                    </div>
                `
						: ""
				}
            </div>
            
            <!-- PAYMENTS -->
            <div class="payments-section" style="margin-bottom: 25px;">
                <h6 style="border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 15px;">
                    💳 Payments (${payments.length})
                </h6>
                <div class="table-responsive">
                    <table class="table table-sm table-bordered">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th>Payment Entry</th>
                                <th class="text-right">Amount</th>
                                <th>Date</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${
								payments.length > 0
									? payments
											.map(
												(payment) => `
                                <tr>
                                    <td><strong><a href="/app/payment-entry/${payment.name}" target="_blank">${payment.name}</a></strong></td>
                                    <td class="text-right">${frappe.format(payment.paid_amount, { fieldtype: "Currency" })}</td>
                                    <td>${frappe.datetime.str_to_user(payment.posting_date)}</td>
                                    <td><span class="badge badge-info">${payment.status}</span></td>
                                </tr>
                            `,
											)
											.join("")
									: '<tr><td colspan="4" class="text-muted text-center">No payments yet</td></tr>'
							}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

		// Create and show modal
		let dialog = new frappe.ui.Dialog({
			title: __("Corporate Reservation: {0}", [reservation.name]),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "modal_content",
					options: modal_content,
				},
			],
			size: "large",
			primary_action_label: __("Close"),
			primary_action: function () {
				dialog.hide();
			},
		});

		// Add action buttons

		// Button 1: Check In All Rooms
		dialog.add_custom_action(__("Check In All Rooms"), () => {
			frappe.confirm(__("Check in all {0} rooms?", [reservation.total_rooms]), () => {
				frappe.call({
					method: "rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_all_rooms",
					args: {
						reservation_name: reservation.name,
						check_in_notes: "Bulk check-in from Corporate Reservations view",
					},
					callback: (r) => {
						if (r.message && r.message.success) {
							frappe.msgprint({
								title: __("Success"),
								message: r.message.message,
								indicator: "green",
							});
							dialog.hide();
							// Refresh the view
							if (this.render_corporate_reservations_view) {
								this.render_corporate_reservations_view();
							}
						}
					},
				});
			});
		});

		// Button 2: Create Invoice
		dialog.add_custom_action(__("Create Invoice"), () => {
			if (reservation.sales_invoice) {
				frappe.msgprint(__("Invoice already exists: {0}", [reservation.sales_invoice]));
				return;
			}

			frappe.call({
				method: "rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.create_sales_invoice_for_reservation",
				args: {
					reservation_name: reservation.name,
				},
				callback: (r) => {
					if (r.message && r.message.success) {
						frappe.msgprint({
							title: __("Success"),
							message: r.message.message,
							indicator: "green",
						});
						dialog.hide();
						// Refresh the view
						if (this.render_corporate_reservations_view) {
							this.render_corporate_reservations_view();
						}
					}
				},
			});
		});

		// Button 3: Edit Reservation
		dialog.add_custom_action(__("Edit Reservation"), () => {
			frappe.set_route("Form", "Hotel Front Desk Reservation", reservation.name);
			dialog.hide();
		});

		dialog.show();

		// ✅ NEW: Bind check-in button events
		dialog.$wrapper.find(".check-in-room-btn").on("click", function (e) {
			e.preventDefault();

			const room_idx = $(this).data("room-idx");
			const room_number = $(this).data("room-number");

			frappe.confirm(__("Check in room <strong>{0}</strong>?", [room_number]), function () {
				// Call backend to check in this single room
				frappe.call({
					method: "rhohotel.rhocom_hotel.doctype.hotel_front_desk_reservation.hotel_front_desk_reservation.check_in_selected_rooms",
					args: {
						reservation_name: reservation.name,
						room_indices: [parseInt(room_idx)], // Single room as array
						check_in_notes: "",
					},
					callback: function (r) {
						if (r.message && r.message.success) {
							frappe.msgprint({
								title: __("Success"),
								message: __("Room {0} checked in successfully", [room_number]),
								indicator: "green",
							});
							// Refresh the modal by reloading details
							setTimeout(() => {
								dialog.hide();
								// Re-open to show updated status
								// Call the parent function to refresh
							}, 500);
						}
					},
				});
			});
		});
	}

	render_payments_view() {
		let $view = this.page.main.find(`[data-view-name="payments_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="payments_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Payment Status...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_rooms_with_payment_status",
			callback: (r) => {
				const rooms = r.message;
				let table_content;

				if (!rooms || rooms.length === 0) {
					table_content = `<p class="text-muted">No occupied rooms with payment data.</p>`;
					$view.html(
						`<div class="frappe-card"><div class="frappe-card-head"><h4>Payment Status</h4></div><div class="frappe-card-body">${table_content}</div></div>`,
					);
				} else {
					const rows = rooms
						.map((room) => {
							const balance_color = room.balance > 0 ? "#ffebee" : "#e8f5e9";
							return `
                        <tr style="background-color: ${balance_color};">
                            <td><strong>${room.room_number}</strong></td>
                            <td><a href="/app/hotel-guest/${room.guest}">${room.guest}</a></td>
                            <td class="text-right">${frappe.format(room.total_invoice, { fieldtype: "Currency" })}</td>
                            <td class="text-right">${frappe.format(room.total_paid, { fieldtype: "Currency" })}</td>
                            <td class="text-right"><strong>${frappe.format(room.balance, { fieldtype: "Currency" })}</strong></td>
                            <td class="text-right">
                                <a href="/app/payment-entry/new?custom_hotel_room_check_in=${room.check_in_id}" class="btn btn-xs btn-primary">Settle</a>
                            </td>
                        </tr>
                    `;
						})
						.join("");

					table_content = `
                        <table id="payments_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Room</th>
                                    <th>Guest</th>
                                    <th class="text-right">Total Invoice</th>
                                    <th class="text-right">Total Paid</th>
                                    <th class="text-right">Balance</th>
                                    <th class="text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

					$view.html(
						`<div class="frappe-card"><div class="frappe-card-head"><h4>Payment Status</h4></div><div class="frappe-card-body">${table_content}</div></div>`,
					);

					// Initialize DataTable
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#payments_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									dom: "Bfrtip",
									buttons: [
										"excel",
										{
											extend: "pdf",
											customize: (doc) => {
												if (this.letterhead_html) {
													doc.header = {
														columns: [
															{
																html: this.letterhead_html,
																margin: [40, 20, 40, 0],
															},
														],
													};
												}
											},
										},
										{
											extend: "print",
											customize: (win) => {
												if (this.letterhead_html)
													$(win.document.body).prepend(
														this.letterhead_html,
													);
											},
										},
									],
								});
							}
						}
					}, 100);
				}
			},
		});
	}

	render_night_audit_view() {
		let $view = this.page.main.find(`[data-view-name="night_audit_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="night_audit_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Night Audit Data...</p></div></div>`,
		);

		// Fetch both summary and chart data in parallel
		Promise.all([
			frappe.call("rhohotel.rhocom_hotel.page.front_desk.front_desk.get_night_audit_data"),
			frappe.call(
				"rhohotel.rhocom_hotel.page.front_desk.front_desk.get_night_audit_charts_data",
			),
		]).then(([summary_res, charts_res]) => {
			const summary_data = summary_res.message;
			const chart_data = charts_res.message;

			// Build the HTML for the entire view
			const audit_cards = `
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                    <div class="frappe-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
                        <div class="card-body">
                            <h5 class="card-title">Occupancy Rate</h5>
                            <h2 style="margin: 1rem 0;">${summary_data.occupancy_rate}%</h2>
                            <small>${summary_data.occupied_rooms}/${summary_data.total_rooms} rooms occupied</small>
                        </div>
                    </div>
                    <div class="frappe-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white;">
                        <div class="card-body">
                            <h5 class="card-title">Today's Revenue</h5>
                            <h2 style="margin: 1rem 0;">${frappe.format(summary_data.today_revenue, { fieldtype: "Currency" })}</h2>
                            <small>Total income today</small>
                        </div>
                    </div>
                    <div class="frappe-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); color: white;">
                        <div class="card-body">
                            <h5 class="card-title">Pending Payments</h5>
                            <h2 style="margin: 1rem 0;">${frappe.format(summary_data.pending_payments, { fieldtype: "Currency" })}</h2>
                            <small>Outstanding balance</small>
                        </div>
                    </div>
                    <div class="frappe-card" style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: #333;">
                        <div class="card-body">
                            <h5 class="card-title">No-Shows</h5>
                            <h2 style="margin: 1rem 0; color: #d32f2f; font-weight: bold;">${summary_data.no_shows}</h2>
                            <small>Cancelled/No-show reservations</small>
                        </div>
                    </div>
                </div>`;

			const charts_html = `
                <div id="night-audit-charts" style="margin-top: 2rem;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                        <div class="frappe-card">
                            <div class="frappe-card-head"><h5>Revenue by Room Type</h5></div>
                            <div class="frappe-card-body">
                                <div id="revenue-by-room-type-chart" style="height: 300px;"></div>
                            </div>
                        </div>
                        <div class="frappe-card">
                            <div class="frappe-card-head"><h5>Revenue by Market Place</h5></div>
                            <div class="frappe-card-body">
                                <div id="revenue-by-market-place-chart" style="height: 300px;"></div>
                            </div>
                        </div>
                    </div>
                    <div class="frappe-card" style="margin-top: 1.5rem;">
                        <div class="frappe-card-head"><h5>Daily Sales (Last 7 Days)</h5></div>
                        <div class="frappe-card-body">
                            <div id="daily-sales-chart" style="height: 300px;"></div>
                        </div>
                    </div>
                </div>`;

			// Set the HTML once
			$view.html(`<div class="frappe-card">
                <div class="frappe-card-head"><h4>Night Audit Dashboard</h4></div>
                <div class="frappe-card-body">${audit_cards}${charts_html}</div>
            </div>`);

			// Now that the DOM is ready, draw the charts
			this.draw_night_audit_charts(chart_data);
		});
	}

	draw_night_audit_charts(chart_data) {
		// 1. Revenue by Room Type (Pie)
		if (chart_data.revenue_by_room_type?.length > 0) {
			new frappe.Chart("#revenue-by-room-type-chart", {
				data: {
					labels: chart_data.revenue_by_room_type.map((d) => d.room_type || "Unknown"),
					datasets: [
						{
							values: chart_data.revenue_by_room_type.map((d) =>
								flt(d.total_revenue),
							),
						},
					],
				},
				type: "pie",
				height: 300,
				colors: ["#7c4dff", "#4fc3f7", "#ff8a65", "#66bb6a", "#ff8a80", "#ffd54f"],
				tooltipOptions: {
					formatTooltipY: (d) => frappe.format(d, { fieldtype: "Currency" }),
				},
			});
		}

		// 2. Revenue by Market Place (Bar)
		if (chart_data.revenue_by_market_place?.length > 0) {
			new frappe.Chart("#revenue-by-market-place-chart", {
				data: {
					labels: chart_data.revenue_by_market_place.map(
						(d) => d.market_place || "Direct",
					),
					datasets: [
						{
							values: chart_data.revenue_by_market_place.map((d) =>
								flt(d.total_revenue),
							),
						},
					],
				},
				type: "bar",
				height: 300,
				colors: ["#ff6b6b", "#f06292", "#ba68c8", "#7986cb"],
				tooltipOptions: {
					formatTooltipY: (d) => frappe.format(d, { fieldtype: "Currency" }),
				},
			});
		}

		// 3. Daily Sales (Line or Bar)
		new frappe.Chart("#daily-sales-chart", {
			data: {
				labels: chart_data.daily_sales.map((d) => moment(d.date).format("ddd, MMM D")),
				datasets: [
					{
						name: "Revenue",
						values: chart_data.daily_sales.map((d) => flt(d.sales)),
					},
				],
			},
			type: "bar",
			height: 300,
			colors: ["#4caf50"],
			axisOptions: {
				yAxisMode: "tick",
				xAxisMode: "tick",
			},
			tooltipOptions: {
				formatTooltipY: (d) => frappe.format(d, { fieldtype: "Currency" }),
			},
		});
	}

	render_room_stay_report() {
		let $view = this.page.main.find(`[data-view-name="room_stay_report"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="room_stay_report" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Room Stay Report...</p></div></div>`,
		);

		// Create date range picker
		const today = frappe.datetime.get_today();
		const thirtyDaysAgo = frappe.datetime.add_days(today, -30);

		const filterHtml = `
            <div style="margin-bottom: 1.5rem;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
                    <div>
                        <label for="stay_from_date" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">From Date</label>
                        <input type="date" id="stay_from_date" value="${thirtyDaysAgo}" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box;">
                    </div>
                    <div>
                        <label for="stay_to_date" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">To Date</label>
                        <input type="date" id="stay_to_date" value="${today}" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box;">
                    </div>
                    <div>
                        <label for="stay_room_filter" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Room Number</label>
                        <input type="text" id="stay_room_filter" placeholder="Search room..." style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box;">
                    </div>
                    <div>
                        <label for="stay_guest_filter" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Guest Name</label>
                        <input type="text" id="stay_guest_filter" placeholder="Search guest..." style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box;">
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                    <div>
                        <label for="stay_room_type_filter" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Room Type</label>
                        <select id="stay_room_type_filter" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box;">
                            <option value="">All Types</option>
                        </select>
                    </div>
                    <div>
                        <label for="stay_status_filter" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Status</label>
                        <select id="stay_status_filter" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 100%; box-sizing: border-box;">
                            <option value="">All Statuses</option>
                            <option value="checked-in">Checked In</option>
                            <option value="reserved">Reserved</option>
                            <option value="both">Both</option>
                        </select>
                    </div>
                    <div style="display: flex; align-items: flex-end; gap: 0.5rem;">
                        <button id="stay_report_generate" class="btn btn-primary" style="flex: 1;">Generate Report</button>
                        <button id="stay_report_reset" class="btn btn-secondary">Reset</button>
                    </div>
                </div>
            </div>`;

		$view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Room Stay Report <br/> 
            <br/>
            <a href="/app/query-report/Room Stay Report" target="_blank"  class="btn btn-primary btn-sm">Open in Report View</a>
            </h4></div><div class="frappe-card-body">${filterHtml}<div id="report_container"></div></div></div>`);

		// Populate room types
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Hotel Room Type",
				fields: ["name"],
				limit_page_length: 0,
			},
			callback: (r) => {
				if (r.message) {
					const roomTypeSelect = $view.find("#stay_room_type_filter");
					r.message.forEach((rt) => {
						roomTypeSelect.append(`<option value="${rt.name}">${rt.name}</option>`);
					});
				}
			},
		});

		// Bind generate button
		$view.find("#stay_report_generate").on("click", () => {
			const filters = {
				from_date: $view.find("#stay_from_date").val(),
				to_date: $view.find("#stay_to_date").val(),
				room_number: $view.find("#stay_room_filter").val(),
				guest_name: $view.find("#stay_guest_filter").val(),
				room_type: $view.find("#stay_room_type_filter").val(),
				status: $view.find("#stay_status_filter").val(),
			};
			this.generate_stay_report(filters, $view.find("#report_container"));
		});

		// Bind reset button
		$view.find("#stay_report_reset").on("click", () => {
			$view.find("#stay_room_filter").val("");
			$view.find("#stay_guest_filter").val("");
			$view.find("#stay_room_type_filter").val("");
			$view.find("#stay_status_filter").val("");
		});

		// Generate initial report
		this.generate_stay_report(
			{
				from_date: thirtyDaysAgo,
				to_date: today,
				room_number: "",
				guest_name: "",
				room_type: "",
				status: "",
			},
			$view.find("#report_container"),
		);
	}

	generate_stay_report(filters, $container) {
		$container.html(`<div class="text-muted">Generating report...</div>`);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_room_stay_data",
			args: {
				from_date: filters.from_date,
				to_date: filters.to_date,
				room_type_filter: filters.room_type,
				status_filter: filters.status,
			},
			callback: (r) => {
				const data = r.message;
				let rooms = data.rooms;
				let checkIns = data.check_ins;
				let reservations = data.reservations;

				// Parse dates
				const startDate = moment(filters.from_date);
				const endDate = moment(filters.to_date);
				const dayCount = endDate.diff(startDate, "days") + 1;

				// Apply room filter
				if (filters.room_number) {
					rooms = rooms.filter((room) => room.room_number.includes(filters.room_number));
				}

				// Apply room type filter if selected
				if (filters.room_type) {
					rooms = rooms.filter((room) => room.room_type === filters.room_type);
				}

				// Apply guest name filter
				if (filters.guest_name) {
					const guestFilter = filters.guest_name.toLowerCase();
					checkIns = checkIns.filter(
						(ci) => ci.guest && ci.guest.toLowerCase().includes(guestFilter),
					);
					reservations = reservations.filter(
						(res) =>
							res.guest_name && res.guest_name.toLowerCase().includes(guestFilter),
					);
				}

				// Generate date headers
				let dateHeaderContent = "";
				for (let i = 0; i < dayCount; i++) {
					const d = moment(startDate).add(i, "days");
					dateHeaderContent += `<div class="date-column date-header">${d.format("DD/MM")}</div>`;
				}

				let headerHtml = `<div class="stay-timeline-header">
                    <div style="font-weight: bold;">Room</div>
                    <div class="timeline-dates">${dateHeaderContent}</div>
                </div>`;

				// Generate room rows
				let rowsHtml = "";
				let roomsWithData = 0;

				rooms.forEach((room) => {
					// Find check-ins for this room
					let roomCheckIns = checkIns.filter(
						(ci) => ci.room_number === room.room_number,
					);
					let roomReservations = reservations.filter(
						(res) => res.room_number === room.room_number,
					);

					// Apply status filter
					if (filters.status === "checked-in") {
						roomReservations = [];
					} else if (filters.status === "reserved") {
						roomCheckIns = [];
					}

					// Skip rooms with no relevant data if guest filter is applied
					if (
						filters.guest_name &&
						roomCheckIns.length === 0 &&
						roomReservations.length === 0
					) {
						return;
					}

					roomsWithData++;

					// Create a map of dates to stay information
					const dateStayMap = {};

					// Fill in check-ins
					for (let ci of roomCheckIns) {
						const ciStart = moment(ci.check_in_datetime);
						const ciEnd = moment(ci.expected_check_out_datetime);

						let currentDay = ciStart.clone();
						while (currentDay.isBefore(ciEnd) || currentDay.isSame(ciEnd)) {
							const dateKey = currentDay.format("YYYY-MM-DD");
							if (!dateStayMap[dateKey]) {
								dateStayMap[dateKey] = {
									guest: ci.guest || "Guest",
									type: "checked-in",
									stayId: ci.name,
								};
							}
							currentDay.add(1, "day");
						}
					}

					// Fill in reservations (only if no check-in for that date)
					for (let res of roomReservations) {
						const resStart = moment(res.from_date);
						const resEnd = moment(res.to_date);

						let currentDay = resStart.clone();
						while (currentDay.isBefore(resEnd) || currentDay.isSame(resEnd)) {
							const dateKey = currentDay.format("YYYY-MM-DD");
							if (!dateStayMap[dateKey]) {
								dateStayMap[dateKey] = {
									guest: res.guest_name,
									type: "reserved",
									stayId: res.name,
								};
							}
							currentDay.add(1, "day");
						}
					}

					let dateContent = "";
					let i = 0;

					// Generate timeline for each day
					while (i < dayCount) {
						const currentDate = moment(startDate).add(i, "days");
						const dateStr = currentDate.format("YYYY-MM-DD");

						const stayInfo = dateStayMap[dateStr];

						if (!stayInfo) {
							// Empty day
							dateContent += `<div class="date-column"><div class="empty-day"></div></div>`;
							i++;
						} else {
							// Find the extent of this stay (how many consecutive days)
							let stayLength = 1;
							let currentStayId = stayInfo.stayId;
							let currentType = stayInfo.type;
							let j = i + 1;

							while (j < dayCount) {
								const nextDate = moment(startDate).add(j, "days");
								const nextDateStr = nextDate.format("YYYY-MM-DD");
								const nextStay = dateStayMap[nextDateStr];

								if (
									nextStay &&
									nextStay.stayId === currentStayId &&
									nextStay.type === currentType
								) {
									stayLength++;
									j++;
								} else {
									break;
								}
							}

							// Calculate width as percentage
							const widthPercent = stayLength * 80 + "px"; // 80px per column
							const barStyle =
								currentType === "reserved"
									? "background: linear-gradient(135deg, #ffa726 0%, #fb8c00 100%);"
									: "background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);";

							// Wrap guest name across multiple lines
							const guestName = stayInfo.guest;
							const displayName = guestName.length > 15 ? guestName : guestName;

							dateContent += `<div class="date-column" style="grid-column: span ${stayLength}; position: relative;">
                                <div class="stay-bar-continuous" style="${barStyle} width: ${widthPercent};" title="${guestName}">
                                    <span class="stay-bar-text">${displayName}</span>
                                </div>
                            </div>`;

							i += stayLength;
						}
					}

					rowsHtml += `<div class="stay-row">
                        <div class="room-label">${room.room_number}</div>
                        <div class="timeline-dates" style="display: grid; grid-template-columns: repeat(${dayCount}, 80px); gap: 0.25rem;">${dateContent}</div>
                    </div>`;
				});

				if (roomsWithData === 0) {
					$container.html(
						`<div class="alert alert-warning">No rooms found matching the selected filters.</div>`,
					);
				} else {
					const finalHtml = `<div class="stay-timeline-container">${headerHtml}${rowsHtml}</div>`;
					$container.html(finalHtml);
				}
			},
		});
	}

	render_hall_booking_view() {
		let $view = this.page.main.find(`[data-view-name="hall_booking_view"]`);
		if (!$view.length) {
			$view = $(
				`<div class="view-container" data-view-name="hall_booking_view" style="padding: 1rem 0;"></div>`,
			).appendTo(this.page.main);
		}
		$view.show();
		$view.html(
			`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Hall Bookings...</p></div></div>`,
		);

		frappe.call({
			method: "rhohotel.rhocom_hotel.page.front_desk.front_desk.get_hall_bookings",
			callback: (r) => {
				const bookings = r.message || [];
				let table_content;

				if (bookings.length === 0) {
					table_content = `<p class="text-muted">No hall bookings found.</p>`;
				} else {
					const rows = bookings
						.map(
							(b) => `
                        <tr>
                            <td><a href="/app/hall-booking/${b.name}">${b.name}</a></td>
                            <td>${b.hall}</td>
                            <td>${b.customer_name}</td>
                            <td>${frappe.datetime.str_to_user(b.start_datetime)}</td>
                            <td>${frappe.datetime.str_to_user(b.end_datetime)}</td>
                            <td class="text-right">${frappe.format(b.net_total, { fieldtype: "Currency" })}</td>
                            <td>${getInvoiceBadge(b.invoice_status)}</td>
                        </tr>
                    `,
						)
						.join("");

					table_content = `
                        <table id="hall_booking_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
                                    <th>Booking ID</th>
                                    <th>Hall</th>
                                    <th>Customer</th>
                                    <th>Start Time</th>
                                    <th>End Time</th>
                                    <th class="text-right">Total Amount</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;
				}

				const card_header = `<div class="frappe-card-head d-flex justify-content-between align-items-center">
                    <h4>Hall Bookings</h4>
                    <a href="/app/hall-booking/new" class="btn btn-primary btn-sm">New Hall Booking</a>
                </div>`;
				const card_body = `<div class="frappe-card-body">${table_content}</div>`;
				$view.html(`<div class="frappe-card">${card_header}${card_body}</div>`);

				// Initialize DataTable
				if (bookings.length > 0) {
					setTimeout(() => {
						if ($.fn.dataTable) {
							const table = $view.find("#hall_booking_table");
							if (table.length && !$.fn.DataTable.isDataTable(table)) {
								table.DataTable({
									paging: true,
									searching: true,
									ordering: true,
									info: true,
									lengthMenu: [
										[10, 25, 50, -1],
										[10, 25, 50, "All"],
									],
									pageLength: 10,
									dom: "Bfrtip",
									buttons: ["excel", "pdf", "print"],
								});
							}
						}
					}, 100);
				}
			},
		});
	}
}

function getInvoiceBadge(status) {
	const map = {
		Paid: "badge-success",
		Unpaid: "badge-warning",
		Overdue: "badge-danger",
		Draft: "badge-secondary",
		Cancelled: "badge-dark",
	};

	return `<span class="badge ${map[status] || "badge-info"}">
    ${status || "No Invoice"}
  </span>`;
}
