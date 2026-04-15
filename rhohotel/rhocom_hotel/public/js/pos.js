frappe.ui.form.on('POS Invoice', {
    onload: function (frm) {
        frm.add_custom_button(__('Select Room'), function () {
            frappe.prompt(
                [
                    {
                        label: 'Room Number',
                        fieldname: 'room_number',
                        fieldtype: 'Link',
                        options: 'Hotel Room',
                        reqd: 1
                    }
                ],
                function (values) {
                    frm.set_value('room_number', values.room_number);

                    // Get active check-in for this room number
                    frappe.call({
                        method: 'rhohotel.api.get_active_checkin_for_room',
                        args: { room_number: values.room_number },
                        callback: function (r) {
                            if (r.message) {
                                frm.set_value('hotel_room_check_in', r.message.name);
                                frm.set_value('customer', r.message.guest);
                                frappe.msgprint(__('Linked to active check-in for Room ' + values.room_number));
                            } else {
                                frappe.msgprint(__('No active check-in for this room.'));
                            }
                        }
                    });
                },
                __('Select Room')
            );
        });
    }
});