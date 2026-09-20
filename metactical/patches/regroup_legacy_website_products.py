# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
"""Legacy Website Product held one website per record; it now holds one item per record, with a row
per website. Fold the old flat records into the new shape.

Only ever relevant to a bench that ran the first build of the Item Merge legacy-slug capture: the
old records are hash-named and their website columns are orphans after the reshape, so nothing reads
them and a fresh save would sit a second record beside them for the same item.
"""
import frappe

DOCTYPE = "Legacy Website Product"


def execute():
	if not frappe.db.table_exists(DOCTYPE) or not frappe.db.has_column(DOCTYPE, "lead_source"):
		return

	old = frappe.db.sql("""
		select name, item_code, template, lead_source, price_list, slug, source, verified, status, drop_log
		from `tab{0}`
		where name != item_code
	""".format(DOCTYPE), as_dict=True)
	if not old:
		return

	by_item = {}
	for row in old:
		by_item.setdefault(row.item_code, []).append(row)

	# Read first, then clear: the new record is named after the item, so the old one holding that
	# item code has to be gone before it can be written.
	for row in old:
		frappe.delete_doc(DOCTYPE, row.name, force=True, ignore_permissions=True)

	for item_code, rows in by_item.items():
		if frappe.db.exists(DOCTYPE, item_code):
			continue  # already in the new shape

		doc = frappe.get_doc({"doctype": DOCTYPE, "item_code": item_code, "status": "Captured",
							  "template": next((r.template for r in rows if r.template), None)})
		seen = set()
		for row in rows:
			if row.status == "Not Published":
				doc.status = "Not Published"
				doc.websites = []
				break
			if not (row.lead_source and row.slug) or row.lead_source in seen:
				continue
			doc.append("websites", {
				"lead_source": row.lead_source, "price_list": row.price_list, "slug": row.slug,
				"source": row.source or "Manual", "verified": row.verified,
				# The old records only recorded whether the site was reached, never what it
				# answered, and that is stale by now. Say it needs checking rather than invent one.
				"state": "Not Checked",
				"status": row.status if row.status in ("Captured", "Dropped") else "Captured",
				"drop_log": row.drop_log,
			})
			seen.add(row.lead_source)

		if doc.status == "Not Published" or doc.websites:
			doc.insert(ignore_permissions=True)

	frappe.db.commit()
