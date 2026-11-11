"""
Pizza Store production configuration.
All Phase 1 decisions are recorded here. Edit this file — not setup.py — when
real values differ from the prototype.
"""

PIZZA_STORE = {
    # ── Company ───────────────────────────────────────────────────────────────
    "company": "Pizza Store",
    "abbr": "PZS",
    "currency": "CAD",
    "country": "Canada",

    # ── Warehouse ─────────────────────────────────────────────────────────────
    # One leaf warehouse per store. Add more for franchises.
    "warehouse": "Store 1",          # becomes "Store 1 - PZS"

    # ── Item Groups ───────────────────────────────────────────────────────────
    "item_groups": [
        "Pizza - Ingredients",
        "Pizza - Prep Items",
        "Pizza - Menu Items",
        "Pizza - Modifiers",
        "Pizza - Drinks",
    ],

    # ── Accounts (children of Stock Expenses - <abbr>) ────────────────────────
    "expense_accounts": [
        "Food Waste",    # waste entries: Dr Food Waste / Cr Stock In Hand
        "Slice Cost",    # bake-pie entries: Dr Slice Cost / Cr Stock In Hand
    ],

    # ── Stock Entry Types (all Material Issue) ────────────────────────────────
    "stock_entry_types": [
        "Waste - Spoiled / Expired",
        "Waste - Dropped / Remade",
        "Waste - Staff Meal",
        "Hot Case Pie Baked",
    ],

    # ── Price List ────────────────────────────────────────────────────────────
    "price_list": "Pizza Store Menu",

    # ── Tax ───────────────────────────────────────────────────────────────────
    # Phase 1 decision: GST + PST (Canada), tax-exclusive prices.
    # Accounting supplies the actual tax templates; rates are placeholders.
    "tax": {
        "gst_rate": 5.0,    # federal GST — confirm with accounting
        "pst_rate": None,   # provincial PST — set per province (e.g. 7.0 for BC)
        # template name will be: "GST and PST - PZS"
    },

    # ── Payment Methods ───────────────────────────────────────────────────────
    # Phase 1 decision: Cash, Debit/Credit Card, Gift Card.
    # GL accounts are created by accounting; listed here for the POS Profile step.
    "payment_methods": ["Cash", "Debit Card", "Credit Card", "Gift Card"],
    "default_payment_method": "Cash",

    # ── POS Profile (Phase 6) ─────────────────────────────────────────────────
    # Follows the site pattern: "<code>-<location>-01 Operators"
    # Fill in before Phase 6.
    "pos_profile_code": "PZ01",          # e.g. PZ01
    "pos_location": "Main",              # e.g. Main, Downtown
    "cash_float": 200,
    "write_off_limit": 0.25,

    # ── Lead Source (Phase 6) ─────────────────────────────────────────────────
    # Site convention: "Store - <Brand> - <Location>"
    "lead_source_name": "Store - Pizza Store - Main",

    # ── Ingredients — Phase 3 ─────────────────────────────────────────────────
    # stock_uom: recipe/storage unit. purchase_uom: how you order it.
    # has_batch=True items also get has_expiry_date=True and create_new_batch=False
    # (batch is assigned at Purchase Receipt, not auto-created on sale).
    "ingredients": [
        # ── Perishables (batch + expiry) ──────────────────────────────────────
        {
            "item_code": "PZ-MOZZ",  "item_name": "Mozzarella Shredded",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 45,
            "reorder_level": 6000,   "reorder_qty": 12000,
        },
        {
            "item_code": "PZ-PEPP",  "item_name": "Pepperoni Sliced",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 60,
            "reorder_level": 2000,   "reorder_qty": 4000,
        },
        {
            "item_code": "PZ-SAUS",  "item_name": "Italian Sausage Crumbled",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 30,
            "reorder_level": 1500,   "reorder_qty": 3000,
        },
        {
            "item_code": "PZ-MUSH",  "item_name": "Mushrooms Fresh",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 7,
            "reorder_level": 1500,   "reorder_qty": 3000,
        },
        {
            "item_code": "PZ-PEPR",  "item_name": "Green Peppers Fresh",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 7,
            "reorder_level": 1000,   "reorder_qty": 2000,
        },
        {
            "item_code": "PZ-ONION", "item_name": "Red Onions Fresh",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 14,
            "reorder_level": 1000,   "reorder_qty": 2000,
        },
        {
            "item_code": "PZ-BASIL", "item_name": "Basil Fresh",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": True,       "shelf_life_days": 5,
            "reorder_level": 200,    "reorder_qty": 500,
        },
        # ── Dry / shelf-stable (no batch) ─────────────────────────────────────
        {
            "item_code": "PZ-TOM",   "item_name": "Crushed Tomatoes Canned",
            "stock_uom": "Gram",     "purchase_uom": "Case", "purchase_factor": 17000,
            "has_batch": False,
            "reorder_level": 8000,   "reorder_qty": 17000,
        },
        {
            "item_code": "PZ-FLOUR", "item_name": "Flour 00",
            "stock_uom": "Gram",     "purchase_uom": "Bag",  "purchase_factor": 20000,
            "has_batch": False,
            "reorder_level": 12000,  "reorder_qty": 40000,
        },
        {
            "item_code": "PZ-YEAST", "item_name": "Yeast Instant",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": False,
            "reorder_level": 200,    "reorder_qty": 500,
        },
        {
            "item_code": "PZ-SALT",  "item_name": "Salt Fine",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": False,
            "reorder_level": 500,    "reorder_qty": 2000,
        },
        {
            "item_code": "PZ-SUGAR", "item_name": "Sugar",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": False,
            "reorder_level": 500,    "reorder_qty": 2000,
        },
        {
            "item_code": "PZ-OIL",   "item_name": "Olive Oil",
            "stock_uom": "Millilitre", "purchase_uom": "Litre", "purchase_factor": 1000,
            "has_batch": False,
            "reorder_level": 1000,   "reorder_qty": 5000,
        },
        {
            "item_code": "PZ-GARLIC","item_name": "Garlic Granulated",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": False,
            "reorder_level": 100,    "reorder_qty": 500,
        },
        {
            "item_code": "PZ-OREG",  "item_name": "Oregano Dried",
            "stock_uom": "Gram",     "purchase_uom": "Kg",   "purchase_factor": 1000,
            "has_batch": False,
            "reorder_level": 100,    "reorder_qty": 300,
        },
        # ── Packaging ─────────────────────────────────────────────────────────
        {
            "item_code": "PZ-BOX-M", "item_name": "Pizza Box 12in",
            "stock_uom": "Nos",      "purchase_uom": "Case", "purchase_factor": 50,
            "has_batch": False,
            "reorder_level": 50,     "reorder_qty": 200,
        },
        {
            "item_code": "PZ-BOX-L", "item_name": "Pizza Box 16in",
            "stock_uom": "Nos",      "purchase_uom": "Case", "purchase_factor": 50,
            "has_batch": False,
            "reorder_level": 50,     "reorder_qty": 200,
        },
    ],

    # ── Prep Items — Phase 3 ──────────────────────────────────────────────────
    # Batch + expiry; manufactured in-store from a BOM.
    "prep_items": [
        {
            "item_code": "PZ-DOUGH", "item_name": "Pizza Dough",
            "stock_uom": "Gram",
            "shelf_life_days": 3,
        },
        {
            "item_code": "PZ-SAUCE", "item_name": "Pizza Sauce",
            "stock_uom": "Gram",
            "shelf_life_days": 5,
        },
    ],

    # ── Prep BOMs — Phase 3 ───────────────────────────────────────────────────
    # Each BOM is submitted and set as default. qty is the batch yield in stock UOM.
    # rm_cost_as_per: Valuation Rate (no operations).
    "prep_boms": [
        {
            "item": "PZ-DOUGH",
            "qty": 10000,   # grams per batch
            "items": [
                {"item_code": "PZ-FLOUR", "qty": 6000,  "uom": "Gram"},
                {"item_code": "PZ-YEAST", "qty": 60,    "uom": "Gram"},
                {"item_code": "PZ-SALT",  "qty": 120,   "uom": "Gram"},
                {"item_code": "PZ-SUGAR", "qty": 120,   "uom": "Gram"},
                {"item_code": "PZ-OIL",   "qty": 200,   "uom": "Millilitre"},
            ],
        },
        {
            "item": "PZ-SAUCE",
            "qty": 9000,    # grams per batch
            "items": [
                {"item_code": "PZ-TOM",    "qty": 8500, "uom": "Gram"},
                {"item_code": "PZ-OIL",    "qty": 200,  "uom": "Millilitre"},
                {"item_code": "PZ-GARLIC", "qty": 100,  "uom": "Gram"},
                {"item_code": "PZ-OREG",   "qty": 50,   "uom": "Gram"},
                {"item_code": "PZ-SALT",   "qty": 100,  "uom": "Gram"},
                {"item_code": "PZ-SUGAR",  "qty": 150,  "uom": "Gram"},
            ],
        },
    ],

    # ── Menu Pizzas — Phase 4 ─────────────────────────────────────────────────
    # Non-stock sale items. Each gets a Product Bundle (stock depletion) and a
    # submitted costing BOM (for cost reporting only). Quantities in grams.
    "menu_pizzas": [
        {
            "item_code": "PZ-MARG-M",     "item_name": "Margherita Pizza – Medium",
            "price": 12.99,
            "bundle": [
                {"item_code": "PZ-DOUGH",  "qty": 250, "uom": "Gram"},
                {"item_code": "PZ-SAUCE",  "qty": 90,  "uom": "Gram"},
                {"item_code": "PZ-MOZZ",   "qty": 120, "uom": "Gram"},
                {"item_code": "PZ-BASIL",  "qty": 5,   "uom": "Gram"},
            ],
        },
        {
            "item_code": "PZ-MARG-L",     "item_name": "Margherita Pizza – Large",
            "price": 17.99,
            "bundle": [
                {"item_code": "PZ-DOUGH",  "qty": 380, "uom": "Gram"},
                {"item_code": "PZ-SAUCE",  "qty": 140, "uom": "Gram"},
                {"item_code": "PZ-MOZZ",   "qty": 180, "uom": "Gram"},
                {"item_code": "PZ-BASIL",  "qty": 8,   "uom": "Gram"},
            ],
        },
        {
            "item_code": "PZ-PEPPERONI-M", "item_name": "Pepperoni Pizza – Medium",
            "price": 14.99,
            "bundle": [
                {"item_code": "PZ-DOUGH",  "qty": 250, "uom": "Gram"},
                {"item_code": "PZ-SAUCE",  "qty": 90,  "uom": "Gram"},
                {"item_code": "PZ-MOZZ",   "qty": 120, "uom": "Gram"},
                {"item_code": "PZ-PEPP",   "qty": 50,  "uom": "Gram"},
            ],
        },
        {
            "item_code": "PZ-PEPPERONI-L", "item_name": "Pepperoni Pizza – Large",
            "price": 19.99,
            "bundle": [
                {"item_code": "PZ-DOUGH",  "qty": 380, "uom": "Gram"},
                {"item_code": "PZ-SAUCE",  "qty": 140, "uom": "Gram"},
                {"item_code": "PZ-MOZZ",   "qty": 180, "uom": "Gram"},
                {"item_code": "PZ-PEPP",   "qty": 80,  "uom": "Gram"},
            ],
        },
        {
            "item_code": "PZ-VEG-M",      "item_name": "Veggie Pizza – Medium",
            "price": 14.49,
            "bundle": [
                {"item_code": "PZ-DOUGH",  "qty": 250, "uom": "Gram"},
                {"item_code": "PZ-SAUCE",  "qty": 90,  "uom": "Gram"},
                {"item_code": "PZ-MOZZ",   "qty": 120, "uom": "Gram"},
                {"item_code": "PZ-MUSH",   "qty": 40,  "uom": "Gram"},
                {"item_code": "PZ-PEPR",   "qty": 30,  "uom": "Gram"},
                {"item_code": "PZ-ONION",  "qty": 25,  "uom": "Gram"},
            ],
        },
        {
            "item_code": "PZ-VEG-L",      "item_name": "Veggie Pizza – Large",
            "price": 19.49,
            "bundle": [
                {"item_code": "PZ-DOUGH",  "qty": 380, "uom": "Gram"},
                {"item_code": "PZ-SAUCE",  "qty": 140, "uom": "Gram"},
                {"item_code": "PZ-MOZZ",   "qty": 180, "uom": "Gram"},
                {"item_code": "PZ-MUSH",   "qty": 60,  "uom": "Gram"},
                {"item_code": "PZ-PEPR",   "qty": 45,  "uom": "Gram"},
                {"item_code": "PZ-ONION",  "qty": 35,  "uom": "Gram"},
            ],
        },
    ],

    # ── Modifiers — Phase 4 ───────────────────────────────────────────────────
    # Non-stock. Each gets a Product Bundle. No costing BOM needed.
    # A modifier is always added as a separate invoice line; the base recipe never changes.
    "modifiers": [
        {"item_code": "PZ-MOD-XMOZZ",   "item_name": "Extra Mozzarella",        "price": 2.50,
         "bundle": [{"item_code": "PZ-MOZZ",  "qty": 80, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-XPEPP",   "item_name": "Extra Pepperoni",          "price": 2.50,
         "bundle": [{"item_code": "PZ-PEPP",  "qty": 40, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-XMUSH",   "item_name": "Extra Mushrooms",          "price": 1.75,
         "bundle": [{"item_code": "PZ-MUSH",  "qty": 40, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-ADDSAUS", "item_name": "Add Italian Sausage",      "price": 2.50,
         "bundle": [{"item_code": "PZ-SAUS",  "qty": 60, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-HPEPP-M", "item_name": "Half Pepperoni – Medium",  "price": 1.50,
         "bundle": [{"item_code": "PZ-PEPP",  "qty": 25, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-HPEPP-L", "item_name": "Half Pepperoni – Large",   "price": 2.00,
         "bundle": [{"item_code": "PZ-PEPP",  "qty": 40, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-HMUSH-M", "item_name": "Half Mushrooms – Medium",  "price": 1.25,
         "bundle": [{"item_code": "PZ-MUSH",  "qty": 20, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-HMUSH-L", "item_name": "Half Mushrooms – Large",   "price": 1.50,
         "bundle": [{"item_code": "PZ-MUSH",  "qty": 30, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-HSAUS-M", "item_name": "Half Sausage – Medium",    "price": 1.50,
         "bundle": [{"item_code": "PZ-SAUS",  "qty": 30, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-HSAUS-L", "item_name": "Half Sausage – Large",     "price": 2.00,
         "bundle": [{"item_code": "PZ-SAUS",  "qty": 45, "uom": "Gram"}]},
        {"item_code": "PZ-MOD-BOX-M",   "item_name": "Take-out Box – Medium",    "price": 0.00,
         "bundle": [{"item_code": "PZ-BOX-M", "qty": 1,  "uom": "Nos"}]},
        {"item_code": "PZ-MOD-BOX-L",   "item_name": "Take-out Box – Large",     "price": 0.00,
         "bundle": [{"item_code": "PZ-BOX-L", "qty": 1,  "uom": "Nos"}]},
    ],

    # ── Slices & Combos — Phase 4 ─────────────────────────────────────────────
    # Non-stock, price only. No bundle. Combo adds a $0 drink as a separate line.
    "slices_combos": [
        {"item_code": "PZ-SLICE-BASIC", "item_name": "Pizza Slice – Basic",                   "price": 3.50},
        {"item_code": "PZ-SLICE-SPEC",  "item_name": "Pizza Slice – Specialty",               "price": 4.25},
        {"item_code": "PZ-COMBO-BASIC", "item_name": "Basic Combo (2 Slices + Drink)",        "price": 8.49},
        {"item_code": "PZ-COMBO-SPEC",  "item_name": "Specialty Combo (2 Slices + Drink)",    "price": 9.99},
    ],

    # ── Drinks — Phase 4 ──────────────────────────────────────────────────────
    # Stock items (Nos). Sold one-for-one; the $0 drink line on combos depletes stock.
    "drinks": [
        {"item_code": "PZ-DRINK-POP",   "item_name": "Canned Pop",      "price": 2.25, "reorder_level": 12, "reorder_qty": 48},
        {"item_code": "PZ-DRINK-WATER", "item_name": "Bottled Water",   "price": 1.75, "reorder_level": 12, "reorder_qty": 48},
        {"item_code": "PZ-DRINK-JUICE", "item_name": "Juice Box",       "price": 2.25, "reorder_level": 12, "reorder_qty": 48},
    ],

    # ── Walk-in Customer — Phase 4 ────────────────────────────────────────────
    # Single POS walk-in customer for all counter sales.
    # The docname is assigned by ERPNext naming series — store it in POS config
    # by docname, never by customer_name.
    "walkin_customer": {
        "customer_name": "Pizza Walk-in Customer",
        "customer_group": "Retail",
        "territory": "All Territories",
        "default_price_list": "Pizza Store Menu",
    },

    # ── Suppliers — Phase 5 ───────────────────────────────────────────────────
    # Add real supplier names and linked item codes before running Phase 5.
    # Each supplier entry maps to a Supplier record + Item Supplier rows on each item.
    # "items" lists the item_codes this supplier provides (for Item Supplier table).
    "suppliers": [
        # {
        #     "supplier_name": "Acme Dairy Co.",
        #     "supplier_group": "All Supplier Groups",
        #     "country": "Canada",
        #     "items": ["PZ-MOZZ"],
        # },
        # {
        #     "supplier_name": "Metro Meats Ltd.",
        #     "supplier_group": "All Supplier Groups",
        #     "country": "Canada",
        #     "items": ["PZ-PEPP", "PZ-SAUS"],
        # },
    ],

    # ── Purchase Tax Template — Phase 5 ───────────────────────────────────────
    # Rates supplied by accounting. Uncomment and fill before running Phase 5.
    "purchase_tax": {
        # "template_name": "GST and PST on Purchases - PZS",
        # "taxes": [
        #     {"charge_type": "On Net Total", "account_head": "Input Tax GST - PZS",  "rate": 5.0,  "description": "GST 5%"},
        #     {"charge_type": "On Net Total", "account_head": "Input Tax PST - PZS",  "rate": 7.0,  "description": "PST 7%"},
        # ],
    },
}
