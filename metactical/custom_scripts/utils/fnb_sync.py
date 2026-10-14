"""Publish Food and Beverage master data to POSWeb through the same RabbitMQ messages the retail
branches use (UpdateVariantMessage, PricingChangeMessage, POSProfileChangeMessage).

Retail items reach POSWeb only when they are variants; a food menu is plain items, so the items under
`POS Profile.neb_fnb_item_group` of every Food and Beverage profile are published from here on save,
together with their prices on the profile's price list and the profile itself. Connection details live
in the single `POS Sync Settings`; when it is disabled nothing is sent.
"""
import frappe
from frappe.utils import cint, flt

from metactical.custom_scripts.utils.rabbitmq_handler import publish_to_rabbitmq

PROFILE_FIELDS = [
	"name", "company", "selling_price_list", "nat_first_priority_price_list", "taxes_and_charges",
	"ifw_default_lead_source", "ifw_drawerfilepath", "ifw_footer", "ifw_header1", "ifw_header2",
	"auto_logout_after_transaction", "neb_allow_manual_order",
	"neb_food_and_beverage", "neb_fnb_item_group", "neb_idle_lock_minutes", "neb_slices_per_pie",
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
	if not frappe.get_meta("POS Profile").has_field("neb_food_and_beverage"):
		return []
	return frappe.get_all("POS Profile", filters={"neb_food_and_beverage": 1, "disabled": 0}, fields=PROFILE_FIELDS)


def fnb_item_groups():
	"""All item groups (with descendants) configured on Food and Beverage profiles, cached per request."""
	if getattr(frappe.local, "fnb_item_groups", None) is not None:
		return frappe.local.fnb_item_groups
	groups = set()
	for profile in fnb_profiles():
		if not profile.neb_fnb_item_group:
			continue
		root = frappe.db.get_value("Item Group", profile.neb_fnb_item_group, ["lft", "rgt"], as_dict=True)
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
	return {
		"message_type": "UpdateVariantMessage",
		"variant_sku": item.name,
		"retailskusiffix": item.get("ifw_retailskusuffix") or item.name,
		"item_id": item.name,
		"group_id": item.item_group,
		"brand": item.get("brand") or "",
		"barcodes": [b.barcode for b in (item.get("barcodes") or []) if b.barcode],
		"name": item.item_name,
		"is_nonstock": not cint(item.is_stock_item),
		"price": [{"price": flt(p.price_list_rate), "currency": p.currency, "price_list": p.price_list} for p in prices],
		"imageUrl": item.get("image") or "",
	}


def price_message(item_code, price_list, rate, currency):
	return {
		"message_type": "PricingChangeMessage",
		"variant_sku": item_code,
		"variant_id": item_code,
		"price": flt(rate),
		"currency": currency,
		"price_list": price_list,
	}


def profile_message(profile):
	"""POSProfileChangeMessage plus the Food and Beverage fields POSWeb maps onto the Branch."""
	doc = frappe.get_doc("POS Profile", profile.name)
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
		# Food and Beverage additions
		"food_and_beverage": bool(cint(doc.get("neb_food_and_beverage"))),
		"idle_lock_minutes": cint(doc.get("neb_idle_lock_minutes")),
		"slices_per_pie": cint(doc.get("neb_slices_per_pie")) or 8,
	}


# ---------------------------------------------------------------------------------------------
# doc_events
# ---------------------------------------------------------------------------------------------
def item_on_update(doc, method=None):
	if cint(doc.has_variants) or not is_fnb_item(doc.item_group):
		return
	publish(item_message(doc))


def item_price_on_update(doc, method=None):
	if doc.price_list not in fnb_price_lists():
		return
	if not is_fnb_item(frappe.db.get_value("Item", doc.item_code, "item_group")):
		return
	publish(price_message(doc.item_code, doc.price_list, doc.price_list_rate, doc.currency))


def item_price_on_trash(doc, method=None):
	if doc.price_list not in fnb_price_lists():
		return
	if not is_fnb_item(frappe.db.get_value("Item", doc.item_code, "item_group")):
		return
	publish(price_message(doc.item_code, doc.price_list, 0, doc.currency))


def pos_profile_on_update(doc, method=None):
	if not cint(doc.get("neb_food_and_beverage")):
		return
	publish(profile_message(doc))


@frappe.whitelist()
def publish_fnb_catalog(pos_profile):
	"""Re-send the profile and every item (with prices) of its item group tree. Use once when a food
	branch is created, or after a bulk import; everything else flows from the save hooks."""
	frappe.only_for("System Manager")
	profile = next((p for p in fnb_profiles() if p.name in (pos_profile, f"{pos_profile} Operators")), None)
	if not profile:
		frappe.throw(f"{pos_profile} is not a Food and Beverage POS Profile")
	if not _settings():
		frappe.throw("POS Sync Settings is disabled or has no server")
	frappe.local.fnb_item_groups = None
	groups = fnb_item_groups()
	count = 0
	for name in frappe.get_all("Item", filters={"item_group": ["in", list(groups)], "disabled": 0, "has_variants": 0}, pluck="name"):
		publish(item_message(frappe.get_doc("Item", name)))
		count += 1
	publish(profile_message(profile))
	return {"items": count, "profile": profile.name}
