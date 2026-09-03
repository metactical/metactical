from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import flt
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
import barcode as _barcode
from barcode.writer import ImageWriter
from io import BytesIO
from frappe.utils import cint, comma_or, cstr, flt, format_time, formatdate, getdate, nowdate
from erpnext.stock.stock_ledger import NegativeStockError, get_previous_sle, get_valuation_rate

class CustomStockEntry(StockEntry):
	def before_submit(self):
		if self.stock_entry_type == "Material Transfer":
			for d in self.items:
				available_qty = self.get_qty(d.item_code, d.s_warehouse)
				if d.qty > available_qty:
					frappe.throw("""Cannot Transfer Qty {} for Item {}, Available Qty is {}, at Row {}
						""".format(str(d.qty), d.item_code, str(available_qty), str(d.idx)))
						
	def get_qty(self, item, warehouse):
		qty = 0
		data= frappe.db.sql("""select actual_qty-reserved_qty from `tabBin`
			where item_code = %s and warehouse=%s
			""",(item,warehouse))
		if data:
			qty = data[0][0] or 0
		return qty
	
	def set_actual_qty(self):
		from erpnext.stock.stock_ledger import is_negative_stock_allowed
		
		for d in self.get("items"):
			allow_negative_stock = is_negative_stock_allowed(item_code=d.item_code)
			previous_sle = get_previous_sle(
				{
					"item_code": d.item_code,
					"warehouse": d.s_warehouse or d.t_warehouse,
					"posting_date": self.posting_date,
					"posting_time": self.posting_time,
				}
			)

			# get actual stock at source warehouse
			d.actual_qty = previous_sle.get("qty_after_transaction") or 0
			
			# Metactical Customization: Get actual quantity at target wareous
			target_previous_sle = get_previous_sle(
				{
					"item_code": d.item_code,
					"warehouse": d.t_warehouse,
					"posting_date": self.posting_date,
					"posting_time": self.posting_time,
				}
			)
			d.ais_target_qoh = target_previous_sle.get("qty_after_transaction")
			
			# Metactical Customization: For in-transit stock entries with material request,
			# get stock level of final target warehouse from Material Request
			if d.material_request:
				# Get the target warehouse from the Material Request Item
				mr_warehouse = frappe.db.get_value(
					"Material Request Item",
					d.material_request_item,
					"warehouse"
				)
				
				if mr_warehouse:
					# Fetch stock level of the final target warehouse
					mr_warehouse_sle = get_previous_sle(
						{
							"item_code": d.item_code,
							"warehouse": mr_warehouse,
							"posting_date": self.posting_date,
							"posting_time": self.posting_time,
						}
					)
					d.ais_active_qoh = mr_warehouse_sle.get("qty_after_transaction")

			# validate qty during submit
			if (
				d.docstatus == 1
				and d.s_warehouse
				and not allow_negative_stock
				and flt(d.actual_qty, d.precision("actual_qty"))
				< flt(d.transfer_qty, d.precision("actual_qty"))
			):
				frappe.throw(
					_(
						"Row {0}: Quantity not available for {4} in warehouse {1} at posting time of the entry ({2} {3})"
					).format(
						d.idx,
						frappe.bold(d.s_warehouse),
						formatdate(self.posting_date),
						format_time(self.posting_time),
						frappe.bold(d.item_code),
					)
					+ "<br><br>"
					+ _("Available quantity is {0}, you need {1}").format(
						frappe.bold(flt(d.actual_qty, d.precision("actual_qty"))), frappe.bold(d.transfer_qty)
					),
					NegativeStockError,
					title=_("Insufficient Stock"),
				)

	def _validate_links(self):
		# _validate_links runs before before_validate and validate in Frappe's lifecycle,
		# so this is the only place we can guarantee warehouses exist before link checks fire.
		if self.stock_entry_type == "Material Transfer":
			for item in self.items:
				if item.t_warehouse:
					try:
						_ensure_warehouse_exists(item.t_warehouse)
					except Exception:
						frappe.log_error(frappe.get_traceback(), f"_ensure_warehouse_exists failed: {item.t_warehouse}")
						raise
		super(CustomStockEntry, self)._validate_links()

	def validate(self):
		super(CustomStockEntry, self).validate()
		# Metactical Customization: Validate that user has permission to make stock entry against warehouse
		user = frappe.session.user
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			s_warehouses = []
			t_warehouses = []
			settings = frappe.get_doc("Warehouse User Permissions", setting_exists)
			for row in settings.source_warehouse:
				s_warehouses.append(row.warehouse)
				
			for row in settings.target_warehouse:
				t_warehouses.append(row.warehouse)
			
			for row in self.items:
				if s_warehouses and row.s_warehouse and row.s_warehouse not in s_warehouses:
					frappe.throw("Warehouse {} not in list of warehouse allowed for user {}".format(row.s_warehouse, frappe.session.user))

				if t_warehouses and row.t_warehouse and row.t_warehouse not in t_warehouses:
					frappe.throw("Warehouse {} not in list of warehouse allowed for user {}".format(row.t_warehouse, frappe.session.user))
				
	def on_submit(self):
		super(CustomStockEntry, self).on_submit()
		# Metactical Customization: Add submitted date and barcode
		frappe.db.set_value('Stock Entry', self.name, 'ais_submitted_date', frappe.utils.today())
		#STE Barcode
		sv = BytesIO()
		_barcode.get('code128', self.name).write(sv, {"module_width":0.4})
		stoBarcode = sv.getvalue()
		self.ais_ste_barcode = stoBarcode.decode('ISO-8859-1')

	def set_material_request_transfer_status(self, status):
		material_requests = []
		if self.outgoing_stock_entry:
			parent_se = frappe.get_value("Stock Entry", self.outgoing_stock_entry, "add_to_transit")

		for item in self.items:
			material_request = item.material_request or None
			if self.purpose == "Material Transfer" and material_request not in material_requests:
				if self.outgoing_stock_entry and parent_se:
					material_request = frappe.get_value(
						"Stock Entry Detail", item.ste_detail, "material_request"
					)
     
			all_completed = True
			if material_request and material_request not in material_requests:
				material_requests.append(material_request)
				material_request_items = frappe.get_doc(
					"Material Request", material_request
				).get("items")
				for item in material_request_items:
					if item.ordered_qty != item.qty and item.received_qty != item.qty:
						all_completed = False
						break  

				if all_completed:
					frappe.db.set_value("Material Request", material_request, "transfer_status", status)

@frappe.whitelist()
def create_stock_entry(source_name, target_doc=None):
	def update_item_quantity(source, target, source_parent):
		qty = flt(flt(source.stock_qty) - flt(source.delivered_qty))/ target.conversion_factor \
			if flt(source.stock_qty) > flt(source.delivered_qty) else 0
		target.qty = qty
		target.transfer_qty = qty * source.conversion_factor
		target.conversion_factor = source.conversion_factor
		
		target.t_warehouse = source.warehouse

	doc = get_mapped_doc('Sales Order', source_name, {
		'Sales Order': {
			'doctype': 'Stock Entry',
			'validation': {
				'docstatus': ['=', 1]
			},
			'field_map': {
				'sales_order_no': 'name'
			}
		},
		'Sales Order Item': {
			'doctype': 'Stock Entry Detail',
			'field_map': {
				'parent': 'sales_order',
				'name': 'sales_order_item',
				'warehouse': 't_warehouse'
			},
			'postprocess': update_item_quantity,
			'condition': lambda doc: doc.delivered_qty < doc.stock_qty
		},
	}, target_doc)

	doc.purpose = 'Transfer'

	return doc
	
@frappe.whitelist()
def get_permitted_source(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabUser Permitted Warehouse`
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='source_warehouse'""",
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})

		if not setting_exists or not warehouses:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses
	
@frappe.whitelist()
def get_permitted_target(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabUser Permitted Warehouse`
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='target_warehouse'""",
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})

		if not setting_exists or not warehouses:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses
	
@frappe.whitelist()
def get_default_transit(user):
	return frappe.db.get_value('Warehouse User Permissions', user, 'add_to_transit')

@frappe.whitelist()
def recalculate_available_qty(items):
	import json
	if isinstance(items, str):
		items = json.loads(items)

	result = {}
	for item in items:
		item_code = item.get("item_code")
		s_warehouse = item.get("s_warehouse")
		row_name = item.get("name")

		if item_code and s_warehouse and row_name:
			bin_name = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": s_warehouse})
			if bin_name:
				bin_doc = frappe.get_doc("Bin", bin_name)
				bin_doc.recalculate_qty()
				result[row_name] = bin_doc.actual_qty

	return result
	
@frappe.whitelist()
def move_stock(source_name, target_doc=None):
	def set_missing_values(source, target):
		target.set_stock_entry_type()

	def update_item(source_doc, target_doc, source_parent):
		target_doc.t_warehouse = ""

		if source_doc.material_request_item and source_doc.material_request:
			add_to_transit = frappe.db.get_value("Stock Entry", source_name, "add_to_transit")
			if add_to_transit:
				warehouse = frappe.get_value(
					"Material Request Item", source_doc.material_request_item, "warehouse"
				)
				target_doc.t_warehouse = warehouse

		target_doc.s_warehouse = source_doc.t_warehouse
		target_doc.qty = source_doc.qty - source_doc.transferred_qty

	doclist = get_mapped_doc(
		"Stock Entry",
		source_name,
		{
			"Stock Entry": {
				"doctype": "Stock Entry",
				"field_map": {"name": "outgoing_stock_entry"},
				"validation": {"docstatus": ["=", 1]},
			},
			"Stock Entry Detail": {
				"doctype": "Stock Entry Detail",
				"field_map": {
					"name": "ste_detail",
					"parent": "against_stock_entry",
					"serial_no": "serial_no",
					"batch_no": "batch_no",
				},
				"postprocess": update_item,
				"condition": lambda doc: flt(doc.qty) - flt(doc.transferred_qty) > 0.01,
			},
		},
		target_doc,
		set_missing_values,
	)
	return doclist


def _ensure_site_bins_warehouse(site: str, company: str, company_abbr: str, site_bins_name: str) -> None:
	"""Create {site}-Bins directly under W01-MainWarehouse if it doesn't exist yet.

	All WXX-Bins nodes live under the single top-level physical warehouse
	(W01-MainWarehouse - abbr). W01-MainWarehouse must already exist in ERPNext.
	"""
	if frappe.db.exists("Warehouse", site_bins_name):
		return

	# All WXX-Bins nodes live directly under W01-MainWarehouse - {abbr}.
	main_wh_name = f"W01-MainWarehouse - {company_abbr}"
	if not frappe.db.exists("Warehouse", main_wh_name):
		frappe.throw(
			f"'{main_wh_name}' not found. Create it in ERPNext first.",
			frappe.DoesNotExistError,
		)

	wh = frappe.new_doc("Warehouse")
	wh.warehouse_name = f"{site}-Bins"
	wh.parent_warehouse = main_wh_name
	wh.company = company
	wh.is_group = 1
	wh.insert(ignore_permissions=True)
	frappe.log_error(f"Created '{site_bins_name}' under '{main_wh_name}'", "StorageBin Debug")


def _ensure_warehouse_exists(warehouse_name: str) -> None:
	"""Create the warehouse and its full parent hierarchy if they don't exist yet.

	Naming convention: "W01-D-01-BA-02-05 - ICL"
	Actual ERPNext hierarchy:
	  W01-Bins - ICL  (site group, must exist, parent is outside W01-* subtree)
	    W01-D - ICL   (zone)
	      W01-D-01 - ICL
	        ...
	          W01-D-01-BA-02-05 - ICL  (leaf, is_group=0)

	chain[0] ("W01 - ICL") does NOT exist in this structure — it is skipped.
	The zone level (chain[1]) is parented to the site group found by querying.
	"""
	frappe.log_error(f"Ensuring warehouse: {warehouse_name}", "StorageBin Debug")
	sep = " - "
	idx = warehouse_name.rfind(sep)
	if idx < 0:
		frappe.log_error(f"No ' - ' separator, skipping: {warehouse_name}", "StorageBin Debug")
		return

	code = warehouse_name[:idx]
	company_abbr = warehouse_name[idx + len(sep):]
	parts = code.split("-")

	# chain[0] = "W01 - ICL", chain[1] = "W01-D - ICL", ..., chain[-1] = full target
	chain = ["-".join(parts[:i]) + sep + company_abbr for i in range(1, len(parts) + 1)]
	frappe.log_error(f"Chain: {chain}", "StorageBin Debug")

	company = frappe.db.get_value("Company", {"abbr": company_abbr}, "name")
	if not company:
		frappe.log_error(f"No company with abbr '{company_abbr}'", "StorageBin Debug")
		frappe.throw(f"No company found with abbreviation '{company_abbr}'")

	# Scan ALL chain entries to find the deepest existing one.
	# Do NOT break early — chain[0] may not exist even if chain[1] does.
	anchor_idx = -1
	for i, name in enumerate(chain):
		if frappe.db.exists("Warehouse", name):
			anchor_idx = i

	frappe.log_error(f"anchor_idx={anchor_idx}, chain_len={len(chain)}", "StorageBin Debug")

	if anchor_idx == len(chain) - 1:
		frappe.log_error(f"Leaf already exists: {warehouse_name}", "StorageBin Debug")
		return

	if anchor_idx >= 0:
		# Normal case: the deepest existing chain entry is the parent.
		first_parent = chain[anchor_idx]
		start_idx = anchor_idx + 1
	else:
		# Nothing in the chain exists. Ensure the canonical bins container
		# "{site}-Bins - {abbr}" exists, creating it (and its MainWarehouse
		# parent) on demand.
		site_bins_name = f"{parts[0]}-Bins - {company_abbr}"
		_ensure_site_bins_warehouse(parts[0], company, company_abbr, site_bins_name)
		first_parent = site_bins_name
		start_idx = 1  # skip chain[0]; chain[1] goes under first_parent

	for i in range(start_idx, len(chain)):
		level_name = chain[i]
		level_code = level_name[:level_name.rfind(sep)]
		is_leaf = i == len(chain) - 1
		parent = first_parent if i == start_idx else chain[i - 1]

		frappe.db.savepoint("before_warehouse_insert")
		try:
			wh = frappe.new_doc("Warehouse")
			wh.warehouse_name = level_code
			wh.parent_warehouse = parent
			wh.company = company
			wh.is_group = 0 if is_leaf else 1
			wh.insert(ignore_permissions=True)
			frappe.log_error(
				f"Created '{level_name}' (is_group={wh.is_group}, parent='{parent}')",
				"StorageBin Debug"
			)
		except frappe.DuplicateEntryError:
			frappe.db.rollback(save_point="before_warehouse_insert")
			frappe.log_error(f"'{level_name}' already exists (concurrent), skipping", "StorageBin Debug")
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Failed to create warehouse '{level_name}'")
			raise