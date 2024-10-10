from __future__ import unicode_literals
import frappe
import json
from six import iteritems
from frappe.model.document import Document
from frappe import _
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import cstr, flt, getdate, cint, nowdate, add_days, get_link_to_form, strip_html
from erpnext.stock.doctype.pick_list.pick_list import PickList, get_available_item_locations, get_items_with_location_and_quantity
import barcode as _barcode
from barcode.writer import ImageWriter
from io import BytesIO
from erpnext.stock.doctype.pick_list.pick_list import (validate_item_locations, set_delivery_note_missing_values, update_delivery_note_item,
	create_dn_with_so, create_dn_wo_so)
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note as create_delivery_note_from_sales_order
import datetime
from pytz import timezone
from pathlib import Path
import shutil
from itertools import groupby
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe import _, msgprint, bold
from frappe.utils.nestedset import get_descendants_of
from erpnext.stock.doctype.packed_item.packed_item import is_product_bundle
import re

class CustomPickList(PickList):
	def validate(self):
		super(CustomPickList, self).validate()
		self.check_for_existing_draft()

	def update_sales_order_item(self, item, picked_qty, item_code):
		item_table = "Sales Order Item" if not item.product_bundle_item else "Packed Item"
		stock_qty_field = "stock_qty" if not item.product_bundle_item else "qty"
		
		# Metactical Customization: Take into consideration returned qty
		already_picked, actual_qty, returned_qty = frappe.db.get_value(
			item_table,
			item.sales_order_item,
			["picked_qty", stock_qty_field, "returned_qty"],
		)
		
		if returned_qty is None:
			returned_qty = 0

		if self.docstatus == 1:
			if (((already_picked + picked_qty - returned_qty) / actual_qty) * 100) > (
				100 + flt(frappe.db.get_single_value("Stock Settings", "over_delivery_receipt_allowance"))
			):
				frappe.throw(
					_(
						"You are picking more than required quantity for {}. Check if there is any other pick list created for {}"
					).format(item_code, item.sales_order)
				)

		frappe.db.set_value(item_table, item.sales_order_item, "picked_qty", already_picked + picked_qty)

	def before_save(self):
		super(CustomPickList, self).before_save()
		# Metactical Customization: removed auto location assignement. Will remove the whole
		# set_item_location in the future from this page
		# self.set_item_locations()
		
		# set percentage picked in SO
		for location in self.locations:
			if (
				location.sales_order
				and frappe.db.get_value("Sales Order", location.sales_order, "per_picked") == 100
			):
				frappe.throw("Row " + str(location.idx) + " has been picked already!")
				
		if len(self.locations) > 0:
			if self.locations[0].get('sales_order'):
				rv = BytesIO()
				_barcode.get('code128', self.locations[0].sales_order).write(rv, {"module_width":0.4})
				bstring = rv.getvalue()
				self.barcode = bstring.decode('ISO-8859-1')
				
				# STO Barcode
				sv = BytesIO()
				_barcode.get('code128', self.name).write(sv, {"module_width":0.4})
				stoBarcode = sv.getvalue()
				self.sal_sto_barcode = stoBarcode.decode('ISO-8859-1')

		#Check if Sales Order has Balance Due or Credit Due
		sales_orders = []
		for item in self.locations:
			if item.sales_order and item.sales_order not in sales_orders:
				sales_orders.append(item.sales_order)
				doc = frappe.get_doc("Sales Order", item.sales_order)
				c_or_d = doc.grand_total - doc.advance_paid
				if c_or_d > 0:
					frappe.msgprint('Warning: Sales Order <a href="/desk#Form/Sales Order/{0}">{0}</a> has not been fully paid'.format(item.sales_order))
				elif c_or_d < 0:
					frappe.msgprint('Warning: Sales Order <a href="/desk#Form/Sales Order/{0}">{0}</a> has credit due.'.format(item.sales_order))

	def on_submit(self):
		super(CustomPickList, self).on_submit()

		# Metactical Customization: Create delivery note automatically on submit
		if self.do_not_create_delivery:
			return
		
		pick_list = frappe.get_doc('Pick List', self.name)
		validate_item_locations(pick_list)

		sales_orders = [d.sales_order for d in pick_list.locations if d.sales_order]
		sales_orders = set(sales_orders)

		delivery_note = None
		for sales_order in sales_orders:
			delivery_note = create_delivery_note_from_sales_order(sales_order,
				delivery_note, skip_item_mapping=True)
			delivery_note.update({
				'ignore_pricing_rule': frappe.db.get_value('Sales Order', sales_order, 'ignore_pricing_rule'),
				"disable_rounded_total": 1
			})
			#Add pick list submitted date in sales order
			sales_doc = frappe.get_doc("Sales Order", sales_order)
			sales_doc.update({"pick_list_submitted_date": datetime.datetime.now(timezone('US/Pacific')).strftime("%Y-%m-%d %H:%M:%S")})
			sales_doc.save()

		# map rows without sales orders as well
		if not delivery_note:
			delivery_note = frappe.new_doc("Delivery Note")

		item_table_mapper = {
			'doctype': 'Delivery Note Item',
			'field_map': {
				'rate': 'rate',
				'name': 'so_detail',
				'parent': 'against_sales_order',
			},
			'condition': lambda doc: abs(doc.delivered_qty) < abs(doc.qty) and doc.delivered_by_supplier!=1
		}

		item_table_mapper_without_so = {
			'doctype': 'Delivery Note Item',
			'field_map': {
				'rate': 'rate',
				'name': 'name',
				'parent': '',
			}
		}

		for location in pick_list.locations:
			if location.sales_order_item:
				sales_order_item = frappe.get_cached_doc('Sales Order Item', {'name':location.sales_order_item})
			else:
				sales_order_item = None

			source_doc, table_mapper = [sales_order_item, item_table_mapper] if sales_order_item \
				else [location, item_table_mapper_without_so]

			dn_item = map_child_doc(source_doc, delivery_note, table_mapper)

			if dn_item:
				dn_item.warehouse = location.warehouse
				dn_item.qty = location.picked_qty
				dn_item.batch_no = location.batch_no
				dn_item.serial_no = location.serial_no

				update_delivery_note_item(source_doc, dn_item, delivery_note)

		set_delivery_note_missing_values(delivery_note)

		delivery_note.pick_list = pick_list.name
		delivery_note.customer = pick_list.customer if pick_list.customer else None
		if pick_list.ais_source:
			delivery_note.source = pick_list.ais_source
		delivery_note.save()
	
	
	def on_cancel(self):
		super(CustomPickList, self).on_cancel()

		# Metactical Customization: Delete delivery notes and clear submitted date in sales orders
		delivery_notes = frappe.get_all('Delivery Note', filters={'pick_list': self.name, 'docstatus': 0}, fields=['name'])
		for delivery_note in delivery_notes:
			# Delete shipments first before deleting delivery notes
			shipments = frappe.db.sql("""
						SELECT DISTINCT sdn.parent AS shipment_id
						FROM 
							 `tabShipment Delivery Note` sdn
						INNER JOIN
							 `tabShipment` s ON s.name = sdn.parent
						WHERE 
							 sdn.delivery_note = %(delivery_note)s AND s.docstatus = 0
						""", {"delivery_note": delivery_note.name}, as_dict=1)
			for shipment in shipments:
				shipment_doc = frappe.get_doc("Shipment", shipment.shipment_id)
				shipment_doc.delete()

			doc = frappe.get_doc('Delivery Note', delivery_note.name)
			doc.delete()
			
		#Clear pick list submitted date in sales order
		pick_list = frappe.get_doc('Pick List', self.name)

		sales_orders = [d.sales_order for d in pick_list.locations if d.sales_order]
		sales_orders = set(sales_orders)
		for sales_order in sales_orders:
			sales_doc = frappe.get_doc("Sales Order", sales_order)
			sales_doc.update({"pick_list_submitted_date": ""})
			sales_doc.save()

	@frappe.whitelist()
	def set_item_locations(self, save=False):
		self.validate_for_qty()
		items = self.aggregate_item_qty()
		picked_items_details = self.get_picked_items_details(items)
		self.item_location_map = frappe._dict()

		from_warehouses = [self.parent_warehouse] if self.parent_warehouse else []
		if self.parent_warehouse:
			from_warehouses.extend(get_descendants_of("Warehouse", self.parent_warehouse))

		# Create replica before resetting, to handle empty table on update after submit.
		locations_replica = self.get("locations")

		# reset
		self.delete_key("locations")
		updated_locations = frappe._dict()


		#Metactical Customization: Get shipping items
		shipping_items = frappe.db.get_all('Pick List Shipping Item', fields=["item"], pluck='item')

		for item_doc in items:
			item_code = item_doc.item_code
			# Metactical Customization: If item is one of the shipping items, 
			# skip this step and readd it later to the locations table
			if item_code in shipping_items:
				continue

			self.item_location_map.setdefault(
				item_code,
				get_available_item_locations(
					item_code,
					from_warehouses,
					self.item_count_map.get(item_code),
					self.company,
					picked_item_details=picked_items_details.get(item_code),
					consider_rejected_warehouses=self.consider_rejected_warehouses,
				),
			)

			locations = get_items_with_location_and_quantity(item_doc, self.item_location_map, self.docstatus)

			item_doc.idx = None
			item_doc.name = None

			for row in locations:
				location = item_doc.as_dict()
				location.update(row)
				key = (
					location.item_code,
					location.warehouse,
					location.uom,
					location.batch_no,
					location.serial_no,
					location.sales_order_item or location.material_request_item,
				)

				if key not in updated_locations:
					updated_locations.setdefault(key, location)
				else:
					updated_locations[key].qty += location.qty
					updated_locations[key].stock_qty += location.stock_qty

		for location in updated_locations.values():
			if location.picked_qty > location.stock_qty:
				location.picked_qty = location.stock_qty

			self.append("locations", location)

		# If table is empty on update after submit, set stock_qty, picked_qty to 0 so that indicator is red
		# and give feedback to the user. This is to avoid empty Pick Lists.
		if not self.get("locations") and self.docstatus == 1:
			for location in locations_replica:
				location.stock_qty = 0
				location.picked_qty = 0
				self.append("locations", location)
			frappe.msgprint(
				_(
					"Please Restock Items and Update the Pick List to continue. To discontinue, cancel the Pick List."
				),
				title=_("Out of Stock"),
				indicator="red",
			)
		# Metactical Customization: Re-add the shipping items
		for location in locations_replica:
			if location.item_code in shipping_items:
				self.append("locations", location)

		if save:
			self.save()

	def submit(self):
		if len(self.locations) > 25:
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=2000)
		else:
			self._submit()

	def validate_stock_qty(self):
		from erpnext.stock.doctype.batch.batch import get_batch_qty
		shipping_items = frappe.db.get_all('Pick List Shipping Item', fields=["item"], pluck='item')
		

		for row in self.get("locations"):
			# Metactical Customization: Skip shipping items
			if row.item_code in shipping_items:
				continue

			# Metactical Customization: If is product budle, validate individual items
			if is_product_bundle(row.item_code):
				bundle_items = frappe.get_all('Product Bundle Item', filters={'parent': row.item_code}, fields=['item_code', 'qty'])
				for bundle_item in bundle_items:
					bin_qty = frappe.db.get_value(
						"Bin",
						{"item_code": bundle_item.item_code, "warehouse": row.warehouse},
						"actual_qty",
					)
					if row.qty > bin_qty:
						frappe.throw(
							_(
								"At Row #{0}: The picked quantity {1} for the product budle item {2} is greater than available stock {3} in the warehouse {5}."
							).format(row.idx, bundle_item.item_code, bundle_item.qty,  bold(row.warehouse)),
							title=_("Insufficient Stock"),
						)
			else:
				if row.batch_no and not row.qty:
					batch_qty = get_batch_qty(row.batch_no, row.warehouse, row.item_code)

					if row.qty > batch_qty:
						frappe.throw(
							_(
								"At Row #{0}: The picked quantity {1} for the item {2} is greater than available stock {3} for the batch {4} in the warehouse {5}."
							).format(row.idx, row.item_code, batch_qty, row.batch_no, bold(row.warehouse)),
							title=_("Insufficient Stock"),
						)

					continue

				bin_qty = frappe.db.get_value(
					"Bin",
					{"item_code": row.item_code, "warehouse": row.warehouse},
					"actual_qty",
				)

				if row.qty > bin_qty:
					frappe.throw(
						_(
							"At Row #{0}: The picked quantity {1} for the item {2} is greater than available stock {3} in the warehouse {4}."
						).format(row.idx, row.qty, bold(row.item_code), bin_qty, bold(row.warehouse)),
						title=_("Insufficient Stock"),
					)
		
	def before_submit(self):
		super(CustomPickList, self).before_submit()
		self.reorder_items_by_location()

	def reorder_items_by_location(self):
		# Sort items based on their location
		rows_with_none_location = []
		digit_rows_with_location = []
		non_digit_rows_with_location = []

		# get rows with None location, digit location and non-digit location
		for row in self.locations:
			if row.ifw_location is None:
				rows_with_none_location.append(row)
			else:
				if row.ifw_location.split("-")[0].isdigit():
					digit_rows_with_location.append(row)
				else:
					non_digit_rows_with_location.append(row)

		data = []
		idx = 1
		if digit_rows_with_location:
			locations_with_digit = []
			digit_rows_with_location_values = []

			# prepare data for sorting
			for row in digit_rows_with_location:
				locations_with_digit.append(row.ifw_location)
				digit_rows_with_location_values.append({
					"location": row.ifw_location,
					"row": row
				})

			# sort digit rows by location
			location_keys = sorted(locations_with_digit, key=sort_key)
				
			# add rows with digit location
			for key in location_keys:
				for i, row in enumerate(digit_rows_with_location_values):
					if row["location"] == key:
						row["row"].idx = idx
						data.append(row["row"])
						idx += 1
						digit_rows_with_location_values.pop(i)
						break


		# sort non-digit rows by location
		if non_digit_rows_with_location:
			sorted_locations = sorted(non_digit_rows_with_location, key=lambda x: x.ifw_location)
			for row in sorted_locations:
				row.idx = idx
				data.append(row)
				idx += 1

		# add rows with None location at the end
		if rows_with_none_location:
			for row in rows_with_none_location:
				row.idx = idx
				data.append(row)
				idx += 1

		self.locations = []
		for row in data:
			self.append("locations", row)

	def check_for_existing_draft(self):
		if self.docstatus == 0:
			sales_order = ""
			for item in self.locations:
				if item.sales_order:
					sales_order = item.sales_order
					break
			
			# Items in the current pick list
			current_items = {item.sales_order_item:item.picked_qty for item in self.locations}

			# Previous draft and submitted pick lists for the same sales order
			existing_pick_list_items = frappe.get_all("Pick List Item", filters={"sales_order": sales_order, "docstatus": 0}, fields=["name", "qty", "picked_qty", "item_code", "parent", "sales_order_item"])
			
			# # The actual qty of the items in the sales order
			sales_order_items = frappe.get_all("Sales Order Item", filters={"parent": sales_order, "docstatus": 1}, fields=["item_code", "qty", "picked_qty", "name"])
			sales_order_items = {item.name:item for item in sales_order_items}

			# group existing pick list items by parent
			pick_list_items_grouped = {}
			for item in existing_pick_list_items:
				if item.parent == self.name:
					continue

				if item.parent in pick_list_items_grouped:
					pick_list_items_grouped[item.parent].append(item)
				else:
					pick_list_items_grouped[item.parent] = [item]

			# sum the picked_qty for each item in the existing pick lists
			existing_items = {}
			for key, so_item in (pick_list_items_grouped).items():
				for item in so_item:
					if item.sales_order_item in existing_items:
						existing_items[item.sales_order_item] += item.picked_qty
					else:
						existing_items[item.sales_order_item] = item.picked_qty

			remaining_to_be_picked = {}
			for so_item, row in sales_order_items.items():
				remaining_to_be_picked[so_item] = row["qty"] - row["picked_qty"]
		
			for so_item, new_qty in current_items.items():
				# if the item is not in the pick_lists_without_dn, it means it has been delivered
				# so we can't pick more than the remaining qty
				
				if not remaining_to_be_picked.get(so_item, 0):
					frappe.throw("Item {} has already been picked".format(sales_order_items.get(so_item).item_code))

				check = remaining_to_be_picked.get(so_item, 0) - existing_items.get(so_item, 0)
				if check < new_qty:
					if check > 0:
						frappe.throw(_("Part of <b>{0}</b> has already been picked in a different Pick List. <br>The remaining quantity is <b>{1}</b>").format(sales_order_items.get(so_item).item_code, check))
					else:
						frappe.throw(_("All of <b>{0}</b> has already been picked in a different Pick List(s).").format(sales_order_items.get(so_item).item_code))

#  Function to extract numerical parts and convert them to integers for sorting
def sort_key(item):
	item = re.split(r'[|]', item)
	if item:
		parts = re.split(r'[-]', item[0])
		return [int(part) if part.strip().isdigit() else part.strip() for part in parts]
	
	return [0]

@frappe.whitelist()
def create_pick_list(source_name, target_doc=None):
	def update_item_quantity(source, target, source_parent) -> None:
		picked_qty = flt(source.picked_qty) / (flt(source.conversion_factor) or 1)
		qty_to_be_picked = flt(source.qty) - max(picked_qty, flt(source.delivered_qty))

		target.qty = qty_to_be_picked
		target.stock_qty = qty_to_be_picked * flt(source.conversion_factor)
		# Metactical Customization: Default pick qty take delivered qty into consideration
		target.picked_qty = flt(source.qty) - flt(source.delivered_qty)

	def update_packed_item_qty(source, target, source_parent) -> None:
		qty = flt(source.qty)
		for item in source_parent.items:
			if source.parent_detail_docname == item.name:
				picked_qty = flt(item.picked_qty) / (flt(item.conversion_factor) or 1)
				pending_percent = (item.qty - max(picked_qty, item.delivered_qty)) / item.qty
				target.qty = target.stock_qty = qty * pending_percent
				return
	
	# Metactical Customization: Add bundled item instead of breaking it down to it's individual items
	def should_pick_order_item(item) -> bool:
		return (
			abs(item.delivered_qty) < abs(item.qty)
			and item.delivered_by_supplier != 1
		)
	
	# Metactcal Customization: Add warehouse, sales order and source to item map
	# and removed packed items replacement 
	doc = get_mapped_doc(
		"Sales Order",
		source_name,
		{
			"Sales Order": {
				"doctype": "Pick List", 
				"validation": {"docstatus": ["=", 1]},
				'field_map': {
					'sales_order': 'name',
					'source': 'ais_source',
					"set_warehouse": "parent_warehouse"
				}
			},
			"Sales Order Item": {
				"doctype": "Pick List Item",
				"field_map": {"parent": "sales_order", "name": "sales_order_item"},
				"postprocess": update_item_quantity,
				"condition": should_pick_order_item,
			}
		},
		target_doc,
	)

	doc.purpose = "Delivery"
	
	# Metactical Customization: Check if it's from previously canceled sales order and
	# default to manual picking
	is_reprint = frappe.db.exists('Pick List Item', {'sales_order': source_name, 'docstatus': 2})
	if is_reprint:
		doc.reprinted = 1
	doc.pick_manually = 1

	#doc.set_item_locations()

	return doc
	
	
@frappe.whitelist()
def save_cancel_reason(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc("Pick List", args.docname)
	doc.db_set("cancel_reason", args.cancel_reason, notify=True)
	doc.db_set("pick_list_cancel_date", datetime.datetime.now(timezone('US/Pacific')).strftime("%Y-%m-%d %H:%M:%S"))
	return 'Success'
	
@frappe.whitelist()
def create_delivery_note(source_name, target_doc=None):
	pick_list = frappe.get_doc("Pick List", source_name)
	validate_item_locations(pick_list)
	sales_dict = dict()
	sales_orders = []
	delivery_note = None
	for location in pick_list.locations:
		if location.sales_order:
			sales_orders.append(
				frappe.db.get_value(
					"Sales Order", location.sales_order, ["customer", "name as sales_order"], as_dict=True
				)
			)

	for customer, rows in groupby(sales_orders, key=lambda so: so["customer"]):
		sales_dict[customer] = {row.sales_order for row in rows}

	if sales_dict:
		delivery_note = create_dn_with_so(sales_dict, pick_list)

	if not all(item.sales_order for item in pick_list.locations):
		delivery_note = create_dn_wo_so(pick_list)
		
	# Metactical Customization: Get source from pick list if set
	if pick_list.ais_source:
		delivery_note.source = pick_list.ais_source

	#frappe.msgprint(_("Delivery Note(s) created for the Pick List"))
	return delivery_note