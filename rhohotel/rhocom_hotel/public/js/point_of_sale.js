// Custom POS Enhancement - Add Room Selector
// Place this in: rhocom_hotel/public/js/point_of_sale.js

frappe.provide("rhohotel.pos");

// Hook into POS page load
frappe.pages['point-of-sale'].on_page_load = function(wrapper) {
    // Wait for POS to fully load
    setTimeout(() => {
        addRoomSelector(wrapper);
    }, 500);
};

function addRoomSelector(wrapper) {
    // Check if room selector already exists
    if ($('.room-selector-section').length) {
        return;
    }

    // Create room selector HTML
    const roomSelectorHTML = `
        <div class="room-selector-section" style="padding: 12px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; margin-bottom: 15px;">
            <div style="margin-bottom: 8px;">
                <label style="display: block; font-weight: 600; margin-bottom: 6px; color: #333;">
                    Load Guest from Room
                </label>
                <div class="room-selector-wrapper" style="display: flex; gap: 8px;">
                    <input type="text" 
                           class="room-number-input form-control" 
                           placeholder="Enter room number..." 
                           style="flex: 1;">
                    <button class="btn btn-primary load-guest-btn" style="white-space: nowrap;">
                        Load Guest
                    </button>
                </div>
                <small style="color: #666; margin-top: 4px; display: block;">
                    Select a room to automatically load the current guest
                </small>
            </div>
        </div>
    `;

    // Find the POS main container and insert the room selector
    const posMain = $('.pos-main') || $('.page-content');
    
    if (posMain.length) {
        // Insert at the top of POS main area
        $(roomSelectorHTML).prependTo(posMain);
        
        // Bind the load guest button
        bindRoomSelector();
    }
}

function bindRoomSelector() {
    // Handle load guest button click
    $(document).on('click', '.load-guest-btn', function() {
        const roomNumber = $('.room-number-input').val().trim();
        
        if (!roomNumber) {
            frappe.msgprint('Please enter a room number');
            return;
        }

        loadGuestFromRoom(roomNumber);
    });

    // Handle Enter key in room input
    $(document).on('keypress', '.room-number-input', function(e) {
        if (e.which === 13) { // Enter key
            e.preventDefault();
            $('.load-guest-btn').click();
        }
    });

    // Add autocomplete to room input
    makeRoomInputAutocomplete();
}

function makeRoomInputAutocomplete() {
    $('.room-number-input').autocomplete({
        source: function(request, response) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Hotel Room',
                    filters: {
                        'room_number': ['like', '%' + request.term + '%'],
                        'status': ['!=', 'Maintenance']
                    },
                    fields: ['name', 'room_number', 'room_type', 'current_guest'],
                    limit_page_length: 10
                },
                callback: function(r) {
                    if (r.message) {
                        response(r.message.map(room => ({
                            label: `${room.room_number} - ${room.room_type}`,
                            value: room.name
                        })));
                    }
                }
            });
        },
        select: function(event, ui) {
            $('.room-number-input').val(ui.item.value);
            loadGuestFromRoom(ui.item.value);
            return false;
        },
        minLength: 1
    });
}

function loadGuestFromRoom(roomNumber) {
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Hotel Room',
            name: roomNumber
        },
        callback: function(r) {
            if (r.message) {
                const room = r.message;
                
                if (room.current_guest) {
                    // Get the POS instance and set the customer
                    if (window.cur_pos) {
                        // Set the customer in the POS
                        cur_pos.frm.set_value('customer', room.current_guest);
                        
                        // Fetch customer details
                        frappe.call({
                            method: 'frappe.client.get',
                            args: {
                                doctype: 'Hotel Guest',
                                name: room.current_guest
                            },
                            callback: function(guest_r) {
                                if (guest_r.message) {
                                    const guest = guest_r.message;
                                    frappe.show_alert({
                                        message: `<strong>${guest.guest_name}</strong> from <strong>Room ${room.room_number}</strong> loaded successfully`,
                                        indicator: 'green'
                                    });
                                }
                            }
                        });
                    }
                } else {
                    frappe.show_alert({
                        message: `Room ${roomNumber} has no current guest assigned`,
                        indicator: 'orange'
                    });
                }
            } else {
                frappe.show_alert({
                    message: `Room ${roomNumber} not found`,
                    indicator: 'red'
                });
            }
        }
    });
}