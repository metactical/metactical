# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from erpnext.stock.utils import get_stock_balance
from frappe.utils import add_to_date, cint, cstr, flt
from frappe import _, bold, msgprint
from frappe.query_builder.functions import CombineDatetime, Sum
from frappe.utils import add_to_date, cint, cstr, flt

import erpnext
from erpnext.accounts.utils import get_company_default
from erpnext.controllers.stock_controller import StockController
from erpnext.stock.doctype.batch.batch import get_batch_qty
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.utils import get_stock_balance
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.model.docstatus import DocStatus

class StockZeroingToolV2(Document):
	def save(self):
		if self.docstatus == DocStatus.submitted() and \
			self.ais_queue_status and self.ais_queue_status != "Queued":
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is \
					any issue on processing in background, the system will add a comment \
					about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=2000)
		else:
			super().save()

	def on_submit(self):
		items = get_items(self.warehouse, self.posting_date, self.posting_time, self.company)
		self.create_reconciliation(items)

	def create_reconciliation(self, data):
		limit = 99
		start = 0
		while start < len(data):
			end = start + limit
			self.create_reconciliation_entries(data[start:end])
			start = end

	def create_reconciliation_entries(self, data):
		doc = frappe.new_doc("Stock Reconciliation")
		doc.purpose = "Stock Reconciliation"
		doc.ais_reason_for_adjustment = self.reason_for_adjustment
		for row in data:
			item_code = row.get("item_code")
			if item_code is not None and item_code != "":
				doc.append("items", {
					"item_code": item_code,
					"warehouse": self.warehouse,
					"qty": 0
				})

		if hasattr(doc, "items"):
			try:
				doc.submit()
				frappe.db.commit()
			except Exception as e:
				frappe.msgprint(frappe.get_traceback())

@frappe.whitelist()
def get_items(warehouse, posting_date, posting_time, company, item_code=None, ignore_empty_stock=True):
	ignore_empty_stock = cint(ignore_empty_stock)
	items = []
	if item_code and warehouse:
		items = get_item_and_warehouses(item_code, warehouse)

	if not item_code:
		items = get_items_for_stock_reco(warehouse, company)

	res = []
	itemwise_batch_data = get_itemwise_batch(warehouse, posting_date, company, item_code)

	for d in items:
		if d.item_code in itemwise_batch_data:
			valuation_rate = get_stock_balance(
				d.item_code, d.warehouse, posting_date, posting_time, with_valuation_rate=True
			)[1]

			for row in itemwise_batch_data.get(d.item_code):
				if ignore_empty_stock and not row.qty:
					continue

				args = get_item_data(row, row.qty, valuation_rate)
				res.append(args)
		else:
			stock_bal = get_stock_balance(
				d.item_code,
				d.warehouse,
				posting_date,
				posting_time,
				with_valuation_rate=True,
				with_serial_no=cint(d.has_serial_no),
			)
			qty, valuation_rate, serial_no = (
				stock_bal[0],
				stock_bal[1],
				stock_bal[2] if cint(d.has_serial_no) else "",
			)

			if ignore_empty_stock and not stock_bal[0]:
				continue

			args = get_item_data(d, qty, valuation_rate, serial_no)

			res.append(args)

	return res


def get_item_and_warehouses(item_code, warehouse):
	from frappe.utils.nestedset import get_descendants_of

	items = []
	if frappe.get_cached_value("Warehouse", warehouse, "is_group"):
		childrens = get_descendants_of("Warehouse", warehouse, ignore_permissions=True, order_by="lft")
		for ch_warehouse in childrens:
			items.append(frappe._dict({"item_code": item_code, "warehouse": ch_warehouse}))
	else:
		items = [frappe._dict({"item_code": item_code, "warehouse": warehouse})]

	return items


def get_items_for_stock_reco(warehouse, company):
	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	items = frappe.db.sql(
		f"""
		select
			i.name as item_code, i.item_name, bin.warehouse as warehouse, i.has_serial_no, i.has_batch_no
		from
			`tabBin` bin, `tabItem` i
		where
			i.name = bin.item_code
			and IFNULL(i.disabled, 0) = 0
			and i.is_stock_item = 1
			and i.has_variants = 0
			and exists(
				select name from `tabWarehouse` where lft >= {lft} and rgt <= {rgt} and name = bin.warehouse and is_group = 0
			)
	""",
		as_dict=1,
	)

	items += frappe.db.sql(
		"""
		select
			i.name as item_code, i.item_name, id.default_warehouse as warehouse, i.has_serial_no, i.has_batch_no
		from
			`tabItem` i, `tabItem Default` id
		where
			i.name = id.parent
			and exists(
				select name from `tabWarehouse` where lft >= %s and rgt <= %s and name=id.default_warehouse and is_group = 0
			)
			and i.is_stock_item = 1
			and i.has_variants = 0
			and IFNULL(i.disabled, 0) = 0
			and id.company = %s
		group by i.name
	""",
		(lft, rgt, company),
		as_dict=1,
	)

	# remove duplicates
	# check if item-warehouse key extracted from each entry exists in set iw_keys
	# and update iw_keys
	iw_keys = set()
	items = [
		item
		for item in items
		if [
			(item.item_code, item.warehouse) not in iw_keys,
			iw_keys.add((item.item_code, item.warehouse)),
		][0]
	]

	return items


def get_item_data(row, qty, valuation_rate, serial_no=None):
	return {
		"item_code": row.item_code,
		"warehouse": row.warehouse,
		"qty": qty,
		"item_name": row.item_name,
		"valuation_rate": valuation_rate,
		"current_qty": qty,
		"current_valuation_rate": valuation_rate,
		"current_serial_no": serial_no,
		"serial_no": serial_no,
		"batch_no": row.get("batch_no"),
	}


def get_itemwise_batch(warehouse, posting_date, company, item_code=None):
	from erpnext.stock.report.batch_wise_balance_history.batch_wise_balance_history import execute

	itemwise_batch_data = {}

	filters = frappe._dict(
		{"warehouse": warehouse, "from_date": posting_date, "to_date": posting_date, "company": company}
	)

	if item_code:
		filters.item_code = item_code

	columns, data = execute(filters)

	for row in data:
		itemwise_batch_data.setdefault(row[0], []).append(
			frappe._dict(
				{
					"item_code": row[0],
					"warehouse": row[3],
					"qty": row[8],
					"item_name": row[1],
					"batch_no": row[4],
				}
			)
		)

	return itemwise_batch_data


@frappe.whitelist()
def get_stock_balance_for(
	item_code: str,
	warehouse: str,
	posting_date,
	posting_time,
	batch_no: str | None = None,
	with_valuation_rate: bool = True,
	inventory_dimensions_dict=None,
	voucher_no=None,
):
	frappe.has_permission("Stock Reconciliation", "write", throw=True)

	item_dict = frappe.get_cached_value("Item", item_code, ["has_serial_no", "has_batch_no"], as_dict=1)

	if not item_dict:
		# In cases of data upload to Items table
		msg = _("Item {} does not exist.").format(item_code)
		frappe.throw(msg, title=_("Missing"))

	serial_nos = None
	has_serial_no = bool(item_dict.get("has_serial_no"))
	has_batch_no = bool(item_dict.get("has_batch_no"))

	if not batch_no and has_batch_no:
		# Not enough information to fetch data
		return {"qty": 0, "rate": 0, "serial_nos": None}

	# TODO: fetch only selected batch's values
	data = get_stock_balance(
		item_code,
		warehouse,
		posting_date,
		posting_time,
		with_valuation_rate=with_valuation_rate,
		with_serial_no=has_serial_no,
		inventory_dimensions_dict=inventory_dimensions_dict,
		batch_no=batch_no,
		voucher_no=voucher_no,
	)

	if has_serial_no:
		qty, rate, serial_nos = data
	else:
		qty, rate = data

	if item_dict.get("has_batch_no"):
		qty = get_batch_qty(batch_no, warehouse, posting_date=posting_date, posting_time=posting_time) or 0

	return {"qty": qty, "rate": rate, "serial_nos": serial_nos}


@frappe.whitelist()
def get_difference_account(purpose, company):
	if purpose == "Stock Reconciliation":
		account = get_company_default(company, "stock_adjustment_account")
	else:
		account = frappe.db.get_value(
			"Account", {"is_group": 0, "company": company, "account_type": "Temporary"}, "name"
		)

	return account
