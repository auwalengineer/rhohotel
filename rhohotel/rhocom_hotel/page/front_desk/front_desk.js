frappe.pages['front-desk'].on_page_load = function (wrapper) {
    new FrontDesk(wrapper);

    // Load DataTables CSS and JS if not already loaded
    if (!$.fn.dataTable) {
        const dtLink = document.createElement('link');
        dtLink.rel = 'stylesheet';
        dtLink.href = 'https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css';
        document.head.appendChild(dtLink);

        const dtScript = document.createElement('script');
        dtScript.src = 'https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js';
        document.head.appendChild(dtScript);
    }

    // Add CSS for blinking animation and uniform card heights
    const style = document.createElement('style');
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
	`;
    document.head.appendChild(style);
}

class FrontDesk {
    constructor(wrapper) {
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Front Desk',
            single_column: true
        });

        this.rooms = [];
        this.filters = {};
        this.current_view = 'room_view';

        this.make_stats_area();
        this.make_view_switcher();
        this.make_filters();
        this.make_view_containers();

        this.switch_view(this.current_view); // Initial render

        this.start_clock();
        this.start_timer_updates();

        // Realtime updates
        frappe.realtime.on('rhohotel_front_desk_update', () => {
            this.refresh();
        });
    }

    make_stats_area() {
        const $header = $(`<div class="front-desk-header"></div>`).prependTo(this.page.main.parent());

        const $top_bar = $(`<div class="d-flex justify-content-between align-items-center p-3"></div>`).appendTo($header);

        this.$clock = $(`<div class="clock-widget"></div>`).appendTo($top_bar);
        this.$clock.css({
            'font-size': '1.5rem',
            'font-weight': 'bold',
        });

        this.$user_display = $(`<div>Welcome, <strong>${frappe.session.user_fullname}</strong></div>`).appendTo($top_bar);
        this.$user_display.css({
            'font-size': '1.2rem',
        });

        this.$stats = $("<div class=\"room-stats\"></div>").appendTo($header);
        this.$stats.css({
            display: 'grid',
            'grid-template-columns': 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1rem',
            padding: '1rem'
        });
    }

    make_view_switcher() {
        const $view_switcher_container = $(`<div class="front-desk-view-switcher-container" style="padding: 1rem 1rem 0;"></div>`).insertAfter(this.page.main.parent().find('.front-desk-header'));
        this.$view_switcher = $(`<div class="btn-group" role="group" style="flex-wrap: wrap;"></div>`).appendTo($view_switcher_container);

        const views = [
            { name: 'room_view', label: 'Room View', icon: 'th' },
            { name: 'check_in_view', label: 'Check-ins', icon: 'sign-in' },
            { name: 'check_out_view', label: 'Check-outs', icon: 'sign-out' },
            { name: 'reservation_view', label: 'Reservations', icon: 'calendar-check-o' },
            { name: 'guest_list_view', label: 'Guests', icon: 'users' },
            { name: 'housekeeping_view', label: 'Housekeeping', icon: 'tasks' },
            { name: 'payments_view', label: 'Payments', icon: 'money' },
            { name: 'room_stay_report', label: 'Room Stay Report', icon: 'calendar' },
            { name: 'night_audit_view', label: 'Night Audit', icon: 'bar-chart' }
        ];

        views.forEach(view => {
            const button = $(`
                <button type="button" class="btn btn-default" data-view="${view.name}">
                    <i class="fa fa-${view.icon}"></i> ${view.label}
                </button>
            `).appendTo(this.$view_switcher);

            button.on('click', () => {
                this.switch_view(view.name);
            });
        });
    }

    make_view_containers() {
        this.$room_grid = $(`<div class="room-grid view-container" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; padding: 1rem 0;"></div>`).appendTo(this.page.main);
    }

    make_filters() {
        const fields = [
            {
                fieldtype: 'Data',
                label: 'Search Room/Guest',
                fieldname: 'search_text',
                placeholder: 'Room number, guest name or email...',
                change: () => this.perform_search()
            },
            {
                fieldtype: 'Link',
                label: 'Floor',
                fieldname: 'floor',
                options: 'Hotel Floor',
                change: () => this.refresh_rooms()
            },
            {
                fieldtype: 'Link',
                label: 'Room Type',
                fieldname: 'room_type',
                options: 'Hotel Room Type',
                change: () => this.refresh_rooms()
            },
            {
                fieldtype: 'Select',
                label: 'Status',
                fieldname: 'status',
                options: '\nVacant\nOccupied\nReserved\nMaintenance',
                change: () => this.refresh_rooms()
            },
            {
                fieldtype: 'Select',
                label: 'Housekeeping',
                fieldname: 'housekeeping_status',
                options: '\nClean\nDirty\nInspected\nIn Progress',
                change: () => this.refresh_rooms()
            },
            {
                fieldtype: 'Check',
                label: 'Checking Out Today',
                fieldname: 'checkout_today',
                change: () => this.refresh_rooms()
            }
        ];

        fields.forEach(df => {
            this.page.add_field(df);
        });
    }

    perform_search() {
        const search_text = this.page.get_form_values().search_text;
        if (search_text && search_text.length > 0) {
            this.$room_grid.empty();
            this.$room_grid.html(`<div class="text-muted">Searching...</div>`);
            frappe.call({
                method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_filtered_rooms',
                args: { search_text: search_text },
                callback: (r) => {
                    const rooms = r.message || [];
                    this.$room_grid.empty();
                    if (rooms.length === 0) {
                        this.$room_grid.html(`<div class="text-muted">No rooms found matching "${search_text}"</div>`);
                    } else {
                        rooms.forEach(room => {
                            const $card = this.get_room_card(room);
                            $card.on('click', () => this.show_room_actions(room));
                            this.$room_grid.append($card);
                        });
                    }
                }
            });
        } else {
            this.refresh_rooms();
        }
    }


    get_room_card(room) {
        const status_colors = {
            'Vacant': 'green',
            'Occupied': 'blue',
            'Reserved': 'orange-color', // Use a valid CSS variable
            'Maintenance': 'red'
        };

        const housekeeping_icons = {
            'Clean': 'check',
            'Dirty': 'trash',
            'Inspected': 'eye',
            'In Progress': 'refresh'
        };

        const status_color = status_colors[room.status] || 'gray';
        const housekeeping_icon = housekeeping_icons[room.housekeeping_status] || 'question';

        return $(
            `<div class="room-card" data-name="${room.name}">${this.get_card_content(room, status_color, housekeeping_icon)}</div>`
        );
    }

    get_card_content(room, status_color, housekeeping_icon) {
        let card_style = `border-left: 3px solid var(--${status_color});`;
        let checkout_warning_style = '';
        let overdue_html = '';

        if (room.status === 'Occupied' && room.expected_check_out_datetime) {
            const now = moment();
            const checkout_time = moment(room.expected_check_out_datetime);
            const diff_minutes = checkout_time.diff(now, 'minutes');

            if (diff_minutes < 0) {
                // Checkout time has passed
                checkout_warning_style = 'background-color: #ef9a9a;'; // A darker, but not pure, red
                const overstay_duration = moment.duration(now.diff(checkout_time)).humanize();
                overdue_html = `<div class="mt-2 text-danger blink-me overdue-message">
                        <strong>Overdue by ${overstay_duration}</strong>
                    </div>`;
            } else if (diff_minutes <= 60) {
                // Checkout is within the next hour
                checkout_warning_style = 'background-color: #ffcdd2;'; // A lighter red
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
                            <div class="text-muted">${room.floor || ''}</div>
                            ${room.current_guest ? `
                                <div class="mt-2">
                                    <strong>Guest:</strong> ${room.current_guest}<br>
                                    <small>Checkout: ${room.expected_check_out_datetime ? frappe.datetime.str_to_user(room.expected_check_out_datetime) : 'N/A'}</small>
                                </div>
                                <div class="overdue-container">${overdue_html}</div>
                            ` : ''}
                            ${room.upcoming_guest ? `
                                <div class="mt-2">
                                    <strong>Reserved:</strong> ${room.upcoming_guest}<br>
                                    <small>Check-in: ${room.check_in_date ? frappe.datetime.str_to_user(room.check_in_date) : 'N/A'}</small>
                                </div>
                            ` : ''}
                            ${room.maintenance_request ? `
                                <div class="mt-2 text-danger">
                                    <i class="fa fa-tools"></i> Under maintenance
                                </div>
                            ` : ''}
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
            </div>`
        );

        if (route_options) {
            $card.on('click', () => {
                frappe.set_route('List', 'Hotel Room', route_options);
            });
            $card.css('cursor', 'pointer');
        }
        return $card;
    }

    refresh() {
        this.render_current_view();
    }

    switch_view(view_name) {
        this.current_view = view_name;

        // Update button styles
        this.$view_switcher.find('button').removeClass('btn-primary').addClass('btn-default');
        this.$view_switcher.find(`button[data-view="${view_name}"]`).removeClass('btn-default').addClass('btn-primary');

        this.render_current_view();
    }

    render_current_view() {
        this.page.main.find('.view-container').hide();
        const $filter_area = this.page.main.find('.page-form');

        if (this.current_view === 'room_view') {
            $filter_area.show();
            this.$room_grid.show();
            this.refresh_stats();
            this.refresh_rooms();
        } else if (this.current_view === 'check_in_view') {
            $filter_area.hide();
            this.refresh_stats();
            this.render_check_in_view();
        } else if (this.current_view === 'guest_list_view') {
            $filter_area.hide();
            this.refresh_stats();
            this.render_guest_list_view();
        } else if (this.current_view === 'check_out_view') {
            $filter_area.hide();
            this.refresh_stats();
            this.render_check_out_view();
        } else if (this.current_view === 'reservation_view') {
            $filter_area.hide();
            this.refresh_stats();
            this.render_reservation_view();
        } else if (this.current_view === 'housekeeping_view') {
            $filter_area.hide();
            this.render_housekeeping_view();
        } else if (this.current_view === 'payments_view') {
            $filter_area.hide();
            this.refresh_stats();
            this.render_payments_view();
        } else if (this.current_view === 'room_stay_report') {
            $filter_area.hide();
            this.render_room_stay_report();
        } else if (this.current_view === 'night_audit_view') {
            $filter_area.hide();
            this.render_night_audit_view();
        } else {
            $filter_area.hide();
            this.refresh_stats(); // Stats are always visible
            let $view = this.page.main.find(`[data-view-name="${this.current_view}"]`);
            if (!$view.length) {
                $view = $(`<div class="view-container" data-view-name="${this.current_view}" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
            }
            $view.show();
            this.render_placeholder_view($view);
        }
    }

    render_placeholder_view($container) {
        const view_name = $container.data('view-name');
        const titles = {
            check_in_view: "Check-in List",
            guest_list_view: "Guest List",
            check_out_view: "Check-out List"
        };
        $container.html(`
            <div class="frappe-card">
                <div class="frappe-card-head"><h4>${titles[view_name] || 'View'}</h4></div>
                <div class="frappe-card-body">
                    <p class="text-muted">This view is under construction. The list of ${view_name.split('_')[0]}s will appear here.</p>
                </div>
            </div>`);
    }

    render_check_in_view() {
        let $view = this.page.main.find(`[data-view-name="check_in_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="check_in_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Check-ins...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_check_in_list',
            callback: (r) => {
                const check_ins = r.message;
                let table_content;

                if (!check_ins || check_ins.length === 0) {
                    table_content = `<p class="text-muted">No guests are currently checked in.</p>`;
                    $view.html(`<div class="frappe-card"><div class="frappe-card-body">${table_content}</div></div>`);
                } else {
                    const rows = check_ins.map(ci => `
                        <tr>
                            <td><a href="/app/hotel-guest/${ci.guest}">${ci.guest}</a></td>
                            <td>${ci.room_number}</td>
                            <td>${frappe.datetime.str_to_user(ci.check_in_datetime)}</td>
                            <td>${frappe.datetime.str_to_user(ci.expected_check_out_datetime)}</td>
                            <td class="text-right">${frappe.format(ci.total_invoice_amount, { fieldtype: 'Currency' })}</td>
                            <td class="text-right">${frappe.format(ci.total_payment_amount, { fieldtype: 'Currency' })}</td>
                            <td class="text-right">${frappe.format(ci.balance, { fieldtype: 'Currency' })}</td>
                            <td class="text-center">
                                ${ci.phone_number ? `<a href="tel:${ci.phone_number}" title="${ci.phone_number}" class="btn btn-xs btn-default"><i class="fa fa-phone"></i></a>` : ''}
                                ${ci.email_id ? `<a href="mailto:${ci.email_id}" title="${ci.email_id}" class="btn btn-xs btn-default"><i class="fa fa-envelope"></i></a>` : ''}
                            </td>
                        </tr>
                    `).join('');

                    table_content = `
                        <table id="check_in_table" class="table table-bordered table-hover table-striped">
                            <thead class="table-light">
                                <tr>
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

                    $view.html(`<div class="frappe-card"><div class="frappe-card-body">${table_content}</div></div>`);

                    // Initialize DataTable
                    setTimeout(() => {
                        if ($.fn.dataTable) {
                            const table = $view.find('#check_in_table');
                            if (table.length && !$.fn.DataTable.isDataTable(table)) {
                                table.DataTable({
                                    paging: true,
                                    searching: true,
                                    ordering: true,
                                    info: true,
                                    lengthMenu: [[10, 25, 50, -1], [10, 25, 50, 'All']],
                                    pageLength: 10,
                                    language: {
                                        search: "Filter:",
                                        lengthMenu: "Show _MENU_ entries"
                                    }
                                });
                            }
                        }
                    }, 100);
                }
            }
        });
    }

    render_guest_list_view() {
        let $view = this.page.main.find(`[data-view-name="guest_list_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="guest_list_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Guest List...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_guest_list',
            callback: (r) => {
                const guests = r.message;
                let table_content;

                if (!guests || guests.length === 0) {
                    table_content = `<p class="text-muted">No guest history found.</p>`;
                } else {
                    const rows = guests.map(g => `
                        <tr>
                            <td><a href="/app/hotel-guest/${g.guest}">${g.guest}</a></td>
                            <td class="text-center">${g.number_of_stays}</td>
                            <td class="text-right">${frappe.format(g.total_revenue, { fieldtype: 'Currency' })}</td>
                            <td>${g.market_place || ''}</td>
                            <td>${frappe.datetime.str_to_user(g.last_stay)}</td>
                        </tr>
                    `).join('');

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
                            const table = $view.find('#guest_list_table');
                            if (table.length && !$.fn.DataTable.isDataTable(table)) {
                                table.DataTable({
                                    paging: true,
                                    searching: true,
                                    ordering: true,
                                    info: true,
                                    lengthMenu: [[10, 25, 50, -1], [10, 25, 50, 'All']],
                                    pageLength: 10
                                });
                            }
                        }
                    }, 100);
                }
            }
        });
    }

    render_check_out_view() {
        let $view = this.page.main.find(`[data-view-name="check_out_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="check_out_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading today's check-outs...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_check_out_list',
            callback: (r) => {
                const check_outs = r.message;
                let table_content;

                if (!check_outs || check_outs.length === 0) {
                    table_content = `<p class="text-muted">No guests are scheduled to check out today.</p>`;
                    const card_header = `<div class="frappe-card-head"><h4>Check-out List</h4></div>`;
                    const card_body = `<div class="frappe-card-body">${table_content}</div>`;
                    $view.html(`<div class="frappe-card">${card_header}${card_body}</div>`);
                } else {
                    const rows = check_outs.map(co => `
                        <tr>
                            <td><a href="/app/hotel-guest/${co.guest}">${co.guest_name}</a></td>
                            <td>${co.room_number}</td>
                            <td>${frappe.datetime.str_to_user(co.check_in_datetime)}</td>
                            <td>${frappe.datetime.str_to_user(co.check_out_datetime)}</td>
                            <td class="text-right">${frappe.format(co.balance, { fieldtype: 'Currency' })}</td>
                            <td>
                                <a href="/app/hotel-room-check-in/${co.check_in}" class="btn btn-xs btn-default">View Check-in</a>
                            </td>
                        </tr>
                    `).join('');

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
                            const table = $view.find('#check_out_table');
                            if (table.length && !$.fn.DataTable.isDataTable(table)) {
                                table.DataTable({
                                    paging: true,
                                    searching: true,
                                    ordering: true,
                                    info: true,
                                    lengthMenu: [[10, 25, 50, -1], [10, 25, 50, 'All']],
                                    pageLength: 10
                                });
                            }
                        }
                    }, 100);
                }
            }
        });
    }

    render_reservation_view() {
        let $view = this.page.main.find(`[data-view-name="reservation_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="reservation_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Reservations...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_reservation_list',
            callback: (r) => {
                const reservations = r.message;
                let table_content;

                if (!reservations || reservations.length === 0) {
                    table_content = `<p class="text-muted">No reservations found.</p>`;
                    $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Reservations</h4></div><div class="frappe-card-body">${table_content}</div></div>`);
                } else {
                    const rows = reservations.map(res => `
                        <tr>
                            <td><a href="/app/hotel-room-reservation/${res.name}">${res.name}</a></td>
                            <td>${res.guest_name}</td>
                            <td><a href="/app/hotel-room/${res.room_number}">${res.room_number}</a></td>
                            <td>${frappe.datetime.str_to_user(res.from_date)}</td>
                            <td>${frappe.datetime.str_to_user(res.to_date)}</td>
                            <td>${res.status}</td>
                            <td>${res.payment_status}</td>
                        </tr>
                    `).join('');

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
                                    <th>Payment Status</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`;

                    $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Reservations</h4></div><div class="frappe-card-body">${table_content}</div></div>`);

                    // Initialize DataTable
                    setTimeout(() => {
                        if ($.fn.dataTable) {
                            const table = $view.find('#reservation_table');
                            if (table.length && !$.fn.DataTable.isDataTable(table)) {
                                table.DataTable({
                                    paging: true,
                                    searching: true,
                                    ordering: true,
                                    info: true,
                                    lengthMenu: [[10, 25, 50, -1], [10, 25, 50, 'All']],
                                    pageLength: 10
                                });
                            }
                        }
                    }, 100);
                }
            }
        });
    }

    refresh_stats() {
        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_room_statistics',
            callback: (r) => {
                this.$stats.empty();
                const stats = r.message;
                this.$stats.append(this.get_stat_card('Vacant Rooms', stats.vacant, 'bed', 'green', { status: 'Vacant' }));
                this.$stats.append(this.get_stat_card('Occupied Rooms', stats.occupied, 'user', 'blue', { status: 'Occupied' }));
                this.$stats.append(this.get_stat_card('Reserved Today', stats.reserved, 'calendar', 'orange', { status: 'Reserved' }));
                this.$stats.append(this.get_stat_card('Dirty Rooms', stats.dirty, 'trash', 'yellow', { housekeeping_status: 'Dirty' }));
                this.$stats.append(this.get_stat_card('In Maintenance', stats.maintenance, 'wrench', 'red', { status: 'Maintenance' }));
            }
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
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_rooms',
            args: { filters: filters },
            callback: (r) => {
                const rooms = r.message;
                this.rooms = rooms; // Store rooms for real-time updates
                this.$room_grid.empty();

                if (rooms.length === 0) {
                    this.$room_grid.html('<p class="text-muted text-center" style="padding: 2rem 0;">No rooms found.</p>');
                    return;
                }

                rooms.forEach(room => {
                    const $card = this.get_room_card(room);
                    this.$room_grid.append($card);

                    $card.click(() => {
                        this.show_room_actions(room);
                    });
                });
            }
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

        this.rooms.forEach(room => {
            if (room.status === 'Occupied' && room.expected_check_out_datetime) {
                const $card = this.$room_grid.find(`.room-card[data-name="${room.name}"] .card`);
                if (!$card.length) return;

                const checkout_time = moment(room.expected_check_out_datetime);
                const diff_minutes = checkout_time.diff(now, 'minutes');

                let new_style = '';
                let overdue_html = '';

                if (diff_minutes < 0) {
                    new_style = 'background-color: #ef9a9a;'; // Darker red
                    const overstay_duration = moment.duration(now.diff(checkout_time)).humanize();
                    overdue_html = `<div class="mt-2 text-danger blink-me overdue-message"><strong>Overdue by ${overstay_duration}</strong></div>`;
                } else if (diff_minutes <= 60) {
                    new_style = 'background-color: #ffcdd2;'; // Lighter red
                }

                $card.css('background-color', new_style ? new_style.split(':')[1].replace(';', '') : '');
                $card.find('.overdue-container').html(overdue_html);
            }
        });
    }

    show_room_actions(room) {
        const actions = [];

        if (room.status === 'Vacant' && room.housekeeping_status === 'Clean') {
            actions.push({
                label: `New Check-in`,
                action: () => frappe.new_doc('Hotel Room Check In', { room_number: room.room_number })
            });
        }

        if (room.status === 'Occupied') {
            actions.push({
                label: 'Check-out',
                action: () => {
                    frappe.call({
                        method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out',
                        args: {
                            source_name: room.current_check_in
                        },
                        callback: (r) => {
                            if (r.message) {
                                frappe.set_route('Form', 'Hotel Room Check Out', r.message.name);
                            }
                        }
                    });
                }
            });
            if (room.current_check_in) {
                actions.push({
                    label: 'Open Check-in',
                    action: () => frappe.set_route('Form', 'Hotel Room Check In', room.current_check_in)
                });
            }
        }

        if (room.status === 'Reserved') {
            // Action to create check-in from reservation
        }

        actions.push({
            label: 'Maintenance Request',
            action: () => frappe.new_doc('Maintenance Request', { room: room.name })
        });

        actions.push({
            label: 'Room Details',
            action: () => frappe.set_route('Form', 'Hotel Room', room.name)
        });

        const dialog_fields = [];

        if (room.status === 'Occupied') {
            dialog_fields.push({ fieldtype: 'Section Break', label: 'Current Check-in Details' });
            dialog_fields.push({
                fieldtype: 'Data', label: 'Guest', default: room.current_guest, read_only: 1
            });
            dialog_fields.push({
                fieldtype: 'Data', label: 'Check-in Time', default: room.check_in_datetime ? frappe.datetime.str_to_user(room.check_in_datetime) : 'N/A', read_only: 1,
                wrapper_class: 'col-md-6'
            });
            dialog_fields.push({
                fieldtype: 'Data', label: 'Expected Check-out', default: room.expected_check_out_datetime ? frappe.datetime.str_to_user(room.expected_check_out_datetime) : 'N/A', read_only: 1,
                wrapper_class: 'col-md-6'
            });
        }
        dialog_fields.push(

            { fieldtype: 'Section Break', label: 'Room Details' },
            {
                fieldtype: 'Data', label: 'Room Type', default: room.room_type, read_only: 1,
                wrapper_class: 'col-md-6'
            },
            {
                fieldtype: 'Data', label: 'Floor', default: room.floor, read_only: 1,
                wrapper_class: 'col-md-6'
            },
            {
                fieldtype: 'Data', label: 'Status', default: room.status, read_only: 1,
                wrapper_class: 'col-md-6'
            },
            {
                fieldtype: 'Data', label: 'Housekeeping', default: room.housekeeping_status, read_only: 1,
                wrapper_class: 'col-md-6'
            }

        );

        const dialog = new frappe.ui.Dialog({
            title: `Room ${room.room_number}`,
            fields: dialog_fields,
            // Set primary action only if actions are available, otherwise it will be 'Close'
            primary_action_label: actions.length > 0 ? actions[0].label : 'Close',
            primary_action: actions[0].action
        });

        actions.slice(1).forEach(act => {
            dialog.add_custom_action(act.label, act.action);
        });

        dialog.show();
    }

    render_housekeeping_view() {
        let $view = this.page.main.find(`[data-view-name="housekeeping_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="housekeeping_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Housekeeping Queue...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_housekeeping_queue',
            callback: (r) => {
                const tasks = r.message;
                let table_content;

                if (!tasks || tasks.length === 0) {
                    table_content = `<p class="text-muted">All rooms are clean!</p>`;
                    $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Housekeeping Queue</h4></div><div class="frappe-card-body">${table_content}</div></div>`);
                } else {
                    const priority_icons = {
                        'In Progress': 'spinner fa-spin',
                        'Dirty': 'trash',
                        'Inspected': 'eye',
                        'Clean': 'check'
                    };

                    const rows = tasks.map(task => `
                        <tr>
                            <td><strong>${task.room_number}</strong></td>
                            <td>${task.floor || '-'}</td>
                            <td>${task.room_type}</td>
                            <td>
                                <span style="padding: 0.25rem 0.75rem; background-color: ${task.priority <= 2 ? '#ffe0e0' : '#e8f5e9'}; border-radius: 4px;">
                                    <i class="fa fa-${priority_icons[task.housekeeping_status] || 'question'}"></i> ${task.housekeeping_status}
                                </span>
                            </td>
                            <td class="text-right">
                                <a href="/app/hotel-room/${task.name}" class="btn btn-xs btn-default">View</a>
                            </td>
                        </tr>
                    `).join('');

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

                    $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Housekeeping Queue</h4></div><div class="frappe-card-body">${table_content}</div></div>`);

                    // Initialize DataTable
                    setTimeout(() => {
                        if ($.fn.dataTable) {
                            const table = $view.find('#housekeeping_table');
                            if (table.length && !$.fn.DataTable.isDataTable(table)) {
                                table.DataTable({
                                    paging: true,
                                    searching: true,
                                    ordering: true,
                                    info: true,
                                    lengthMenu: [[10, 25, 50, -1], [10, 25, 50, 'All']],
                                    pageLength: 10
                                });
                            }
                        }
                    }, 100);
                }
            }
        });
    }

    render_payments_view() {
        let $view = this.page.main.find(`[data-view-name="payments_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="payments_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Payment Status...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_rooms_with_payment_status',
            callback: (r) => {
                const rooms = r.message;
                let table_content;

                if (!rooms || rooms.length === 0) {
                    table_content = `<p class="text-muted">No occupied rooms with payment data.</p>`;
                    $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Payment Status</h4></div><div class="frappe-card-body">${table_content}</div></div>`);
                } else {
                    const rows = rooms.map(room => {
                        const balance_color = room.balance > 0 ? '#ffebee' : '#e8f5e9';
                        return `
                        <tr style="background-color: ${balance_color};">
                            <td><strong>${room.room_number}</strong></td>
                            <td><a href="/app/hotel-guest/${room.guest}">${room.current_guest}</a></td>
                            <td class="text-right">${frappe.format(room.total_invoice, { fieldtype: 'Currency' })}</td>
                            <td class="text-right">${frappe.format(room.total_paid, { fieldtype: 'Currency' })}</td>
                            <td class="text-right"><strong>${frappe.format(room.balance, { fieldtype: 'Currency' })}</strong></td>
                            <td class="text-right">
                                <a href="/app/payment-entry/new?custom_hotel_room_check_in=${room.current_check_in}" class="btn btn-xs btn-primary">Settle</a>
                            </td>
                        </tr>
                    `}).join('');

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

                    $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Payment Status</h4></div><div class="frappe-card-body">${table_content}</div></div>`);

                    // Initialize DataTable
                    setTimeout(() => {
                        if ($.fn.dataTable) {
                            const table = $view.find('#payments_table');
                            if (table.length && !$.fn.DataTable.isDataTable(table)) {
                                table.DataTable({
                                    paging: true,
                                    searching: true,
                                    ordering: true,
                                    info: true,
                                    lengthMenu: [[10, 25, 50, -1], [10, 25, 50, 'All']],
                                    pageLength: 10
                                });
                            }
                        }
                    }, 100);
                }
            }
        });
    }

    render_night_audit_view() {
        let $view = this.page.main.find(`[data-view-name="night_audit_view"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="night_audit_view" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Night Audit Data...</p></div></div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_night_audit_data',
            callback: (r) => {
                const data = r.message;

                const audit_cards = `
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                        <div class="frappe-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
                            <div class="card-body">
                                <h5 class="card-title">Occupancy Rate</h5>
                                <h2 style="margin: 1rem 0;">${data.occupancy_rate}%</h2>
                                <small>${data.occupied_rooms}/${data.total_rooms} rooms occupied</small>
                            </div>
                        </div>
                        <div class="frappe-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white;">
                            <div class="card-body">
                                <h5 class="card-title">Today's Revenue</h5>
                                <h2 style="margin: 1rem 0;">${frappe.format(data.today_revenue, { fieldtype: 'Currency' })}</h2>
                                <small>Total income today</small>
                            </div>
                        </div>
                        <div class="frappe-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); color: white;">
                            <div class="card-body">
                                <h5 class="card-title">Pending Payments</h5>
                                <h2 style="margin: 1rem 0;">${frappe.format(data.pending_payments, { fieldtype: 'Currency' })}</h2>
                                <small>Outstanding balance</small>
                            </div>
                        </div>
                        <div class="frappe-card" style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: #333;">
                            <div class="card-body">
                                <h5 class="card-title">No-Shows</h5>
                                <h2 style="margin: 1rem 0; color: #d32f2f;">${data.no_shows}</h2>
                                <small>Cancelled/No-show reservations</small>
                            </div>
                        </div>
                    </div>`;

                $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Night Audit Dashboard</h4></div><div class="frappe-card-body">${audit_cards}</div></div>`);
            }
        });
    }

    render_room_stay_report() {
        let $view = this.page.main.find(`[data-view-name="room_stay_report"]`);
        if (!$view.length) {
            $view = $(`<div class="view-container" data-view-name="room_stay_report" style="padding: 1rem 0;"></div>`).appendTo(this.page.main);
        }
        $view.show();
        $view.html(`<div class="frappe-card"><div class="frappe-card-body"><p class="text-muted">Loading Room Stay Report...</p></div></div>`);

        // Create date range picker
        const today = frappe.datetime.get_today();
        const thirtyDaysAgo = frappe.datetime.add_days(today, -30);

        const filterHtml = `
            <div style="margin-bottom: 1rem; display: flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap;">
                <div>
                    <label for="stay_from_date" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">From Date</label>
                    <input type="date" id="stay_from_date" value="${thirtyDaysAgo}" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 150px;">
                </div>
                <div>
                    <label for="stay_to_date" style="display: block; margin-bottom: 0.5rem; font-weight: 500;">To Date</label>
                    <input type="date" id="stay_to_date" value="${today}" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; width: 150px;">
                </div>
                <button id="stay_report_generate" class="btn btn-primary">Generate Report</button>
            </div>`;

        $view.html(`<div class="frappe-card"><div class="frappe-card-head"><h4>Room Stay Report</h4></div><div class="frappe-card-body">${filterHtml}<div id="report_container"></div></div></div>`);

        // Bind generate button
        $view.find('#stay_report_generate').on('click', () => {
            const fromDate = $view.find('#stay_from_date').val();
            const toDate = $view.find('#stay_to_date').val();
            this.generate_stay_report(fromDate, toDate, $view.find('#report_container'));
        });

        // Generate initial report
        this.generate_stay_report(thirtyDaysAgo, today, $view.find('#report_container'));
    }

    generate_stay_report(fromDate, toDate, $container) {
        $container.html(`<div class="text-muted">Generating report...</div>`);

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_room_stay_data',
            args: { from_date: fromDate, to_date: toDate },
            callback: (r) => {
                const data = r.message;
                const rooms = data.rooms;
                const checkIns = data.check_ins;
                const reservations = data.reservations;

                // Parse dates
                const startDate = moment(fromDate);
                const endDate = moment(toDate);
                const dayCount = endDate.diff(startDate, 'days') + 1;

                // Generate date headers
                let dateHeaderContent = '';
                for (let i = 0; i < dayCount; i++) {
                    const d = moment(startDate).add(i, 'days');
                    dateHeaderContent += `<div class="date-column date-header">${d.format('DD/MM')}</div>`;
                }

                let headerHtml = `<div class="stay-timeline-header">
                    <div style="font-weight: bold;">Room</div>
                    <div class="timeline-dates">${dateHeaderContent}</div>
                </div>`;

                // Generate room rows
                let rowsHtml = '';

                rooms.forEach(room => {
                    // Find check-ins for this room
                    const roomCheckIns = checkIns.filter(ci => ci.room_number === room.room_number);
                    const roomReservations = reservations.filter(res => res.room_number === room.room_number);

                    // Create a map of dates to stay information
                    const dateStayMap = {};

                    // Fill in check-ins
                    for (let ci of roomCheckIns) {
                        const ciStart = moment(ci.check_in_datetime);
                        const ciEnd = moment(ci.expected_check_out_datetime);

                        let currentDay = ciStart.clone();
                        while (currentDay.isBefore(ciEnd) || currentDay.isSame(ciEnd)) {
                            const dateKey = currentDay.format('YYYY-MM-DD');
                            if (!dateStayMap[dateKey]) {
                                dateStayMap[dateKey] = {
                                    guest: ci.guest || 'Guest',
                                    type: 'checked-in',
                                    stayId: ci.name
                                };
                            }
                            currentDay.add(1, 'day');
                        }
                    }

                    // Fill in reservations (only if no check-in for that date)
                    for (let res of roomReservations) {
                        const resStart = moment(res.from_date);
                        const resEnd = moment(res.to_date);

                        let currentDay = resStart.clone();
                        while (currentDay.isBefore(resEnd) || currentDay.isSame(resEnd)) {
                            const dateKey = currentDay.format('YYYY-MM-DD');
                            if (!dateStayMap[dateKey]) {
                                dateStayMap[dateKey] = {
                                    guest: res.guest_name,
                                    type: 'reserved',
                                    stayId: res.name
                                };
                            }
                            currentDay.add(1, 'day');
                        }
                    }

                    let dateContent = '';
                    let i = 0;

                    // Generate timeline for each day
                    while (i < dayCount) {
                        const currentDate = moment(startDate).add(i, 'days');
                        const dateStr = currentDate.format('YYYY-MM-DD');

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
                                const nextDate = moment(startDate).add(j, 'days');
                                const nextDateStr = nextDate.format('YYYY-MM-DD');
                                const nextStay = dateStayMap[nextDateStr];

                                if (nextStay && nextStay.stayId === currentStayId && nextStay.type === currentType) {
                                    stayLength++;
                                    j++;
                                } else {
                                    break;
                                }
                            }

                            // Calculate width as percentage
                            const widthPercent = (stayLength * 80) + 'px'; // 80px per column
                            const barStyle = currentType === 'reserved'
                                ? 'background: linear-gradient(135deg, #ffa726 0%, #fb8c00 100%);'
                                : 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);';

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

                const finalHtml = `<div class="stay-timeline-container">${headerHtml}${rowsHtml}</div>`;
                $container.html(finalHtml);
            }
        });
    }
}
