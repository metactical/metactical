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
| 1 | **Templates** | Search templates by SKU and/or name. Tick one to continue, or several to merge them into one (optionally renaming the survivor). Merging is **blocked** when the variants use more than one item group, and needs an explicit tick when the product names differ. |
| 2 | **Variants** | Pick one or two Item Attributes (Frappe Link controls). *Suggest combinations* reads colour/size out of the old variants' names; add more with *Add in bulk*; edit codes and names; create the new attribute variants. The template's code and name can be edited here too. |
| 3 | **Align** | Old variants on the left, new on the right, auto-paired by colour and size. Drag or move rows to fix pairs, choose the item name / retail SKU each new variant ends with, fix stock settings, tick leftovers to delete, then **Queue merge**. |
| 4 | **Merge job** | An *Item Merge Job* runs in the `long` queue: align settings -> merge pair by pair -> delete leftovers -> drop Variant Number -> website slugs + Load Data From SB -> website check. Progress arrives over realtime; the page also polls. Failed or interrupted jobs **Resume** where they stopped. |
| - | **Item codes** | Any time (e.g. after a merge): rename variant codes (e.g. to their retail SKU), change names and retail SKUs. Saved as an *Item Changes* job. Shows the website check for the template. |
| - | **Jobs** | Every job, searchable by template. Each job is also a read-only *Item Merge Job* document. |

## Files

```
metactical/item_merge/                 logic (no whitelisted methods here)
  pairing.py    old -> new pairing from item names (pure)
  rules.py      codes, names, attribute reading, settings checks, safeguards (pure)
  family.py     reads/writes on a template family: search, template merge/rename, variants, alignment
  merge.py      one old variant into one new variant, leftover deletion with Pricing Rule clean-up
  jobs.py       Item Merge Job create / run / resume / status, realtime progress
  websites.py   Item Detail slugs from the Storebuilder product API, website check
  tests/        offline tests (see below)
metactical/metactical/page/item_merge/ the Page: json, js (mounts the app), py (whitelisted API), css
metactical/metactical/doctype/item_merge_job{,_pair,_leftover,_change}/
metactical/public/js/item_merge.js     mounts ItemMerge.vue on #item_merge_ui
metactical/public/js/components/item_merge/
  ItemMerge.vue  tabs, stepper, routing (/app/item-merge/<view>/<arg>)
  StepTemplates.vue StepVariants.vue StepAlign.vue JobView.vue JobsList.vue ItemCodes.vue
  TemplateCode.vue WebsiteCheck.vue
  api.js         the only place that calls the backend (frappe.call)
  utils.js       Frappe dialogs/alerts, status pills, Link control helper, routes
```

## API

All methods are on `metactical.metactical.page.item_merge.item_merge`, need **System Manager** or
**Item Manager**, take list/dict arguments as JSON, and return snake_case. A problem the user can
fix comes back as a `frappe.throw` (shown by Frappe's message dialog).

| Method | Args | Writes |
|---|---|---|
| `search_templates` | `sku`, `name` | |
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

## Websites

Storebuilder maps a product's variants through its **External ID**, which must equal the ERP template
code. `websites.py` asks each site live, through the product API configured in *Storebuilder Sync
Settings > Image APIs* (the same endpoint `s3_image_api._fetch_sb_product` uses):

- **Slugs:** only price lists in `PRICE_LISTS` that the family has an Item Price on. A site is asked for
  each identity the family may be known by (template code, template retail SKU, templates merged or
  renamed into it and the old colour templates from Item Merge History). Exactly one slug found ->
  add/fill the Item Detail row; never overwrite a slug; several products -> left for a person.
- **Load Data From SB** runs afterwards, but **never while any row has a blank slug**: `get_item_details`
  fills a blank-slug row with an unrelated product.
- Rows Load Data From SB could not fill (no Item Detail API for that price list) take the name and
  description from the product API **if it returns them** (`name`, `description`) - confirm the payload
  on a bench.
- **Check:** for each row with a slug, the site's External ID vs the template code and its variant count
  vs ERP. Shown on the job and on the Item codes screen.

The stand-alone app read slugs from the sites' Metabase copies (days behind); this version asks the sites
directly, so there is no "copy as of" date and no Metabase credential on the server.

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
  interrupted jobs, item changes, template merge safeguards, website rules. Skipped on a bench.

## Bench checklist (not yet run on a bench)

- `bench build --app metactical` and `bench migrate` (new Page and four DocTypes).
- Open `/app/item-merge` as an Item Manager; check the Link controls, dialogs, dark mode.
- Run a small family end to end on a test site, including a leftover with a per-item Pricing Rule.
- Confirm `is_job_enqueued` marks a killed worker's job as Interrupted, and Resume continues it.
- Confirm the Storebuilder product API payload (`found`, `products[].externalId/slug/variants`, and
  whether `name`/`description` are included).
- Merge speed is ERPNext-bound (~20-30 s per pair measured over REST; in-process should be faster).
