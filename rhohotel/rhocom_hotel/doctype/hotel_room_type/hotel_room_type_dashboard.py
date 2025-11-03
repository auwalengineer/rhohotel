from frappe import _

def get_data():
    return {
        'fieldname': 'room_type',
        'transactions': [
            {
                'label': _('Related'),
                'items': ['Hotel Room']
            }
        ],
        'charts': [
            {
                'label': _('Average Rate per Room Type'),
                'type': 'bar',
                'method': 'rhohotel.api.get_average_rate_per_room_type'
            },
            {
                'label': _('Number of Active Rooms'),
                'type': 'bar',
                'method': 'rhohotel.api.get_active_rooms_count'
            }
        ]
    }
