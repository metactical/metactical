# Address Verification

How Sales Order shipping addresses get verified in the `metactical` app, which
services are involved, and where the results are stored.

## Summary

Address verification is a **manual, on-demand action** triggered from a
button on the Sales Order form — there is no automatic hook on save, no
scheduled job, and no webhook. Clicking it calls one whitelisted Python
method that routes to one of two independent implementations depending on a
site-wide settings toggle:

- **New path** — Storebuilder Canadian Address Verification API, with an
  optional Melissa Global Address API fallback for weak matches.
- **Legacy path** — ShipStation, used as a side effect of creating (and then
  deleting) a real ShipStation order.

Both paths write the same three result fields onto the `Address` and the
`Sales Order`.

## Trigger

`apps/metactical/metactical/custom_scripts/sales_order/sales_order.js`

A **"Verify Shipping Address"** button is added to every saved (non-new)
Sales Order:

```js
// line 60-62
if(!frm.doc.__islocal){
    frm.add_custom_button(__("Verify Shipping Address"), () => frm.events.verify_address(frm));
}
```

```js
// line 409-422
verify_address(frm) {
    frappe.call({
        method: "metactical.api.address_verification.verify_shipping_address",
        args: { "sales_order_name": frm.doc.name },
        freeze: true,
        callback: function(ret){
            frm.refresh_field("custom_ais_address_verified");
            frm.refresh_field("custom_ais_validation_entity");
            frm.refresh_field("custom_ais_validation_warning");
        }
    });
}
```

The `Address` doctype override (`hooks.py` → `CustomAddress` in
`apps/metactical/metactical/custom_scripts/address/address.py`) only handles
autonaming and phone normalization; it does not call verification. There is
no `validate`/`before_save` hook on `Address` or `Sales Order` that invokes
this — it only runs when a user clicks the button.

## Routing: `verify_shipping_address()`

`apps/metactical/metactical/api/address_verification.py:31`

```python
@frappe.whitelist()
def verify_shipping_address(sales_order_name):
    settings = frappe.get_single("Address Verification Settings")

    if not settings.enabled:
        from metactical.api.shipstation import verify_shipping_address as _ss_verify
        _ss_verify(sales_order_name)
        return

    # --- Storebuilder / Melissa path ---
    ...
```

The **`Address Verification Settings`** singleton (`enabled` checkbox)
decides which implementation runs. Sites/orgs that haven't opted in keep
using ShipStation with no code change required.

## Config: Address Verification Settings

`apps/metactical/metactical/metactical/doctype/address_verification_settings/address_verification_settings.json`
(single doctype, System Manager only)

| Field | Type | Default | Purpose |
|---|---|---|---|
| `enabled` | Check | off | On → use Storebuilder/Melissa; off → use ShipStation |
| `base_url` | Data (required) | `https://address.storebuilder.com` | Storebuilder API base URL |
| `api_key` | Password | — | Sent as `X-API-Key` header on every Storebuilder request |
| `timeout` | Int | 10 | Request timeout (seconds), shared by both Storebuilder and Melissa calls |
| `weak_match_threshold` | Float | 0.75 | Confidence cutoff — used only by the bulk audit tool (`verify_addresses`), not the per-order button |
| `enable_melissa_fallback` | Check | off | Re-check weak/failed Storebuilder matches with Melissa |
| `melissa_key` | Password | — | Melissa CustomerID / License Key |

## Path 1: Storebuilder + Melissa fallback

`apps/metactical/metactical/api/address_verification.py:45-143`

1. Loads the Sales Order's `shipping_address_name` Address doc. Throws if no
   shipping address is set.
2. `build_address_payload()` (line 329) maps ERPNext fields to the API's
   structured format and drops empty ones:

   | ERPNext field | API field |
   |---|---|
   | `address_line1` | `address_line_1` (required — throws if missing) |
   | `address_line2` | `address_line_2` |
   | `city` | `city` |
   | `state` | `province` |
   | `pincode` | `postal_code` |

3. `POST {base_url}/api/verify` with header `X-API-Key: <api_key>`,
   `timeout` seconds. On failure: logs to Error Log (title *"Address
   Verification - Storebuilder request failed"*) and re-throws to the user.
4. Reads `match_level` from the response and maps it:

   | `match_level` | Resulting status | Melissa fallback triggered? |
   |---|---|---|
   | `fully_verified` / `street_verified` | **Validated** | no |
   | `postal_verified` | **Validation Warning** ("Only postal code was verified") | yes, if enabled — can upgrade to Validated |
   | anything else / missing | **Validation Failed** | yes, if enabled — can upgrade to Validated or Validation Warning |

5. If Melissa fallback fires and returns a street-level-or-better match
   (`fully_verified`/`street_verified`), the final status is upgraded to
   **Validated** and `custom_ais_validation_entity` becomes `Melissa`.
6. Whenever Storebuilder's own `match_level` isn't fully/street verified, an
   Error Log entry (*"Address Verification - Unverified Address"*) is
   written recording the Storebuilder response, the final status, and which
   entity produced it — this happens even when Melissa later rescues the
   address, so Storebuilder's original miss stays on record for improving
   its matching.

### Melissa Global Address fallback

`verify_with_melissa()` — `apps/metactical/metactical/api/address_verification.py:230`

- `POST https://address.melissadata.net/V3/WEB/GlobalAddress/doGlobalAddress`
- Result codes (`Results` field, comma-separated) are parsed into AV (match)
  and AE (error) codes:
  - AV codes map to `postal_verified` / `street_verified` / `fully_verified`
    via `_MELISSA_AV_LEVELS` (line 155) — state/city-only matches (AV11,
    AV12, AV21, AV22) are **not** treated as verified, only street (AV13,
    AV14, AV23) or premise (AV24, AV25) matches are.
  - AE codes are translated to human-readable reasons via
    `_MELISSA_AE_DESCRIPTIONS` (line 188), e.g. `AE02` → "street name could
    not be matched (no match or multiple matches)".
  - The strongest AV code found wins (`_MELISSA_LEVEL_RANK`).
- **Every** outbound Melissa call — success or failure — writes a `Melissa
  Log` record so Melissa credit usage can be audited independently of the
  Error Log (which only captures failures). A call with nothing to send
  (missing `address_line1`) is skipped entirely and not logged (no credit
  consumed).

## Path 2: ShipStation (legacy)

`verify_shipping_address()` — `apps/metactical/metactical/api/shipstation.py:469`

This is the default when `Address Verification Settings.enabled` is off.
Unlike the Storebuilder path, it has no dedicated verification endpoint — it
piggybacks on order creation:

1. Builds a full ShipStation order payload (customer + shipping address,
   line items, totals) from the Sales Order.
2. `POST https://ssapi.shipstation.com/orders/createorder`, authenticated
   with API key/secret from the `Shipstation Settings` doctype
   (`get_settings()`, selected by the Sales Order's `source` if set).
3. Reads `shipTo.addressVerified` from ShipStation's response and maps it:

   | ShipStation string | Status |
   |---|---|
   | "Address validated successfully" | Validated |
   | "Address validation failed" | Validation Failed |
   | "Address validation warning" | Partially Validated |

4. If the order validated successfully, **deletes the ShipStation order it
   just created** (`DELETE /orders/{orderId}`) so the verification check
   doesn't leave dummy orders in ShipStation.
5. HTTP errors are logged to the Error Log (title *"ShipStation Order
   Creation Error"*).

## Result fields

Both paths write the **same three fields**, via `frappe.db.set_value` (a
direct DB write — bypasses `validate`, versioning, and the usual save flow)
onto **both** the `Address` and the `Sales Order`:

| Field | Type | Values | Notes |
|---|---|---|---|
| `custom_ais_address_verified` | Select | Address: `Validated / Validation Failed / Validation Warning`. Sales Order: `Validated / Partially Validated / Validation Failed / Validation Warning` | Defined in `fixtures/custom_field.json`. Sales Order's copy has `fetch_from: shipping_address_name.custom_ais_address_verified`. |
| `custom_ais_validation_entity` | Select | `Storebuilder / Shipstation / Melissa` | Which service produced the final verdict. **Not present in `fixtures/custom_field.json`** — added via Customize Form but not yet re-exported to fixtures. |
| `custom_ais_validation_warning` | Data | free text | Human-readable explanation, e.g. "Only postal code was verified" or a Melissa AE-code reason. |

`apps/metactical/metactical/fixtures/custom_field.json` — Address entry
around line 12770 (label "Address Validation Status"), Sales Order entry
around line 25025 (`insert_after: shipping_address`).

### Historical backfill

`apps/metactical/metactical/patches/set_validation_entity_for_validated_addresses.py`
sets `custom_ais_validation_entity = "Shipstation"` on any pre-existing
`Address` with `custom_ais_address_verified = "Validated"` but no entity
recorded — i.e. addresses validated before the `custom_ais_validation_entity`
field existed are assumed to have come from ShipStation, since that was the
only implementation at the time.

## Logging / audit trail

| What | Where |
|---|---|
| Storebuilder request failures | Error Log, title "Address Verification - Storebuilder request failed" |
| Storebuilder match not fully/street verified | Error Log, title "Address Verification - Unverified Address" (includes final status after any Melissa rescue) |
| Every Melissa API call (success or failure) | `Melissa Log` doctype — `date`, `status`, `sales_order`, `address`, `match_level`, `verified`, `http_status_code`, `detail`, full `request`/`response` JSON, `error` traceback |
| Melissa Log save failures | Error Log, title "Address Verification - Melissa Log save failed" |
| ShipStation order/verification errors | Error Log, title "ShipStation Order Creation Error" |

Only the Melissa side has a structured log doctype; Storebuilder and
ShipStation rely solely on the Frappe Error Log.

## Bulk / offline audit tool

`verify_addresses(limit=None, verbose=False, log_unverified=False)` —
`apps/metactical/metactical/api/address_verification.py:349`

A **read-only, console-only** utility, run via:

```bash
bench --site <site> execute "metactical.api.address_verification.verify_addresses" \
    --kwargs "{'limit': 10, 'verbose': True, 'log_unverified': True}"
```

Loops over every `Address` with `country = "Canada"`, calls the Storebuilder
`/api/verify` endpoint for each, and prints/returns summary stats
(`total_checked`, `verified_count`, `average_confidence`, `weak_matches`,
counts per `match_level`). It **does not write anything back** to Address
records — it's a reporting tool only, used to gauge database-wide address
quality against `weak_match_threshold`. Optionally writes unverified
addresses to `logs/address_verification_unverified.log` (bench logs
folder), overwriting any log from a previous run.

## Related fields/functions that are *not* part of this flow

These share similar names or nearby concepts but are separate — noted here
so they aren't confused with the above:

- **`mena_is_cp_verified`** ("Is CP Verified", Check field on Address,
  Sales Order, Sales Invoice, Delivery Note, Shipment) is populated in
  `apps/metactical/metactical/custom_scripts/utils/orders_api.py`
  (`check_if_cp_verified()`, ~line 188). It just reads an `IsVerified` flag
  off an inbound RabbitMQ order payload — presumably set by the Storebuilder
  Commerce storefront's own checkout-time Canada Post AddressComplete check.
  It does not call any verification API itself.
- **`orders_api.py` also has its own `verify_address(address_doc, so_address,
  sales_order)`** (~line 930) — same function name as the one in
  `address_verification.py`, but an unrelated purpose: it reconciles which
  Address record is linked on a re-synced Sales Order during order import.
- **`canadaPostAddressVerification/`** (top-level directory, outside any
  app) contains only recovered planning notes for an earlier, unimplemented
  design (local `Canadian Postal Code` / `Canadian Street` doctypes built
  from Canada Post datasets). The corresponding doctype folders under
  `apps/metactical/metactical/metactical/doctype/` contain no source, only
  stale `__pycache__` files — this design was superseded by the
  Storebuilder/Melissa integration documented above.
- **`canada_post`, `canada_post_shipment`, `canada_post_disabled_service`**
  doctypes are for Canada Post *shipping/label generation*, not address
  verification.

## File reference

| File | Role |
|---|---|
| `apps/metactical/metactical/custom_scripts/sales_order/sales_order.js` | "Verify Shipping Address" button + client callback |
| `apps/metactical/metactical/api/address_verification.py` | Routing, Storebuilder call, Melissa fallback, bulk audit tool |
| `apps/metactical/metactical/api/shipstation.py` | Legacy ShipStation-based verification (`verify_shipping_address`) |
| `apps/metactical/metactical/metactical/doctype/address_verification_settings/` | Settings singleton (API keys, toggle, thresholds) |
| `apps/metactical/metactical/metactical/doctype/melissa_log/` | Audit log doctype for Melissa API calls |
| `apps/metactical/metactical/patches/set_validation_entity_for_validated_addresses.py` | Backfill patch for `custom_ais_validation_entity` |
| `apps/metactical/metactical/fixtures/custom_field.json` | Custom field definitions (`custom_ais_address_verified` etc.) |
