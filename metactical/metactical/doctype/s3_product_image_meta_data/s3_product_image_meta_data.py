# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import cint

ROLES = ("icon", "small", "medium", "large")


class S3ProductImageMetaData(Document):
	def validate(self):
		self.set_metadata()

	def set_metadata(self):
		"""Store the export JSON on the record, identical to the "Download JSON" button.

		Built from the child tables as they stand in memory, so the field always matches
		the rows it was saved with — whether the save came from the uploader page or a
		manual edit of the child tables. Runs in `validate`, which Frappe calls before the
		mandatory-field check, so the read-only reqd field is filled in by then.

		Imported inside the method: the page module imports `upsert_upload` from this file,
		so a module-level import would be circular.
		"""
		from metactical.metactical.page.s3_uploader.s3_uploader import _record_products

		# `indent=2` and plain json.dumps (not frappe.as_json, which sorts keys) to match
		# what the button downloads — JSON.stringify(payload, null, 2) — byte for byte.
		self.nat_metadata = json.dumps({"products": _record_products(self)}, indent=2)


def _build_record_name(template_item):
	"""Name the record after its product template (one record per template).

	A numeric suffix is appended only if that exact name somehow already exists.
	"""
	return append_number_if_name_exists("S3 Product Image Meta Data", template_item)


def _new_state(files):
	"""Comparable snapshot of an upload payload.

	`images` is keyed per image (sku, order, role) and carries both the path and the
	image's own set of websites, so per-image site/order changes are detectable.
	"""
	skus = {}  # sku -> item_code
	images = {}  # (sku, order, role) -> {"path", "sites": frozenset}
	for f in files:
		role = f["role"]
		order = f.get("order") or 0
		path = f.get("path")
		fsites = frozenset(f.get("sites") or [])
		for item in f["skuItems"]:
			sku = item.get("sku")
			if not sku:
				continue
			skus.setdefault(sku, item.get("item_code"))
			if path:
				images[(sku, order, role)] = {"path": path, "sites": fsites}
	return {"skus": skus, "images": images}


def _doc_state(doc):
	"""Comparable snapshot of a stored record (same shape as `_new_state`)."""
	skus = {r.nat_sku: r.nat_item_code for r in doc.nat_skus if r.nat_sku}

	# Sites tagged per image: (sku, order, role) -> set of websites.
	sites_by = {}
	for r in doc.nat_sites:
		key = (r.nat_sku, r.nat_image_order or 0, r.nat_role)
		sites_by.setdefault(key, set()).add(r.nat_site)

	images = {}
	for r in doc.nat_images:
		for role in ROLES:
			path = r.get("nat_" + role)
			if path:
				key = (r.nat_sku, r.nat_image_order or 0, role)
				images[key] = {"path": path, "sites": frozenset(sites_by.get(key, set()))}
	return {"skus": skus, "images": images}


def _fmt_img(key, item_of):
	"""Readable label for one image: "icon of UMX225245-01 (order 1)" (item code)."""
	sku, order, role = key
	code = item_of.get(sku) or sku
	return f"{role} of {code} (order {order})"


def _change_summary(old, new, old_override=None, new_override=None):
	"""Specific, human-readable list of what changed between two snapshots."""
	lines = []

	# sku -> item code, so the log shows item codes rather than retail SKUs.
	item_of = {**old["skus"], **new["skus"]}

	if old_override is not None and old_override != new_override:
		lines.append(f"Override Full Product: turned {'ON' if new_override else 'OFF'}")

	old_skus, new_skus = set(old["skus"]), set(new["skus"])
	added_codes = sorted({item_of.get(s) or s for s in new_skus - old_skus})
	removed_codes = sorted({item_of.get(s) or s for s in old_skus - new_skus})
	if added_codes or removed_codes:
		parts = []
		if added_codes:
			parts.append(f"added {', '.join(added_codes)}")
		if removed_codes:
			parts.append(f"removed {', '.join(removed_codes)}")
		lines.append(f"Items: {'; '.join(parts)}")

	oi, ni = old["images"], new["images"]
	added = sorted(k for k in ni if k not in oi)
	removed = sorted(k for k in oi if k not in ni)
	if added:
		lines.append("Images added: " + ", ".join(_fmt_img(k, item_of) for k in added))
	if removed:
		lines.append("Images removed: " + ", ".join(_fmt_img(k, item_of) for k in removed))

	# Images present in both: detect replaced files and per-image website changes.
	for k in sorted(set(oi) & set(ni)):
		o, n = oi[k], ni[k]
		if o["path"] != n["path"]:
			lines.append(f"Image replaced: {_fmt_img(k, item_of)}")
		if o["sites"] != n["sites"]:
			s_add = sorted(n["sites"] - o["sites"])
			s_rem = sorted(o["sites"] - n["sites"])
			parts = []
			if s_add:
				parts.append(f"added {', '.join(s_add)}")
			if s_rem:
				parts.append(f"removed {', '.join(s_rem)}")
			lines.append(f"Websites on {_fmt_img(k, item_of)}: {'; '.join(parts)}")

	return lines


def _populate(doc, files, override_full_product, template_item):
	"""(Re)build the child tables of `doc` from the per-FILE upload payload.

	SKUs go to `nat_skus`; images are grouped by (sku, order) into `nat_images`
	(role columns); each site is stored tagged with its image's SKU + order + role
	on `nat_sites`, so sites can be restored per image (not unioned).
	"""
	doc.nat_override_full_product = 1 if cint(override_full_product) else 0
	if template_item:
		doc.nat_product_template = template_item

	doc.set("nat_skus", [])
	doc.set("nat_sites", [])
	doc.set("nat_images", [])

	seen_skus = {}
	image_rows = {}  # (sku, order) -> nat_images row

	for f in files:
		role = f["role"]
		order = f.get("order") or 0
		path = f.get("path")
		sites = f.get("sites") or []

		for item in f["skuItems"]:
			sku = item.get("sku")
			if not sku:
				continue

			if sku not in seen_skus:
				seen_skus[sku] = True
				doc.append("nat_skus", {"nat_item_code": item.get("item_code"), "nat_sku": sku})

			row = image_rows.get((sku, order))
			if not row:
				row = doc.append("nat_images", {"nat_sku": sku, "nat_image_order": order})
				image_rows[(sku, order)] = row
			row.set("nat_" + role, path)

			for site in sites:
				doc.append(
					"nat_sites",
					{"nat_site": site, "nat_sku": sku, "nat_image_order": order, "nat_role": role},
				)


def upsert_upload(files, override_full_product=0, template_item=None):
	"""Upsert one record per product template from the per-FILE upload payload.

	If a record already exists for `template_item` it is updated in place and a
	timeline comment logs what changed (SKUs / websites / images added or removed);
	otherwise a new record named "<template> <timestamp>" is created.
	"""
	files = [f for f in files if f.get("role") and (f.get("skuItems") or [])]
	if not files:
		return None

	new_state = _new_state(files)

	existing = None
	if template_item:
		matches = frappe.get_all(
			"S3 Product Image Meta Data",
			filters={"nat_product_template": template_item},
			order_by="creation desc",
			limit=1,
			pluck="name",
		)
		existing = matches[0] if matches else None

	new_override = 1 if cint(override_full_product) else 0

	if existing:
		doc = frappe.get_doc("S3 Product Image Meta Data", existing)
		# Normalize any legacy record that was submitted before this became editable.
		if doc.docstatus == 1:
			doc.docstatus = 0
		old_state = _doc_state(doc)
		old_override = 1 if cint(doc.nat_override_full_product) else 0
		_populate(doc, files, override_full_product, template_item)
		doc.save(ignore_permissions=True)

		# Always log the save; spell out exactly what changed (incl. override).
		lines = _change_summary(old_state, new_state, old_override, new_override)
		if lines:
			text = "Updated this product:<br>" + "<br>".join("• " + l for l in lines)
		else:
			text = "Saved with no changes."
		doc.add_comment("Comment", text)
	else:
		doc = frappe.new_doc("S3 Product Image Meta Data")
		doc.name = _build_record_name(template_item)
		doc.flags.name_set = True
		_populate(doc, files, override_full_product, template_item)
		doc.insert(ignore_permissions=True)

		items = ", ".join(sorted({(v or k) for k, v in new_state["skus"].items()})) or "—"
		all_sites = sorted({s for img in new_state["images"].values() for s in img["sites"]})
		sites = ", ".join(all_sites) or "—"
		doc.add_comment(
			"Comment",
			"Created this product:<br>"
			f"• Items: {items}<br>"
			f"• Websites: {sites}<br>"
			f"• Images: {len(new_state['images'])}<br>"
			f"• Override Full Product: {'ON' if new_override else 'OFF'}",
		)

	return doc.name
