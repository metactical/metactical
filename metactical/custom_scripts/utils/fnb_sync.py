"""Publish Food and Beverage master data to POSWeb through the same RabbitMQ messages the retail
branches use (UpdateVariantMessage, PricingChangeMessage, POSProfileChangeMessage, TaxInformationUpdateMessage,
UserPinChangeMessage, DropProductMessage).

Transport, like retail: Frappe **Webhook** records (created by `install_fnb_webhooks`, visible and
tracked in the Webhook Request Log) post to the ERP's own `rabbitmq_handler.webhook` endpoint, which
publishes to RabbitMQ. Each webhook body is one Jinja call, `{{ fnb_webhook_body(doc, "<kind>") }}`,
so the message JSON is built here (tested code), while what fires and where it posts stays site
configuration. Connection details come from the single `POS Sync Settings`. The POS consumes the
messages asynchronously; the ERP never calls the POS. `publish_fnb_catalog` is the bulk initial load
and publishes directly (no webhook rows).
"""
import json

import frappe
from frappe.utils import cint, flt

from metactical.custom_scripts.utils.fnb_api import fnb_settings
from metactical.custom_scripts.utils.rabbitmq_handler import publish_to_rabbitmq

PROFILE_FIELDS = [
	"name", "company", "selling_price_list", "nat_first_priority_price_list", "taxes_and_charges",
	"ifw_default_lead_source", "ifw_drawerfilepath", "ifw_footer", "ifw_header1", "ifw_header2",
	"auto_logout_after_transaction", "neb_allow_manual_order",
]


# ---------------------------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------------------------
def _settings():
	if not frappe.db.exists("DocType", "POS Sync Settings"):
		return None
	settings = frappe.get_cached_doc("POS Sync Settings")
	if not cint(settings.enabled) or not settings.server_ip:
		return None
	return settings


def publish(message):
	"""Queue the message after the current transaction commits; a sync failure never blocks a save."""
	if not _settings():
		return
	message.setdefault("last_modified_by", frappe.session.user)
	frappe.enqueue(publish_now, queue="short", enqueue_after_commit=True, message=message)


def publish_now(message):
	settings = _settings()
	if not settings:
		return
	try:
		publish_to_rabbitmq(
			settings.server_ip, settings.exchange, settings.exchange_type or "topic", settings.routing_key,
			message, settings.username, settings.get_password("password", raise_exception=False), settings.queue_name,
		)
	except Exception:
		frappe.log_error(title="POS Sync publish failed", message=f"{message.get('message_type')} {message.get('variant_sku') or message.get('name')}\n{frappe.get_traceback()}")


# ---------------------------------------------------------------------------------------------
# scope: which items belong to a Food and Beverage branch
# ---------------------------------------------------------------------------------------------
def fnb_profiles():
	"""Enabled Food and Beverage branches: the POS Profile fields merged with their FnB POS Profile settings."""
	settings = {s.pos_profile: s for s in frappe.get_all(
		"FnB POS Profile", filters={"enabled": 1},
		fields=["pos_profile", "menu", "idle_lock_minutes"],
	)}
	if not settings:
		return []
	profiles = frappe.get_all("POS Profile", filters={"name": ["in", list(settings)], "disabled": 0}, fields=PROFILE_FIELDS)
	for profile in profiles:
		profile.update(settings[profile.name])
	return profiles


def fnb_item_groups():
	"""All item groups (with descendants) of the FnB Menus used by enabled Food and Beverage profiles, cached
	per request. Items in these groups are the ones published to the POS."""
	if getattr(frappe.local, "fnb_item_groups", None) is not None:
		return frappe.local.fnb_item_groups
	groups = set()
	menus = {p.menu for p in fnb_profiles() if p.menu}
	for menu_group in frappe.get_all("FnB Menu", filters={"name": ["in", list(menus) or [""]], "disabled": 0}, pluck="item_group"):
		root = frappe.db.get_value("Item Group", menu_group, ["lft", "rgt"], as_dict=True)
		if root:
			groups.update(frappe.get_all("Item Group", filters={"lft": [">=", root.lft], "rgt": ["<=", root.rgt]}, pluck="name"))
	frappe.local.fnb_item_groups = groups
	return groups


def fnb_price_lists():
	return {p.selling_price_list for p in fnb_profiles() if p.selling_price_list}


def is_fnb_item(item_group):
	return bool(item_group) and item_group in fnb_item_groups()


# ---------------------------------------------------------------------------------------------
# message bodies (same shape POSWeb's processors read)
# ---------------------------------------------------------------------------------------------
def item_message(item):
	prices = frappe.get_all(
		"Item Price", filters={"item_code": item.name, "selling": 1},
		fields=["price_list_rate", "currency", "price_list"],
	)
	# Same keys as the retail Item webhook (HOOK-0035 on deverp), so POSWeb sees one message shape.
	# F&B items are plain (non-variant) items, hence the empty template / attribute / spec blocks.
	template = frappe.get_doc("Item", item.variant_of) if item.get("variant_of") else None
	return {
		"message_type": "UpdateVariantMessage",
		"name": item.item_name,
		"parent_template": item.get("variant_of") or "",
		"retailskusiffix": item.get("ifw_retailskusuffix") or item.name,
		"item_id": item.name,
		"variant_sku": item.get("ifw_sku") or item.name,
		"group_id": item.item_group,
		"brand": item.get("brand") or "",
		"display_order": cint(template.get("nat_display_order_in_listing")) if template else 0,
		"is_nonstock": not cint(item.is_stock_item),
		"barcodes": [b.barcode for b in (item.get("barcodes") or []) if b.barcode],
		"availability_rule": "HideVariantWhenOutOfStock" if cint(item.disabled) or cint(item.get("ifw_discontinued"))
			else (item.get("neb_variantavailabilityrule") or ""),
		"ship_height": str(item.get("ais_shipping_height") or ""),
		"ship_width": str(item.get("ais_shipping_width") or ""),
		"ship_length": str(item.get("ais_shipping_length") or ""),
		"ship_unit": item.get("weight_uom") or "",
		"ship_weight": str(item.get("weight_per_unit") or ""),
		"paypal_restricted": cint(item.get("neb_paypal_restricted")),
		"air_shipping_restricted": cint(item.get("neb_airship_restricted")),
		"last_modified_by": item.modified_by or frappe.session.user,
		"imageUrl": _absolute_url(item.get("image")),
		"short_name": item.get("nat_variant_short_name") or "",
		"supplier_qoh": sum(cint(si.get("ifw_supplier_qoh")) for si in (item.get("supplier_items") or [])),
		"attributes": [{
			"attribute": a.attribute or "",
			"attribute_value": a.attribute_value or "",
			"attribute_sort_order": cint(frappe.db.get_value("Item Attribute", a.attribute, "sort_order")),
			"value_sort_order": cint(frappe.db.get_value("Item Attribute Value", {"parent": a.attribute, "attribute_value": a.attribute_value}, "sort_order")),
		} for a in (item.get("attributes") or [])],
		"price": [{"price_list": p.price_list, "price": flt(p.price_list_rate), "currency": p.currency} for p in prices],
		"specs": [{
			"name": sp.get("label") or "",
			"value": sp.get("description") or "",
			"is_a_search_filter": bool(cint(frappe.db.get_value("Website Specification Label", sp.get("label") or "", "is_a_search_filter"))),
			"order": cint(sp.get("sort_order")),
		} for sp in (item.get("neb_website_specifications") or [])],
		"template_item_details": [{
			"item_name": d.get("item_name") or "",
			"description": d.get("description") or "",
			"slug": (d.get("slug") or "").strip().replace("\n", ""),
			"price_list": d.get("price_list") or "",
			"product_se_title": d.get("productmetasetitle") or "",
			"product_se_description": d.get("productmetasedescription") or "",
			"product_se_keywords": d.get("productmetasekeywords") or "",
			"h2": d.get("h2") or "",
			"h3": d.get("h3") or "",
		} for d in ((template.get("item_detail") if template else None) or [])],
		"tags": [t.sb_tag for t in (item.get("sb_tags") or []) if t.get("sb_tag")],
		"suppliers": [{
			"supplier_name": si.supplier or "",
			"rules": [{"lead_source": r.lead_source or "", "availability_rule": r.variant_availability_rule or ""}
				for r in frappe.get_all("Website Variant Available Rule",
					filters={"parent": si.supplier, "parenttype": "Supplier", "parentfield": "variant_available_rules"},
					fields=["variant_availability_rule", "lead_source"], order_by="idx asc")],
		} for si in (item.get("supplier_items") or [])],
	}


def _absolute_url(path):
	"""Item.image is a site-relative file path when the image lives on the ERP (S3-hosted images are already
	absolute); POSWeb only keeps absolute http(s) URLs."""
	if not path:
		return ""
	return frappe.utils.get_url(path) if path.startswith("/") else path


def drop_message(item):
	"""DropProductMessage: POSWeb removes the product from every branch (a disabled or deleted item)."""
	return {
		"message_type": "DropProductMessage",
		"product": item.item_group,
		"slug": item.name,
		"variants": [{
			"id": item.name,
			"retailskusuffix": item.get("ifw_retailskusuffix") or item.name,
			"barcodes": [b.barcode for b in (item.get("barcodes") or []) if b.barcode],
		}],
	}


def price_message(item_code, price_list, rate, currency, modified_by=None):
	"""Same keys as the retail Item Price webhooks; F&B items have no retail SKU suffix, so the item code is the SKU."""
	return {
		"message_type": "PricingChangeMessage",
		"price_list": price_list,
		"price": flt(rate),
		"currency": currency,
		"variant_sku": frappe.db.get_value("Item", item_code, "ifw_retailskusuffix") or item_code,
		"variant_id": item_code,
		"last_modified_by": modified_by or frappe.session.user,
	}


def pin_messages(doc):
	"""One UserPinChangeMessage per profile user with a PIN. POSWeb creates users from the profile message with a
	random password and only takes the PIN from this message (retail gets it from a separate webhook)."""
	out = []
	for row in doc.get("applicable_for_users") or []:
		if row.get("neb_pin"):
			out.append({
				"message_type": "UserPinChangeMessage",
				"user_id": row.user,
				"pin": str(row.get("neb_pin")),
				"can_disable_auto_logout": False,
				"can_create_embedded_codes": False,
			})
	return out


def tax_message(template_name):
	"""TaxInformationUpdateMessage for a Sales Taxes and Charges Template (same shape the retail tax webhook sends)."""
	if not template_name or not frappe.db.exists("Sales Taxes and Charges Template", template_name):
		return None
	doc = frappe.get_doc("Sales Taxes and Charges Template", template_name)
	return {
		"message_type": "TaxInformationUpdateMessage",
		"last_modified_by": doc.modified_by or frappe.session.user,
		"name": doc.name,
		"disabled": bool(cint(doc.disabled)),
		"is_default": bool(cint(doc.is_default)),
		"tax_category": doc.get("tax_category") or "",
		"taxes": [{
			"charge_type": row.charge_type,
			"description": row.description,
			"rate": str(flt(row.rate)),
			"erpnext_id": row.name,
		} for row in doc.taxes],
	}


def publish_profile(doc):
	"""Everything POSWeb needs for the branch: its tax template first, then the profile, then the PINs."""
	tax = tax_message(doc.taxes_and_charges)
	if tax:
		publish(tax)
	publish(profile_message(doc))
	for message in pin_messages(doc):
		publish(message)


def profile_message(profile):
	"""POSProfileChangeMessage plus the Food and Beverage fields POSWeb maps onto the Branch."""
	doc = frappe.get_doc("POS Profile", profile.name)
	settings = fnb_settings(doc.name)  # None for retail profiles
	users = []
	for row in doc.get("applicable_for_users") or []:
		users.append({
			"user": row.user,
			"full_name": frappe.db.get_value("User", row.user, "full_name"),
			"pin": row.get("neb_pin"),
			# POSWeb's POSProfileUser reads the main-user flag as a string and the two others as booleans
			"ifw_is_main_pos_user": "1" if cint(row.get("ifw_is_main_pos_user")) else "0",
			"ifw_max_discount_percent": flt(row.get("ifw_max_discount_percent")),
			"ifw_allow_to_edit_rate_increase_only": bool(cint(row.get("ifw_allow_to_edit_rate_increase_only"))),
			"allow_flat_rate": bool(cint(row.get("allow_flat_rate"))),
			"default": "1" if cint(row.get("default")) else "0",
		})
	groups = []
	for row in doc.get("item_groups") or []:
		items = frappe.get_all(
			"Item", filters={"item_group": row.item_group, "disabled": 0, "has_variants": 0},
			fields=["name", "ifw_retailskusuffix"], limit=50,
		)
		groups.append({"item_group": row.item_group, "items": [{"sku": i.name, "retail_skusuffix": i.ifw_retailskusuffix or ""} for i in items]})
	return {
		"message_type": "POSProfileChangeMessage",
		"last_modified_by": doc.modified_by or frappe.session.user,
		"name": doc.name,
		"tax_and_charges": doc.taxes_and_charges or "",
		"price_list": doc.selling_price_list or "",
		"secondary_price_list": doc.get("nat_first_priority_price_list") or "",
		"lead_source": doc.get("ifw_default_lead_source") or "",
		"users": users,
		"item_groups": groups,
		"meta_company": doc.company or "",
		"meta_drawer": doc.get("ifw_drawerfilepath") or "",
		"meta_footer": doc.get("ifw_footer") or "",
		"meta_header1": doc.get("ifw_header1") or "",
		"meta_header2": doc.get("ifw_header2") or "",
		"auto_logout": cint(doc.get("auto_logout_after_transaction")),
		"manual_orders_enabled": bool(cint(doc.get("neb_allow_manual_order"))),
		# Food and Beverage additions (from the FnB POS Profile companion; same keys POSWeb already reads)
		"food_and_beverage": bool(settings),
		"idle_lock_minutes": cint(settings.idle_lock_minutes) if settings else 0,
		# everything the till shows for this concept (menu, order types, resources, notes, presets); null = retail
		"fnb": fnb_config(doc.name) if settings else None,
	}


# ---------------------------------------------------------------------------------------------
# the `fnb` block: the branch concept as configured on the FnB doctypes (no naming conventions)
# ---------------------------------------------------------------------------------------------
def _percent_list(value):
	from metactical.metactical.doctype.fnb_pos_profile.fnb_pos_profile import parse_percent_list
	return parse_percent_list(value)


def _labels(parent_doc, table):
	return [row.label for row in (parent_doc.get(table) or []) if row.label]


def menu_config(menu_name):
	"""The FnB Menu as the till renders it: sizes, categories, items (with sizes / modifier groups / choices)
	and modifier groups. Disabled rows are left out. Items are referenced by item code; the POS takes their
	names, prices and images from the product catalog."""
	if not menu_name or not frappe.db.exists("FnB Menu", menu_name):
		return None
	categories = frappe.get_all("FnB Menu Category", filters={"menu": menu_name, "disabled": 0},
		fields=["name", "category_name", "icon", "sort_order", "show_on_rail"], order_by="sort_order asc, category_name asc")
	groups = []
	for g in frappe.get_all("FnB Modifier Group", filters={"menu": menu_name, "disabled": 0},
			fields=["name", "title", "selection", "min_selected", "max_selected"], order_by="title asc"):
		rows = frappe.get_all("FnB Modifier", filters={"parent": g.name, "parenttype": "FnB Modifier Group"},
			fields=["label", "size", "item", "default_selected"], order_by="idx asc")
		groups.append({"id": g.name, "title": g.title, "selection": g.selection or "Multiple",
			"min": cint(g.min_selected), "max": cint(g.max_selected),
			"modifiers": [{"label": r.label, "size": r.size or "", "item": r.item, "default": bool(cint(r.default_selected))} for r in rows]})
	items = []
	for mi in frappe.get_all("FnB Menu Item", filters={"menu": menu_name, "disabled": 0},
			fields=["name", "title", "category", "sort_order", "image", "item", "packaging_item", "made_to_order"],
			order_by="sort_order asc, title asc"):
		sizes = frappe.get_all("FnB Menu Item Size", filters={"parent": mi.name, "parenttype": "FnB Menu Item"},
			fields=["size", "item", "packaging_item"], order_by="idx asc")
		image = mi.image or (frappe.db.get_value("Item", sizes[-1].item if sizes else mi.item, "image") if (sizes or mi.item) else "")
		items.append({
			"id": mi.name, "title": mi.title, "category": mi.category, "order": cint(mi.sort_order),
			"image": _absolute_url(image), "item": "" if sizes else (mi.item or ""),
			"packaging_item": "" if sizes else (mi.packaging_item or ""), "made_to_order": bool(cint(mi.made_to_order)),
			"sizes": [{"size": s.size, "item": s.item, "packaging_item": s.packaging_item or ""} for s in sizes],
			"modifier_groups": frappe.get_all("FnB Menu Item Modifier Group", filters={"parent": mi.name, "parenttype": "FnB Menu Item"}, pluck="modifier_group", order_by="idx asc"),
			"choices": [{"label": c.label, "category": c.category, "qty": cint(c.qty) or 1, "included": bool(cint(c.included))}
				for c in frappe.get_all("FnB Menu Item Choice", filters={"parent": mi.name, "parenttype": "FnB Menu Item"}, fields=["label", "category", "qty", "included"], order_by="idx asc")],
		})
	used_sizes = {s["size"] for it in items for s in it["sizes"]} | {m["size"] for g in groups for m in g["modifiers"] if m["size"]}
	sizes = frappe.get_all("FnB Size", filters={"name": ["in", list(used_sizes) or [""]]},
		fields=["name", "short_label", "sort_order"], order_by="sort_order asc, name asc")
	return {
		"name": menu_name,
		"sizes": [{"id": s.name, "label": s.name, "short": s.short_label or "", "order": cint(s.sort_order)} for s in sizes],
		"categories": [{"id": c.name, "label": c.category_name, "icon": _absolute_url(c.icon), "order": cint(c.sort_order), "show_on_rail": bool(cint(c.show_on_rail))} for c in categories],
		"items": items,
		"modifier_groups": groups,
	}


def resources_config(pos_profile_name):
	out = []
	for r in frappe.get_all("FnB Prepared Resource", filters={"pos_profile": pos_profile_name, "disabled": 0},
			fields=["name", "label", "action_label", "icon", "portion_noun", "portions_per_batch", "tracking"], order_by="label asc"):
		consumers = frappe.get_all("FnB Resource Consumer", filters={"parent": r.name, "parenttype": "FnB Prepared Resource"},
			fields=["item", "portions"], order_by="idx asc")
		out.append({"id": r.name, "label": r.label, "action_label": r.action_label, "icon": _absolute_url(r.icon),
			"portion_noun": r.portion_noun or "portion", "portions_per_batch": cint(r.portions_per_batch) or 1,
			"tracking": r.tracking or "Count remaining at close",
			"consumers": [{"item": c.item, "portions": flt(c.portions)} for c in consumers]})
	return out


def fnb_config(pos_profile_name):
	"""The `fnb` key of the profile message (contract: webpos/claude/fnb-config-contract.md)."""
	settings = frappe.get_doc("FnB POS Profile", {"pos_profile": pos_profile_name})
	return {
		"menu": menu_config(settings.menu),
		"order_types": [{
			"label": row.label, "icon": _absolute_url(row.icon), "default": bool(cint(row.is_default)),
			"requires_customer": bool(cint(row.requires_customer)), "requires_address": bool(cint(row.requires_address)),
			"adds_packaging": bool(cint(row.adds_packaging)), "kitchen_ticket_all_items": bool(cint(row.kitchen_ticket_all_items)),
		} for row in settings.order_types],
		"resources": resources_config(pos_profile_name),
		"order_notes": _labels(settings, "order_notes"),
		"variance_reasons": _labels(settings, "variance_reasons"),
		"discount_reasons": _labels(settings, "discount_reasons"),
		"discount_presets": _percent_list(settings.discount_presets),
		"max_discount_percent": cint(settings.max_discount_percent),
		"tip_presets": _percent_list(settings.tip_presets),
		"cash_rounding_to": flt(settings.cash_rounding_to),
		"variance_warn_portions": cint(settings.variance_warn_portions),
		"delivery_city": settings.delivery_city or "",
	}


# ---------------------------------------------------------------------------------------------
# webhook transport (Frappe Webhook records -> rabbitmq_handler.webhook -> RabbitMQ)
# ---------------------------------------------------------------------------------------------
def item_webhook_condition():
	"""Webhook conditions see only `doc`, so the Item condition lists the configured menu item groups (with
	their sub-groups). Regenerated whenever a menu or profile changes (`refresh_item_webhook_condition`)."""
	frappe.local.fnb_item_groups = None
	groups = sorted(fnb_item_groups())
	if not groups:
		return "False"
	return "(doc.item_group or \"\") in " + json.dumps(groups)


def refresh_item_webhook_condition():
	"""Keep the installed Item webhooks' condition in step with the menus' item groups (no-op until installed)."""
	condition = item_webhook_condition()
	for name in frappe.get_all("Webhook", filters={"webhook_doctype": "Item", "webhook_json": ["like", "%fnb_webhook_body%"]}, pluck="name"):
		if frappe.db.get_value("Webhook", name, "condition") != condition:
			frappe.db.set_value("Webhook", name, "condition", condition)


def fnb_webhook_body(doc, kind):
	"""Jinja method for the F&B Webhook records: the handler's connection fields (POS Sync Settings)
	plus `messages` for the saved document. Returns '[]' messages when the document is not F&B."""
	settings = _settings()
	if not settings:
		return json.dumps({"messages": []})
	body = {
		"server_ip": settings.server_ip,
		"exchange": settings.exchange,
		"exchange_type": settings.exchange_type or "topic",
		"routing_key": settings.routing_key or "",
		"queue_name": settings.queue_name,
		"username": settings.username or "",
		"password": settings.get_password("password", raise_exception=False) or "",
		"messages": _messages_for(doc, kind),
	}
	for m in body["messages"]:
		m.setdefault("last_modified_by", frappe.session.user)
	return json.dumps(body)


def _messages_for(doc, kind):
	if kind == "item":
		if cint(doc.has_variants) or not is_fnb_item(doc.item_group):
			return []
		return [drop_message(doc) if cint(doc.disabled) else item_message(doc)]
	if kind == "item_drop":
		return [] if cint(doc.has_variants) or not is_fnb_item(doc.item_group) else [drop_message(doc)]
	if kind in ("item_price", "item_price_drop"):
		if doc.price_list not in fnb_price_lists() or not is_fnb_item(frappe.db.get_value("Item", doc.item_code, "item_group")):
			return []
		return [price_message(doc.item_code, doc.price_list, 0 if kind == "item_price_drop" else doc.price_list_rate, doc.currency, doc.modified_by)]
	if kind == "pos_profile":
		return _profile_bundle(doc) if fnb_settings(doc.name) else []
	if kind == "fnb_pos_profile":
		# the companion was saved or deleted: re-send the profile (deleted -> food_and_beverage false)
		return _profile_bundle(frappe.get_doc("POS Profile", doc.pos_profile))
	if kind == "fnb_config":
		# a menu / category / item / modifier group / size / resource changed: re-send every profile it feeds
		out = []
		for name in _profiles_fed_by(doc):
			out.append(profile_message(frappe._dict(name=name)))
		return out
	if kind == "tax_template":
		used = frappe.get_all("POS Profile", filters={"taxes_and_charges": doc.name, "name": ["in", [p.name for p in fnb_profiles()] or [""]]}, limit=1)
		return [tax_message(doc.name)] if used else []
	return []


def _profiles_fed_by(doc):
	"""Enabled F&B profiles whose `fnb` block includes this configuration document."""
	profiles = fnb_profiles()
	if doc.doctype == "FnB Prepared Resource":
		return [p.name for p in profiles if p.name == doc.pos_profile]
	if doc.doctype == "FnB Size":
		return [p.name for p in profiles]
	menu = doc.name if doc.doctype == "FnB Menu" else doc.get("menu")
	return [p.name for p in profiles if p.menu == menu]


def _profile_bundle(profile_doc):
	out = []
	tax = tax_message(profile_doc.taxes_and_charges)
	if tax:
		out.append(tax)
	out.append(profile_message(profile_doc))
	out.extend(pin_messages(profile_doc))
	return out


# (doctype, event, condition on `doc` only - webhook conditions cannot query the database, kind, name suffix)
CONFIG_DOCTYPES = ("FnB Menu", "FnB Menu Category", "FnB Menu Item", "FnB Modifier Group", "FnB Size", "FnB Prepared Resource")


def fnb_webhook_rows():
	rows = [
		("Item", "on_update", item_webhook_condition(), "item", "Item"),
		("Item", "on_trash", item_webhook_condition(), "item_drop", "Item deleted"),
		("POS Profile", "on_update", "", "pos_profile", "POS Profile"),
		("FnB POS Profile", "on_update", "", "fnb_pos_profile", "F&B settings"),
		("FnB POS Profile", "on_trash", "", "fnb_pos_profile", "F&B settings removed"),
		("Sales Taxes and Charges Template", "on_update", "", "tax_template", "Tax template"),
	]
	for doctype in CONFIG_DOCTYPES:
		short = doctype.replace("FnB ", "")
		rows.append((doctype, "on_update", "", "fnb_config", short))
		rows.append((doctype, "on_trash", "", "fnb_config", f"{short} deleted"))
	return rows


@frappe.whitelist()
def install_fnb_webhooks(request_url):
	"""Create / update the Food and Beverage Webhook records (idempotent). `request_url` is the ERP's own
	rabbitmq_handler.webhook endpoint as reachable from the ERP server, e.g.
	http://frontend:8080/api/method/metactical.custom_scripts.utils.rabbitmq_handler.webhook.
	One Item Price webhook is created per enabled F&B price list (like the retail price-list webhooks)."""
	frappe.only_for("System Manager")
	rows = fnb_webhook_rows()
	for price_list in sorted(fnb_price_lists()):
		rows.append(("Item Price", "on_update", f'(doc.price_list or "") == "{price_list}"', "item_price", f"Item Price {price_list}"))
		rows.append(("Item Price", "on_trash", f'(doc.price_list or "") == "{price_list}"', "item_price_drop", f"Item Price {price_list} deleted"))
	names = []
	for doctype, event, condition, kind, label in rows:
		name = f"POS F&B - {label}"
		doc = frappe.get_doc("Webhook", name) if frappe.db.exists("Webhook", name) else frappe.new_doc("Webhook")
		doc.update({
			"webhook_doctype": doctype,
			"webhook_docevent": event,
			"condition": condition,
			"request_url": request_url,
			"request_method": "POST",
			"request_structure": "JSON",
			"webhook_json": '{{ fnb_webhook_body(doc, "%s") }}' % kind,
			"enabled": 1,
			"timeout": 10,
		})
		doc.set("webhook_headers", [{"key": "Content-Type", "value": "application/json"}])
		if doc.is_new():
			doc.name = name
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)
		names.append(doc.name)
	return names


# ---------------------------------------------------------------------------------------------
# bulk initial load
# ---------------------------------------------------------------------------------------------
@frappe.whitelist()
def publish_fnb_catalog(pos_profile):
	"""Initial / bulk load of a Food and Beverage branch: fires the F&B Webhook records for every item of
	its menu group tree and for the profile (tax template + profile + PINs), so the whole load goes through
	the same transport as day-to-day changes and is tracked in the Webhook Request Log."""
	frappe.only_for("System Manager")
	from frappe.integrations.doctype.webhook import run_webhooks
	profile = next((p for p in fnb_profiles() if p.name in (pos_profile, f"{pos_profile} Operators")), None)
	if not profile:
		frappe.throw(f"{pos_profile} is not a Food and Beverage POS Profile")
	if not _settings():
		frappe.throw("POS Sync Settings is disabled or has no server")
	if not frappe.db.exists("Webhook", {"webhook_doctype": "Item", "webhook_docevent": "on_update", "enabled": 1, "webhook_json": ["like", "%fnb_webhook_body%"]}):
		frappe.throw("The F&B webhooks are not installed: run fnb_sync.install_fnb_webhooks(<handler url>) first")
	frappe.local.fnb_item_groups = None
	groups = fnb_item_groups()
	count = 0
	for name in frappe.get_all("Item", filters={"item_group": ["in", list(groups)], "disabled": 0, "has_variants": 0}, pluck="name"):
		run_webhooks(frappe.get_doc("Item", name), "on_update")
		count += 1
	run_webhooks(frappe.get_doc("FnB POS Profile", {"pos_profile": profile.name}), "on_update")
	return {"items": count, "profile": profile.name}
