import frappe


def execute():
	frappe.reload_doc("metactical", "doctype", "warehouse_user_permissions")

	for se_perm in frappe.get_all("Stock Entry User Permissions", fields=["name", "user", "add_to_transit"]):
		doc = get_or_create_warehouse_user_permissions(se_perm.user)
		doc.add_to_transit = se_perm.add_to_transit
		se_perm_doc = frappe.get_doc("Stock Entry User Permissions", se_perm.name)
		copy_warehouse_rows(se_perm_doc.source_warehouse, doc, "source_warehouse")
		copy_warehouse_rows(se_perm_doc.target_warehouse, doc, "target_warehouse")
		copy_warehouse_rows(se_perm_doc.cycle_count_warehouse, doc, "cycle_count_warehouse")
		doc.save(ignore_permissions=True)

	for mr_perm in frappe.get_all("Material Request User Permission", fields=["name", "user"]):
		doc = get_or_create_warehouse_user_permissions(mr_perm.user)
		mr_perm_doc = frappe.get_doc("Material Request User Permission", mr_perm.name)
		copy_warehouse_rows(
			mr_perm_doc.permitted_target_warehouse, doc, "material_request_target_warehouse"
		)
		doc.save(ignore_permissions=True)

	frappe.db.commit()


def get_or_create_warehouse_user_permissions(user):
	existing = frappe.db.get_value("Warehouse User Permissions", {"user": user})
	if existing:
		return frappe.get_doc("Warehouse User Permissions", existing)

	doc = frappe.new_doc("Warehouse User Permissions")
	doc.user = user
	return doc


def copy_warehouse_rows(source_rows, target_doc, target_fieldname):
	existing_warehouses = {row.warehouse for row in target_doc.get(target_fieldname)}
	for row in source_rows:
		if row.warehouse not in existing_warehouses:
			target_doc.append(target_fieldname, {"warehouse": row.warehouse})
			existing_warehouses.add(row.warehouse)
