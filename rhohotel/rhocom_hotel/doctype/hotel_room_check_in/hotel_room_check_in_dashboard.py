from frappe import _

def get_data():
    return {
        'fieldname': 'custom_hotel_room_check_in',
        'non_standard_fieldnames': {
            'Sales Invoice': 'custom_hotel_room_check_in',
            'Payment Entry': 'custom_hotel_room_check_in'
        },
        'transactions': [
            {
                'label': _('Related'),
                'items': ['Sales Invoice', 'Payment Entry']
            }
        ],
        'charts': [
            {
                'label': _('Occupancy Rate'),
                'type': 'percentage',
                'method': 'rhohotel.api.get_occupancy_rate'
            },
            {
                'label': _('Average Stay Length'),
                'type': 'number',
                'method': 'rhohotel.api.get_average_stay_length'
            },
            {
                'label': _('Revenue per Day'),
                'type': 'bar',
                'method': 'rhohotel.api.get_room_revenue'
            }
        ]
    }
