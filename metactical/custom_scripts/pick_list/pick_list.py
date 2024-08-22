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
from frappe import _, msgprint
from frappe.utils.nestedset import get_descendants_of

class CustomPickList(PickList):
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

@frappe.whitelist()
def create_pick_list(source_name, target_doc=None):
	from erpnext.stock.doctype.packed_item.packed_item import is_product_bundle

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
