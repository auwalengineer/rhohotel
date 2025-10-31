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
        this.make_filters();
        this.make_room_grid();
        this.refresh();

        // Auto refresh every minute
        setInterval(() => this.refresh(), 60000);
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
        this.$grid = $('<div class="room-grid"></div>').appendTo(this.page.main);
        this.$grid.css({
            display: 'grid',
            'grid-template-columns': 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1rem',
            padding: '1rem'
        });
    }

    get_room_card(room) {
        const status_colors = {
            'Vacant': 'green',
            'Occupied': 'blue',
            'Reserved': 'orange',
            'Maintenance': 'red'
        };

        const housekeeping_icons = {
            'Clean': 'check',
            'Dirty': 'remove',
            'Inspected': 'eye',
            'In Progress': 'refresh'
        };

        return $(`
			<div class="room-card" data-name="${room.name}">
				<div class="card" style="border-left: 3px solid var(--${status_colors[room.status]}-500)">
					<div class="card-body">
						<h5 class="card-title">
							${room.room_number}
							<span class="float-right">
								<i class="fa fa-${housekeeping_icons[room.housekeeping_status] || 'question'}"
								   title="${room.housekeeping_status}"></i>
							</span>
						</h5>
						<div class="card-text">
							<div>${room.hotel_room_type}</div>
							<div class="text-muted">${room.floor_name || ''}</div>
							${room.current_guest ? `
								<div class="mt-2">
									<strong>Guest:</strong> ${room.current_guest}<br>
									<small>Checkout: ${room.expected_checkout || 'N/A'}</small>
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
			</div>
		`);
    }

    refresh() {
        const filters = this.page.get_form_values();
        this.filters = filters;

        frappe.call({
            method: 'rhohotel.rhocom_hotel.page.front_desk.front_desk.get_rooms',
            args: { filters: filters },
            callback: (r) => {
                this.$grid.empty();
                r.message.forEach(room => {
                    const $card = this.get_room_card(room);
                    this.$grid.append($card);

                    // Add click handler
                    $card.click(() => {
                        this.show_room_actions(room);
                    });
                });
            }
        });
    }

    show_room_actions(room) {
        const actions = [];

        if (room.status === 'Vacant') {
            actions.push({
                label: 'New Check-in',
                action: () => frappe.new_doc('Hotel Room Check In', { room: room.name })
            });
        }

        if (room.status === 'Occupied') {
            actions.push({
                label: 'Check-out',
                action: () => {
                    frappe.model.open_mapped_doc({
                        method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_in.hotel_room_check_in.make_check_out',
                        frm: room.check_in
                    });
                }
            });
            // Add button to open check-in guest
            if (room.check_in) {
                actions.push({
                    label: 'Open Check-in Guest',
                    action: () => frappe.set_route('Form', 'Hotel Room Check In', room.check_in)
                });
            }
        }

        actions.push({
            label: 'Maintenance Request',
            action: () => frappe.new_doc('Hotel Room Maintenance Request', { room: room.name })
        });

        actions.push({
            label: 'Room Details',
            action: () => frappe.set_route('Form', 'Hotel Room', room.name)
        });

        frappe.msgprint({
            title: `Room ${room.room_number}`,
            primary_action_label: actions[0].label,
            primary_action: actions[0].action,
            secondary_actions: actions.slice(1)
        });
    }
}