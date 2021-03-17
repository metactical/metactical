from __future__ import unicode_literals
import frappe


@frappe.whitelist()
def save_cancel_reason(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc("Sales Order", args.docname)
	doc.db_set("cancel_reason", args.cancel_reason, notify=True)
	return 'Success'
