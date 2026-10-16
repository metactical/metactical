"""
W6: server-side computation backing the "Sales order new" Webhook's
NewOrderMessage template.

Registered as a Jinja global via hooks.py's `jinja.methods` (NOT called
through `frappe.call` from the template) — Webhook execution always runs
via `frappe.enqueue`, i.e. inside a background job with no HTTP request
context, and `frappe.call`'s `execute_cmd` path needs `frappe.local.request`
to check the HTTP method. A plain Jinja-global function has no such
dependency, so the template calls `get_order_warehouse_bin_config(doc.get("name"))`
directly.

Returns the deduplicated warehouses[]/bins[] for the order, plus
`config_version` — the max `modified` across all included config records,
taken from the records themselves rather than publish time.

Per OQ-3 (Bin.name isn't guaranteed stable across environments), bin `id`
is the natural key `{warehouse}::{item_code}` rather than `Bin.name` —
`lines[].bin_id` in the template uses the same composite so it always
joins against an entry in `bins[]`.
"""

import frappe


def _warehouse_site(warehouse_name: str) -> str:
    """`site` is the segment before the first '-' in the warehouse's base
    name, stripped of any trailing ` - {Company}` suffix."""
    base = warehouse_name.split(" - ")[0]
    return base.split("-")[0]


def _parse_bin_location(warehouse_name: str) -> dict:
    """
    Warehouse names are `SITE-ZONE-AISLE-SECTION-RACK-BIN`, optionally
    suffixed ` - {Company}`. A warehouse not matching that six-part shape
    is a bulk location; only its site prefix is meaningful.
    """
    base = warehouse_name.split(" - ")[0]
    parts = base.split("-")

    if len(parts) == 6:
        site, zone, aisle, section, rack, bin_no = parts
        return {
            "code": base,
            "site": site,
            "zone": zone,
            "aisle": aisle,
            "section": section,
            "rack": rack,
            "bin": bin_no,
            "is_bulk": False,
        }

    return {
        "code": base,
        "site": parts[0] if parts else base,
        "zone": None,
        "aisle": None,
        "section": None,
        "rack": None,
        "bin": None,
        "is_bulk": True,
    }


def get_order_warehouse_bin_config(sales_order: str) -> dict:
    so = frappe.get_doc("Sales Order", sales_order)

    warehouse_names = sorted({item.warehouse for item in so.items if item.warehouse})
    bin_keys = sorted({
        (item.item_code, item.warehouse) for item in so.items
        if item.item_code and item.warehouse
    })

    max_modified = None

    def _track_max(value):
        nonlocal max_modified
        if value and (max_modified is None or value > max_modified):
            max_modified = value

    warehouse_rows = {}
    warehouses = []
    for wh_name in warehouse_names:
        wh = frappe.db.get_value(
            "Warehouse", wh_name,
            ["warehouse_name", "parent_warehouse", "is_group", "disabled", "company", "modified"],
            as_dict=True,
        )
        if not wh:
            continue
        warehouse_rows[wh_name] = wh
        _track_max(wh.modified)
        warehouses.append({
            "id": wh_name,
            "warehouse_name": wh.warehouse_name,
            "parent_warehouse": wh.parent_warehouse,
            "is_group": bool(wh.is_group),
            "disabled": bool(wh.disabled),
            "company": wh.company,
            "site": _warehouse_site(wh_name),
            "modified": str(wh.modified) if wh.modified else None,
        })

    bins = []
    for item_code, warehouse in bin_keys:
        bin_modified = frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": warehouse}, "modified"
        )
        wh = warehouse_rows.get(warehouse)
        modified = bin_modified or (wh.modified if wh else None)
        _track_max(modified)

        location = _parse_bin_location(warehouse)
        bins.append({
            "id": f"{warehouse}::{item_code}",
            "item_code": item_code,
            "warehouse_id": warehouse,
            "code": location["code"],
            "site": location["site"],
            "zone": location["zone"],
            "aisle": location["aisle"],
            "section": location["section"],
            "rack": location["rack"],
            "bin": location["bin"],
            "is_bulk": location["is_bulk"],
            "disabled": bool(wh.disabled) if wh else False,
            "company": wh.company if wh else None,
            "modified": str(modified) if modified else None,
        })

    return {
        "warehouses": warehouses,
        "bins": bins,
        "config_version": str(max_modified) if max_modified else None,
    }
