# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import time, subprocess, os, signal
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

class MTBackgroundSync(Document):
	pass

def get_command():
	file_path = os.path.abspath(__file__)	
	main_dir = file_path.split("apps")[0][:-1]

	site = frappe.local.site
	command = f"bench --site {site} start-background-sync"
	command = f"cd {main_dir} && {command}"	
 
	return command

@frappe.whitelist()
def start_sync(filters):
	"""
	Start the web sync process for the given document name and filters.
	"""
	
	# frappe.db.set_single_value("MT Background Sync", "last_filters_used", filters, update_modified=False)
	# frappe.db.commit()
 
	if filters == '[]':
		frappe.throw("Please select filters to sync items.")
 
	items_count = frappe.db.get_list(
		"Item",
		filters=filters,
		group_by="item_code"
	)
  
	max_number_of_items_to_sync  = frappe.db.get_single_value("Metactical Settings", "max_number_of_items_to_sync")
	if len(items_count) > max_number_of_items_to_sync:
		frappe.throw(f"Cannot sync more than {max_number_of_items_to_sync} items at a time. Please refine your filters to reduce the number of items to sync.")
  
	pids = []
	site = frappe.local.site
	try:
		output = subprocess.check_output(["pgrep", "-f", f"bench --site {site} start-background-sync"]).decode().splitlines()
		pids = [int(pid) for pid in output]
	except subprocess.CalledProcessError:
		pass

	if pids:
		frappe.throw("A background sync process is already running. Please stop it before starting a new one.")
  
	sync_doc = frappe.get_single("MT Background Sync")
	if sync_doc:
		sync_doc.last_filters_used = filters
		sync_doc.save()
		frappe.db.commit()
  
	command = get_command()
	try:
		b_process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error starting background sync process")
	frappe.msgprint("Background sync process started.")
 
@frappe.whitelist()
def stop_sync():
	import os, signal, subprocess, psutil

	killed = []

	for proc in psutil.process_iter(['pid', 'cmdline']):
		cmd = " ".join(proc.info['cmdline'] or [])
		if "bench" in cmd and "start-background-sync" in cmd:
			try:
				proc.kill()
				killed.append(proc.pid)
			except Exception as ex:
				frappe.log_error(frappe.get_traceback(), "Error killing background sync process")
				frappe.msgprint(f"Error killing process {proc.pid}: {str(ex)}")

	if killed:
		frappe.msgprint(f"Killed background sync processes: {killed}")
	else:
		frappe.msgprint("No background sync process found.")
  
def sync_items_to_websites():
	
	sync_doc = frappe.get_single("MT Background Sync")	
	filters = sync_doc.last_filters_used or {}
	
	items_found = True
	offset = sync_doc.last_offset or 0
	while items_found:
		items = frappe.db.get_list(
			"Item",
			filters=filters,
			fields=["name", "item_code", "item_name", "image", "variant_of"],
			page_length=sync_doc.batch_size,
			start = offset,
			group_by="item_code"
		)
		if items:
			offset += sync_doc.batch_size
			sync_items(items, sync_doc, offset)
		else:
			items_found = False
		
		time.sleep(sync_doc.delay_time)

def sync_items(items_list, sync_doc, offset):
	"""
	Synchronize the given list of items.
	"""
	try:
		for item in items_list:
			if sync_doc.sync_item_detail:
				item_update_webhook = frappe.db.exists("Webhook", {"webhook_doctype": "Item", "webhook_docevent": "on_update", "enabled": 1, "condition": "doc.variant_of"})
				if item_update_webhook:
					webhook = frappe.get_doc("Webhook", item_update_webhook)
					item_doc = frappe.get_doc("Item", item.name)
					enqueue_webhook(item_doc, webhook)
				else:
					frappe.log_error(title="Item Update Webhook Not Found", message=f"No webhook found for Item updates with condition 'doc.variant_of'")
			
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
		
		frappe.db.set_single_value("MT Background Sync", "last_sync_time", frappe.utils.now(), update_modified=False)
		frappe.db.set_single_value("MT Background Sync", "last_offset", offset, update_modified=False)
		frappe.db.commit()
	except Exception as e:
		frappe.db.set_single_value("MT Background Sync", "last_offset", offset-sync_doc.batch_size, update_modified=False)
		frappe.log_error(message=frappe.get_traceback(), title="Items Background Sync Error")
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

if __name__ == "__main__":
	try:
		start_sync()
	except Exception as e:
		print(f"Error starting sync: {str(e)}")