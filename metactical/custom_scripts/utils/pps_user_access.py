"""
W7 (optional): UserAccessSyncMessage — a PPS-side projection of
Warehouse User Permissions. Superseded by W1 (PPS reads permissions live
at sign-in via pps_api.authenticate) rather than depended on; this exists
in case a synced local projection is wanted instead of/alongside that.

Registered as a Jinja global (hooks.py `jinja.methods`) for native Webhook
records on "Warehouse User Permissions" (on_update/on_trash) and "User"
(on_update/on_trash) — same pattern as the rest of this integration, no
custom Python doc_events/publish code.
"""

import frappe

WAREHOUSE_PERMISSION_FIELDS = [
    "source_warehouse",
    "target_warehouse",
    "cycle_count_warehouse",
    "purchase_receipt_accepted_warehouse",
    "material_request_target_warehouse",
    "material_request_target_warehouse_purchase",
    "pps_source_warehouse",
    "pps_target_warehouse",
]


def get_user_access_sync_payload(user_id: str, deleted: bool = False) -> dict:
    """
    Full-mode UserAccessSyncMessage payload for one user.

    "Revocation must be explicit, never by omission... In full mode,
    absence is authoritative" — read together: `enabled`/`deleted` are
    always explicit flags (never inferred from a missing message), while
    within a full snapshot a warehouse simply not appearing in its list IS
    the revocation signal — no separate per-warehouse "access": "revoked"
    entries are needed here since every payload is a complete snapshot,
    not a delta.

    Queries the DB directly for the current `enabled` state and permission
    doc rather than trusting the triggering doc's own fields, since
    Webhook execution runs in a background job — by the time it renders,
    a since-deleted Warehouse User Permissions record correctly reads back
    as "not found", so on_trash naturally produces empty lists without
    needing special-casing.
    """
    permissions = {field: [] for field in WAREHOUSE_PERMISSION_FIELDS}

    if not deleted and frappe.db.exists("Warehouse User Permissions", user_id):
        doc = frappe.get_doc("Warehouse User Permissions", user_id)
        for field in WAREHOUSE_PERMISSION_FIELDS:
            warehouses = []
            for row in doc.get(field) or []:
                if row.warehouse and row.warehouse not in warehouses:
                    warehouses.append(row.warehouse)
            permissions[field] = warehouses

    enabled = False
    if not deleted:
        enabled = bool(frappe.db.get_value("User", user_id, "enabled"))

    return {
        "user_id": user_id,
        "sync_mode": "full",
        "enabled": enabled,
        "deleted": deleted,
        "warehouse_permissions": permissions,
    }
