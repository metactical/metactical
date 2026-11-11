"""Move a doctype's webhooks to the long queue while a GearStock patch runs, then put them back.

Each item a patch saves queues one job per webhook. Left on the default queue, tens of thousands
of them sit in front of emails and every other ordinary job for hours. Moving them to long keeps
default free.

The queue each webhook had before is kept in a global default (tabDefaultValue) under the
patch's own key, so a later restore — even from another job — puts back exactly what was there.
Moving is safe to repeat: a webhook already moved keeps its first recorded queue.

If a run stops before it finishes, the webhooks stay on long until the run is completed, or
until someone calls restore(<key>) by hand.
"""

import json

import frappe

QUEUE = "long"


def move_to_long(doctypes, key):
	saved = _saved(key)
	changed = False
	for webhook in frappe.get_all(
		"Webhook",
		filters={"webhook_doctype": ["in", list(doctypes)]},
		fields=["name", "background_jobs_queue"],
	):
		if webhook.background_jobs_queue == QUEUE:
			continue
		saved.setdefault(webhook.name, webhook.background_jobs_queue or "")
		frappe.db.set_value("Webhook", webhook.name, "background_jobs_queue", QUEUE, update_modified=False)
		changed = True

	if changed:
		frappe.db.set_global(key, json.dumps(saved))
		_clear_cache()
	return changed


def restore(key):
	saved = _saved(key)
	for name, queue in saved.items():
		if frappe.db.exists("Webhook", name):
			frappe.db.set_value("Webhook", name, "background_jobs_queue", queue or None, update_modified=False)

	if saved:
		frappe.db.set_global(key, None)
		_clear_cache()
	return bool(saved)


def _saved(key):
	return json.loads(frappe.db.get_global(key) or "{}")


def _clear_cache():
	# run_webhooks reads the webhook list, queue included, from this cache. Webhook.on_update
	# clears it, but set_value does not run on_update.
	frappe.cache.delete_value("webhooks")
