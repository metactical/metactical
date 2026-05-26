import random
import frappe
from frappe.utils import add_days, nowdate
from metactical.custom_scripts.pick_list.pick_list import create_pick_list
from erpnext.stock.doctype.delivery_note.delivery_note import make_packing_slip
import json

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
        item_count = int(form_data.get("item_count") or 5)

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
                "dimensions": {"height": 1, "width": 2, "length": 0},
                "weight": 0,
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

    order_id = None
    log = None
    try:
        form_data = dict(frappe.form_dict)
        log = create_log(form_data, "Pack Order")
        order_id = form_data.get("order_id")
        if not order_id:
            return {
                "status": "error",
                "message": "Order ID is required."
            }

        packing_slips = form_data.get("packing_slips") or []
        if not packing_slips:
            return {
                "status": "error",
                "message": "Packing slips are required."
            }

        validation_errors = validate_packing_slips(
            packing_slips,
            order_id
        )

        if validation_errors:
            return {
                "status": "error",
                "message": "; ".join(validation_errors)
            }

        items = flatten_packing_slip_items(packing_slips)
        pick_list_result = create_pick_list_for_order(
            order_id,
            items
        )

        if not pick_list_result.get("success"):
            frappe.db.rollback()
            frappe.db.set_value("PPS API Log", log, "error", json.dumps({
                "status": "error",
                "message": pick_list_result.get("error")
            }))
            
            return {
                "status": "error",
                "message": pick_list_result.get("error")
            }

        pick_list = frappe.get_doc("Pick List", pick_list_result.get("pick_list"))
        frappe.db.set_value("PPS API Log", log, "pick_list", pick_list.name)

        packing_slip_docs, dn = create_packing_slips(pick_list, packing_slips)        
        frappe.db.set_value("PPS API Log", log, {
            "delivery_note": dn,
            "packing_slips": ", ".join([str(slip) for slip in packing_slip_docs])
        })
        
        frappe.db.commit()

        return {
            "status": "success",
            "message": f"Order {order_id} packed successfully.",
            "pick_list": pick_list.name,
            "delivery_note": dn,
            "packing_slips": packing_slip_docs
        }

    except Exception as e:
        frappe.get_traceback()
        if log:
            frappe.db.set_value("PPS API Log", log, "error", json.dumps({
                "status": "error",
                "message": str(e)
            }))
            
        frappe.log_error(message=frappe.get_traceback(), title=f"Error packing order {order_id}")
        frappe.db.commit()
        
        return {
            "status": "error",
            "message": str(e)
        }


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
        