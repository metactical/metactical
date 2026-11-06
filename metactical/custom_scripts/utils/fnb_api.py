"""Food and Beverage (restaurant) support for the POS.

Nothing here changes an existing doctype. A POS Profile is a Food and Beverage branch when it has an
enabled `FnB POS Profile` row, and every other Food and Beverage value lives on a companion doctype that
links back to the original record (the original is never edited):
- FnB POS Profile -> POS Profile        flag, idle lock, customer group, menu, order types, tips/discount settings
- FnB Menu / Category / Item / Modifier Group / Size   what the till shows (no naming conventions)
- FnB Prepared Resource / FnB Batch     things cooked in batches (pies, broth pots) and each batch cooked
- FnB Customer    -> Customer           owned by a food branch: phone look-up on that till only, never retail, never marketing
- FnB Address     -> Address            delivery area -> zone -> delivery fee item
- FnB Order       -> Sales Order        order type, delivery area, tip, cash rounding + the invoice / tip entry it became
- FnB Opening     -> POS Opening        portions of each counted resource on hand at opening
- FnB Closing     -> End of Day Closing per-resource reconciliation (produced, consumed, counted, variance), tips
Retail branches never get a companion row, so their behaviour is untouched. The POS calls the whitelisted
methods here; the ERP never calls the POS (changes reach it through fnb_sync's RabbitMQ messages).
"""
import json
import re

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from frappe import _
from frappe.utils import cint, flt, nowdate

POS_PROFILE_FIELDS = ["name", "company", "warehouse", "selling_price_list", "customer", "disabled"]
FNB_SETTINGS_FIELDS = [
	"enabled", "idle_lock_minutes", "customer_group", "menu", "tips_payable_account", "delivery_city",
	"tip_presets", "discount_presets", "max_discount_percent", "cash_rounding_to", "variance_warn_portions",
]

# original doctype -> (companion doctype, link field): rows removed when the original is deleted
COMPANIONS = {
	"POS Profile": ("FnB POS Profile", "pos_profile"),
	"Customer": ("FnB Customer", "customer"),
	"Address": ("FnB Address", "address"),
	"Sales Order": ("FnB Order", "sales_order"),
	"End of Day Closing": ("FnB Closing", "closing_entry"),
	"POS Opening": ("FnB Opening", "opening_entry"),
}
# original doctype -> FnB Order field cleared when the original is deleted
CLEARED_LINKS = {"Sales Invoice": "sales_invoice", "Journal Entry": "tip_journal_entry"}


# ---------------------------------------------------------------------------------------------
# profile helpers
# ---------------------------------------------------------------------------------------------
def profile_name(pos_profile):
	"""The POS sends the branch name ("Pizza Store"); the ERP profile is "<branch> Operators"."""
	if not pos_profile:
		return None
	if frappe.db.exists("POS Profile", pos_profile):
		return pos_profile
	candidate = f"{pos_profile} Operators"
	return candidate if frappe.db.exists("POS Profile", candidate) else None


def fnb_settings(pos_profile_name):
	"""The enabled FnB POS Profile row of an exact POS Profile name, else None (= retail branch)."""
	if not pos_profile_name:
		return None
	row = frappe.db.get_value("FnB POS Profile", {"pos_profile": pos_profile_name}, FNB_SETTINGS_FIELDS, as_dict=True)
	return row if row and cint(row.enabled) else None


def get_fnb_profile(pos_profile):
	"""The POS Profile fields merged with its FnB POS Profile settings when it is a Food and Beverage
	branch, else None."""
	name = profile_name(pos_profile)
	if not name:
		return None
	settings = fnb_settings(name)
	if not settings:
		return None
	profile = frappe.db.get_value("POS Profile", name, POS_PROFILE_FIELDS, as_dict=True)
	if not profile:
		return None
	profile.update(settings)
	return profile


def is_fnb_customer(customer):
	"""True when the customer is owned by a Food and Beverage profile (must never leak to retail)."""
	if not customer:
		return False
	owner = frappe.db.get_value("FnB Customer", {"customer": customer}, "pos_profile")
	return bool(owner and fnb_settings(owner))


# ---------------------------------------------------------------------------------------------
# customers: isolated per branch, looked up by phone
# ---------------------------------------------------------------------------------------------
def _digits(value):
	return re.sub(r"\D", "", value or "")


def _phone_match(wanted, candidate):
	wanted, candidate = _digits(wanted), _digits(candidate)
	if not wanted or not candidate:
		return False
	return wanted[-10:] == candidate[-10:]


def _linked_parents(parenttype, customer):
	return [d.parent for d in frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": parenttype, "link_doctype": "Customer", "link_name": customer},
		fields=["parent"],
	)]


def _contacts_of(customer):
	contacts = []
	for name in _linked_parents("Contact", customer):
		contact = frappe.db.get_value("Contact", name, ["name", "first_name", "last_name", "phone", "mobile_no", "email_id"], as_dict=True)
		if not contact:
			continue
		phones = {p for p in (contact.phone, contact.mobile_no) if p}
		phones.update(d.phone for d in frappe.get_all("Contact Phone", filters={"parent": name}, fields=["phone"]) if d.phone)
		contact["phones"] = sorted(phones)
		contacts.append(contact)
	return contacts


def _delivery_fee(area, price_list):
	"""area -> (zone, delivery item, item name, price on the branch price list)."""
	if not area:
		return {}
	zone = frappe.db.get_value("Delivery Area", area, "delivery_zone")
	if not zone:
		return {}
	item = frappe.db.get_value("Delivery Zone", zone, "delivery_item")
	if not item:
		return {"delivery_zone": zone}
	price = frappe.db.get_value("Item Price", {"item_code": item, "price_list": price_list}, "price_list_rate")
	return {
		"delivery_zone": zone,
		"delivery_item": item,
		"delivery_item_name": frappe.db.get_value("Item", item, "item_name"),
		"delivery_price": flt(price),
	}


def _addresses_of(customer, price_list):
	addresses = []
	for name in _linked_parents("Address", customer):
		address = frappe.db.get_value(
			"Address", name,
			["name", "address_type", "address_title", "address_line1", "address_line2", "city", "state", "pincode",
			 "country", "phone", "email_id", "disabled"],
			as_dict=True,
		)
		if not address or cint(address.disabled):
			continue
		# response key kept as `neb_delivery_area`: it is what POSWeb's FnbAddress model reads
		address["neb_delivery_area"] = frappe.db.get_value("FnB Address", {"address": name}, "delivery_area")
		address.update(_delivery_fee(address.neb_delivery_area, price_list))
		addresses.append(address)
	return addresses


@frappe.whitelist()
def get_fnb_customers(pos_profile, phone=None, query=None, limit=20):
	"""Customers owned by this Food and Beverage branch, by phone (any format) or name fragment.

	Returns each customer with its contacts, phones and addresses; each address carries the
	delivery area, zone, delivery item and the fee on the branch price list.
	"""
	profile = get_fnb_profile(pos_profile)
	if not profile:
		frappe.throw(_("{0} is not a Food and Beverage POS Profile").format(pos_profile))

	owned = frappe.get_all("FnB Customer", filters={"pos_profile": profile.name}, pluck="customer")
	if not owned:
		return []
	filters = {"name": ["in", owned], "disabled": 0}
	if query and not phone:
		filters["customer_name"] = ["like", f"%{query}%"]

	limit = cint(limit) or 20
	customers = frappe.get_all(
		"Customer", filters=filters,
		fields=["name", "customer_name", "first_name", "last_name", "mobile_no", "email_id"],
		order_by="modified desc", limit=1000 if phone else limit,
	)

	result = []
	for customer in customers:
		contacts = _contacts_of(customer.name)
		addresses = _addresses_of(customer.name, profile.selling_price_list)
		phones = {p for c in contacts for p in c["phones"]}
		phones.update(a.phone for a in addresses if a.phone)
		if customer.mobile_no:
			phones.add(customer.mobile_no)
		if phone and not any(_phone_match(phone, p) for p in phones):
			continue
		customer.update({"phones": sorted(phones), "contacts": contacts, "addresses": addresses})
		result.append(customer)
		if len(result) >= limit:
			break
	return result


@frappe.whitelist()
def get_delivery_areas(pos_profile):
	"""Every active delivery area of the branch with its zone, delivery item and current fee."""
	profile = get_fnb_profile(pos_profile)
	if not profile:
		frappe.throw(_("{0} is not a Food and Beverage POS Profile").format(pos_profile))

	zones = {z.name: z for z in frappe.get_all(
		"Delivery Zone", filters={"pos_profile": profile.name, "disabled": 0},
		fields=["name", "zone_name", "delivery_item"],
	)}
	if not zones:
		return []
	areas = frappe.get_all(
		"Delivery Area", filters={"delivery_zone": ["in", list(zones)], "disabled": 0},
		fields=["name", "area_name", "delivery_zone"], order_by="area_name",
	)
	out = []
	for area in areas:
		zone = zones[area.delivery_zone]
		price = frappe.db.get_value("Item Price", {"item_code": zone.delivery_item, "price_list": profile.selling_price_list}, "price_list_rate")
		out.append({
			"area": area.name, "area_name": area.area_name,
			"delivery_zone": zone.name, "zone_name": zone.zone_name,
			"delivery_item": zone.delivery_item,
			"delivery_item_name": frappe.db.get_value("Item", zone.delivery_item, "item_name"),
			"delivery_price": flt(price),
		})
	return out


# ---------------------------------------------------------------------------------------------
# hot case: Bake Pie
# ---------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------
# prepared resources: batches cooked on the till, consumption per shift
# ---------------------------------------------------------------------------------------------
def open_shift(pos_profile_name):
	"""The profile's current POS Opening (the last one without an End of Day Closing), else None."""
	last = frappe.get_all("POS Opening", filters={"pos_profile": pos_profile_name, "docstatus": ["!=", 2]},
		fields=["name", "opening_date", "opening_time", "creation"], order_by="creation desc", limit=1)
	if not last:
		return None
	opening = last[0]
	if frappe.db.exists("End of Day Closing", {"pos_profile": pos_profile_name, "opening_entry": opening.name}):
		return None
	return opening


def _resource_doc(resource, profile):
	doc = frappe.get_doc("FnB Prepared Resource", resource)
	if doc.pos_profile != profile.name:
		frappe.throw(_("{0} does not belong to {1}").format(resource, profile.name))
	if cint(doc.disabled):
		frappe.throw(_("{0} is disabled").format(resource))
	return doc


@frappe.whitelist()
def cook_batch(pos_profile, resource, qty=1, batch_id=None, user=None):
	"""One press of a prepared resource's button on the till: issue `qty` batches of the resource's recipe
	(a Product Bundle) from the branch warehouse to its cost account as a Stock Entry, and record the FnB Batch
	(portions produced, shift, user, cost). `batch_id` (the till's UUID) makes the call idempotent."""
	profile = get_fnb_profile(pos_profile)
	if not profile:
		frappe.throw(_("{0} is not a Food and Beverage POS Profile").format(pos_profile))
	qty = cint(qty)
	if qty <= 0:
		frappe.throw(_("Quantity must be positive"))
	if batch_id:
		existing = frappe.db.get_value("FnB Batch", {"batch_id": batch_id}, "name")
		if existing:
			return _batch_result(frappe.get_doc("FnB Batch", existing), duplicate=True)

	res = _resource_doc(resource, profile)
	bundle = frappe.db.get_value("Product Bundle", {"new_item_code": res.recipe_item, "disabled": 0}, "name")
	if not bundle:
		frappe.throw(_("{0} has no Product Bundle (recipe) in ERP").format(res.recipe_item))
	shift = open_shift(profile.name)

	if user and frappe.db.exists("User", user):
		frappe.set_user(user)
	try:
		entry = _submit_with_retry(lambda: frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": res.stock_entry_type,
			"purpose": "Material Issue",
			"company": profile.company,
			"from_warehouse": profile.warehouse,
			"posting_date": nowdate(),
			"remarks": f"{res.action_label}: {res.label} x {qty} | batch {batch_id or ''} | by {user or frappe.session.user}",
			"items": [{
				"item_code": row.item_code,
				"qty": flt(row.qty) * qty,
				"uom": row.uom,
				"s_warehouse": profile.warehouse,
				"expense_account": res.cost_account,
			} for row in frappe.get_all("Product Bundle Item", filters={"parent": bundle}, fields=["item_code", "qty", "uom"])],
		}))
		batch = frappe.get_doc({
			"doctype": "FnB Batch",
			"resource": res.name,
			"pos_profile": profile.name,
			"qty": qty,
			"portions": qty * cint(res.portions_per_batch),
			"stock_entry": entry.name,
			"opening_entry": shift.name if shift else None,
			"cooked_by": user or frappe.session.user,
			"cooked_at": frappe.utils.now_datetime(),
			"batch_id": batch_id or None,
			"cost": flt(entry.total_outgoing_value),
		}).insert(ignore_permissions=True)
		frappe.db.commit()
	finally:
		frappe.set_user("Administrator")
	return _batch_result(batch, duplicate=False)


def _submit_with_retry(make_doc, attempts=3):
	"""Insert + submit the document; a stock ledger deadlock (another job posting the same items) is retried."""
	for attempt in range(1, attempts + 1):
		try:
			doc = make_doc()
			doc.insert(ignore_permissions=True)
			doc.submit()
			frappe.db.commit()
			return doc
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt == attempts:
				raise
			import time
			time.sleep(0.5 * attempt)


def _batch_result(batch, duplicate):
	per_batch = cint(frappe.db.get_value("FnB Prepared Resource", batch.resource, "portions_per_batch")) or 1
	value = flt(batch.cost)
	return {
		"name": batch.name,
		"stock_entry": batch.stock_entry,
		"duplicate": duplicate,
		"batches": batch.qty,
		"portions": batch.portions,
		"portions_per_batch": per_batch,
		"total_value": value,
		"cost_per_batch": round(value / batch.qty, 4) if batch.qty else 0,
		"cost_per_portion": round(value / batch.portions, 4) if batch.portions else 0,
	}


def _shift_consumption(profile_name, since):
	"""Portions consumed per resource by the Sales Orders of the profile since `since`: each sold item times
	the portions it draws on the resource's consumer table."""
	rows = frappe.db.sql("""
		select c.parent as resource, sum(soi.qty * c.portions) as portions
		from `tabFnB Order` fo
		join `tabSales Order` so on so.name = fo.sales_order and so.docstatus < 2
		join `tabSales Order Item` soi on soi.parent = so.name
		join `tabFnB Resource Consumer` c on c.item = soi.item_code and c.parenttype = 'FnB Prepared Resource'
		join `tabFnB Prepared Resource` r on r.name = c.parent and r.pos_profile = %(profile)s
		where fo.pos_profile = %(profile)s and so.creation >= %(since)s
		group by c.parent""", {"profile": profile_name, "since": since}, as_dict=True)
	return {r.resource: flt(r.portions) for r in rows}


def _shift_production(profile_name, opening_name):
	rows = frappe.get_all("FnB Batch", filters={"pos_profile": profile_name, "opening_entry": opening_name},
		fields=["resource", "sum(qty) as batches", "sum(portions) as portions"], group_by="resource")
	return {r.resource: r for r in rows}


def _shift_opening_counts(opening_name):
	rows = frappe.get_all("FnB Opening Resource", filters={"parent": opening_name, "parenttype": "FnB Opening"},
		fields=["resource", "portions_on_hand"])
	return {r.resource: cint(r.portions_on_hand) for r in rows}


def shift_resources(profile, shift):
	"""Per prepared resource of the profile: opening count, batches / portions produced, portions consumed and
	the resulting on-hand estimate for the given shift (an `open_shift` row)."""
	resources = frappe.get_all("FnB Prepared Resource", filters={"pos_profile": profile.name, "disabled": 0},
		fields=["name", "label", "action_label", "portion_noun", "portions_per_batch", "tracking"], order_by="label")
	if not shift:
		return [dict(resource=r.name, label=r.label, action_label=r.action_label, portion_noun=r.portion_noun,
			portions_per_batch=cint(r.portions_per_batch), tracking=r.tracking, opening_portions=0, batches=0,
			portions_produced=0, portions_consumed=0, on_hand=0) for r in resources]
	since = f"{shift.opening_date} {shift.opening_time}" if shift.get("opening_date") else shift.creation
	opening = _shift_opening_counts(shift.name)
	produced = _shift_production(profile.name, shift.name)
	consumed = _shift_consumption(profile.name, since)
	out = []
	for r in resources:
		prod = produced.get(r.name)
		o, p, c = opening.get(r.name, 0), cint(prod.portions) if prod else 0, cint(round(consumed.get(r.name, 0)))
		out.append(dict(resource=r.name, label=r.label, action_label=r.action_label, portion_noun=r.portion_noun,
			portions_per_batch=cint(r.portions_per_batch), tracking=r.tracking, opening_portions=o,
			batches=cint(prod.batches) if prod else 0, portions_produced=p, portions_consumed=c, on_hand=o + p - c))
	return out


@frappe.whitelist()
def get_shift_resources(pos_profile):
	"""The till's hot-case / batch figures for the current shift, computed by the ERP (FnB Opening, FnB Batch,
	sold items x consumer portions)."""
	profile = get_fnb_profile(pos_profile)
	if not profile:
		return []
	return shift_resources(profile, open_shift(profile.name))


# ---------------------------------------------------------------------------------------------
# money: cash rounding and tips (called from pos_api on the invoice path)
# ---------------------------------------------------------------------------------------------
def cash_rounding_row(form_data, profile):
	"""The 5-cent cash rounding (`CashRounding` = cash collected - exact total, signed, e.g. +0.01 or -0.02)
	as an "Actual" charge row to the company's Round Off account. Added to the Sales Order (and so copied
	to the invoice) so the grand total equals what the customer actually paid; GST is unaffected because
	the row is an actual amount, not a percentage. Returns None when there is nothing to round.
	"""
	rounding = flt(form_data.get("CashRounding"))
	if not rounding or not profile:
		return None
	company = frappe.db.get_value("Company", profile.company, ["round_off_account", "round_off_cost_center"], as_dict=True)
	if not company or not company.round_off_account:
		frappe.throw(_("Set the Round Off account on company {0}").format(profile.company))
	return {
		"charge_type": "Actual",
		"account_head": company.round_off_account,
		"cost_center": company.round_off_cost_center,
		"description": "Cash rounding",
		"tax_amount": rounding,
		"included_in_print_rate": 0,
	}


def apply_fnb_invoice_fields(sales_invoice, form_data, profile=None):
	"""Food and Beverage invoices are never rounded to the dollar (the POS already applied the 5-cent cash
	rounding as a charge row on the Sales Order)."""
	profile = profile or get_fnb_profile(form_data.get("POSProfile"))
	if not profile:
		return
	sales_invoice.disable_rounded_total = 1


def create_tip_entry(sales_invoice, form_data, profile=None, sales_order=None):
	"""Book the tip as Dr tender account / Cr Tips Payable. Tips are never revenue and never taxed.
	The entry is recorded on the order's FnB Order row."""
	tip = flt(form_data.get("Tip"))
	if tip <= 0:
		return None
	profile = profile or get_fnb_profile(form_data.get("POSProfile"))
	if not profile:
		return None
	if not profile.tips_payable_account:
		frappe.throw(_("Set 'Tips Payable Account' on FnB POS Profile {0}").format(profile.name))

	mode = form_data.get("TipModeOfPayment")
	if not mode:
		payments = form_data.get("Payment") or []
		mode = payments[0].get("ModeOfPayment") if payments else "Cash"
	tender_account = get_bank_cash_account(company=profile.company, mode_of_payment=mode).get("account")
	if not tender_account:
		frappe.throw(_("Mode of Payment {0} has no account for {1}").format(mode, profile.company))

	entry = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"company": profile.company,
		"posting_date": nowdate(),
		"user_remark": f"Tip on {sales_invoice.name} ({mode})",
		"accounts": [
			{"account": tender_account, "debit_in_account_currency": tip, "cost_center": sales_invoice.cost_center},
			{"account": profile.tips_payable_account, "credit_in_account_currency": tip, "cost_center": sales_invoice.cost_center},
		],
	})
	entry.insert(ignore_permissions=True)
	entry.submit()

	sales_order = sales_order or next((row.sales_order for row in sales_invoice.items if row.get("sales_order")), None)
	row = sales_order and frappe.db.get_value("FnB Order", {"sales_order": sales_order}, "name")
	if row:
		frappe.db.set_value("FnB Order", row, {"tip_journal_entry": entry.name, "tip_mode_of_payment": mode}, update_modified=False)
	return entry.name


def create_tip_entry_safe(sales_invoice, form_data, sales_order=None):
	"""Same as create_tip_entry but never fails the order: the problem lands on the invoice timeline."""
	try:
		name = create_tip_entry(sales_invoice, form_data, sales_order=sales_order)
		if name:
			frappe.db.commit()
		return name
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Create Tip Entry Error", message=frappe.get_traceback())
		sales_invoice.add_comment("Comment", f"<b>Tip of $ {flt(form_data.get('Tip'))} was NOT booked:</b> {e}")
		frappe.db.commit()
		return None


# ---------------------------------------------------------------------------------------------
# companion rows written on the POS order / shift path (every caller gates on the profile)
# ---------------------------------------------------------------------------------------------
def customer_display_name(customer, fnb):
	"""Customer name / address title from the POS payload. Food and Beverage: first + last name, a single
	name is fine. Retail keeps the expression the API has always used (behaviour unchanged)."""
	first = customer.get("FirstName") or ""
	last = customer.get("LastName")
	if fnb:
		return (first + " " + (last or "")).strip()
	return first + " " + last if last else ""


def record_fnb_customer(customer_name, fnb):
	"""Mark a customer the POS just created as owned by the Food and Beverage branch."""
	if frappe.db.exists("FnB Customer", {"customer": customer_name}):
		return
	frappe.get_doc({"doctype": "FnB Customer", "customer": customer_name, "pos_profile": fnb.name}).insert(ignore_permissions=True)


def set_delivery_area(address_name, area, fnb):
	"""Upsert the FnB Address row of an address; a no-op for retail or when the POS sent no area."""
	if not fnb or not address_name or not area:
		return
	existing = frappe.db.get_value("FnB Address", {"address": address_name}, "name")
	if existing:
		doc = frappe.get_doc("FnB Address", existing)
		if doc.delivery_area != area:
			doc.delivery_area = area
			doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": "FnB Address", "address": address_name, "delivery_area": area}).insert(ignore_permissions=True)


def record_fnb_order(sales_order, form_data, fnb):
	"""FnB Order row of a freshly inserted Sales Order (written in the same transaction as the order)."""
	order_type = form_data.get("OrderType") or ""
	customer = form_data.get("Customer") or {}
	tip_mode = form_data.get("TipModeOfPayment") or None
	frappe.get_doc({
		"doctype": "FnB Order",
		"sales_order": sales_order.name,
		"pos_profile": fnb.name,
		"order_type": order_type,
		"delivery_area": customer.get("DeliveryArea") or None,
		"tip_amount": flt(form_data.get("Tip")),
		"tip_mode_of_payment": tip_mode if tip_mode and frappe.db.exists("Mode of Payment", tip_mode) else None,
		"cash_rounding": flt(form_data.get("CashRounding")),
	}).insert(ignore_permissions=True)


def link_fnb_invoice(sales_order_name, sales_invoice_name):
	"""Record the invoice a Food and Beverage order became; a no-op for retail orders (no row)."""
	row = frappe.db.get_value("FnB Order", {"sales_order": sales_order_name}, "name")
	if row:
		frappe.db.set_value("FnB Order", row, "sales_invoice", sales_invoice_name, update_modified=False)


def _block(value):
	"""The `FoodAndBeverage` block of an opening / closing payload (a dict, or JSON text from a form post)."""
	if isinstance(value, str):
		value = json.loads(value or "{}")
	return value or {}


def record_fnb_opening(opening_name, fnb):
	"""`{"Resources": [{"Resource", "PortionsOnHand"}]}` -> FnB Opening with one row per counted resource."""
	fnb = _block(fnb)
	doc = frappe.get_doc({"doctype": "FnB Opening", "opening_entry": opening_name})
	for row in fnb.get("Resources") or []:
		if row.get("Resource") and frappe.db.exists("FnB Prepared Resource", row["Resource"]):
			doc.append("resources", {"resource": row["Resource"], "portions_on_hand": cint(row.get("PortionsOnHand"))})
	doc.insert(ignore_permissions=True)


def record_fnb_closing(closing_name, fnb):
	"""`{"Resources": [{"Resource", "PortionsCounted", "VarianceReason"}], "TipsCollected"}` -> FnB Closing. The
	till only sends what it counted; opening, produced and consumed come from the ERP's own records."""
	fnb = _block(fnb)
	closing = frappe.db.get_value("End of Day Closing", closing_name, ["pos_profile", "opening_entry"], as_dict=True)
	profile = get_fnb_profile(closing.pos_profile) if closing else None
	doc = frappe.get_doc({"doctype": "FnB Closing", "closing_entry": closing_name, "tips_collected": flt(fnb.get("TipsCollected"))})
	counted = {r.get("Resource"): r for r in (fnb.get("Resources") or []) if r.get("Resource")}
	if profile:
		shift = None
		if closing.opening_entry:
			shift = frappe.db.get_value("POS Opening", closing.opening_entry, ["name", "opening_date", "opening_time", "creation"], as_dict=True)
		for r in shift_resources(profile, shift):
			c = counted.get(r["resource"], {})
			tracked = r["tracking"] == "Count remaining at close"
			n_counted = cint(c.get("PortionsCounted")) if tracked else 0
			doc.append("resources", {
				"resource": r["resource"],
				"opening_portions": r["opening_portions"],
				"batches": r["batches"],
				"portions_produced": r["portions_produced"],
				"portions_consumed": r["portions_consumed"],
				"portions_counted": n_counted,
				"variance": (n_counted - r["on_hand"]) if tracked else 0,
				"variance_reason": (c.get("VarianceReason") or "") if tracked else "",
			})
	doc.insert(ignore_permissions=True)


def on_trash_original(doc, method=None):
	"""on_trash of the original doctypes: remove or unlink their companion rows first, so Frappe's
	"document is linked" check does not stop the deletion. Retail documents have no rows: nothing happens.
	Cancelling is never affected (companions are not submittable)."""
	companion = COMPANIONS.get(doc.doctype)
	if companion:
		doctype, field = companion
		for name in frappe.get_all(doctype, filters={field: doc.name}, pluck="name"):
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=1, ignore_on_trash=True)
	field = CLEARED_LINKS.get(doc.doctype)
	if field:
		for name in frappe.get_all("FnB Order", filters={field: doc.name}, pluck="name"):
			frappe.db.set_value("FnB Order", name, field, None, update_modified=False)


# ---------------------------------------------------------------------------------------------
# marketing guard: food customers never reach an Email Group
# ---------------------------------------------------------------------------------------------
def _fnb_customers_with_email(email):
	email = (email or "").strip().lower()
	if not email:
		return []
	customers = set(frappe.get_all("Customer", filters={"email_id": email}, pluck="name"))
	contacts = set(frappe.get_all("Contact", filters={"email_id": email}, pluck="name"))
	contacts.update(frappe.get_all("Contact Email", filters={"email_id": email}, pluck="parent"))
	if contacts:
		customers.update(frappe.get_all(
			"Dynamic Link", filters={"parenttype": "Contact", "parent": ["in", list(contacts)], "link_doctype": "Customer"},
			pluck="link_name",
		))
	return [c for c in customers if is_fnb_customer(c)]


def guard_email_group_member(doc, method=None):
	"""before_insert on Email Group Member: block the only route into marketing for food customers
	(manual "Import Subscribers" / newsletter sign-ups)."""
	owners = _fnb_customers_with_email(doc.email)
	if owners:
		frappe.throw(
			_("{0} belongs to customer {1} of a Food and Beverage branch and must not be added to an Email Group.")
			.format(doc.email, owners[0]),
			title=_("Not allowed"),
		)
