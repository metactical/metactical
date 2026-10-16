"""
Section 7 backfill: publish one message per currently-active record, so
PPS's projections start populated instead of empty when it first comes
online. Scoped to Warehouse, Sales Order, Picklist Tote and Shipment
Parcel Template only — Item/Customer are deliberately excluded here
(272K+88K active records; that volume risks overwhelming the broker) and
BinStockMessage has no backfill since it was never built (skipped per an
earlier call on OQ-4).

Reuses the exact live Webhook templates built earlier (rendered directly
against each record, not via a real save), so the backfilled message
shape is guaranteed identical to what ongoing live updates will send, with
zero duplicated field-mapping logic. Each webhook's own `condition` is
honored too — a record that wouldn't trigger the live webhook is skipped
here as well, so the backfilled projection can't include records PPS
would never receive from a real update.
"""

import json

import frappe
from frappe.integrations.doctype.webhook.webhook import get_context

BACKFILL_WEBHOOKS = {
    "Warehouse": "PPS Warehouse Update",
    "Sales Order": "Sales order change",
    "Picklist Tote": "Picklist Tote",
    "Shipment Parcel Template": "Shipment Parcel Template",
}

# Keys in the rendered body that are connection config, not part of the
# message payload itself — split out before calling publish_to_rabbitmq.
_CONFIG_KEYS = ["server_ip", "exchange", "exchange_type", "routing_key", "queue_name", "username", "password"]


def _render_message(webhook, doc_dict) -> dict:
    body = frappe.render_template(webhook.webhook_json, get_context(doc_dict))
    return json.loads(body)


def _matches_condition(webhook, doc_dict) -> bool:
    if not webhook.condition:
        return True
    return bool(frappe.safe_eval(webhook.condition, eval_locals=get_context(doc_dict)))


def _active_record_names(doctype: str) -> list:
    if doctype == "Warehouse":
        return frappe.get_all(doctype, filters={"disabled": 0}, pluck="name")
    if doctype == "Sales Order":
        return frappe.get_all(doctype, filters={"docstatus": 1, "per_delivered": ["<", 100]}, pluck="name")
    if doctype == "Picklist Tote":
        return frappe.get_all(doctype, pluck="name")
    return frappe.get_all(doctype, pluck="name")


@frappe.whitelist()
def backfill_reference_data(doctypes=None, dry_run=True, limit=None):
    """
    doctypes: optional list (or JSON list, or single string) restricting
              to a subset of BACKFILL_WEBHOOKS's keys. Defaults to all of
              them.
    dry_run:  True (default) renders every message and counts them without
              publishing anything. Pass False to actually publish.
    limit:    optional cap per doctype, for a small test run before a full
              backfill.
    """
    frappe.only_for("System Manager")

    if isinstance(dry_run, str):
        dry_run = dry_run.lower() not in ("0", "false", "no")
    if isinstance(doctypes, str):
        doctypes = json.loads(doctypes) if doctypes.strip().startswith("[") else [doctypes]
    doctypes = doctypes or list(BACKFILL_WEBHOOKS.keys())
    if isinstance(limit, str):
        limit = int(limit)

    from metactical.custom_scripts.utils.rabbitmq_handler import publish_to_rabbitmq

    results = {}
    for doctype in doctypes:
        webhook_name = BACKFILL_WEBHOOKS.get(doctype)
        if not webhook_name or not frappe.db.exists("Webhook", webhook_name):
            results[doctype] = {"error": f"No backfill Webhook configured for {doctype}"}
            continue

        webhook = frappe.get_doc("Webhook", webhook_name)
        names = _active_record_names(doctype)
        if limit:
            names = names[:limit]

        count = 0
        skipped = 0
        failed = []
        for name in names:
            try:
                doc_dict = frappe.get_doc(doctype, name).as_dict(convert_dates_to_str=True)
                if not _matches_condition(webhook, doc_dict):
                    skipped += 1
                    continue
                message = _render_message(webhook, doc_dict)
                if not dry_run:
                    config = {key: message.pop(key) for key in _CONFIG_KEYS}
                    publish_to_rabbitmq(message=message, **config)
                count += 1
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"PPS Backfill Error: {doctype} {name}",
                )
                failed.append(name)

        results[doctype] = {
            "total_candidates": len(names),
            "skipped_by_condition": skipped,
            "published" if not dry_run else "would_publish": count,
            "failed": failed,
        }

    return {"dry_run": dry_run, "results": results}
