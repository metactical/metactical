import base64
import random
import frappe
from frappe.utils import add_days, nowdate, flt
from metactical.custom_scripts.pick_list.pick_list import create_pick_list
from erpnext.stock.doctype.delivery_note.delivery_note import make_packing_slip
import json
from metactical.utils.shipping.shipping import get_rate
from concurrent.futures import ThreadPoolExecutor
import time

site = frappe.local.site

# Child-table fieldnames on "Warehouse User Permissions" that hold a list of
# permitted warehouses. Every key here is always returned by
# `get_warehouse_permissions`, even when empty, so PPS (which fails closed)
# can tell "no access" apart from "unrecognised contract".
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

def _get_random_instock_items(warehouse, count):
    """Return `count` random items that have actual_qty >= 1 in `warehouse`."""
    rows = frappe.db.sql("""
        SELECT b.item_code, b.actual_qty, i.standard_rate
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE b.warehouse = %(warehouse)s
          AND b.actual_qty >= 1
          AND i.disabled = 0
          AND i.is_stock_item = 1
        ORDER BY RAND()
        LIMIT %(count)s
    """, {"warehouse": warehouse, "count": count}, as_dict=True)
    return rows

@frappe.whitelist()
def create_sales_order(*args, **kwargs):
    """
    Create and submit a Sales Order using random in-stock items.

    Required: customer
    Optional: company, warehouse, item_count (default 2), delivery_date,
              shipping_address_name, taxes_and_charges, source
    """
    try:
        form_data = dict(frappe.form_dict)

        customer = form_data.get("customer")
  
        company = form_data.get("company") or frappe.db.get_single_value("Global Defaults", "default_company")
        warehouse = form_data.get("warehouse") or "R01-Gor-Active Stock - ICL"
        item_count = int(form_data.get("item_count") or 2)

        stock_items = _get_random_instock_items(warehouse, item_count)
        if not stock_items:
            return {"status": "error", "message": f"No in-stock items found in warehouse {warehouse}."}

        company_currency = frappe.get_cached_value("Company", company, "default_currency") or "CAD"

        so = frappe.new_doc("Sales Order")
        so.company = company
        so.customer = "CS-25-05663"
        so.currency = company_currency
        so.set("company_currency", company_currency)
        so.conversion_rate = 1
        so.source = "Store - Camo - Edmonds"
        so.shipping_address_name = "CS-25-05663-Billing"
        so.customer_address = "CS-25-05663-Billing"
        so.taxes_and_charges = "Alberta - ICL"
        so.exchange_rate = 1
        so.transaction_date = nowdate()
        so.delivery_date = form_data.get("delivery_date") or add_days(nowdate(), 7)

        if form_data.get("taxes_and_charges"):
            so.taxes_and_charges = form_data.get("taxes_and_charges")
        if form_data.get("source"):
            so.source = form_data.get("source")

        for stock_item in stock_items:
            so.append("items", {
                "item_code": stock_item.item_code,
                "warehouse": warehouse,
                "qty": 1,
                "rate": stock_item.standard_rate or 0,
            })

        so.set_missing_values()
        so.insert(ignore_permissions=True)
        so.submit()
        frappe.db.commit()

        packing_slips = []
        for idx, item in enumerate(so.items, start=1):
            packing_slips.append({
                "parcel_template": f"BOX 1",
                "dimensions": {"height": 1, "width": 2, "length": 3},
                "weight": 1,
                "items": [{
                    "item_code": item.item_code,
                    "quantity": int(item.qty),
                    "sales_order_item": item.name,
                }],
            })

        return {
            "order_id": so.name,
            "packing_slips": packing_slips,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error creating sales order")
        return {
            "status": "error",
            "message": str(e),
        }


@frappe.whitelist()
def pack_order_complete(*args, **kwargs):
    """
    Packs an order using nested packing_slips payload structure: creates
    the Pick List, Delivery Note, Packing Slips and Shipment as one unit.

    Atomicity: any failure partway — including an exception nobody
    anticipated — unwinds every document this call created so far via
    `_clear_created_documents`, rather than leaving an orphaned Delivery
    Note with no Packing Slip. `pick_list_name`, `dn` and `shipment_name`
    are tracked from the moment each becomes known so the outer `except`
    can always reach them.

    Attribution: every document this call creates gets a Comment
    ("Created through PPS by {user}") via `_attribute_pps_write`, using
    `frappe.session.user` — this endpoint isn't `allow_guest`, so it only
    runs in a real signed-in PPS user's session (see `authenticate`).
    """
    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Pack Order")
    order_id = form_data.get("order_id")

    pick_list_name = ""
    dn = None
    shipment_name = None
    packing_slip_docs = []

    try:
        # --- Validate input ---
        if not order_id:
            return _error("Order ID is required.")

        packing_slips = form_data.get("packing_slips") or []
        if not packing_slips:
            return _error("Packing slips are required.")

        validation_errors = validate_packing_slips(packing_slips, order_id)
        if validation_errors:
            return _error("; ".join(validation_errors))

        # --- Idempotency: a retried/duplicate call for an order that's
        # already been packed must not create a second Pick List/Delivery
        # Note/Shipment chain. Recognize "already packed" rather than
        # diffing the retried payload, and hand back the existing chain.
        already_packed = _find_existing_pack(order_id)
        if already_packed:
            return already_packed

        # --- Create pick list ---
        items = flatten_packing_slip_items(packing_slips)
        pick_list_result = create_pick_list_for_order(order_id, items)
        pick_list_name = pick_list_result.get("pick_list", "")

        if not pick_list_result.get("success"):
            return _fail_with_log(log, pick_list_result.get("error"))

        pick_list = frappe.get_doc("Pick List", pick_list_name)
        frappe.db.set_value("PPS API Log", log, "pick_list", pick_list.name)
        _attribute_pps_write("Pick List", pick_list.name)

        # --- Create packing slips + delivery note ---
        packing_slip_docs, dn = create_packing_slips(pick_list, packing_slips)
        expected_slip_count = len(packing_slips)
        if len(packing_slip_docs) != expected_slip_count:
            _clear_created_documents(packing_slip_docs, pick_list_name, dn, shipment_name)
            return _fail_with_log(log, "Failed to create packing slips.")

        if dn:
            _attribute_pps_write("Delivery Note", dn)
        for slip_name in packing_slip_docs:
            _attribute_pps_write("Packing Slip", slip_name)

        frappe.db.set_value("PPS API Log", log, {
            "delivery_note": dn,
            "packing_slips": ", ".join(str(s) for s in packing_slip_docs),
        })

        # --- Resolve shipment ---
        shipment_name = _get_shipment_for_delivery_note(dn)
        if not shipment_name:
            _clear_created_documents(packing_slip_docs, pick_list_name, dn, shipment_name)
            return _fail_with_log(log, f"No shipment found for Delivery Note {dn}")

        _attribute_pps_write("Shipment", shipment_name)

        # Trigger parcel auto-population
        frappe.get_doc("Shipment", shipment_name).save(ignore_permissions=True)
        frappe.db.commit()

        # --- Fetch shipping rates concurrently ---
        rates = _fetch_rates_concurrently(shipment_name)
        response = {
            "status": "success",
            "message": f"Order {order_id} packed successfully.",
            "pick_list": pick_list.name,
            "delivery_note": dn,
            "shipment": shipment_name,
            "canada_post": rates.get("Canada Post"),
            "purolator": rates.get("Purolator"),
            "packing_slips": packing_slip_docs,
        }

        frappe.db.set_value("PPS API Log", log, "response", frappe.as_json(response))
        frappe.db.commit()

        return response

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error packing order {order_id}")
        _clear_created_documents(packing_slip_docs, pick_list_name, dn, shipment_name)
        if log:
            frappe.db.set_value("PPS API Log", log, "error", frappe.as_json(_error(str(e))))
        frappe.db.commit()
        return _error(str(e))

@frappe.whitelist()
def create_label(*args, **kwargs):
    """
    Submit a shipment and create a shipping label using the selected rate
    option(s) returned from `pack_order_complete` (the `canada_post` / `purolator`
    rate groups).

    Required params:
        shipment    - Shipment docname (e.g. "SHIPMENT-05598")
        provider    - "Canada Post" or "Purolator"
        selections  - dict keyed by parcel name (the "name" field of each
                      rate group from pack_order_complete) -> the chosen rate item,
                      e.g.:
                      {
                        "drugqpvo7h": {
                            "carrier_service": "PurolatorExpress",
                            "service_name": "PurolatorExpress",
                            "shipment_amount": 115.57
                        }
                      }
                      For a single-parcel shipment, a flat dict with one
                      entry is fine too.

    Optional params:
        submit_shipment  - submit the Shipment doc before creating the
                            label if it is still in draft (default true)
    """
    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Create Label")

    shipment = form_data.get("shipment")
    provider = form_data.get("provider")
    selections = form_data.get("selections")
    submit_shipment = form_data.get("submit_shipment", True)
    if isinstance(submit_shipment, str):
        submit_shipment = submit_shipment.lower() not in ("0", "false", "no")

    try:
        if not shipment:
            return _fail_with_log(log, "shipment is required.")
        if not frappe.db.exists("Shipment", shipment):
            return _fail_with_log(log, f"Shipment {shipment} does not exist.")
        if not provider:
            return _fail_with_log(log, "provider is required.")
        if provider not in ("Canada Post", "Purolator"):
            return _fail_with_log(log, f"Unsupported provider: {provider}. Use 'Canada Post' or 'Purolator'.")
        if not selections:
            return _fail_with_log(log, "selections is required (chosen rate per parcel).")

        if isinstance(selections, str):
            try:
                selections = json.loads(selections)
            except ValueError:
                return _fail_with_log(log, "selections must be valid JSON.")

        carrier_service = {}
        service_name = {}
        shipment_amount = 0.0

        for parcel_name, choice in selections.items():
            carrier_service[parcel_name] = choice.get("carrier_service")
            service_name[parcel_name] = choice.get("service_name")
            shipment_amount += float(choice.get("shipment_amount") or 0)

        shipment_doc = frappe.get_doc("Shipment", shipment)

        # --- If every selected parcel already has a label, reuse it instead of
        # creating a new one (which would call the carrier API again and, for
        # Purolator, generate and bill a brand new label). ---
        existing_labels_by_row = {}
        for row in shipment_doc.shipments:
            if row.row_id and row.label:
                existing_labels_by_row.setdefault(row.row_id, []).append(row.label)

        selected_parcels = list(selections.keys())
        if selected_parcels and all(existing_labels_by_row.get(parcel_name) for parcel_name in selected_parcels):
            existing_label_files = [
                label for parcel_name in selected_parcels for label in existing_labels_by_row[parcel_name]
            ]
            printing_disabled = frappe.db.get_single_value("Shipment Settings", "disable_automatic_print")
            response = {
                "status": "success",
                "shipment": shipment,
                "provider": provider,
                "label_files": _encode_files_as_base64(existing_label_files),
                "printing_disabled": printing_disabled,
                "message": f"Labels already exist for shipment {shipment} using {provider}.",
            }
            frappe.db.commit()
            return response

        # --- Submit the shipment first, if required ---
        if submit_shipment and shipment_doc.docstatus == 0:
            shipment_doc.submit()
            frappe.db.commit()

        from metactical.utils.shipping.shipping import create_shipping

        result = create_shipping(
            name=shipment,
            provider=provider,
            carrier_service=carrier_service,
            service_name=service_name,
            shipment_amount=shipment_amount,
        )

        if not result or not result.get("labels"):
            return _fail_with_log(log, f"No labels returned from {provider}.")

        response = {
            "status": "success",
            "shipment": shipment,
            "provider": provider,
            "label_files": _encode_files_as_base64(result.get("labels")),
            "printing_disabled": result.get("printing_disabled"),
            "message": f"Labels created successfully for shipment {shipment} using {provider}.",
        }

        # frappe.db.set_value("PPS API Log", log, "response", frappe.as_json(response))
        frappe.db.commit()

        return response

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error creating label for shipment {shipment}")
        if log:
            frappe.db.set_value("PPS API Log", log, "error", frappe.as_json(_error(str(e))))
        frappe.db.commit()
        return _error(str(e))


@frappe.whitelist()
def receive_purchase_order(*args, **kwargs):
    """
    Create and submit a Purchase Receipt directly from a Purchase Order in
    one call, using ERPNext's own `make_purchase_receipt` mapper (maps
    every still-outstanding line at its full outstanding qty).

    Required: purchase_order.
    Optional: items: [{item_code, qty}] — receive only these item(s), each
    capped at its own outstanding qty, instead of receiving everything
    outstanding on the PO.

    No Supplier Order Confirmation / Inbound Shipment involved: PO ->
    outstanding received_qty is core ERPNext bookkeeping, updated on PR
    submit regardless of how the PR was built. CustomPurchaseReceipt still
    enforces accepted-warehouse permissions and requires every item to
    have a barcode before submit; those errors surface here verbatim.
    """
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Receive Purchase Order")
    purchase_order = form_data.get("purchase_order")
    items = form_data.get("items")

    pr_name = None

    try:
        if not purchase_order:
            return _error("purchase_order is required.")
        if not frappe.db.exists("Purchase Order", purchase_order):
            return _error(f"Purchase Order {purchase_order} does not exist.")

        pr = make_purchase_receipt(purchase_order)
        if not pr.items:
            return _error(f"No outstanding items to receive on Purchase Order {purchase_order}.")

        if items:
            requested = {item.get("item_code"): item.get("qty") for item in items}
            kept_rows = []
            for row in pr.items:
                if row.item_code not in requested:
                    continue
                qty = requested[row.item_code]
                if qty is not None:
                    row.qty = min(flt(qty), flt(row.qty))
                    row.stock_qty = row.qty * flt(row.conversion_factor or 1)
                kept_rows.append(row)
            if not kept_rows:
                return _error("None of the requested items have outstanding qty on this Purchase Order.")
            pr.items = kept_rows

        pr.insert()
        pr_name = pr.name
        pr.submit()
        frappe.db.commit()

        _attribute_pps_write("Purchase Receipt", pr.name)

        response = {
            "status": "success",
            "message": f"Purchase Receipt {pr.name} created from Purchase Order {purchase_order}.",
            "purchase_receipt": pr.name,
            "items": [
                {"item_code": item.item_code, "qty": item.qty, "warehouse": item.warehouse}
                for item in pr.items
            ],
        }
        frappe.db.set_value("PPS API Log", log, "response", frappe.as_json(response))
        frappe.db.commit()

        return response

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error receiving purchase order {purchase_order}")
        if pr_name and frappe.db.exists("Purchase Receipt", pr_name):
            pr_doc = frappe.get_doc("Purchase Receipt", pr_name)
            if pr_doc.docstatus == 1:
                pr_doc.cancel()
            if frappe.db.exists("Purchase Receipt", pr_name):
                pr_doc.delete()
            frappe.db.commit()
        return _fail_with_log(log, str(e))


@frappe.whitelist()
def reconcile_count(*args, **kwargs):
    """
    Create and submit a Stock Reconciliation from a cycle count in one call.

    Required: warehouse, items: [{item_code, qty, valuation_rate?}],
    reason_for_adjustment (mandatory custom field on this instance's Stock
    Reconciliation — ais_reason_for_adjustment).
    valuation_rate is optional per row — ERPNext's own Stock Reconciliation
    validate() already looks it up (get_stock_balance, then Item.valuation_rate
    as a fallback) when a row's valuation_rate is left blank, so no separate
    valuation-lookup call is needed before submitting.
    """
    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Reconcile Count")
    warehouse = form_data.get("warehouse")
    items = form_data.get("items") or []
    company = form_data.get("company") or frappe.db.get_single_value("Global Defaults", "default_company")
    reason_for_adjustment = form_data.get("reason_for_adjustment")

    sr_name = None

    try:
        if not warehouse:
            return _error("warehouse is required.")
        if not items:
            return _error("items is required.")
        if not reason_for_adjustment:
            return _error("reason_for_adjustment is required.")
        for item in items:
            if not item.get("item_code") or item.get("qty") is None:
                return _error("Each item requires item_code and qty.")

        sr = frappe.new_doc("Stock Reconciliation")
        sr.company = company
        sr.purpose = "Stock Reconciliation"
        sr.set_posting_time = 1
        sr.ais_reason_for_adjustment = reason_for_adjustment
        for item in items:
            row = {
                "item_code": item.get("item_code"),
                "warehouse": warehouse,
                "qty": item.get("qty"),
            }
            if item.get("valuation_rate") is not None:
                row["valuation_rate"] = item.get("valuation_rate")
            sr.append("items", row)

        sr.insert()
        sr_name = sr.name
        sr.submit()
        frappe.db.commit()

        _attribute_pps_write("Stock Reconciliation", sr.name)

        response = {
            "status": "success",
            "message": f"Stock Reconciliation {sr.name} submitted for {warehouse}.",
            "stock_reconciliation": sr.name,
            "items": [
                {"item_code": row.item_code, "qty": row.qty, "valuation_rate": row.valuation_rate}
                for row in sr.items
            ],
        }
        frappe.db.set_value("PPS API Log", log, "response", frappe.as_json(response))
        frappe.db.commit()

        return response

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error reconciling count for {warehouse}")
        if sr_name and frappe.db.exists("Stock Reconciliation", sr_name):
            sr_doc = frappe.get_doc("Stock Reconciliation", sr_name)
            if sr_doc.docstatus == 1:
                sr_doc.cancel()
            if frappe.db.exists("Stock Reconciliation", sr_name):
                sr_doc.delete()
            frappe.db.commit()
        return _fail_with_log(log, str(e))


@frappe.whitelist()
def reopen_pick_list(*args, **kwargs):
    """
    Reopen a Pick List for re-picking in one call: clears `ais_picked_by`
    (the field the picking board actually gates on — see the existing
    `close_pick_list`/`clear_totes_picklist` in picklist_page.py, which this
    generalizes) and, for every Picklist Tote holding items from this pick
    list, removes just this pick list's rows from `tote_items` (leaving
    any other pick list's rows on a shared tote intact), clearing `used_by`
    if the tote is left empty and `current_delivery_note` if that note was
    against this same pick list.
    """
    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Reopen Pick List")
    pick_list_name = form_data.get("pick_list")

    try:
        if not pick_list_name:
            return _error("pick_list is required.")
        if not frappe.db.exists("Pick List", pick_list_name):
            return _error(f"Pick List {pick_list_name} does not exist.")

        frappe.db.set_value("Pick List", pick_list_name, "ais_picked_by", "")

        dn_names = {
            row.parent for row in frappe.db.get_all(
                "Delivery Note Item",
                filters={"against_pick_list": pick_list_name},
                fields=["parent"],
            )
        }

        tote_names = {
            row.parent for row in frappe.db.get_all(
                "Picklist Tote Item",
                filters={"pick_list": pick_list_name},
                fields=["parent"],
            )
        }

        cleared_totes = []
        for tote_name in tote_names:
            tote = frappe.get_doc("Picklist Tote", tote_name)
            tote.tote_items = [row for row in tote.tote_items if row.pick_list != pick_list_name]
            if not tote.tote_items:
                tote.used_by = ""
            if tote.current_delivery_note and tote.current_delivery_note in dn_names:
                tote.current_delivery_note = ""
            tote.save(ignore_permissions=True)
            cleared_totes.append(tote.name)

        frappe.db.commit()
        _attribute_pps_write("Pick List", pick_list_name, action="Reopened")

        response = {
            "status": "success",
            "message": f"Pick List {pick_list_name} reopened for re-picking.",
            "pick_list": pick_list_name,
            "totes_cleared": cleared_totes,
        }
        frappe.db.set_value("PPS API Log", log, "response", frappe.as_json(response))
        frappe.db.commit()

        return response

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error reopening pick list {pick_list_name}")
        return _fail_with_log(log, str(e))


@frappe.whitelist(allow_guest=True)
def authenticate(*args, **kwargs):
    """
    Single-call authenticate + warehouse permissions for PPS.

    Required: usr, pwd (a full ERPNext password, not a PIN).

    Credential check goes through Frappe's own `LoginManager.authenticate` —
    the same code path `POST /api/method/login` uses, so password policy,
    the disabled-user check and login-attempt lockout tracking all apply
    natively. It deliberately does not call `post_login`/`make_session`, so
    no browser-visible session is created; PPS mints its own bearer token
    from this response.

    Never logs the raw form data (it contains the password), unlike the
    other PPS API methods here which log via `create_log`.
    """
    form_data = frappe.local.form_dict
    usr = form_data.get("usr")
    pwd = form_data.get("pwd")

    if not usr or not pwd:
        return {"authenticated": False, "reason": "invalid_credentials"}

    from frappe.auth import LoginManager

    login_manager = LoginManager.__new__(LoginManager)
    try:
        login_manager.authenticate(user=usr, pwd=pwd)
    except frappe.AuthenticationError:
        reason = "user_disabled" if frappe.local.response.get("message") == "User disabled or missing" else "invalid_credentials"
        return {"authenticated": False, "reason": reason}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PPS Authenticate Error")
        return {"authenticated": False, "reason": "invalid_credentials"}

    user = login_manager.user

    return {
        "authenticated": True,
        "user_id": user,
        "full_name": frappe.db.get_value("User", user, "full_name"),
        "enabled": True,
        "roles": frappe.get_roles(user),
        "warehouse_permissions": _get_warehouse_permissions(user),
    }


def _get_warehouse_permissions(user):
    """
    Full document read of `Warehouse User Permissions` (child tables only
    come back on a full read, never on a list query) — every key is always
    present, deduplicated, so PPS's fail-closed client never sees a missing
    contract as "no access".
    """
    permissions = {field: [] for field in WAREHOUSE_PERMISSION_FIELDS}

    if not frappe.db.exists("Warehouse User Permissions", user):
        return permissions

    doc = frappe.get_doc("Warehouse User Permissions", user)
    for field in WAREHOUSE_PERMISSION_FIELDS:
        warehouses = []
        for row in doc.get(field) or []:
            if row.warehouse and row.warehouse not in warehouses:
                warehouses.append(row.warehouse)
        permissions[field] = warehouses

    return permissions


@frappe.whitelist()
def search_inventory(*args, **kwargs):
    """
    Single-call inventory search: resolves a scanned barcode, an exact item
    code, or a free-text description, and returns per-warehouse bin
    quantities for each match — one call, no second round trip.

    Request: q, site, warehouse, in_stock_only, include_disabled, limit, cursor.

    Exact match (barcode or item code) always wins over the fuzzy match,
    and is only returned on the first page (no cursor) — everything after
    that is keyset-paginated fuzzy results, ordered by item_code, using
    item_code as the cursor. The fuzzy match itself is a prefix match:
    item_code / item_name / description / barcode must each START WITH
    `q`, not merely contain it anywhere.
    """
    form_data = frappe.local.form_dict
    q = (form_data.get("q") or "").strip()
    site_filter = form_data.get("site")
    warehouse_filter = form_data.get("warehouse")
    in_stock_only = _as_bool(form_data.get("in_stock_only"))
    include_disabled = _as_bool(form_data.get("include_disabled"))
    limit = min(int(form_data.get("limit") or 25), 100)
    cursor_item_code = _decode_cursor(form_data.get("cursor"))

    if not q:
        return {"results": [], "next_cursor": None, "has_more": False, "stock_as_of": _utc_now_iso()}

    exact_item_codes = [] if cursor_item_code else _resolve_exact_matches(q, include_disabled)

    remaining = max(limit - len(exact_item_codes), 0)
    fuzzy_item_codes = []
    has_more = False
    if remaining:
        # fetch one extra row to know whether another page follows. site/warehouse/
        # in_stock_only are applied inside the query itself (not after truncating to
        # `limit`) — otherwise a candidate consumed by the limit but filtered out
        # downstream could leave a page empty despite matches existing further on.
        candidates = _resolve_fuzzy_matches(
            q, include_disabled, exclude=exact_item_codes, after=cursor_item_code, limit=remaining + 1,
            site_filter=site_filter, warehouse_filter=warehouse_filter, in_stock_only=in_stock_only,
        )
        has_more = len(candidates) > remaining
        fuzzy_item_codes = candidates[:remaining]

    ordered_item_codes = exact_item_codes + fuzzy_item_codes
    results = _load_items_with_locations(
        ordered_item_codes, site_filter, warehouse_filter, in_stock_only
    )

    next_cursor = _encode_cursor(fuzzy_item_codes[-1]) if has_more and fuzzy_item_codes else None

    return {
        "results": results,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
        "stock_as_of": _utc_now_iso(),
    }


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _encode_cursor(item_code: str) -> str:
    payload = json.dumps({"i": item_code}, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def _decode_cursor(cursor):
    if not cursor:
        return None
    try:
        payload = json.loads(base64.b64decode(cursor))
        return payload.get("i")
    except Exception:
        return None


def _resolve_exact_matches(q: str, include_disabled: bool) -> list:
    """Barcode exact match first (a scan must never be beaten by a
    substring hit), then an exact item-code match, deduplicated."""
    disabled_clause = "" if include_disabled else "AND i.disabled = 0"

    barcode_rows = frappe.db.sql(f"""
        SELECT DISTINCT i.name
        FROM `tabItem Barcode` bc
        JOIN `tabItem` i ON i.name = bc.parent
        WHERE bc.barcode = %(q)s
        {disabled_clause}
    """, {"q": q}, as_dict=True)

    item_code_rows = frappe.db.sql(f"""
        SELECT i.name
        FROM `tabItem` i
        WHERE i.name = %(q)s
        {disabled_clause}
    """, {"q": q}, as_dict=True)

    item_codes = []
    for row in barcode_rows + item_code_rows:
        if row.name not in item_codes:
            item_codes.append(row.name)

    return item_codes


def _resolve_fuzzy_matches(
    q: str, include_disabled: bool, exclude: list, after, limit: int,
    site_filter=None, warehouse_filter=None, in_stock_only: bool = False,
) -> list:
    """Prefix match — item_code, item_name, description and barcode must
    each START WITH `q`, not merely contain it anywhere.

    site/warehouse/in_stock_only are applied here, inside the query, rather
    than after the caller has already truncated the candidate list to
    `limit` — otherwise a candidate that consumes the limit but gets
    filtered out downstream can leave a page empty even though matches
    exist further down the alphabet.
    """
    disabled_clause = "" if include_disabled else "AND i.disabled = 0"
    exclude_clause = ""
    params = {"term": f"{q}%", "limit": limit}

    if exclude:
        exclude_clause = "AND i.name NOT IN %(exclude)s"
        params["exclude"] = tuple(exclude)

    after_clause = ""
    if after:
        after_clause = "AND i.name > %(after)s"
        params["after"] = after

    bin_join = ""
    bin_conditions = []
    if site_filter or warehouse_filter or in_stock_only:
        bin_join = "JOIN `tabBin` b ON b.item_code = i.name"
        if warehouse_filter:
            bin_conditions.append("b.warehouse = %(warehouse_filter)s")
            params["warehouse_filter"] = warehouse_filter
        elif site_filter:
            # the dash is part of the pattern so "R01-%" can't accidentally
            # match a warehouse whose site code merely starts with "R01"
            # (e.g. a hypothetical "R010-...")
            bin_conditions.append("b.warehouse LIKE %(site_pattern)s")
            params["site_pattern"] = f"{site_filter}-%"
        if in_stock_only:
            bin_conditions.append("b.actual_qty > 0")
    bin_where = ("AND " + " AND ".join(bin_conditions)) if bin_conditions else ""

    rows = frappe.db.sql(f"""
        SELECT DISTINCT i.name
        FROM `tabItem` i
        LEFT JOIN `tabItem Barcode` bc ON bc.parent = i.name
        {bin_join}
        WHERE (
            i.name LIKE %(term)s
            OR i.item_name LIKE %(term)s
            OR i.description LIKE %(term)s
            OR bc.barcode LIKE %(term)s
        )
        {disabled_clause}
        {exclude_clause}
        {after_clause}
        {bin_where}
        ORDER BY i.name ASC
        LIMIT %(limit)s
    """, params, as_dict=True)

    return [row.name for row in rows]


def _load_items_with_locations(item_codes: list, site_filter, warehouse_filter, in_stock_only: bool) -> list:
    if not item_codes:
        return []

    items_by_code = {
        row.name: row
        for row in frappe.db.get_all(
            "Item",
            filters={"name": ["in", item_codes]},
            fields=["name", "item_name", "item_group", "stock_uom", "disabled"],
        )
    }

    barcodes_by_item = {}
    for row in frappe.db.get_all(
        "Item Barcode",
        filters={"parent": ["in", item_codes]},
        fields=["parent", "barcode"],
    ):
        barcodes_by_item.setdefault(row.parent, []).append(row.barcode)

    bin_filters = {"item_code": ["in", item_codes]}
    if warehouse_filter:
        bin_filters["warehouse"] = warehouse_filter

    locations_by_item = {}
    for row in frappe.db.get_all(
        "Bin",
        filters=bin_filters,
        fields=["item_code", "warehouse", "actual_qty", "reserved_qty"],
    ):
        bin_site = _warehouse_site(row.warehouse)
        if site_filter and bin_site != site_filter:
            continue

        actual_qty = row.actual_qty or 0.0
        reserved_qty = row.reserved_qty or 0.0
        if in_stock_only and actual_qty <= 0:
            continue

        locations_by_item.setdefault(row.item_code, []).append({
            "warehouse": row.warehouse,
            "site": bin_site,
            "actual_qty": actual_qty,
            "reserved_qty": reserved_qty,
            "available_qty": actual_qty - reserved_qty,
        })

    results = []
    for item_code in item_codes:
        item = items_by_code.get(item_code)
        if not item:
            continue

        locations = locations_by_item.get(item_code, [])
        if in_stock_only and not locations:
            continue

        results.append({
            "item_code": item.name,
            "item_name": item.item_name,
            "item_group": item.item_group,
            "stock_uom": item.stock_uom,
            "barcodes": barcodes_by_item.get(item_code, []),
            "disabled": bool(item.disabled),
            "locations": locations,
        })

    return results


def _warehouse_site(warehouse_name: str) -> str:
    """`site` is the segment before the first '-' in the warehouse's base
    name, stripped of any trailing ` - {Company}` suffix."""
    base = warehouse_name.split(" - ")[0]
    return base.split("-")[0]


def _clear_created_documents(packing_slip_docs, pick_list_name, delivery_note, shipment_name=None):
    """
    Roll back everything `pack_order_complete` may have created, in dependency
    order. Every step is existence-guarded rather than assumed present:
    cancelling the Pick List cascades (via `CustomPickList.on_cancel`) to
    delete any still-draft Delivery Note/Shipment tied to it, so by the
    time we get to the explicit Shipment/Delivery Note steps below they
    may already be gone — that's expected, not an error.
    """
    try:
        # Cancel and delete packing slips first — Frappe won't let you
        # cancel/delete a Pick List or Delivery Note that a submitted
        # Packing Slip still links to.
        for slip_name in packing_slip_docs or []:
            if not frappe.db.exists("Packing Slip", slip_name):
                continue
            slip = frappe.get_doc("Packing Slip", slip_name)
            if slip.docstatus == 1:
                slip.cancel()
            if frappe.db.exists("Packing Slip", slip_name):
                frappe.get_doc("Packing Slip", slip_name).delete()

        # Cancel and delete the shipment before the pick list, in case the
        # pick list's own cancel cascade doesn't reach it (e.g. it was
        # already submitted, or the pick list is gone/absent).
        if shipment_name and frappe.db.exists("Shipment", shipment_name):
            shipment = frappe.get_doc("Shipment", shipment_name)
            if shipment.docstatus == 1:
                shipment.cancel()
            if frappe.db.exists("Shipment", shipment_name):
                frappe.get_doc("Shipment", shipment_name).delete()

        # Cancel and delete the pick list — this cascades to delete any
        # still-draft Shipment/Delivery Note tied to it.
        if pick_list_name and frappe.db.exists("Pick List", pick_list_name):
            pick_list = frappe.get_doc("Pick List", pick_list_name)
            if pick_list.docstatus == 1:
                pick_list.cancel()
            if frappe.db.exists("Pick List", pick_list_name):
                pick_list.delete()

        # Cancel and delete the delivery note, if the cascade above
        # didn't already remove it.
        if delivery_note and frappe.db.exists("Delivery Note", delivery_note):
            dn = frappe.get_doc("Delivery Note", delivery_note)
            if dn.docstatus == 1:
                dn.cancel()
            if frappe.db.exists("Delivery Note", delivery_note):
                dn.delete()

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="Error clearing created documents")
        frappe.db.rollback()


def _attribute_pps_write(doctype: str, docname: str, action: str = "Created"):
    """
    W4: stamp a Comment ("{action} through PPS by {user}") on every document
    a PPS write method creates or mutates. Must be a Comment, never the
    `remarks` field — a caller-supplied remark would silently overwrite it.
    A failed comment must never roll back the real write, so this only
    ever logs.
    """
    try:
        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Comment",
            "reference_doctype": doctype,
            "reference_name": docname,
            "content": f"{action} through PPS by {frappe.session.user}",
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"PPS Attribution Error for {doctype} {docname}",
        )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(message: str) -> dict:
    return {"status": "error", "message": message}

def _fail_with_log(log, message: str) -> dict:
    if log:
        frappe.db.set_value("PPS API Log", log, "error", json.dumps(_error(message)))
        frappe.db.commit()
    return _error(message)


def _encode_files_as_base64(file_urls: list, dpi: int = 150) -> list:
    """
    Render each label PDF (by its site `file_url`) to PNG image(s) and
    return them base64-encoded, one entry per page, so the frontend
    (JS/Vue) can decode and display them directly (e.g. as an
    `<img :src="data_uri">`) without needing a PDF viewer/library or an
    extra authenticated request to fetch the file.
    """
    import fitz  # PyMuPDF

    encoded_files = []
    for file_url in file_urls or []:
        try:
            file_path = frappe.get_site_path(file_url.lstrip("/"))
            base_name = file_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]

            pdf = fitz.open(file_path)
            zoom = dpi / 72
            matrix = fitz.Matrix(zoom, zoom)
            for page_number, page in enumerate(pdf, start=1):
                pixmap = page.get_pixmap(matrix=matrix)
                encoded = base64.b64encode(pixmap.tobytes("png")).decode("utf-8")
                encoded_files.append({
                    "file_name": f"{base_name}_page{page_number}.png",
                    "file_url": file_url,
                    "page": page_number,
                    "content_type": "image/png",
                    "base64": encoded,
                    "data_uri": f"data:image/png;base64,{encoded}",
                })
            pdf.close()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Error encoding label file {file_url}")

    return encoded_files

def _find_existing_pack(order_id: str) -> dict | None:
    """
    Idempotency guard for `pack_order_complete`: if this Sales Order
    already has a submitted Pick List with a resulting Delivery Note and
    Shipment, return that existing chain's response shape instead of
    letting a retried/duplicate call create a second one.
    """
    row = frappe.db.sql("""
        SELECT DISTINCT pli.parent AS pick_list, dni.parent AS delivery_note
        FROM `tabPick List Item` pli
        JOIN `tabPick List` pl ON pl.name = pli.parent
        JOIN `tabDelivery Note Item` dni ON dni.against_pick_list = pl.name
        WHERE pli.sales_order = %(order_id)s AND pl.docstatus = 1
        LIMIT 1
    """, {"order_id": order_id}, as_dict=True)

    if not row:
        return None

    pick_list_name = row[0].pick_list
    dn = row[0].delivery_note
    shipment_name = _get_shipment_for_delivery_note(dn)
    if not shipment_name:
        return None

    packing_slip_docs = [
        r.name for r in frappe.db.get_all("Packing Slip", filters={"delivery_note": dn, "docstatus": 1}, fields=["name"])
    ]

    rates = _fetch_rates_concurrently(shipment_name)
    return {
        "status": "success",
        "message": f"Order {order_id} already packed.",
        "pick_list": pick_list_name,
        "delivery_note": dn,
        "shipment": shipment_name,
        "canada_post": rates.get("Canada Post"),
        "purolator": rates.get("Purolator"),
        "packing_slips": packing_slip_docs,
    }


def _get_shipment_for_delivery_note(dn: str) -> str | None:
    rows = frappe.db.sql(
        """
        SELECT parent
        FROM `tabShipment Delivery Note`
        WHERE delivery_note = %s
        LIMIT 1
        """,
        (dn,),
        as_dict=True,
    )
    return rows[0]["parent"] if rows else None


def _fetch_rates_concurrently(shipment_name: str) -> dict:
    providers = ["Canada Post", "Purolator"]
    results = {}

    def get_rate_threadsafe(provider):
        frappe.init(site=site)
        frappe.connect()
        try:
            return get_rate(name=shipment_name, provider=provider)
        finally:
            frappe.destroy()

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {p: executor.submit(get_rate_threadsafe, p) for p in providers}
        for provider, future in futures.items():
            try:
                results[provider] = future.result()
            except Exception:
                frappe.log_error(
                    title=f"{provider} Rate Error",
                    message=frappe.get_traceback(),
                )
                results[provider] = None

    return results

def flatten_packing_slip_items(packing_slips):
    """
    Extract all items from packing slips into a flat list.
    """

    items = []
    for slip in packing_slips:
        for item in slip.get("items", []):
            items.append(item)

    return items


def validate_packing_slips(packing_slips, order_id):
    """
    Validate packing slip payload.
    """

    errors = []
    for index, slip in enumerate(packing_slips, start=1):
        items = slip.get("items") or []
        if not items:
            errors.append(
                f"Packing slip {index} has no items."
            )
            continue

        for item in items:

            item_code = item.get("item_code")
            quantity = item.get("quantity")
            sales_order_item = item.get("sales_order_item")

            if not sales_order_item:
                errors.append(
                    f"Missing sales_order_item in packing slip {index}."
                )
                continue

            if not quantity or quantity <= 0:
                errors.append(
                    f"Invalid quantity for item {sales_order_item}."
                )
                continue

            so_item = frappe.db.get_value(
                "Sales Order Item",
                {
                    "name": sales_order_item,
                    "parent": order_id
                },
                ["item_code", "qty"],
                as_dict=True
            )

            if not so_item:
                errors.append(
                    f"Sales Order Item {sales_order_item} does not exist in order {order_id}."
                )
                continue

            if item_code and so_item.item_code != item_code:
                errors.append(
                    f"Item code mismatch for SO Item {sales_order_item}."
                )

            if quantity > so_item.qty:
                errors.append(
                    f"Quantity {quantity} exceeds ordered qty for {sales_order_item}."
                )

    return errors


def create_pick_list_for_order(order_id, items):
    """
    Create pick list using provided quantities.
    """
    try:
        pick_list = create_pick_list(source_name=order_id)

        items_dict = {
            i["sales_order_item"]: i
            for i in items
        }

        valid_locations = []
        for location in pick_list.locations:

            sales_order_item = location.get("sales_order_item")
            if sales_order_item not in items_dict:
                continue

            item_data = items_dict[sales_order_item]
            location.qty = item_data["quantity"]
            valid_locations.append(location)

        if not valid_locations:
            return {
                "success": False,
                "error": "No valid items found for pick list."
            }

        pick_list.locations = valid_locations
        
        pick_list.save()
        pick_list.submit()

        return {
            "success": True,
            "pick_list": pick_list.name
        }

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error creating pick list for order {order_id}")

        return {
            "success": False,
            "error": str(e)
        }

def create_packing_slips(pick_list, packing_slips, round=1):
    """
    Create ERPNext packing slips.
    """
    delivery_notes = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabDelivery Note Item`
        WHERE against_pick_list = %s
    """, (pick_list.name,), as_dict=True)
    
    delivery_note = delivery_notes[0]["parent"] if delivery_notes else None
    if not delivery_note:
        if round < 4:
            time.sleep(.3)
            return create_packing_slips(pick_list, packing_slips, round=round+1)
        else:
            return [], None

    delivery_note = delivery_notes[0]["parent"]

    created_slips = []
    case_no = 1

    try:
        for slip in packing_slips:

            packing_slip_doc = make_packing_slip(delivery_note)
            items = []
            for dn_item in packing_slip_doc.items:
                for slip_item in slip.get("items", []):
                    if dn_item.item_code == slip_item.get("item_code"):
                        dn_item.qty = slip_item.get("quantity")
                        dn_item.sales_order_item = slip_item.get("sales_order_item")
                        items.append(dn_item)
                        

            dimensions = slip.get("dimensions") or {}

            packing_slip_doc.update({
                "from_case_no": case_no,
                "to_case_no": case_no,
                "gross_weight_pkg": slip.get("weight"),
                "net_weight_pkg": slip.get("weight"),
                "custom_neb_box_height": dimensions.get("height"),
                "custom_neb_box_width": dimensions.get("width"),
                "custom_neb_box_length": dimensions.get("length"),
                "custom_neb_parcel_template": slip.get("parcel_template"),
                "items": items
            })

            packing_slip_doc.insert()
            packing_slip_doc.submit()

            created_slips.append(packing_slip_doc.name)
            case_no += 1

        return created_slips, delivery_note
    except Exception as e:
        # Do NOT frappe.db.rollback() here — the Pick List submit (and the
        # Delivery Note/Shipment it cascades into) is still uncommitted in
        # this same request transaction, and a rollback here would erase it
        # out from under the caller before it gets a chance to clean it up
        # explicitly via `_clear_created_documents`. Return whichever slips
        # did get created so the caller can actually roll them back, rather
        # than silently discarding their names.
        frappe.log_error(message=frappe.get_traceback(), title=f"Error creating packing slips for delivery note {delivery_note}")
        return created_slips, delivery_note

def create_log(form_data, request_type):
    try:
        log = frappe.get_doc({
            'doctype': 'PPS API Log',
            'request_type': request_type,
            'payload': json.dumps(form_data),
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log.name
    except Exception as e:
        frappe.log_error(title='POS API Log Error', message=frappe.get_traceback())
        