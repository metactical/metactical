# Pizza Store — Production Setup Plan

Status: **planning**. No code has been written yet. We are waiting on management's answers (see §6).
Source: `1-DEV-PRODUCTION-SETUP.md`, from the deverp prototype under company `Pizza Store (Sample)` / `PZS`.
The companion docs (`2-FRONTEND-POS-SPEC.md`, `3-ACCOUNTING-GUIDE.md`) and the prototype's
`reference-scripts/` are **not available**. This plan is re-derived from doc 1 and can be checked
against deverp.

## 1. Scope

The goal is to reproduce the prototype's **structure** on production: company, items, BOMs, product
bundles, accounts, stock entry types, POS Profile, Lead Source and settings. We use management's real
values and do **not** copy the sample prices, recipes or quantities.

Out of scope: the POS frontend and API, and opening stock. Opening stock is done with accounting,
through a Purchase Receipt or a Stock Reconciliation.

## 2. Delivery: a migrate patch

The setup ships as a Frappe patch that runs on `bench migrate`.

| Piece | Path |
|---|---|
| Patch entry, under `[post_model_sync]` | `metactical/patches.txt` → `metactical.patches.setup_pizza_store` |
| Patch file | `metactical/patches/setup_pizza_store.py`: `execute()` calls `setup.run(config.PIZZA_STORE)`, then `frappe.db.commit()` |
| Logic | `metactical/pizza_store/setup.py` |
| Real values | `metactical/pizza_store/config.py` |

The style follows `metactical/patches/migrate_to_warehouse_user_permissions.py`.

Rules:
- **Every step is get-or-create.** A patch that fails halfway reruns from the top on the next migrate,
  so it must never duplicate anything. To re-apply on purpose, add a suffix to the patch line
  (`... v2`), which is the repo convention.
- **Migrate runs as Administrator.** That satisfies the Company guard at
  `metactical/custom_scripts/company/company.py:9`. Submits are direct `doc.submit()` calls, so there
  is no REST `TimestampMismatchError` and no API keys are needed.
- **The patch runs on every site that migrates** (metactical, metactical2/3, _dev, _prod). Merge it
  only once `config.py` holds the real production values.
- **Global settings change automatically on migrate.** Get management and accounting sign-off
  **before merge**.
- Reuse for Store 2 or a franchise company means a new config plus a new patch line.

## 3. Build steps (one function each, run in order)

0. **Company.** Name, abbr, CAD, Canada, Standard chart of accounts, fiscal year. The auto-created
   accounts, `Main - <abbr>` and the warehouses are picked up afterwards.
1. **Foundation.**
   - Item Group tree under `Pizza Store` (Ingredients, Prep Items, Menu Items, Modifiers, Drinks);
     align the naming with the item-master owner's numbering.
   - UOM `Bag`, if missing.
   - Warehouse `Store 1 - <abbr>`.
   - Accounts `Food Waste - <abbr>` and `Slice Cost - <abbr>`, under `Stock Expenses`.
   - Stock Entry Types `Waste - Spoiled / Expired`, `Waste - Dropped / Remade`, `Waste - Staff Meal`
     and `Hot Case Pie Baked` (all Material Issue).
   - Selling price list for the menu.
2. **Tax, payments, Lead Source, POS Profile.** Follows the existing store pattern; see §4.
3. **Ingredients.**
   - Stock items whose stock UOM is the recipe unit (Gram / Millilitre / Nos).
   - A purchase-UOM conversion row on each.
   - Batch, expiry and shelf life on perishables.
   - A default warehouse.
   - Item Reorder rows (Purchase).
4. **Prep items and BOMs.** `DOUGH` and `SAUCE` (batch + expiry), with submitted default BOMs costed at valuation rate.
5. **Menu, modifiers and bundles.**
   - Non-stock sale items, each with a Product Bundle and an Item Price.
   - Submitted costing BOMs for the whole pizzas.
   - Modifiers are their own lines with their own small bundles; the base recipe never changes.
6. **Slices, combos and drinks.**
   - Slices and combos are non-stock, price only. A combo is sold with a separate $0 drink line.
   - Drinks are stock items (Nos) with reorder rows.
7. **Suppliers.** Suppliers and supplier item prices. Receiving goes PO → PR (batch + expiry per line) → PI.
8. **Settings** (gated; needs sign-off):
   - Stock Settings: `auto_create_serial_and_batch_bundle_for_outward=1` and
     `pick_serial_and_batch_based_on=Expiry`. The patch first counts and logs items with
     `has_batch_no=1 OR has_serial_no=1`, and **aborts this step if it finds unexpected tracked items**.
   - Rounding: metactical ships the property setter `Sales Invoice-disable_rounded_total-default`
     (`metactical/fixtures/property_setter.json:1452`). Check its value on production before touching
     Global Defaults. Otherwise, send `disable_rounded_total=1` on every invoice, or follow
     management's 5-cent cash-rounding decision.
9. **Users.**
   - A POS API user with a minimal custom role and a Company User Permission.
   - Human roles per the management matrix.
   - Known cache issue: after deleting a User Permission, re-save one of the user's remaining
     User Permissions to reset the cache.

## 4. POS Profile and Lead Source: existing structure on the site

These findings come from reading the `metactical` site database on 2026-10-09.

### POS Profile pattern

There are 15 profiles. The recent store profiles follow one pattern: `ZE02-Oshawa-01 Operators`,
`SS01-Hubert-01 Operators` and `AO01-Houston Operators`.

| Field | Pattern |
|---|---|
| name | `<code>-<location>-01 Operators` |
| company / warehouse / selling_price_list | the store's own |
| customer | dedicated walk-in customer `DefaultPOS<profile>` (group Retail, with territory and default price list) |
| currency / update_stock | CAD / 1 |
| taxes_and_charges | e.g. `Ontario HST - ZE`, `Quebec GST and QST - SS` |
| write_off_account / write_off_cost_center / write_off_limit | `Write Off - <abbr>` / `Main - <abbr>` / 0.25–1.00 |
| account_for_change_amount | `Cash - <abbr>` |
| income_account / expense_account | `Sales - <abbr>` / `Cost of Goods Sold - <abbr>` |
| company_address | `<store> - Billing` or `- Shipping` |
| apply_discount_on | Grand Total |
| Payments table | Cash, Visa, Amex, Master Card, Debit Card, Gift Card; one marked default |
| Users table | the store's operators |
| Item groups | usually empty; `Downtown - BarberShop` restricts to `09 - Barber Shop` |
| `ifw_default_lead_source` (custom) | the store's Lead Source |
| `ifw_return_warehouse` (custom) | the store warehouse |
| `ifw_end_of_day_closing_account` (custom) | `Undeposited Fund - CAD - <abbr>` |
| `neb_cash_float` (custom) | 200–400 |
| `auto_logout_after_transaction` (custom) | 1 |

### Lead Source pattern

Store lead sources are named `Store - <Brand> - <Location>`. Their custom fields:

| Field | Meaning |
|---|---|
| `neb_company` | company |
| `neb_country` | country |
| `custom_neb_price_list` | price list |
| `neb_default_warehouse` | default warehouse (only Chilliwack sets it today) |
| `neb_company_address` | company address |
| `ais_report_label` | short report label |

### Why the Lead Source matters

- **End of Day Closing** only counts invoices where `invoice.source = POS Profile.ifw_default_lead_source`
  (`metactical/metactical/doctype/end_of_day_closing/end_of_day_closing.py:68`,
  `custom_scripts/utils/closing_api.py:43`). **Every pizza sale must carry `source` = the pizza Lead Source**,
  or the close-out won't see it.
- `custom_scripts/controllers/accounts_controller.py:85` falls back to the Lead Source's
  `neb_default_warehouse` when an item has no warehouse, so we set it to the store warehouse.
- `orders_api.py` and `item_inventory_output.py` read `custom_neb_price_list`, so we set it to the menu price list.

### What step 2 creates

1. The Sales Taxes & Charges Template for the province.
2. Mode of Payment Account rows for the new company on the existing payment methods.
3. The `Undeposited Fund - CAD - <abbr>` account, if missing.
4. The Company Address.
5. The Lead Source `Store - <Pizza brand> - <Location>`, with all the fields above.
6. The walk-in Customer `DefaultPOS<profile>`.
7. The POS Profile `<code>-<location>-01 Operators`, with the fields above and its item groups
   restricted to the Pizza Store groups.

## 5. Stock and accounting model (from doc 1)

| Thing | Stock effect | How |
|---|---|---|
| Ingredient | is the stock | Stock Item |
| Dough / Sauce | made in batches | BOM + Stock Entry **Manufacture** (no GL: inventory → inventory) |
| Whole pizza | ingredients out at sale | Product Bundle on a non-stock item (BOM only for costing) |
| Modifier | ingredients out at sale | Product Bundle on a non-stock item |
| Slice | none | non-stock item, price only |
| Bake Pie | ingredients out at bake | Stock Entry `Hot Case Pie Baked`, Dr `Slice Cost` / Cr `Stock In Hand` |
| Combo | none (the drink line is stock) | non-stock item + a $0 drink line |
| Waste | out, with reason | Stock Entry `Waste - …`, Dr `Food Waste` / Cr `Stock In Hand` |
| Weekly count | variance | Stock Reconciliation → `Stock Adjustment` |

Negative stock is disallowed, so a sale or a bake fails when stock is short. The POS must handle that error.

## 6. Inputs needed from management (→ `config.py`)

- **Company:** legal name, abbr, fiscal year start, address, tax/business number, and whether it is a new Company.
- **Tax:** sales tax (province template); are prices tax-inclusive or exclusive?
- **Rounding policy:** none, or 5-cent cash rounding.
- **Payments:** payment methods, the account each posts to, and the default method.
- **Menu:** items, sizes, prices; recipes in grams for pizzas, modifiers, dough and sauce.
- **Slices and combos:** slices per pie and slice prices; combo prices and drink options.
- **Suppliers:** purchase units (case/bag sizes) and prices.
- **POS:** profile code and location name, Lead Source name, cash float, write-off limit, store
  address, and the profile's users.
- **Users:** the production System Administrator, the user list and the role matrix.
- **Sign-off:** written approval for the Stock Settings change.

## 7. Verification

1. Dry run on the local site:
   `bench --site metactical execute metactical.patches.setup_pizza_store.execute`.
   Run it **twice** and confirm the second run creates nothing.
2. Then run doc 1 §10 on production:
   1. Receive stock with a batch.
   2. Run a dough Manufacture entry.
   3. Sell a Large pizza + modifier + box. Packed Items should list the ingredients, and the stock
      ledger should show a batch picked by earliest expiry.
   4. Bake a pie and check the Slice Cost GL entry.
   5. Sell slices and a combo.
   6. Sell an item with zero stock and confirm the error.
   7. Log a waste entry and check the Food Waste GL entry.
   8. Do a Stock Reconciliation.
   9. Check that a reorder level raises a draft Material Request.
   10. Check that invoice totals are not rounded to whole dollars.
3. Also confirm that a pizza sale appears in End of Day Closing for the new POS Profile (the Lead Source check).
4. Clean up the test transactions afterwards.

## 8. Housekeeping

- Rotate the deverp API keys that were pasted into chat during the prototype.
- Fix the `erpnext` MCP credentials if MCP access to deverp or production is wanted.
- The `Bag` UOM already exists on the shared deverp site.
