from frappe import _

def get_data():
    return {
        'fieldname': 'guest_name',
        'transactions': [
            {
                'label': _('Related'),
                'items': ['Hotel Room Check In', 'Sales Invoice']
            }
        ],
        'charts': [
            {
                'label': _('Total Nights Stayed'),
                'type': 'number',
                'method': 'rhohotel.api.get_total_nights_stayed'
            },
            {
                'label': _('Lifetime Value'),
                'type': 'number',
                'method': 'rhohotel.api.get_guest_lifetime_value'
            }
        ]
    }
