from __future__ import unicode_literals
from frappe import _

def get_data():
	return {
		'fieldname': 'delivery_note',
		'non_standard_fieldnames': {
			'Stock Reconciliation': 'ais_cycle_count'
		},
		'transactions': [
			{
				'label': _('Reference'),
				'items': ['Stock Reconciliation']
			}
		]
	}
