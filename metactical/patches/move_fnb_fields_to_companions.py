import frappe
from frappe.utils import cint, flt

# The first pos-pizza build put its Food and Beverage fields straight onto core doctypes
# (custom fields, plus DocFields on End of Day Closing and POS Opening). Those fields now live
# on the FnB companion doctypes and the field definitions are gone, but Frappe never drops a
# table column when a field is removed. This patch copies whatever the leftover columns still
# hold into the companion rows (only where no row exists yet) and then drops the columns.
# Safe to re-run: every step checks the column first.

ORPHAN_COLUMNS = {
	"POS Profile": [
		"neb_food_and_beverage", "neb_idle_lock_minutes", "neb_slices_per_pie", "neb_fnb_item_group",
		"neb_fnb_customer_group", "neb_tips_payable_account", "neb_slice_cost_account",
	],
	"Customer": ["neb_owned_by_pos_profile"],
	"Address": ["neb_delivery_area", "neb_delivery_zone"],
	"Sales Order": ["neb_order_type", "neb_delivery_area", "neb_tip_amount", "neb_cash_rounding"],
	"Sales Invoice": ["neb_order_type", "neb_delivery_area", "neb_tip_amount", "neb_cash_rounding"],
	"End of Day Closing": [
		"neb_opening_slices", "neb_pies_baked", "neb_slices_sold", "neb_slices_counted",
		"neb_slice_variance", "neb_slice_variance_reason", "neb_tips_collected",
	],
	"POS Opening": ["neb_opening_slices"],
}


def execute():
	_move_pos_profiles()
	_move_customers()
	_move_addresses()
	_move_orders()
	_move_closings()
	_move_openings()
	_drop_columns()


def _has_all(doctype, columns):
	return all(frappe.db.has_column(doctype, c) for c in columns)


def _insert(doc):
	frappe.get_doc(doc).insert(ignore_permissions=True, ignore_mandatory=True)


def _move_pos_profiles():
	if not _has_all("POS Profile", ORPHAN_COLUMNS["POS Profile"]):
		return
	for row in frappe.db.sql("""select name, neb_idle_lock_minutes, neb_slices_per_pie, neb_fnb_item_group,
			neb_fnb_customer_group, neb_tips_payable_account, neb_slice_cost_account
		from `tabPOS Profile` where neb_food_and_beverage = 1""", as_dict=True):
		if frappe.db.exists("FnB POS Profile", {"pos_profile": row.name}):
			continue
		_insert({
			"doctype": "FnB POS Profile",
			"pos_profile": row.name,
			"enabled": 1,
			"idle_lock_minutes": cint(row.neb_idle_lock_minutes),
			"slices_per_pie": cint(row.neb_slices_per_pie) or 8,
			"menu_item_group": row.neb_fnb_item_group,
			"customer_group": row.neb_fnb_customer_group,
			"tips_payable_account": row.neb_tips_payable_account,
			"slice_cost_account": row.neb_slice_cost_account,
		})


def _move_customers():
	if not _has_all("Customer", ORPHAN_COLUMNS["Customer"]):
		return
	for row in frappe.db.sql("""select name, neb_owned_by_pos_profile from `tabCustomer`
		where ifnull(neb_owned_by_pos_profile, '') != ''""", as_dict=True):
		if frappe.db.exists("FnB Customer", {"customer": row.name}):
			continue
		_insert({"doctype": "FnB Customer", "customer": row.name, "pos_profile": row.neb_owned_by_pos_profile})


def _move_addresses():
	if not _has_all("Address", ORPHAN_COLUMNS["Address"]):
		return
	for row in frappe.db.sql("""select name, neb_delivery_area, neb_delivery_zone from `tabAddress`
		where ifnull(neb_delivery_area, '') != ''""", as_dict=True):
		if frappe.db.exists("FnB Address", {"address": row.name}) or not frappe.db.exists("Delivery Area", row.neb_delivery_area):
			continue
		area = frappe.db.get_value("Delivery Area", row.neb_delivery_area, ["delivery_zone", "pos_profile"], as_dict=True)
		_insert({
			"doctype": "FnB Address",
			"address": row.name,
			"delivery_area": row.neb_delivery_area,
			"delivery_zone": row.neb_delivery_zone or area.delivery_zone,
			"pos_profile": area.pos_profile,
		})


def _move_orders():
	if not _has_all("Sales Order", ORPHAN_COLUMNS["Sales Order"]):
		return
	for row in frappe.db.sql("""select name, neb_order_type, neb_delivery_area, neb_tip_amount, neb_cash_rounding
		from `tabSales Order`
		where ifnull(neb_order_type, '') != '' or ifnull(neb_tip_amount, 0) != 0 or ifnull(neb_cash_rounding, 0) != 0""",
		as_dict=True):
		if frappe.db.exists("FnB Order", {"sales_order": row.name}):
			continue
		# The invoice the order became carries the POS Profile; the order itself does not.
		invoice = frappe.db.get_value("Sales Invoice Item", {"sales_order": row.name, "docstatus": 1}, "parent") \
			or frappe.db.get_value("Sales Invoice Item", {"sales_order": row.name}, "parent")
		pos_profile = frappe.db.get_value("Sales Invoice", invoice, "pos_profile") if invoice else None
		_insert({
			"doctype": "FnB Order",
			"sales_order": row.name,
			"sales_invoice": invoice,
			"pos_profile": pos_profile,
			"order_type": row.neb_order_type or "",
			"delivery_area": row.neb_delivery_area if row.neb_delivery_area and frappe.db.exists("Delivery Area", row.neb_delivery_area) else None,
			"tip_amount": flt(row.neb_tip_amount),
			"cash_rounding": flt(row.neb_cash_rounding),
		})


def _move_closings():
	if not _has_all("End of Day Closing", ORPHAN_COLUMNS["End of Day Closing"]):
		return
	for row in frappe.db.sql("""select name, neb_opening_slices, neb_pies_baked, neb_slices_sold, neb_slices_counted,
			neb_slice_variance, neb_slice_variance_reason, neb_tips_collected
		from `tabEnd of Day Closing`
		where ifnull(neb_opening_slices, 0) != 0 or ifnull(neb_pies_baked, 0) != 0 or ifnull(neb_slices_sold, 0) != 0
			or ifnull(neb_slices_counted, 0) != 0 or ifnull(neb_tips_collected, 0) != 0""", as_dict=True):
		if frappe.db.exists("FnB Closing", {"closing_entry": row.name}):
			continue
		_insert({
			"doctype": "FnB Closing",
			"closing_entry": row.name,
			"opening_slices": cint(row.neb_opening_slices),
			"pies_baked": cint(row.neb_pies_baked),
			"slices_sold": cint(row.neb_slices_sold),
			"slices_counted": cint(row.neb_slices_counted),
			"slice_variance": cint(row.neb_slice_variance),
			"slice_variance_reason": row.neb_slice_variance_reason,
			"tips_collected": flt(row.neb_tips_collected),
		})


def _move_openings():
	if not _has_all("POS Opening", ORPHAN_COLUMNS["POS Opening"]):
		return
	for row in frappe.db.sql("""select name, neb_opening_slices from `tabPOS Opening`
		where ifnull(neb_opening_slices, 0) != 0""", as_dict=True):
		if frappe.db.exists("FnB Opening", {"opening_entry": row.name}):
			continue
		_insert({"doctype": "FnB Opening", "opening_entry": row.name, "opening_slices": cint(row.neb_opening_slices)})


def _drop_columns():
	for doctype, columns in ORPHAN_COLUMNS.items():
		# Never drop a column that a (re)defined field still owns.
		owned = {f.fieldname for f in frappe.get_meta(doctype).fields}
		owned |= set(frappe.get_all("Custom Field", {"dt": doctype}, pluck="fieldname"))
		for column in columns:
			if column in owned or not frappe.db.has_column(doctype, column):
				continue
			frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `{column}`")
		frappe.clear_cache(doctype=doctype)
