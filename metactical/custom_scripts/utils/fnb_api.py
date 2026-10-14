"""Food and Beverage (restaurant) support for the POS.

Everything here is gated on `POS Profile.neb_food_and_beverage`, so retail branches are untouched:
- customers owned by a food branch (isolated group, phone look-up, never exported to marketing)
- delivery areas -> delivery zones -> delivery fee item
- hot-case "Bake Pie" stock entries (ingredients of the Large pizza bundle issued to Slice Cost)
- tips booked to a Tips Payable liability, 5-cent cash rounding booked to Round Off
"""
import re

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from frappe import _
from frappe.utils import cint, flt, nowdate

FNB_PROFILE_FIELDS = [
	"name", "company", "warehouse", "selling_price_list", "customer",
	"neb_food_and_beverage", "neb_fnb_customer_group", "neb_fnb_item_group",
	"neb_tips_payable_account", "neb_slice_cost_account", "neb_slices_per_pie", "neb_idle_lock_minutes",
]

ORDER_TYPES = ("Dine-in", "Take-out", "Delivery")


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


def get_fnb_profile(pos_profile):
	"""Return the POS Profile fields when it is a Food and Beverage branch, else None."""
	name = profile_name(pos_profile)
	if not name:
		return None
	if not frappe.get_meta("POS Profile").has_field("neb_food_and_beverage"):
		return None
	profile = frappe.db.get_value("POS Profile", name, FNB_PROFILE_FIELDS, as_dict=True)
	return profile if profile and cint(profile.neb_food_and_beverage) else None


def is_fnb_customer(customer):
	"""True when the customer is owned by a Food and Beverage profile (must never leak to retail)."""
	if not customer or not frappe.get_meta("Customer").has_field("neb_owned_by_pos_profile"):
		return False
	owner = frappe.db.get_value("Customer", customer, "neb_owned_by_pos_profile")
	return bool(owner and cint(frappe.db.get_value("POS Profile", owner, "neb_food_and_beverage")))


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
			 "country", "phone", "email_id", "neb_delivery_area", "disabled"],
			as_dict=True,
		)
		if not address or cint(address.disabled):
			continue
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

	filters = {"neb_owned_by_pos_profile": profile.name, "disabled": 0}
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
@frappe.whitelist()
def bake_pie(pos_profile, item_code, qty=1, bake_id=None, user=None):
	"""Issue the ingredients of `qty` pies of `item_code` (a Product Bundle) from the branch warehouse
	to the Slice Cost account as a `Hot Case Pie Baked` Stock Entry. `bake_id` (the till's UUID) makes
	the call idempotent: a retry returns the entry that was already posted instead of baking again.
	"""
	profile = get_fnb_profile(pos_profile)
	if not profile:
		frappe.throw(_("{0} is not a Food and Beverage POS Profile").format(pos_profile))
	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("Quantity must be positive"))

	marker = f"bake:{bake_id}" if bake_id else None
	if marker:
		existing = frappe.db.get_value(
			"Stock Entry", {"company": profile.company, "docstatus": 1, "remarks": ["like", f"%{marker}%"]},
			["name", "total_outgoing_value"], as_dict=True,
		)
		if existing:
			return _bake_result(existing, qty, profile, duplicate=True)

	bundle = frappe.db.get_value("Product Bundle", {"new_item_code": item_code, "disabled": 0}, "name")
	if not bundle:
		frappe.throw(_("{0} has no Product Bundle (recipe) in ERP").format(item_code))
	if not frappe.db.exists("Stock Entry Type", "Hot Case Pie Baked"):
		frappe.throw(_("Stock Entry Type 'Hot Case Pie Baked' does not exist"))

	expense_account = profile.neb_slice_cost_account or frappe.db.get_value(
		"Account", {"account_name": "Slice Cost", "company": profile.company, "is_group": 0}, "name")
	if not expense_account:
		frappe.throw(_("Set 'Slice Cost account' on POS Profile {0}").format(profile.name))

	if user and frappe.db.exists("User", user):
		frappe.set_user(user)
	try:
		entry = _submit_with_retry(lambda: frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Hot Case Pie Baked",
			"purpose": "Material Issue",
			"company": profile.company,
			"from_warehouse": profile.warehouse,
			"posting_date": nowdate(),
			"remarks": f"Hot case bake {marker or ''} | {item_code} x {qty:g} | by {user or frappe.session.user}".replace("  ", " "),
			"items": [{
				"item_code": row.item_code,
				"qty": flt(row.qty) * qty,
				"uom": row.uom,
				"s_warehouse": profile.warehouse,
				"expense_account": expense_account,
			} for row in frappe.get_all("Product Bundle Item", filters={"parent": bundle}, fields=["item_code", "qty", "uom"])],
		}))
	finally:
		frappe.set_user("Administrator")
	return _bake_result(entry, qty, profile, duplicate=False)


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


def _bake_result(entry, qty, profile, duplicate):
	slices = cint(profile.neb_slices_per_pie) or 8
	value = flt(entry.total_outgoing_value)
	return {
		"name": entry.name,
		"duplicate": duplicate,
		"pies": qty,
		"slices_per_pie": slices,
		"total_value": value,
		"cost_per_pie": round(value / qty, 4) if qty else 0,
		"cost_per_slice": round(value / qty / slices, 4) if qty else 0,
	}


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


def create_tip_entry(sales_invoice, form_data, profile=None):
	"""Book the tip as Dr tender account / Cr Tips Payable. Tips are never revenue and never taxed."""
	tip = flt(form_data.get("Tip"))
	if tip <= 0:
		return None
	profile = profile or get_fnb_profile(form_data.get("POSProfile"))
	if not profile:
		return None
	if not profile.neb_tips_payable_account:
		frappe.throw(_("Set 'Tips payable account' on POS Profile {0}").format(profile.name))

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
			{"account": profile.neb_tips_payable_account, "credit_in_account_currency": tip, "cost_center": sales_invoice.cost_center},
		],
	})
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry.name


def create_tip_entry_safe(sales_invoice, form_data):
	"""Same as create_tip_entry but never fails the order: the problem lands on the invoice timeline."""
	try:
		name = create_tip_entry(sales_invoice, form_data)
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
# marketing guard: food customers never reach an Email Group
# ---------------------------------------------------------------------------------------------
def _fnb_customers_with_email(email):
	email = (email or "").strip().lower()
	if not email or not frappe.get_meta("Customer").has_field("neb_owned_by_pos_profile"):
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
