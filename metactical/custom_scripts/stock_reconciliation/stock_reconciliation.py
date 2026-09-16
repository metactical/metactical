import frappe
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from frappe.model.docstatus import DocStatus
from metactical.custom_scripts.utils.metactical_utils import queue_action
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

class CustomStockReconciliation(StockReconciliation):
	# def save(self):
	# 	if self.docstatus == DocStatus.submitted() and len(self.items) > 100 and \
	# 		self.ais_queue_status and self.ais_queue_status != "Queued":
	# 		msgprint(
	# 			_(
	# 				"The task has been enqueued as a background job. In case there is \
	# 				any issue on processing in background, the system will add a comment \
	# 				about the error on this document and revert to the Draft stage"
	# 			)
	# 		)
	# 		queue_action(self, "submit", timeout=2000)
	# 	else:
			# super().save()

	def validate(self):
		super(CustomStockReconciliation, self).validate()
		# Metactical Customization: Validate that user has permission to reconcile stock against warehouse.
		# Uses Nested Set lft/rgt so group warehouses cover all descendants without expanding them.
		from metactical.metactical.doctype.warehouse_user_permissions.warehouse_user_permissions import (
			get_setting_name, has_permitted_warehouses, is_warehouse_permitted,
		)
		user = frappe.session.user
		setting_name = get_setting_name(user)
		if not setting_name or not has_permitted_warehouses(setting_name, "cycle_count_warehouse"):
			return

		for item in self.items:
			if item.warehouse and not is_warehouse_permitted(item.warehouse, setting_name, "cycle_count_warehouse"):
				frappe.throw(
					"Warehouse {} not in list of warehouses allowed for user {}".format(item.warehouse, user)
				)

	def on_submit(self):
		super(CustomStockReconciliation, self).on_submit()
		
		# Metactical Customization: Added
		for item in self.items:
			frappe.enqueue(update_item_inventory_output, item_code=item.item_code, queue='default')
