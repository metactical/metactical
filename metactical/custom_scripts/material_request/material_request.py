import frappe
import json
from erpnext.stock.doctype.material_request.material_request import MaterialRequest
from erpnext.buying.utils import validate_for_items

class CustomMaterialRequest(MaterialRequest):
	def validate(self):
		# Metactical Customization: reomve automatic loading of price list
		self.buying_price_list = None
		validate_target_warehouse(self)
		validate_purchase_items(self)

def before_save(self, method):
	self.set_status(update=True)	
	if len(self.items) > 0:
		set_default_supplier(self)
		suppliers = ''
		unique_suppliers = []
		for item in self.items:
			if item.ais_default_supplier and item.ais_default_supplier not in unique_suppliers:
				unique_suppliers.append(item.ais_default_supplier)
				if suppliers != '':
					suppliers += ', ' + item.ais_default_supplier
				else:
					suppliers += item.ais_default_supplier
		self.ais_suppliers = suppliers

def on_submit(self, method):
	# check if a qty greater than the quantity on hand is entered
	if self.material_request_type == "Material Transfer":
		items = []
		for item in self.items:
			if item.qty > item.qoh:
				items.append(item.item_code) 

		if items:
			message = 'The quantities of these items exceed the available warehouse stock. <br>'
			message += "<b>" + ', '.join(items) + "</b>"
			frappe.msgprint(message)

def set_default_supplier(self):
	for item in self.items:
		if not item.ais_default_supplier:
			doc = frappe.get_doc('Item', item.item_code)
			for defaults in doc.item_defaults:
				if defaults.company == self.company:
					item.ais_default_supplier = defaults.default_supplier

	
@frappe.whitelist()
def validate_target_warehouse(doc):
	if isinstance(doc, str):
		doc = frappe._dict(json.loads(doc))

	user = frappe.session.user
	setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
	if not setting_exists:
		return

	parentfield = "material_request_target_warehouse_purchase" \
		if doc.get("material_request_type") == "Purchase" \
		else "material_request_target_warehouse"

	permitted = frappe.db.sql("""
		SELECT warehouse FROM `tabMaterial Request Permitted Warehouse`
		WHERE parent = %s AND parentfield = %s
	""", (setting_exists, parentfield), pluck="warehouse")

	if not permitted:
		return

	invalid = []

	# Validate header-level set_warehouse
	set_warehouse = doc.get("set_warehouse")
	if set_warehouse and set_warehouse not in permitted:
		invalid.append(f"Set Warehouse <b>{set_warehouse}</b> is not permitted for {user}")

	# Validate each item's warehouse and t_warehouse
	for item in doc.get("items") or []:
		for field in ("warehouse", "t_warehouse"):
			warehouse = item.get(field)
			if warehouse and warehouse not in permitted:
				invalid.append(f"Row #{item.get('idx', '')}: <b>{field}</b> <b>{warehouse}</b> is not permitted for {user}")

	if invalid:
		frappe.throw("<br>".join(invalid))


@frappe.whitelist()
def get_target_warehouse(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabMaterial Request Permitted Warehouse`
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='material_request_target_warehouse'""",
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})

		if not setting_exists or not warehouses:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses

@frappe.whitelist()
def get_target_warehouse_for_purchase(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabMaterial Request Permitted Warehouse`
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='material_request_target_warehouse_purchase'""",
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})

		if not setting_exists or not warehouses:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses

@frappe.whitelist()
def get_qoh(filters):
	filters = json.loads(filters)
	updated_qty = []

	for value in filters:
		qty = 0
		data= frappe.db.sql("""select actual_qty-reserved_qty AS qty from `tabBin`
			where item_code = %s and warehouse=%s
			""",(value['item'], value["warehouse"]), as_dict=1)
		if data and data[0]['qty'] > 0:
			qty = data[0]['qty']
		
		updated_qty.append({
			'item_code': value['item'],
			'qty': qty,
			'name': value['name']
		})

	return updated_qty

# ---------------------------------------------------------------------------
# A Purchase MR may not ask for an item that
#   - is discontinued (Item.ifw_discontinued) or disabled, or
#   - is already on a Purchase Order still in progress -- Draft, On Hold, To
#     Receive and Bill, To Receive -- for the same warehouse, with some of the
#     line still to be received. Every PO3 has a native twin, so this covers PO3.
# A Closed, Completed or Cancelled PO, or one fully received (To Bill), does not
# count: once it is done the item may well need restocking again.
#
# A person is stopped with the reason. ERPNext's auto-reorder puts many items
# on one MR (created with flags.ignore_mandatory, outside a web request), so for
# that the offending lines are dropped instead -- one bad line must not cost
# the whole reorder.
# ---------------------------------------------------------------------------
IN_PROGRESS_PO = ("Draft", "On Hold", "To Receive and Bill", "To Receive")


def validate_purchase_items(doc):
	if doc.material_request_type != "Purchase":
		return
	auto_reorder = bool(doc.flags.ignore_mandatory) and not frappe.request

	blocked = [d for d in doc.items if d.item_code and any(frappe.utils.cint(v) for v in
		frappe.get_cached_value("Item", d.item_code, ["disabled", "ifw_discontinued"]) or [])]
	on_po = in_progress_po_lines(doc)

	if auto_reorder:
		drop = {d.name for d in blocked} | {r.mr_row for r in on_po}
		if drop:
			doc.set("items", [d for d in doc.items if d.name not in drop])
			if not doc.items:
				frappe.throw("Every item on this reorder is discontinued, disabled or already on a "
					"Purchase Order in progress.")
		return

	if blocked:
		frappe.throw("These items are discontinued or disabled and can't be requested:<br>"
			+ "<br>".join("Row {0}: <b>{1}</b>{2}".format(d.idx, d.item_code,
				" (disabled)" if frappe.get_cached_value("Item", d.item_code, "disabled") else " (discontinued)")
				for d in blocked),
			title="Item not available")

	if on_po:
		rows = "".join(
			"<tr><td>{po}</td><td>{status}</td><td>{item}</td><td>{wh}</td>"
			"<td style='text-align:right'>{qty:g}</td><td style='text-align:right'>{rec:g}</td></tr>".format(
				po=frappe.utils.get_link_to_form("Purchase Order", r.po)
					+ (" / " + frappe.utils.get_link_to_form("Purchase Order V3", r.po3) if r.po3 else ""),
				status=r.status, item="Row " + str(r.idx) + ": <b>" + r.item_code + "</b>", wh=r.warehouse,
				qty=frappe.utils.flt(r.qty), rec=frappe.utils.flt(r.received_qty))
			for r in on_po)
		frappe.throw("These items are already on a Purchase Order in progress for the same warehouse, "
			"so they can't be requested again until it is received or closed:"
			"<table class='table table-bordered' style='margin-top:8px'><tr><th>Purchase Order</th>"
			"<th>Status</th><th>Item</th><th>Warehouse</th><th>Ordered</th><th>Received</th></tr>"
			+ rows + "</table>", title="Already on order")


def in_progress_po_lines(doc):
	"""The in-progress PO lines that cover this MR's lines: same item, same
	warehouse, not yet fully received. Lines ordered off this very MR do not
	count. No company filter: the warehouse already belongs to one company, and
	an MR's company can differ from its warehouse's."""
	pairs = [(d.item_code, d.warehouse) for d in doc.items if d.item_code and d.warehouse]
	if not pairs:
		return []
	cond = " or ".join(["(poi.item_code = %s and poi.warehouse = %s)"] * len(pairs))
	lines = frappe.db.sql("""select po.name po, po.status, po.custom_purchase_order_v3 po3,
			poi.item_code, poi.warehouse, poi.qty, poi.received_qty
		from `tabPurchase Order Item` poi join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus < 2 and po.status in %s
			and poi.received_qty < poi.qty and ifnull(poi.material_request, '') != %s
			and ({cond})
		order by po.name, poi.idx""".format(cond=cond),
		[IN_PROGRESS_PO, doc.name or ""] + [v for p in pairs for v in p], as_dict=True)
	out = []
	for d in doc.items:
		for l in lines:
			if l.item_code == d.item_code and l.warehouse == d.warehouse:
				out.append(frappe._dict(l, idx=d.idx, mr_row=d.name))
	return out
