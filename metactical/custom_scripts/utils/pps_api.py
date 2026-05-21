import frappe
from metactical.custom_scripts.pick_list.pick_list import create_pick_list

@frappe.whitelist()
def pack_order(*args, **kwargs):
    """
    Packs an order by calling the appropriate method in the PPS API.
    """
    try:
        form_data = dict(frappe.form_dict)
        
        order_id = form_data.get("order_id")
        if not order_id:
            return {"status": "error", "message": "Order ID is required to pack an order."}
        
        
        items = form_data.get("items")
        # items list will be in the format: [{"item_code": "ITEM001", "quantity": 2, "sales_order_item": "SOI-00001"}, ...]
        
        validation_errors = validate_items(items, order_id)
        if validation_errors:
            return {"status": "error", "message": "; ".join(validation_errors)}
        
        
        create_pick_list_response = create_pick_list_for_order(order_id, items)
        print(f"Create pick list response: {create_pick_list_response}")
        if not create_pick_list_response.get("success"):
            return {"status": "error", "message": f"Failed to create pick list for order {order_id}: {create_pick_list_response.get('error')}"}
        
        
        # Assuming you have a method in your PPS API to pack an order
        response = call_pps_api_to_pack_order(order_id)
        if response.get("success"):
            return {"status": "success", "message": f"Order {order_id} packed successfully."}
        else:
            return {"status": "error", "message": f"Failed to pack order {order_id}: {response.get('error')}"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Error packing order {order_id}")
        return {"status": "error", "message": f"An error occurred while packing order {order_id}: {str(e)}"}
    
def call_pps_api_to_pack_order(order_id):
    """
    Placeholder function to call the PPS API to pack an order.
    Replace this with actual API call logic.
    """
    # Example response from the PPS API
    return {"success": True}

def validate_items(items, order_id):
    """
    Validates the items being packed against the sales order.
    """
    errors = []
    for item in items:
        item_code = item.get("item_code")
        quantity = item.get("quantity")
        sales_order_item = item.get("sales_order_item")
        
        if not item_code or not quantity or not sales_order_item:
            errors.append(f"Item {item_code} is missing required fields.")
            continue
        
        # Validate that the item exists in the sales order
        so_item = frappe.db.get_value("Sales Order Item", {"name": sales_order_item, "parent": order_id}, ["item_code", "qty"], as_dict=True)
        if not so_item:
            errors.append(f"Sales Order Item {sales_order_item} does not exist for Order {order_id}.")
            continue
        
        if so_item.item_code != item_code:
            errors.append(f"Item code {item_code} does not match Sales Order Item {so_item.item_code}.")
        
        if quantity > so_item.qty:
            errors.append(f"Quantity {quantity} for item {item_code} exceeds quantity in Sales Order Item {so_item.item_code}.")
    
    return errors

def create_pick_list_for_order(order_id, items):
    """
    Creates a pick list for the order using the provided items.
    """
    try:
        pick_list = create_pick_list(source_name=order_id)
        items_dict = {i["sales_order_item"]: i for i in items}
        locations = []
        
        for item in pick_list.locations:
            item_code = item.get("item_code")
            quantity = item.get("qty")
            sales_order_item = item.get("sales_order_item")
            
            print(f"Processing item in pick list: {item_code}, quantity: {quantity}, sales_order_item: {sales_order_item}")
            if not item_code or not quantity or not sales_order_item:
                continue
            
            if sales_order_item in items_dict:
                locations.append(item)
                
        if not locations:
            return {"success": False, "error": "No valid items found to create pick list."}
        
        pick_list.locations = locations
        pick_list.save()
        frappe.db.commit()

        return {"success": True, "pick_list": pick_list.name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Error creating pick list for order {order_id}")
        return {"success": False, "error": str(e)}