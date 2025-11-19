frappe.pages['front-desk'].on_page_load = function (wrapper) {
    new FrontDesk(wrapper);

    // Add CSS for blinking animation
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
        this.make_stats_area();
        this.make_filters();
        this.make_room_grid();

        this.refresh();
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

    make_filters() {
        const fields = [
            {
                fieldtype: 'Link',
                label: 'Floor',
                fieldname: 'floor',
                options: 'Hotel Floor',
                change: () => this.refresh()
            },
            {
                fieldtype: 'Link',
                label: 'Room Type',
                fieldname: 'room_type',
                options: 'Hotel Room Type',
                change: () => this.refresh()
            },
            {
                fieldtype: 'Select',
                label: 'Status',
                fieldname: 'status',
                options: '\nVacant\nOccupied\nReserved\nMaintenance',
                change: () => this.refresh()
            },
            {
                fieldtype: 'Select',
                label: 'Housekeeping',
                fieldname: 'housekeeping_status',
                options: '\nClean\nDirty\nInspected\nIn Progress',
                change: () => this.refresh()
            },
            {
                fieldtype: 'Check',
                label: 'Checking Out Today',
                fieldname: 'checkout_today',
                change: () => this.refresh()
            }
        ];

        fields.forEach(df => {
            this.page.add_field(df);
        });
    }

    make_room_grid() {
        this.$room_grid = $(`<div class="room-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; padding: 1rem 0;"></div>`).appendTo(this.page.main);
    }
    // -----------------------------------------------------------

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
        this.refresh_stats();
        this.refresh_rooms();
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
            // Set primary action only if actions are available
            primary_action_label: actions.length > 0 ? actions[0].label : 'Close',
            primary_action: actions[0].action
        });

        actions.slice(1).forEach(act => {
            dialog.add_custom_action(act.label, act.action);
        });

        dialog.show();
    }
}
