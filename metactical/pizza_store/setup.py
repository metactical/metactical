"""
Pizza Store setup logic.
Called by metactical/patches/setup_pizza_store.py.

Each step is idempotent — safe to re-run on subsequent bench migrate calls.
To force a full re-run, bump the patch line to v2 in patches.txt.

Phase coverage:
  run()  → Phase 2 (Foundation) + Phase 3 (Ingredients, Prep Items, BOMs)
           + Phase 4 (Menu, Bundles, Pricing) + Phase 5 (Purchasing scaffold).
           Phases 6-9 added later.
"""

import frappe


def run(cfg):
    """Entry point called by the patch. cfg = config.PIZZA_STORE dict."""
    abbr = cfg["abbr"]
    company = cfg["company"]

    _assert_company_exists(company)

    # Phase 2 — Foundation
    _ensure_item_groups(cfg)
    _ensure_uom_bag()
    _ensure_warehouse(cfg)
    _ensure_expense_accounts(cfg)
    _ensure_stock_entry_types(cfg)
    _ensure_price_list(cfg)
    _update_stock_settings(company)
    _update_rounding()

    # Phase 3 — Items & BOMs
    _ensure_ingredients(cfg)
    _ensure_prep_items(cfg)
    _ensure_prep_boms(cfg)

    # Phase 4 — Menu, Bundles & Pricing
    _ensure_menu_pizzas(cfg)
    _ensure_modifiers(cfg)
    _ensure_slices_combos(cfg)
    _ensure_drinks(cfg)
    _ensure_walkin_customer(cfg)

    # Phase 5 — Purchasing scaffold
    _ensure_suppliers(cfg)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(action, doctype, name):
    marker = "CREATE" if action == "create" else "SKIP  "
    frappe.logger("pizza_store").info(f"  {marker}  {doctype}: {name}")


def _insert_if_missing(doctype, name_field, name_value, data):
    if frappe.db.exists(doctype, name_value):
        _log("skip", doctype, name_value)
        return
    doc = frappe.new_doc(doctype)
    for k, v in data.items():
        doc.set(k, v)
    doc.insert(ignore_permissions=True)
    _log("create", doctype, name_value)


# ── Step 0: guard ─────────────────────────────────────────────────────────────

def _assert_company_exists(company):
    if not frappe.db.exists("Company", company):
        frappe.throw(
            f"Company '{company}' does not exist. Create it as Administrator "
            f"before running this patch (metactical custom rule blocks non-admin "
            f"company creation)."
        )


# ── Step 1a: Item Groups ──────────────────────────────────────────────────────

def _ensure_item_groups(cfg):
    parent = cfg["company"]   # top-level group shares the company name

    _insert_if_missing("Item Group", "item_group_name", parent, {
        "item_group_name": parent,
        "parent_item_group": "All Item Groups",
        "is_group": 1,
    })

    for group in cfg["item_groups"]:
        _insert_if_missing("Item Group", "item_group_name", group, {
            "item_group_name": group,
            "parent_item_group": parent,
            "is_group": 0,
        })


# ── Step 1b: UOM ──────────────────────────────────────────────────────────────

def _ensure_uom_bag():
    _insert_if_missing("UOM", "uom_name", "Bag", {
        "uom_name": "Bag",
        "must_be_whole_number": 1,
    })


# ── Step 1c: Warehouse ────────────────────────────────────────────────────────

def _ensure_warehouse(cfg):
    abbr = cfg["abbr"]
    wh_name = f"{cfg['warehouse']} - {abbr}"
    _insert_if_missing("Warehouse", "warehouse_name", wh_name, {
        "warehouse_name": cfg["warehouse"],
        "parent_warehouse": f"All Warehouses - {abbr}",
        "company": cfg["company"],
    })


# ── Step 1d: Expense Accounts ─────────────────────────────────────────────────

def _ensure_expense_accounts(cfg):
    abbr = cfg["abbr"]
    for acct in cfg["expense_accounts"]:
        acct_name = f"{acct} - {abbr}"
        _insert_if_missing("Account", "account_name", acct_name, {
            "account_name": acct,
            "parent_account": f"Stock Expenses - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account",
            "company": cfg["company"],
            "is_group": 0,
        })


# ── Step 1e: Stock Entry Types ────────────────────────────────────────────────

def _ensure_stock_entry_types(cfg):
    # Stock Entry Type uses autoname=Prompt, so doc.name must be set explicitly.
    for et in cfg["stock_entry_types"]:
        _insert_if_missing("Stock Entry Type", "name", et, {
            "name": et,
            "stock_entry_type": et,
            "purpose": "Material Issue",
        })


# ── Step 1f: Price List ───────────────────────────────────────────────────────

def _ensure_price_list(cfg):
    pl = cfg["price_list"]
    _insert_if_missing("Price List", "price_list_name", pl, {
        "price_list_name": pl,
        "currency": cfg["currency"],
        "selling": 1,
        "buying": 0,
        "enabled": 1,
    })


# ── Step 1g: Stock Settings ───────────────────────────────────────────────────

def _update_stock_settings(company):
    # Safety check: abort if any non-pizza-store items already use batch/serial
    # tracking — the auto-pick change would affect them too.
    tracked = frappe.db.count("Item", {
        "has_batch_no": 1,
        "item_name": ["not like", "PZ-%"],
    })
    tracked += frappe.db.count("Item", {
        "has_serial_no": 1,
        "item_name": ["not like", "PZ-%"],
    })
    if tracked:
        frappe.logger("pizza_store").warning(
            f"Stock Settings NOT updated: {tracked} non-pizza items with "
            f"batch/serial tracking found. Review before enabling auto batch-pick."
        )
        return

    ss = frappe.get_single("Stock Settings")
    if (
        ss.auto_create_serial_and_batch_bundle_for_outward
        and ss.pick_serial_and_batch_based_on == "Expiry"
    ):
        _log("skip", "Stock Settings", "auto batch-pick already configured")
        return

    ss.auto_create_serial_and_batch_bundle_for_outward = 1
    ss.pick_serial_and_batch_based_on = "Expiry"
    ss.save(ignore_permissions=True)
    _log("create", "Stock Settings", "auto batch-pick by Expiry enabled")


# ── Step 1h: Disable invoice rounding ────────────────────────────────────────

def _update_rounding():
    # The metactical app ships a property setter that defaults Sales Invoice
    # disable_rounded_total to 0 (rounding on). Phase 1 decision: no rounding.
    # We update the property setter value rather than Global Defaults so the
    # behaviour is scoped to Sales Invoice only.
    ps_name = "Sales Invoice-disable_rounded_total-default"
    if frappe.db.exists("Property Setter", ps_name):
        current = frappe.db.get_value("Property Setter", ps_name, "value")
        if current == "1":
            _log("skip", "Property Setter", ps_name)
            return
        frappe.db.set_value("Property Setter", ps_name, "value", "1")
        _log("create", "Property Setter", f"{ps_name} → value=1")
    else:
        # Property setter doesn't exist yet — insert it.
        _insert_if_missing("Property Setter", "name", ps_name, {
            "name": ps_name,
            "doctype_or_field": "DocField",
            "doc_type": "Sales Invoice",
            "field_name": "disable_rounded_total",
            "property": "default",
            "property_type": "Text",
            "value": "1",
        })


# ── Phase 3: Ingredients ──────────────────────────────────────────────────────

def _ensure_ingredients(cfg):
    abbr = cfg["abbr"]
    warehouse = f"{cfg['warehouse']} - {abbr}"

    for ing in cfg["ingredients"]:
        code = ing["item_code"]
        if frappe.db.exists("Item", code):
            _log("skip", "Item", code)
            continue

        doc = frappe.new_doc("Item")
        doc.item_code = code
        doc.item_name = ing["item_name"]
        doc.item_group = "Pizza - Ingredients"
        doc.stock_uom = ing["stock_uom"]
        doc.is_stock_item = 1

        if ing["has_batch"]:
            doc.has_batch_no = 1
            doc.has_expiry_date = 1
            doc.shelf_life_in_days = ing["shelf_life_days"]
            doc.create_new_batch = 0

        # Purchase UOM conversion (only add if different from stock UOM)
        if ing["purchase_uom"] != ing["stock_uom"]:
            doc.append("uoms", {
                "uom": ing["purchase_uom"],
                "conversion_factor": ing["purchase_factor"],
            })

        # Default warehouse
        doc.append("item_defaults", {
            "company": cfg["company"],
            "default_warehouse": warehouse,
        })

        # Reorder level
        doc.append("reorder_levels", {
            "warehouse": warehouse,
            "warehouse_reorder_level": ing["reorder_level"],
            "warehouse_reorder_qty": ing["reorder_qty"],
            "material_request_type": "Purchase",
        })

        doc.insert(ignore_permissions=True)
        _log("create", "Item", code)


# ── Phase 3: Prep Items ───────────────────────────────────────────────────────

def _ensure_prep_items(cfg):
    abbr = cfg["abbr"]
    warehouse = f"{cfg['warehouse']} - {abbr}"

    for prep in cfg["prep_items"]:
        code = prep["item_code"]
        if frappe.db.exists("Item", code):
            _log("skip", "Item", code)
            continue

        doc = frappe.new_doc("Item")
        doc.item_code = code
        doc.item_name = prep["item_name"]
        doc.item_group = "Pizza - Prep Items"
        doc.stock_uom = prep["stock_uom"]
        doc.is_stock_item = 1
        doc.has_batch_no = 1
        doc.has_expiry_date = 1
        doc.shelf_life_in_days = prep["shelf_life_days"]
        doc.create_new_batch = 0

        doc.append("item_defaults", {
            "company": cfg["company"],
            "default_warehouse": warehouse,
        })

        doc.insert(ignore_permissions=True)
        _log("create", "Item", code)


# ── Phase 3: Prep BOMs ────────────────────────────────────────────────────────

def _ensure_prep_boms(cfg):
    abbr = cfg["abbr"]

    for bom_cfg in cfg["prep_boms"]:
        item_code = bom_cfg["item"]

        # Skip if a submitted default BOM already exists for this item.
        existing = frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_default": 1, "docstatus": 1},
            "name",
        )
        if existing:
            _log("skip", "BOM", f"{item_code} (default={existing})")
            continue

        doc = frappe.new_doc("BOM")
        doc.item = item_code
        doc.quantity = bom_cfg["qty"]
        doc.is_default = 1
        doc.is_active = 1
        doc.rm_cost_as_per = "Valuation Rate"
        doc.company = cfg["company"]
        doc.currency = cfg["currency"]

        for row in bom_cfg["items"]:
            doc.append("items", {
                "item_code": row["item_code"],
                "qty": row["qty"],
                "uom": row["uom"],
                "stock_uom": row["uom"],
            })

        doc.insert(ignore_permissions=True)
        doc.submit()
        _log("create", "BOM", f"{item_code} → {doc.name}")


# ── Phase 4 helpers ───────────────────────────────────────────────────────────

def _make_nonstock_item(code, name, group, cfg):
    """Insert a non-stock sales item if it doesn't exist. Returns whether created."""
    if frappe.db.exists("Item", code):
        _log("skip", "Item", code)
        return False
    doc = frappe.new_doc("Item")
    doc.item_code = code
    doc.item_name = name
    doc.item_group = group
    doc.stock_uom = "Nos"
    doc.is_stock_item = 0
    doc.append("item_defaults", {
        "company": cfg["company"],
        "default_warehouse": f"{cfg['warehouse']} - {cfg['abbr']}",
    })
    doc.insert(ignore_permissions=True)
    _log("create", "Item", code)
    return True


def _ensure_item_price(code, price, cfg):
    existing = frappe.db.get_value(
        "Item Price",
        {"item_code": code, "price_list": cfg["price_list"]},
        "name",
    )
    if existing:
        _log("skip", "Item Price", f"{code} @ {cfg['price_list']}")
        return
    doc = frappe.new_doc("Item Price")
    doc.item_code = code
    doc.price_list = cfg["price_list"]
    doc.price_list_rate = price
    doc.currency = cfg["currency"]
    doc.insert(ignore_permissions=True)
    _log("create", "Item Price", f"{code} = {cfg['currency']} {price}")


def _ensure_product_bundle(code, bundle_rows):
    if frappe.db.exists("Product Bundle", code):
        _log("skip", "Product Bundle", code)
        return
    doc = frappe.new_doc("Product Bundle")
    doc.new_item_code = code
    for row in bundle_rows:
        doc.append("items", {
            "item_code": row["item_code"],
            "qty": row["qty"],
            "uom": row["uom"],
        })
    doc.insert(ignore_permissions=True)
    _log("create", "Product Bundle", code)


def _ensure_costing_bom(code, bundle_rows, cfg):
    """Submitted BOM on a non-stock item — used for cost reporting only."""
    existing = frappe.db.get_value(
        "BOM",
        {"item": code, "is_default": 1, "docstatus": 1},
        "name",
    )
    if existing:
        _log("skip", "BOM (costing)", f"{code} (default={existing})")
        return
    doc = frappe.new_doc("BOM")
    doc.item = code
    doc.quantity = 1
    doc.is_default = 1
    doc.is_active = 1
    doc.rm_cost_as_per = "Valuation Rate"
    doc.company = cfg["company"]
    doc.currency = cfg["currency"]
    for row in bundle_rows:
        doc.append("items", {
            "item_code": row["item_code"],
            "qty": row["qty"],
            "uom": row["uom"],
            "stock_uom": row["uom"],
        })
    doc.insert(ignore_permissions=True)
    doc.submit()
    _log("create", "BOM (costing)", f"{code} → {doc.name}")


# ── Phase 4: Whole Pizzas ─────────────────────────────────────────────────────

def _ensure_menu_pizzas(cfg):
    for pizza in cfg["menu_pizzas"]:
        code = pizza["item_code"]
        _make_nonstock_item(code, pizza["item_name"], "Pizza - Menu Items", cfg)
        _ensure_item_price(code, pizza["price"], cfg)
        _ensure_product_bundle(code, pizza["bundle"])
        _ensure_costing_bom(code, pizza["bundle"], cfg)


# ── Phase 4: Modifiers ────────────────────────────────────────────────────────

def _ensure_modifiers(cfg):
    for mod in cfg["modifiers"]:
        code = mod["item_code"]
        _make_nonstock_item(code, mod["item_name"], "Pizza - Modifiers", cfg)
        _ensure_item_price(code, mod["price"], cfg)
        _ensure_product_bundle(code, mod["bundle"])


# ── Phase 4: Slices & Combos ──────────────────────────────────────────────────

def _ensure_slices_combos(cfg):
    for item in cfg["slices_combos"]:
        code = item["item_code"]
        _make_nonstock_item(code, item["item_name"], "Pizza - Menu Items", cfg)
        _ensure_item_price(code, item["price"], cfg)


# ── Phase 4: Drinks ───────────────────────────────────────────────────────────

def _ensure_drinks(cfg):
    abbr = cfg["abbr"]
    warehouse = f"{cfg['warehouse']} - {abbr}"

    for drink in cfg["drinks"]:
        code = drink["item_code"]
        if frappe.db.exists("Item", code):
            _log("skip", "Item", code)
        else:
            doc = frappe.new_doc("Item")
            doc.item_code = code
            doc.item_name = drink["item_name"]
            doc.item_group = "Pizza - Drinks"
            doc.stock_uom = "Nos"
            doc.is_stock_item = 1
            doc.append("item_defaults", {
                "company": cfg["company"],
                "default_warehouse": warehouse,
            })
            doc.append("reorder_levels", {
                "warehouse": warehouse,
                "warehouse_reorder_level": drink["reorder_level"],
                "warehouse_reorder_qty": drink["reorder_qty"],
                "material_request_type": "Purchase",
            })
            doc.insert(ignore_permissions=True)
            _log("create", "Item", code)

        _ensure_item_price(code, drink["price"], cfg)


# ── Phase 4: Walk-in Customer ─────────────────────────────────────────────────

def _ensure_walkin_customer(cfg):
    wc = cfg["walkin_customer"]
    name = wc["customer_name"]

    existing = frappe.db.get_value("Customer", {"customer_name": name}, "name")
    if existing:
        _log("skip", "Customer", name)
        return

    doc = frappe.new_doc("Customer")
    doc.customer_name = name
    doc.customer_group = wc["customer_group"]
    doc.territory = wc["territory"]
    doc.default_price_list = wc["default_price_list"]
    doc.insert(ignore_permissions=True)
    # Log the assigned docname — store this in POS config, not the customer_name.
    _log("create", "Customer", f"{name} → docname={doc.name}")
    frappe.logger("pizza_store").info(
        f"  *** POS CONFIG: set walk-in customer docname = {doc.name!r} ***"
    )


# ── Phase 5: Suppliers ────────────────────────────────────────────────────────

def _ensure_suppliers(cfg):
    suppliers = cfg.get("suppliers", [])
    if not suppliers:
        frappe.logger("pizza_store").info(
            "  SKIP  Suppliers: none configured in config.py "
            "(add real supplier names to cfg['suppliers'] to enable)"
        )
        return

    for sup in suppliers:
        sup_name = sup["supplier_name"]
        if not frappe.db.exists("Supplier", sup_name):
            doc = frappe.new_doc("Supplier")
            doc.supplier_name = sup_name
            doc.supplier_group = sup.get("supplier_group", "All Supplier Groups")
            doc.country = sup.get("country", cfg["country"])
            doc.insert(ignore_permissions=True)
            _log("create", "Supplier", sup_name)
        else:
            _log("skip", "Supplier", sup_name)

        # Add Item Supplier rows on each linked item.
        for item_code in sup.get("items", []):
            if not frappe.db.exists("Item", item_code):
                continue
            item_doc = frappe.get_doc("Item", item_code)
            already = any(
                r.supplier == sup_name for r in item_doc.get("supplier_items", [])
            )
            if not already:
                item_doc.append("supplier_items", {"supplier": sup_name})
                item_doc.save(ignore_permissions=True)
                _log("create", "Item Supplier row", f"{item_code} ← {sup_name}")
