(function () {
    if (typeof frappe === 'undefined') return;

    function fetchFilters() {
        return {
            floor: document.getElementById('fd-floor').value || null,
            room_type: document.getElementById('fd-room-type').value || null,
            status: document.getElementById('fd-status').value || null,
            maintenance: document.getElementById('fd-maint').value ? 1 : null,
            upcoming_checkout_hours: +(document.getElementById('fd-upcoming').value || 0) || null
        };
    }

    function renderRoomCard(room) {
        var color = '#bdc3c7';
        switch ((room.status || '').toLowerCase()) {
            case 'vacant': color = '#2ecc71'; break;
            case 'occupied': color = '#e74c3c'; break;
            case 'reserved': color = '#f1c40f'; break;
            case 'non operational': color = '#7f8c8d'; break;
        }
        if (room.maintenance) color = '#e67e22';

        var col = document.createElement('div');
        col.className = 'col-sm-3 mb-3';
        var card = document.createElement('div');
        card.className = 'card';
        card.style.borderTop = '6px solid ' + color;
        card.innerHTML = '\n            <div class="card-body">\n                <h5 class="card-title">' + room.room + '</h5>\n                <p class="card-text small">' + (room.room_type || '') + ' • Floor: ' + (room.floor || '') + '</p>\n                <p class="card-text small">Status: <strong>' + (room.status || '') + '</strong></p>\n                <p class="card-text small">Guest: ' + (room.guest_name || '-') + '</p>\n                <p class="card-text small">Checkout: ' + (room.expected_check_out_datetime || '-') + '</p>\n                <div class="btn-group">\n                    <a class="btn btn-sm btn-outline-primary" href="#/desk#Form/Hotel Room/' + room.room + '">Open</a>\n                    <a class="btn btn-sm btn-outline-secondary" href="#/desk#Form/Hotel Room Check In/' + (room.current_check_in || 'new') + '">Check In</a>\n                </div>\n            </div>';
        col.appendChild(card);
        return col;
    }

    function loadFiltersAndGrid() {
        // populate floors and room types
        frappe.call({
            method: 'frappe.client.get_list',
            args: { doctype: 'Hotel Floor', fields: ['name'], limit_page_length: 200 },
            callback: function (r) {
                function updateNumberCards(rooms) {
                    var vacant = 0, occupied = 0, reserved = 0, maintenance = 0;
                    rooms.forEach(function (room) {
                        if (room.maintenance) maintenance++;
                        else if ((room.status || '').toLowerCase() === 'vacant') vacant++;
                        else if ((room.status || '').toLowerCase() === 'occupied') occupied++;
                        else if ((room.status || '').toLowerCase() === 'reserved') reserved++;
                    });
                    document.getElementById('fd-vacant-count').textContent = vacant;
                    document.getElementById('fd-occupied-count').textContent = occupied;
                    document.getElementById('fd-reserved-count').textContent = reserved;
                    document.getElementById('fd-maintenance-count').textContent = maintenance;
                }

                var sel = document.getElementById('fd-floor');
                if (r.message) {
                    r.message.forEach(function (f) {
                        var o = document.createElement('option'); o.value = f.name; o.text = f.name; sel.appendChild(o);
                    });
                }
            }
        });
        frappe.call({
            method: 'frappe.client.get_list',
            args: { doctype: 'Hotel Room Type', fields: ['name'], limit_page_length: 200 },
            callback: function (r) {
                var sel = document.getElementById('fd-room-type');
                if (r.message) {
                    r.message.forEach(function (f) {
                        var o = document.createElement('option'); o.value = f.name; o.text = f.name; sel.appendChild(o);
                    });
                }
            }
        });

        fetchAndRender();
    }

    function fetchAndRender() {
        var filters = fetchFilters();
        frappe.call({
            method: 'rhohotel.rhocom_hotel.api.front_desk.get_rooms_summary',
            args: { filters: JSON.stringify(filters) },
            callback: function (r) {
                var grid = document.getElementById('fd-grid');
                grid.innerHTML = '';
                if (!r.message) return;
                r.message.forEach(function (room) {
                    grid.appendChild(renderRoomCard(room));
                });
            }
        });
    }
    updateNumberCards(r.message);

    frappe.ready(function () {
        loadFiltersAndGrid();
        document.getElementById('fd-filter').onclick = fetchAndRender;
        updateNumberCards([]);
        document.getElementById('fd-refresh').onclick = fetchAndRender;
    });
})();