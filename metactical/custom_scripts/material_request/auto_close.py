# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Close (stop) a Purchase Material Request once its items are back in stock.

The same items often get requested again and again -- by the warehouse, by
whoever asked purchasing to order them -- and the requests keep nagging after
the stock has arrived. A Purchase MR still Pending (nothing of it on a PO yet)
is stopped once EVERY line has at least its qty on hand in its warehouse.

Event-based, not scheduled: each incoming Stock Ledger Entry notes its item and
warehouse, and once that stock transaction has committed, one batched check runs
in the same process (frappe.db.after_commit). No RQ job, so it does not wait
behind big imports, and it can never block or undo the stock transaction itself
-- a failure is only logged. Partially ordered MRs are left for a person.
"""

import frappe
from frappe.utils import flt

_KEYS = "mr_autoclose_keys"


def on_sle_submit(doc, method=None):
	"""Stock Ledger Entry on_submit: queue incoming stock for the check."""
	if doc.is_cancelled or flt(doc.actual_qty) <= 0 or not (doc.item_code and doc.warehouse):
		return
	keys = frappe.local.flags.get(_KEYS)
	if keys is None:
		keys = frappe.local.flags[_KEYS] = set()
		frappe.db.after_commit.add(_run_after_commit)
		frappe.db.after_rollback.add(_forget)
	keys.add((doc.item_code, doc.warehouse))


def _forget():
	frappe.local.flags.pop(_KEYS, None)


def _run_after_commit():
	keys = frappe.local.flags.pop(_KEYS, None)
	if not keys:
		return
	try:
		close_covered_mrs(keys)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Material Request auto-close failed")


def candidate_mrs(keys=None):
	"""Pending Purchase MRs -- all of them, or those with a line on one of
	`keys` ((item_code, warehouse) pairs)."""
	query = """select distinct mr.name from `tabMaterial Request` mr
		join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.docstatus = 1 and mr.status = 'Pending' and mr.material_request_type = 'Purchase'"""
	if keys is None:
		return frappe.db.sql_list(query)
	names, keys = set(), list(keys)
	for i in range(0, len(keys), 500):
		chunk = keys[i:i + 500]
		cond = " or ".join(["(mri.item_code = %s and mri.warehouse = %s)"] * len(chunk))
		names.update(frappe.db.sql_list(query + " and (" + cond + ")", [v for k in chunk for v in k]))
	return sorted(names)


def close_covered_mrs(keys=None):
	"""Stop every candidate MR whose lines are all covered by stock on hand.
	Returns the MRs stopped."""
	closed = []
	for name in candidate_mrs(keys):
		mr = frappe.get_doc("Material Request", name)
		# the list was read a moment ago; only a still-Pending MR is ours to stop
		if mr.status != "Pending" or mr.material_request_type != "Purchase":
			continue
		covered = []
		for d in mr.items:
			on_hand = flt(frappe.db.get_value("Bin", {"item_code": d.item_code, "warehouse": d.warehouse},
				"actual_qty"))
			needed = flt(d.stock_qty) or flt(d.qty) * (flt(d.conversion_factor) or 1)
			if on_hand < needed:
				break
			covered.append(f"{d.item_code}: {on_hand:g} on hand in {d.warehouse}, {needed:g} requested")
		else:
			stop_mr(name)
			mr.add_comment("Comment", "Stopped automatically: every item is back in stock.<br>"
				+ "<br>".join(covered))
			closed.append(name)
	return closed


def stop_mr(name):
	"""Stop the MR the way its form's Stop button does: ERPNext's own
	update_status. That checks the session user can write the MR, and the stock
	that triggered this was moved by whoever moved it -- often a warehouse user
	with no rights on MRs -- so it runs as Administrator."""
	from erpnext.stock.doctype.material_request.material_request import update_status

	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		update_status(name, "Stopped")
	finally:
		frappe.set_user(user)


@frappe.whitelist()
def close_all_covered_mrs():
	"""One-off / on demand: check every Pending Purchase MR, not just those
	whose items just moved."""
	frappe.only_for(("System Manager", "Purchase Manager"))
	closed = close_covered_mrs()
	frappe.db.commit()
	return closed
