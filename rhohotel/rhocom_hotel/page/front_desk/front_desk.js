frappe.pages['front-desk'].on_page_load = function (wrapper) {
    new FrontDesk(wrapper);
}

class FrontDesk {
    constructor(wrapper) {
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Front Desk',
            single_column: true
        });

        this.filters = {};
        this.make_stats_area();
        this.make_filters();
        this.make_room_grid();

        this.refresh();
        this.start_clock();

        // Realtime updates
        frappe.realtime.on('rhohotel_front_desk_update', () => {
            this.refresh();
        });
    }


    make_stats_area() {
        this.$stats = $("<div class=\"room-stats\"></div>").appendTo(this.page.main);
        this.$stats.css({
            display: 'grid',
            'grid-template-columns': 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1rem',
            padding: '1rem'
        });

        // Insert stats area at the top of the page
        $(this.page.main).parent().prepend(this.$stats);

        this.$clock = $("<div class=\"clock-widget\"></div>").prependTo(this.$stats);
        this.$clock.css({
            'font-size': '1.5rem',
            'font-weight': 'bold',
            'text-align': 'center',
            'padding': '1rem',
            'grid-column': '1 / -1'
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
                label: 'Checkout Today',
                fieldname: 'checkout_today',
                change: () => this.refresh()
            }
        ];

        fields.forEach(df => {
            this.page.add_field(df);
        });
    }

    make_room_grid() {
        this.$tab_nav = $(`<ul class="nav nav-tabs" role="tablist"></ul>`).appendTo(this.page.main);
        this.$tab_content = $(`<div class="tab-content"></div>`).appendTo(this.page.main);
    }
    // -----------------------------------------------------------

    get_room_card(room) {
        const status_colors = {
            'Vacant': 'green',
            'Occupied': 'blue',
            'Reserved': 'orange',
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
            `<div class="room-card" data-name="${room.name}">
                <div class="card" style="border-left: 3px solid var(--${status_color}-500)">
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
                                    <small>Checkout: ${room.expected_checkout ? frappe.datetime.str_to_user(room.expected_checkout) : 'N/A'}</small>
                                </div>
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
                </div>
            </div>`
        );
    }

    get_stat_card(label, value, icon, color) {
        return $(
            `<div class="stat-card">
                <div class="card" style="background-color: var(--${color}-50)">
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
                this.$stats.append(this.get_stat_card('Vacant Rooms', stats.vacant, 'bed', 'green'));
                this.$stats.append(this.get_stat_card('Occupied Rooms', stats.occupied, 'user', 'blue'));
                this.$stats.append(this.get_stat_card('Reserved Today', stats.reserved, 'calendar', 'orange'));
                this.$stats.append(this.get_stat_card('Dirty Rooms', stats.dirty, 'trash', 'yellow'));
                this.$stats.append(this.get_stat_card('In Maintenance', stats.maintenance, 'wrench', 'red'));
            }
        });
    }

    refresh_rooms() {
        const filters = this.page.get_form_values();
        this.filters = filters;

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_rooms',
            args: { filters: filters },
            callback: (r) => {
                const rooms = r.message;
                this.$tab_nav.empty();
                this.$tab_content.empty();

                if (rooms.length === 0) {
                    this.$tab_content.html('<p class="text-muted text-center" style="padding: 2rem 0;">No rooms found.</p>');
                    return;
                }

                const rooms_by_floor = this.group_by(rooms, 'floor');

                Object.keys(rooms_by_floor).forEach((floor, index) => {
                    const floor_id = floor.replace(/\s+/g, '-').toLowerCase();
                    const is_active = index === 0;

                    this.$tab_nav.append(`
                        <li class="nav-item">
                            <a class="nav-link ${is_active ? 'active' : ''}" id="${floor_id}-tab" data-toggle="tab" href="#${floor_id}" role="tab" aria-controls="${floor_id}" aria-selected="${is_active}">${floor}</a>
                        </li>
                    `);

                    const $tab_pane = $(`
                        <div class="tab-pane fade ${is_active ? 'show active' : ''}" id="${floor_id}" role="tabpanel" aria-labelledby="${floor_id}-tab">
                            <div class="room-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; padding: 1rem 0;"></div>
                        </div>
                    `).appendTo(this.$tab_content);

                    const $grid = $tab_pane.find('.room-grid');
                    rooms_by_floor[floor].forEach(room => {
                        const $card = this.get_room_card(room);
                        $grid.append($card);

                        $card.click(() => {
                            this.show_room_actions(room);
                        });
                    });
                });
            }
        });
    }

    group_by(array, key) {
        return array.reduce((result, currentValue) => {
            (result[currentValue[key]] = result[currentValue[key]] || []).push(currentValue);
            return result;
        }, {});
    }

    start_clock() {
        setInterval(() => {
            this.$clock.text(frappe.datetime.now_datetime());
        }, 1000);
    }

    show_room_actions(room) {
        const actions = [];

        if (room.status === 'Vacant' && room.housekeeping_status === 'Clean') {
            actions.push({
                label: 'New Check-in',
                action: () => frappe.new_doc('Hotel Room Check In', { room: room.name })
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

        const dialog = new frappe.ui.Dialog({
            title: `Room ${room.room_number}`,
            fields: [
                // Can add more details here if needed
            ],
            primary_action_label: actions[0].label,
            primary_action: actions[0].action
        });

        actions.slice(1).forEach(act => {
            dialog.add_custom_action(act.label, act.action);
        });

        dialog.show();
    }
}
