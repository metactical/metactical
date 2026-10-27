import frappe


def execute():
	"""Enqueue the cancellation work as a background job (1-hour timeout)."""
	frappe.enqueue(
		"metactical.patches.cancel_duplicate_zero_invoices_for_icl_dns._run",
		queue="long",
		timeout=3600,
		job_id="cancel_duplicate_zero_invoices_for_icl_dns",
		deduplicate=True,
	)


def _run():
	"""Cancel duplicate zero-value Sales Invoices linked to ICL Delivery Notes.

	For each Completed, zero-grand-total DN from this month for ICL, if more than
	one invoice is linked, keep the one with the highest grand_total (earliest
	creation as tiebreaker) and cancel any remaining submitted zero-value invoices.
	"""
	dns = frappe.get_all(
		"Delivery Note",
		filters=[
			["creation", "Timespan", "this month"],
			["customer", "=", "International Camouflage Ltd."],
			["status", "=", "Completed"],
			["grand_total", "=", 0],
		],
		pluck="name",
	)
	if not dns:
		return

	si_items = frappe.get_all(
		"Sales Invoice Item",
		filters=[["delivery_note", "in", dns]],
		fields=["delivery_note", "parent"],
		distinct=True,
	)

	dn_invoice_map = {}
	for row in si_items:
		if row.delivery_note and row.parent:
			dn_invoice_map.setdefault(row.delivery_note, set()).add(row.parent)

	for dn, inv_set in dn_invoice_map.items():
		inv_list = list(inv_set)
		if len(inv_list) <= 1:
			continue

		invoices = frappe.get_all(
			"Sales Invoice",
			filters=[["name", "in", inv_list]],
			fields=["name", "grand_total", "status", "creation"],
			order_by="grand_total desc, creation asc",
		)

		keep = invoices[0]

		for inv in invoices[1:]:
			if (inv.grand_total or 0) == 0 and inv.status == "Paid":
				try:
					doc = frappe.get_doc("Sales Invoice", inv.name)
					doc.cancel()
					frappe.db.commit()
					frappe.logger().info(
						"cancel_duplicate_zero_invoices: cancelled %s (dup of %s via DN %s)",
						inv.name, keep.name, dn,
					)
				except Exception:
					frappe.log_error(
						title="cancel_duplicate_zero_invoices: failed on {0}".format(inv.name)
					)
