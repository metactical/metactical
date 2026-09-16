# Item Merge

A desk page (`/app/item-merge`) that replaces the legacy **Variant Number** attribute with real Item
Attributes, one template family at a time. It is the Frappe version of the stand-alone Item Merge app
the team has been running against the dev site; the screens, rules and safeguards are the same.

Built the way the S3 Uploader page is built: a standard Page whose JS mounts a Vue 3 app
(`<script setup>` components) imported in `metactical.bundle.js`, Frappe controls and dialogs inside
it, and page CSS scoped under `#item_merge_ui`.

## The flow

| Step | Screen | What it does |
|---|---|---|
| 1 | **Templates** | The *Template SKU* and *Template name* boxes are Frappe Autocompletes fed from Item: they suggest as you type, picking one searches straight away, and a partial term still works. Tick one result to continue, or several to merge them into one (optionally renaming the survivor). Merging is **blocked** when the variants use more than one item group, and needs an explicit tick when the product names differ. |
| 2 | **Variants** | Pick one or two Item Attributes (Frappe Link controls). *Suggest combinations* reads colour/size out of the old variants' names; add more with *Add in bulk*; edit codes and names; create the new attribute variants. The template's code and name can be edited here too. |
| 3 | **Align** | Old variants on the left, new on the right, auto-paired by colour and size. Drag or move rows to fix pairs, choose the item name / retail SKU each new variant ends with, fix stock settings, tick leftovers to delete, then **Queue merge**. |
| 4 | **Merge job** | An *Item Merge Job* runs in the `long` queue: align settings -> merge pair by pair -> delete leftovers -> drop Variant Number -> website slugs + Load Data From SB -> website check. Progress arrives over realtime; the page also polls. Failed or interrupted jobs **Resume** where they stopped. |
| - | **Item codes** | Any time (e.g. after a merge): the template is picked with a Frappe Link on Item. Rename variant codes (one click sets each to its retail SKU, another collapses the doubled dashes `create_variant` leaves behind), change names and retail SKUs. Saved as an *Item Changes* job. Shows the website check for the template. |
| - | **Jobs** | Every job, filtered by template with a Frappe Link on Item. Each job is also a read-only *Item Merge Job* document. |

### Which boxes are controls, and which are not

Anything that names something already in ERP is a native Frappe control, never a bare `<input>`:

| Box | Control | Why |
|---|---|---|
| Item codes template, Jobs filter | **Link** on Item, `has_variants = 1` | must resolve to one template that exists |
| Attribute 1 / Attribute 2 | **Link** on Item Attribute, `numeric_values = 0` | must be a real attribute, and never the legacy numeric one |
| Template SKU, Template name | **Autocomplete** on Item | suggests what exists, but a half-typed term is a valid search and a Link would blank it on blur |

Everything still typed free-hand is a value being **authored**, so offering existing values would be
wrong - a dropdown there would list exactly what is forbidden or irrelevant:

- the template rename boxes and *Rename it to* - the new code must **not** already exist
- *Product name* on the variants screen, and each new variant's item code and name
- the item name / retail SKU each pair ends with on Align, and the same three columns on Item codes
- the bulk-add search box, which filters a list already loaded from the chosen attribute

## Files

```
metactical/item_merge/                 logic (no whitelisted methods here)
  pairing.py    old -> new pairing from item names (pure)
  rules.py      codes, names, attribute reading, settings checks, safeguards (pure)
  family.py     reads/writes on a template family: search, template merge/rename, variants, alignment
  merge.py      one old variant into one new variant, leftover deletion with Pricing Rule clean-up
  jobs.py       Item Merge Job create / run / resume / status, realtime progress
  demo_data.py  a legacy-shaped catalogue to try the page against on a test site
  catalogue.py  the price lists, deduct Lead Sources and legacy attribute, read from ERPNext
  websites.py   Item Detail slugs from the Storebuilder copies in Metabase, website check
  tests/        offline tests (see below)
metactical/metactical/page/item_merge/ the Page: json, js (mounts the app), py (whitelisted API), css
metactical/metactical/doctype/item_merge_job{,_pair,_leftover,_change}/
metactical/metactical/doctype/item_merge_settings/       merge fields + the Metabase URL, key and database ids
metactical/metactical/doctype/metabase_site_database/    its child table (price list -> database id)
metactical/public/js/item_merge.js     mounts ItemMerge.vue on #item_merge_ui
metactical/public/js/components/item_merge/
  ItemMerge.vue  tabs, stepper, routing (/app/item-merge/<view>/<arg>)
  StepTemplates.vue StepVariants.vue StepAlign.vue JobView.vue JobsList.vue ItemCodes.vue
  TemplateCode.vue WebsiteCheck.vue
  api.js         the only place that calls the backend (frappe.call)
  utils.js       Frappe dialogs/alerts, status pills, Link/Autocomplete control helpers, routes
```

## API

All methods are on `metactical.metactical.page.item_merge.item_merge`, need **System Manager** or
**Item Manager**, take list/dict arguments as JSON, and return snake_case. A problem the user can
fix comes back as a `frappe.throw` (shown by Frappe's message dialog).

**The role check is the real guard, not the Page's roles.** Those only decide who can open
`/app/item-merge`; every `@frappe.whitelist()` method is reachable by any logged-in user, and most
reads go through `frappe.get_all`, which applies no permissions of its own - without the check a
Sales User could read the whole catalogue structure, stock and retail SKUs through these endpoints.
`frappe.only_for` raises a *bare* `PermissionError`, which reaches the browser as an empty dialog, so
`_require_roles()` catches it and says what is missing instead:

> You need the **Item Manager** role to use Item Merge. Ask a System Manager to add it to your user.

The same message appears in the page body for anyone who reaches the route without the role, rather
than mounting an app whose every call fails. The three places that name the roles - the Page JSON,
`ROLES` in the API, and the page's own check - are kept by hand, so a test asserts they agree.

| Method | Args | Writes |
|---|---|---|
| `search_templates` | `sku`, `name` | |
| `template_code_options` / `template_name_options` | `txt` (called by the Autocomplete controls) | |
| `check_consolidation` | `target`, `sources` | |
| `consolidate_templates` | `target`, `sources`, `rename_to`, `confirm_different_products` | yes |
| `rename_template` | `template`, `new_code`, `item_name` | yes |
| `get_variants` | `template` | |
| `get_attribute_values` | `attribute` | |
| `suggest_combinations` | `template`, `attributes` | |
| `create_variants` | `template`, `attributes`, `combinations`, `style_name`, `dry_run` | yes |
| `get_alignment` | `template` | |
| `check_alignment` | `template`, `pairs`, `leftovers` | |
| `fix_settings` | `template`, `pairs` | yes |
| `queue_merge` | `template`, `pairs` (`old`, `new`, `item_name`, `retail_sku`), `leftovers`, `options` (`sku`: keep/code, `fix_names`) | job |
| `queue_item_changes` | `template`, `changes` (`item_code`, `new_code`, `item_name`, `retail_sku`) | job |
| `list_jobs` / `get_job` / `resume_job` | `template` / `job`, `live` / `job` | |
| `get_reposts` | `template` | |
| `get_website_plan` / `apply_websites` / `check_websites` | `template` | apply: yes |

Realtime event: `item_merge_progress` `{job, template, status, processed, total, line}` to the user who queued the job.

Writes made outside a job (template merge/rename, variant creation, settings fixes, website slugs)
leave an *Info* comment on the template's timeline.

## How a pair is merged (`merge.merge_pair`)

1. Snapshot the old and new items and their bins onto the job row.
2. Preflight: a different stock UOM / batch / serial / fixed-asset setting fails the pair; the one known
   trap (new variant not a stock item while the old one is) is fixed on the new item.
3. `frappe.rename_doc("Item", old, new, merge=True)`. The **CustomItem** hooks do the rest of the carry:
   barcodes, supplier rows, website specs, item defaults, Item Price clean-up, Item Merge Settings
   fields, Item Merge History and the reposts.
4. Verify the old item is gone and no stock ledger rows are left on it.
5. Follow-ups on the new item in one save: the item name and retail SKU chosen on the align screen,
   **duplicate supplier rows removed** (the hook adds the old item's row next to the template's blank
   one), website specs restored if the hook wiped them, a `Website - Camo` deduct row at qty 0 if missing.
6. Insert Item Merge History if the hook didn't, record the expected qty, commit.

The job stops on the first failed pair; Resume skips pairs already merged. Leftovers are deleted only
when they have no stock ledger; a per-item Pricing Rule that blocks the deletion is removed (and backed
up on the job) only when every item it prices is in the leftover set. Variant Number is dropped from the
template only when no Variant Number variant is left.

## No webhooks from this page

A merge saves, renames and deletes hundreds of records: every variant, the template, Item Merge
History rows, the Item Prices the merge hook clears, the Pricing Rules leftover deletion removes.
Each of those doctypes carries **Webhook** records that push to the websites - Item alone has three
unconditional ones plus one on `doc.variant_of`, i.e. every variant save. None of them should fire
while a family is half restructured.

So both entry points - `_api()` for every whitelisted call, and `run_job` for the background job -
set two flags around their work and restore them afterwards:

```python
WEBHOOK_FLAGS = ("in_import", "item_from_excel")
```

- **`in_import`** is the first thing frappe's `run_webhooks` checks; it returns before queueing
  anything.
- **`item_from_excel`** has to be set with it. `CustomItem.validate` does
  `if not frappe.flags.get("item_from_excel"): frappe.flags.in_import = False`, so on an Item save
  the flag would be cleared during validate, before `on_update` runs, and the webhooks would fire
  anyway. Measured on this bench against the site's own Item webhooks, temporarily enabled:
  baseline **3** queued, `in_import` alone **3** queued, both flags **0** queued.
- `frappe.flags` proxies `frappe.local.flags`, which is thread-local, so a concurrent request in the
  same worker keeps its webhooks.

**What else these flags change.** Nothing on the doctypes this page writes: there is no `in_import`
guard in ERPNext's Item, Item Price or Pricing Rule, nor anywhere in the stock path, so validation
runs exactly as it does in the UI. The guards that exist elsewhere are on User, Report, DocType, Web
Form, Customer and the accounting documents, none of which this page touches. Two metactical guards
do read them, both written for bulk paths and both wanted here:

  - `s3_image_api.queue_retail_sku_change` - no per-row image re-push while codes are churning
  - `validate_variants_in_websites` - a warn-only website check, pointless mid-restructure

The websites are brought back in step deliberately at the end of the job, by the website slugs step
and Load Data From SB.

## Websites

Storebuilder maps a product's variants through its **External ID**, which must equal the ERP template
code. `websites.py` reads each site's Storebuilder database from its **Metabase** copy:

- **Where the credentials live:** the **Item Merge Settings** Single, in its *Metabase* section -
  Enable Metabase, base URL, an API key stored as a Password field, a query timeout, and one row per
  website mapping a price list to that site's snapshot database id (*Metabase Site Database*). With it
  off or incomplete the website steps report "needs setup" and nothing is written; the merge itself is
  unaffected. The form has a **Test Metabase connection** button that counts products in each database.
- **Which price lists count** comes from ERPNext, not from a list in the code: every Lead Source that
  names a `custom_neb_price_list` (`catalogue.price_lists()`). Adding a website in ERPNext is enough.
- **Slugs:** only price lists the family has an Item Price on. One query per site matches **every SKU
  column** - `ExternalId`, `Sku`, `RetailSku` and the four variant SKU columns - against every code
  the family has ever had (template, variants, retail SKUs, and everything merged or renamed into
  them via Item Merge History). Exactly one slug found -> add/fill the Item Detail row; never
  overwrite a slug; several products -> left for a person.
- **Load Data From SB** runs afterwards - ERPNext's own action, not a product API - but **never while
  any row has a blank slug**: `get_item_details` fills a blank-slug row with an unrelated product.
- Rows it could not fill (no Item Detail API for that price list, e.g. CamoUSA) take the English name
  and description from the snapshot's `ProductTranslations`.
- **Check:** for each row with a slug, the site's External ID vs the template code and its variant
  count vs ERP.

**Every snapshot is dated.** A copy refreshes irregularly - days, not hours - so every row carries an
`as_of` and the screens show it in a *Copy as of* column. A mismatch found right after a merge is
expected until the copy catches up.

## Tests

```bash
# from the app repo root, no bench needed
python -m unittest discover -s metactical/item_merge/tests -t . -v
```

- `test_pairing.py` - pairing against three real families merged on dev (fixtures trimmed to name,
  item name, template and attributes).
- `test_rules.py` - codes, attribute reading, safeguards, settings, supplier de-duplication, change validation.
- `test_flows.py` - the real `family` / `merge` / `jobs` / `websites` code end to end against an in-memory
  frappe (`fake_frappe.py`): create variants -> align -> queue -> run -> audit, failure + resume,
  interrupted jobs, item changes, template merge safeguards, website rules, and the Metabase fallback
  (a stand-in Single answers canned rows). Skipped on a bench.

Note `fake_frappe._dict.__getattr__` must raise on a missing dunder, as frappe's own `_dict` does:
returning `None` for `__getstate__` makes `copy.deepcopy` call `None` on Python < 3.11, which is what
this bench runs.

## Nothing site-specific is hard-coded

Everything the stand-alone app carried as a literal is now read from ERPNext (`catalogue.py`), cached
per request:

| Was | Now |
|---|---|
| `PRICE_LISTS` - five `RET - …` names | every Lead Source that names a `custom_neb_price_list` |
| `DEDUCT_LEAD = "Website - Camo"` | the Lead Source of each price list the family actually sells on |
| `VARIANT_NUMBER = "Variant Number"` | the numeric attribute **that family's own template** carries |
| `SB_DATABASES` - domain to Metabase db id | the *Metabase Site Databases* table on Item Merge Settings |

So a sixth website, a differently named deduct source, or a family hanging off a differently named
numeric attribute all work without touching the code. The only tables left in code are the item-name
alias wordings in `pairing.py` (`XL` -> `XLarge`, `OD` -> `Olive`, `BLK` -> `Black`), which the base
project also keeps there: those wordings appear **only inside legacy item names** and exist nowhere in
ERPNext - not as values, not as abbreviations.

## Demo data (`demo_data.py`)

A catalogue to try the page against on a test site, shaped like the real legacy one: templates
carrying only Variant Number, variants coded `-0001, -0002 …` with the colour and size buried in the
item name, real stock behind a Material Receipt, and an Item Price so the website step has something
to look up.

It uses the **real Item Attributes** copied from the server - `Colour - Clothing - PS`,
`Size - Clothing - XS to 8XL`, and `Colour - Actual` for the awkward-abbreviation family - and refuses
to run if they are missing. Codes therefore come out with the real abbreviations (`-001-0003`), and
the "check code" case uses genuinely unusable ones like `D. Grey`. `destroy()` never removes the
attributes; they are the site's, not the demo's.

```bash
bench --site <site> execute metactical.item_merge.demo_data.create
bench --site <site> execute metactical.item_merge.demo_data.create --kwargs "{'families': 60}"
bench --site <site> execute metactical.item_merge.demo_data.summary
bench --site <site> execute metactical.item_merge.demo_data.destroy
```

`families` counts the ordinary families; eight awkward ones are always made, one per branch of the
screens that is otherwise hard to find a real example of:

| Family | What it is for |
|---|---|
| `ZZGRP1001` | template parked in a **group** item group, written there behind `validate_item_group`'s back exactly as the real ones predate it |
| `ZZUNR1002` | a variant whose name names no attribute value - shows as **not read** |
| `ZZABB1003` | `Coyo Brn` and `-014` abbreviations - the grid raises **check code** |
| `ZZCNF1004` | two olds that resolve to one new variant - pairing refuses them |
| `ZZCOL1005` | one attribute only, single-value variants |
| `ZZLFT1006` | two never-transacted leftovers, one held by a per-item Pricing Rule |
| `ZZALI1007` | `XL` / `Olive Drab` / `Woodland` wording - exercises the alias tables |
| `ZZSET1008` | a variant with Maintain Stock off - Align offers to fix it |

The per-colour split families (every fourth one, e.g. `ZZCM4119BLK`) also reproduce the **code clash**:
their legacy variants are `-0001…-0004`, so choosing *Size only* generates `TEMPLATE-0003`, which is
already one of those old variants. Picking a second attribute, or merging the colour templates first,
gives `TEMPLATE-colour-size` and no clash.

Everything is prefixed `ZZ` and `destroy()` removes exactly that, so it is safe to re-run; the random
seed is fixed, so the same catalogue comes back every time. The **Lead Sources** it creates keep their
real names (`Website - Camo` and friends) and are deliberately *not* removed by `destroy()`: `merge.py`
adds a deduct-qty row pointing at `Website - Camo` after every merge and that field is a Link, so a
site without it fails every pair. **Never run any of this on production.**

## Bench checklist (not yet run on a bench)

- `bench build --app metactical` and `bench migrate` (new Page, the Item Merge Job DocTypes, the
  *Metabase Site Database* child table, and the Metabase fields on *Item Merge Settings*).
- Open `/app/item-merge` as an Item Manager; check the Link controls, dialogs, dark mode.
- Run a small family end to end on a test site, including a leftover with a per-item Pricing Rule.
- Confirm `is_job_enqueued` marks a killed worker's job as Interrupted, and Resume continues it.
- Confirm the Storebuilder product API payload (`found`, `products[].externalId/slug/variants`, and
  whether `name`/`description` are included).
- Metabase stays off until someone fills in the Metabase section of Item Merge Settings; then use
  **Test Metabase connection** to confirm the URL, key and each database id, and check the snapshot
  table names (`Products`, `ProductVariants`, `ProductTranslations`, `Locales`) match the queries in
  `websites.py`.
- Merge speed is ERPNext-bound (~20-30 s per pair measured over REST; in-process should be faster).
