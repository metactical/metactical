# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

class MTBackgroundSync(Document):
	pass


@frappe.whitelist()
def start_sync(name, filters):
	"""
	Start the web sync process for the given document name and filters.
	"""
	try:
		sync_doc = frappe.get_single("MT Web Sync")	
		items = frappe.db.get_list(
			"Item",
			filters=filters,
			fields=["name", "item_code", "item_name", "image", "variant_of"]
		)
	
		i = 0
		items_list = []
		for item in items:
			if i % 500 == 0 and i > 0:
				frappe.enqueue(sync_items, items_list=items_list, queue='long', sync_doc=sync_doc, timeout=3600)
				items_list = []
			items_list.append(item)
	
			i += 1
	
		if items_list:
			frappe.enqueue(sync_items, items_list=items_list, queue='long', sync_doc=sync_doc, timeout=3600)
	
		frappe.response["message"] = f"Background Sync started for {len(items)} items."
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "MT Web Sync Error")
		frappe.response["message"] = f"Error starting sync: {str(e)}"
  
def sync_items(items_list, sync_doc):
	"""
	Synchronize the given list of items.
	"""
	try:
		item_update_webhook = frappe.db.exists("Webhook", {"webhook_doctype": "Item", "webhook_docevent": "on_update", "enabled": 1})
		if item_update_webhook:
			webhook = frappe.get_doc("Webhook", item_update_webhook)
		else:
			return
	
		for item in items_list:
			item_doc = frappe.get_doc("Item", item.name)
			enqueue_webhook(item_doc, webhook)
	
			if sync_doc.sync_item_with_price_lists:
				item_prices  = frappe.get_all(
					"Item Price",
					fields=["price_list", "currency", "name"],
					filters={"item_code": item.name})
		
				for item_price in item_prices:
					price_list_webhook = frappe.db.exists("Webhook", {"webhook_doctype": "Item Price", "webhook_docevent": "on_change", "enabled": 1, "condition": f'doc.price_list == "{item_price.price_list}"'})

					if price_list_webhook:
						price_list_webhook_doc = frappe.get_cached_doc("Webhook", price_list_webhook)
						price_list_doc = frappe.get_doc("Item Price", item_price.name)
						enqueue_webhook(price_list_doc, price_list_webhook_doc)

			if sync_doc.sync_item_with_discounts:
				for item_price in item_prices:
					price_list = item_price.price_list
					pricing_rule = get_item_discount(item.name, price_list, item_doc.brand)
					if pricing_rule:
						pricing_rule_webhook = frappe.db.exists("Webhook", {
							"webhook_doctype": "Pricing Rule",
							"webhook_docevent": "on_update",
							"enabled": 1,
							"condition": f'doc.for_price_list=="{price_list}"'
						})

						if pricing_rule_webhook:
							pricing_rule_doc = frappe.get_doc("Pricing Rule", pricing_rule)
							pricing_rule_webhook_doc = frappe.get_cached_doc("Webhook", pricing_rule_webhook)
							enqueue_webhook(pricing_rule_doc, pricing_rule_webhook_doc)
		
			if sync_doc.sync_item_with_inventory:
				frappe.enqueue(update_item_inventory_output, item_code=item.name, queue='default')

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Items Background Sync Error")
		frappe.response["message"] = f"Error syncing items: {str(e)}"
    
def get_item_discount(item, price_list, brand=None):
    # select all pricing rules for the item and pick the one with the highest priority for each item
    pricing_rule = frappe.db.sql(f"""
        SELECT
            `tabPricing Rule`.name
        FROM
            `tabPricing Rule Item Code`
        JOIN
            `tabPricing Rule` ON `tabPricing Rule`.name = `tabPricing Rule Item Code`.parent
        WHERE
            `tabPricing Rule Item Code`.item_code = '{item}'
            AND (`tabPricing Rule`.for_price_list = '{price_list}' or `tabPricing Rule`.for_price_list is NULL)
            AND `tabPricing Rule`.disable = 0
            AND `tabPricing Rule`.selling = 1
            AND `tabPricing Rule`.valid_upto >= CURDATE()
        ORDER BY
            CAST(`tabPricing Rule`.priority AS UNSIGNED) DESC
        LIMIT 1;
    """, as_dict=1)
    
    if pricing_rule:
        return pricing_rule[0].name
    else:
        if brand:
            pricing_rule = frappe.db.sql(f"""
				SELECT
					`tabPricing Rule`.name
				FROM
					`tabPricing Rule Brand`
				JOIN
					`tabPricing Rule` ON `tabPricing Rule`.name = `tabPricing Rule Brand`.parent
				WHERE
					`tabPricing Rule Brand`.brand = '{brand}'
					AND (`tabPricing Rule`.for_price_list = '{price_list}' or `tabPricing Rule`.for_price_list is NULL)
					AND `tabPricing Rule`.disable = 0
					AND `tabPricing Rule`.selling = 1
					AND `tabPricing Rule`.valid_upto >= CURDATE()
				ORDER BY
					CAST(`tabPricing Rule`.priority AS UNSIGNED) DESC
				LIMIT 1;
			""", as_dict=1)
            
            if pricing_rule:
                return pricing_rule[0].name
    
    return None