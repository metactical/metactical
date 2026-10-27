import frappe


def execute():
	"""Re-save Item Prices that were written by Price Revision apply.

	apply_revision() writes prices via a raw SQL UPDATE (set_rates), which
	skips Frappe's document lifecycle and never fires webhooks. This patch
	does a doc.save() on every Item Price that has an Applied, non-reverted
	log entry so that webhooks fire and downstream sites sync.
	"""
	names = frappe.db.sql_list(
		"""
		SELECT DISTINCT item_price
		FROM `tabPrice Revision Log`
		WHERE action = 'Applied'
		  AND reverted = 0
		  AND item_price IS NOT NULL
		  AND item_price != ''
		"""
	)
	if not names:
		return

	alive = set(frappe.db.sql_list(
		"SELECT name FROM `tabItem Price` WHERE name IN %(names)s",
		{"names": names},
	))

	total = len(alive)
	frappe.logger().info("resave_item_prices_for_webhooks: touching %d Item Price records", total)

	names_list = list(alive)
	for i in range(0, total, 50):
		for name in names_list[i:i + 50]:
			try:
				doc = frappe.get_doc("Item Price", name)
				doc.flags.ignore_permissions = True
				doc.save()
			except Exception:
				frappe.log_error(
					title="resave_item_prices_for_webhooks: failed on {0}".format(name)
				)
		frappe.db.commit()

	frappe.logger().info("resave_item_prices_for_webhooks: done")
