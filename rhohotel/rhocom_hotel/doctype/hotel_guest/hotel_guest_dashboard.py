from frappe import _

def get_data():
    return {
        'fieldname': 'guest',   # default for doctypes that use guest
        'non_standard_fieldnames': {
            'Sales Invoice': 'customer',
            'Payment Entry': 'party'   # or 'customer' if that's your custom field
        },
        'transactions': [
            {
                'label': _('Related'),
                'items': ['Hotel Room Check In', 'Payment Entry', 'Sales Invoice']
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

