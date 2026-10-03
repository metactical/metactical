import frappe

DOCTYPE_RENAMES = [
	("Goods Receipt V3", "Purchase Receipt V3"),
	("Goods Receipt V3 Item", "Purchase Receipt V3 Item"),
]

FIELD_RENAMES = [
	("Supplier Claim V3", "goods_receipt_v3", "purchase_receipt_v3"),
	("Supplier Claim V3 Item", "goods_receipt_v3", "purchase_receipt_v3"),
]

OLD_WORKFLOW = "Goods Receipt V3 Flow"
NEW_WORKFLOW = "Purchase Receipt V3 Flow"


def execute():
	# Runs pre model sync, so the new doctype JSONs land on the renamed tables
	# instead of creating empty ones next to the old data.
	for old, new in DOCTYPE_RENAMES:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)

	for doctype, old_field, new_field in FIELD_RENAMES:
		if frappe.db.has_column(doctype, old_field) and not frappe.db.has_column(doctype, new_field):
			frappe.db.rename_column(doctype, old_field, new_field)
			frappe.db.set_value("DocField", {"parent": doctype, "fieldname": old_field}, "fieldname", new_field)

	if frappe.db.exists("Workflow", OLD_WORKFLOW) and not frappe.db.exists("Workflow", NEW_WORKFLOW):
		frappe.rename_doc("Workflow", OLD_WORKFLOW, NEW_WORKFLOW, force=True)

	# Custom Field / Property Setter names are prefixed with the doctype and are
	# not touched by rename_doc; fixtures would otherwise insert duplicates.
	for old, new in DOCTYPE_RENAMES:
		for dt in ("Custom Field", "Property Setter"):
			for name in frappe.get_all(dt, filters={"name": ("like", old + "-%")}, pluck="name"):
				new_name = new + name[len(old):]
				if not frappe.db.exists(dt, new_name):
					frappe.rename_doc(dt, name, new_name, force=True)

	# Plain Data field (not a Link), so rename_doc does not update it.
	if frappe.db.has_column("Purchase Receipt Item", "neb_source_doctype"):
		frappe.db.sql(
			"""update `tabPurchase Receipt Item` set neb_source_doctype = 'Purchase Receipt V3'
			where neb_source_doctype = 'Goods Receipt V3'"""
		)

	# Scripts stored in the DB reference the doctype and fieldname by string.
	for script_dt in ("Client Script", "Server Script"):
		for s in frappe.get_all(script_dt, fields=["name", "script"]):
			script = s.script or ""
			updated = script.replace("Goods Receipt V3", "Purchase Receipt V3").replace(
				"goods_receipt_v3", "purchase_receipt_v3"
			)
			if updated != script:
				frappe.db.set_value(script_dt, s.name, "script", updated, update_modified=False)
