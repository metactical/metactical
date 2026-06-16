import random
import frappe
from frappe.utils import add_days, nowdate
from metactical.custom_scripts.pick_list.pick_list import create_pick_list
from erpnext.stock.doctype.delivery_note.delivery_note import make_packing_slip
import json
from metactical.utils.shipping.shipping import get_rate
from concurrent.futures import ThreadPoolExecutor

site = frappe.local.site

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
        so.customer = "CS-25-00099"
        so.currency = company_currency
        so.set("company_currency", company_currency)
        so.conversion_rate = 1
        so.source = "Store - Camo - Edmonds"
        so.shipping_address_name = "CS-25-00117-Shipping"
        so.customer_address = "_Test PPS Shipping Address-9"
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
def pack_order(*args, **kwargs):
    """
    Packs an order using nested packing_slips payload structure.
    """
    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Pack Order")
    order_id = form_data.get("order_id")

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

        # --- Create pick list ---
        items = flatten_packing_slip_items(packing_slips)
        pick_list_result = create_pick_list_for_order(order_id, items)

        if not pick_list_result.get("success"):
            return _fail_with_log(log, pick_list_result.get("error"))

        pick_list = frappe.get_doc("Pick List", pick_list_result["pick_list"])
        frappe.db.set_value("PPS API Log", log, "pick_list", pick_list.name)

        # --- Create packing slips + delivery note ---
        packing_slip_docs, dn = create_packing_slips(pick_list, packing_slips)
        frappe.db.set_value("PPS API Log", log, {
            "delivery_note": dn,
            "packing_slips": ", ".join(str(s) for s in packing_slip_docs),
        })

        # --- Resolve shipment ---
        shipment_name = _get_shipment_for_delivery_note(dn)
        if not shipment_name:
            return _fail_with_log(log, f"No shipment found for Delivery Note {dn}")

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
        if log:
            frappe.db.set_value("PPS API Log", log, "error", frappe.as_json(_error(str(e))))
        frappe.db.commit()
        return _error(str(e))

@frappe.whitelist()
def create_label(*args, **kwargs):
    """
    Create a shipping label for a given shipment using the specified provider.

    Required params:
        shipment      - Shipment docname
        provider      - "Canada Post" or "Purolator"

    Optional params:
        carrier_service  - carrier service code (Canada Post)
        service_name     - service name dict passed to create_shipping
        shipment_amount  - declared shipment value (default 0)
    """
    form_data = dict(frappe.form_dict)
    log = create_log(form_data, "Create Label")

    shipment = form_data.get("shipment")
    provider = form_data.get("provider")
    carrier_service = form_data.get("carrier_service")
    service_name = form_data.get("service_name") or {}
    shipment_amount = float(form_data.get("shipment_amount") or 0)
    

    try:
        shipment_exist = frappe.db.exists("Shipment", shipment)
        if not shipment_exist:
            return _fail_with_log(log, f"Shipment {shipment} does not exist.")
        
        if not shipment:
            return _fail_with_log(log, "shipment is required.")
        if not provider:
            return _fail_with_log(log, "provider is required.")
        
        if provider not in ("Canada Post", "Purolator"):
            return _fail_with_log(log, f"Unsupported provider: {provider}. Use 'Canada Post' or 'Purolator'.")

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
            # "labels": result.get("labels"),
            # "printing_disabled": result.get("printing_disabled"),
        }

        frappe.db.set_value("PPS API Log", log, "response", json.dumps(response))
        frappe.db.commit()

        return response

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title=f"Error creating label for shipment {shipment}")
        if log:
            frappe.db.set_value("PPS API Log", log, "error", json.dumps(_error(str(e))))
        frappe.db.commit()
        return _error(str(e))


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

        pick_list = create_pick_list(
            source_name=order_id
        )

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

def create_packing_slips(pick_list, packing_slips):
    """
    Create ERPNext packing slips.
    """

    print("Creating packing slips in ERPNext...")
    print(f"Pick List: {pick_list.name}")
    print(f"Packing Slips Payload: {packing_slips}")

    delivery_notes = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabDelivery Note Item`
        WHERE against_pick_list = %s
    """, (pick_list.name,), as_dict=True)
    
    delivery_note = delivery_notes[0]["parent"] if delivery_notes else None
    
    if not delivery_note:
        frappe.throw(
            f"No Delivery Note found for Pick List {pick_list.name}"
        )

    delivery_note = delivery_notes[0]["parent"]
    print(f"Using Delivery Note: {delivery_note} for packing slips.")

    created_slips = []
    case_no = 1

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
        