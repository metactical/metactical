import frappe
from erpnext.stock.stock_balance import update_bin_qty, get_reserved_qty

def recalculate_reserved_qty():
	items = frappe.get_all("Bin", fields=['item_code', 'warehouse'])
	for item in items:
		update_bin_qty(item.item_code, item.warehouse, {
			"reserved_qty": get_reserved_qty(item.item_code, item.warehouse)
		})
		
