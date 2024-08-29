# -*- coding: utf-8 -*-
# Copyright (c) 2021, Techlift Technologies and Contributors
# See license.txt
from __future__ import unicode_literals
import frappe
from frappe.core.doctype.data_import.data_import import import_doc
import unittest, os
from unittest.mock import Mock, patch
from metactical.api.shipstation import orders_shipped_webhook, create_shipstation_orders
import json
from requests import Request
from datetime import datetime
import requests

class TestShipstationSettings(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		
		#Import custom fields
		import_doc(path=frappe.get_app_path("metactical", "metactical/doctype/shipstation_settings/test_data/custom_field.json"))
			
		frappe.reload_doctype("Delivery Note")
		
		#So it doesn't raise insuficient stock error
		frappe.db.set_value("Stock Settings", None, "allow_negative_stock", 1)
		
		self.setup_shipstation()
		self.create_delivery_note()

	def tearDown(self):
		frappe.db.rollback()
		
	def setup_shipstation(self):
		#Create lead source
		if not frappe.db.exists("Lead Source", "_Test_Lead_Source"):
			lead_source = frappe.get_doc({
				"doctype": "Lead Source",
				"source_name": "_Test_Lead_Source"
			})
			self.lead_source = lead_source.insert(ignore_permissions=True)
		else:
			self.lead_source = frappe.get_doc("Lead Source", "_Test_Lead_Source")
		
		shipstation_settings = frappe.new_doc("Shipstation Settings")
		shipstation_settings.update({
			"api_key": '_Test_98980898989898',
			"api_secret": '98989898989898',
			"shipstation_user": "web6@dogtagbuilder.com"
		})
		
		#Map lead source
		shipstation_settings.append("store_mapping", {
			"source": self.lead_source.name,
			"store_id": "_Test_Store_ID"
		})

		#Create supplier
		existing_group = frappe.db.exists("Supplier Group", {"supplier_group_name": "_Test Supplier Group"})
		if not existing_group:
			supplier_group = frappe.new_doc("Supplier Group")
			supplier_group.update({
				"supplier_group_name": "_Test Supplier Group"
			})
			supplier_group.insert()
		else:
			supplier_group = frappe.get_doc("Supplier Group", existing_group)

		supplier_exists = frappe.db.exists("Supplier", {"supplier_name": "_Test Supplier"})
		if not supplier_exists:
			supplier = frappe.new_doc("Supplier")
			supplier.update({
				"supplier_name": "_Test Supplier",
				"supplier_group": supplier_group.name
			})
			supplier.insert()
		else:
			supplier = frappe.get_doc("Supplier", supplier_exists)
		self.supplier = supplier.name
		
		#Map transporter
		shipstation_settings.append("transporter_mapping", {
			"transporter": supplier.name,
			"carrier_code": "canada_post"
		})
		
		self.settingId = shipstation_settings.insert(ignore_permissions=True)
		
	def create_delivery_note(self):
    # Check and create test company
		if not frappe.db.exists("Company", {"company_name": "_Test Company"}):
			company = frappe.get_doc({
				"doctype": "Company",
				"company_name": "_Test Company",
				"abbr": "_TC",
				"default_currency": "USD"
			}).insert(ignore_permissions=True)
		else:
			company = frappe.get_doc("Company", {"company_name": "_Test Company"})

		# Check and create test warehouse
		if not frappe.db.exists("Warehouse", {"warehouse_name": "_Test Warehouse"}):
			warehouse = frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": "_Test Warehouse",
				"company": company.name
			}).insert(ignore_permissions=True)
		else:
			warehouse = frappe.get_doc("Warehouse", {"warehouse_name": "_Test Warehouse"})

		# Check and create test UOM
		if not frappe.db.exists("UOM", {"uom_name": "_Test UOM"}):
			uom = frappe.get_doc({
				"doctype": "UOM",
				"uom_name": "_Test UOM"
			}).insert(ignore_permissions=True)
		else:
			uom = frappe.get_doc("UOM", {"uom_name": "_Test UOM"})

		# Check and create test item
		if not frappe.db.exists("Item", {"item_code": "_Test Item"}):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": "_Test Item",
				"item_name": "_Test Item",
				"description": "_Test Item",
				"stock_uom": uom.name,
				"is_stock_item": 1
			}).insert(ignore_permissions=True)
		else:
			item = frappe.get_doc("Item", {"item_code": "_Test Item"})

		# Check and create test company address
		if not frappe.db.exists("Address", {"address_title": "_Test Company Address"}):
			company_address = frappe.get_doc({
				"doctype": "Address",
				"address_title": "_Test Company Address",
				"address_type": "Billing",
				"address_line1": "123 Test Street",
				"city": "Test City",
				"country": "Canada",
				"company": company.name
			}).insert(ignore_permissions=True)
		else:
			company_address = frappe.get_doc("Address", {"address_title": "_Test Company Address"})

		# Check and create test customer group
		if not frappe.db.exists("Customer Group", {"customer_group_name": "_Test Customer Group"}):
			customer_group = frappe.get_doc({
				"doctype": "Customer Group",
				"customer_group_name": "_Test Customer Group"
			}).insert(ignore_permissions=True)
		else:
			customer_group = frappe.get_doc("Customer Group", {"customer_group_name": "_Test Customer Group"})

		# Check and create test territory
		if not frappe.db.exists("Territory", {"territory_name": "_Test Territory"}):
			territory = frappe.get_doc({
				"doctype": "Territory",
				"territory_name": "_Test Territory"
			}).insert(ignore_permissions=True)
		else:
			territory = frappe.get_doc("Territory", {"territory_name": "_Test Territory"})

		# Check and create test customer
		if not frappe.db.exists("Customer", {"customer_name": "_Test Customer1"}):
			customer = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": "_Test Customer1",
				"customer_type": "Individual",
				"customer_group": customer_group.name,
				"territory": territory.name,
				"default_price_list": "_Test Shipstation Selling Price List",
				"default_currency": "USD"
			}).insert(ignore_permissions=True)
		else:
			customer = frappe.get_doc("Customer", {"customer_name": "_Test Customer1"})

		# Check and create test shipping address linked to customer
		if not frappe.db.exists("Address", {"address_title": "_Test Shipping Address"}):
			shipping_address = frappe.get_doc({
				"doctype": "Address",
				"address_title": "_Test Shipping Address",
				"address_type": "Shipping",
				"address_line1": "456 Test Avenue",
				"city": "Test City",
				"country": "Canada",
				"links": [{
					"link_doctype": "Customer",
					"link_name": customer.name
				}]
			}).insert(ignore_permissions=True)
		else:
			shipping_address = frappe.get_doc("Address", {"address_title": "_Test Shipping Address"})

		# Check and create test contact person linked to customer
		if not frappe.db.exists("Contact", {"first_name": "_Test Contact"}):
			contact_person = frappe.get_doc({
				"doctype": "Contact",
				"first_name": "_Test Contact",
				"links": [{
					"link_doctype": "Customer",
					"link_name": customer.name
				}]
			}).insert(ignore_permissions=True)
		else:
			contact_person = frappe.get_doc("Contact", {"first_name": "_Test Contact"})

		# Create Pick List
		pick_list = frappe.get_doc({
			"doctype": "Pick List",
			"company": company.name,
			"purpose": "Delivery",
			"locations": [{
				"item_code": item.item_code,
				"item_name": item.item_name,
				"description": item.description,
				"qty": 1,
				"uom": uom.name,
				"warehouse": warehouse.name,
				"picked_qty": 1,
				"stock_qty": 1
			}]
		}).insert(ignore_permissions=True)
		self.pick_list = pick_list.name

		# Create Delivery Note
		delivery_note = frappe.get_doc({
			"doctype": "Delivery Note",
			"company": company.name,
			"customer": customer.name,
			"currency": "USD",
			"conversion_rate": 1,
			"selling_price_list": "_Test Shipstation Selling Price List",
			"price_list_currency": "USD",
			"plc_conversion_rate": 1,
			"pick_list": self.pick_list,
			"source": self.lead_source.name,
			"company_address": company_address.name,
			"shipping_address_name": shipping_address.name,
			"contact_person": contact_person.name,
			"items": [{
				"item_code": item.item_code,
				"item_name": item.item_name,
				"description": item.description,
				"qty": 1,
				"stock_uom": uom.name,
				"uom": uom.name,
				"conversion_factor": 1,
				"warehouse": warehouse.name,
				"rate": 20
			}]
		}).insert(ignore_permissions=True)
		self.delivery_note = delivery_note.name
		
	def test_webhook(self):
		with patch('metactical.api.shipstation.requests.get') as mock_get:
			
			with open (os.path.join(os.path.dirname(__file__), 'test_data', 'shipments.json')) as shipment_json:
				shipment_json = json.load(shipment_json)
				shipment = shipment_json.get("shipments")[0]
				shipment["orderKey"] = self.pick_list
				shipment["orderNumber"] = self.pick_list
			mock_get.return_value.json.return_value = shipment_json
			
			#Mock the request URL
			url = "http://deverp.metactical.com/api/method/metactical.api.shipstation.orders_shipped_webhook?settingid=" + self.settingId.name
			data = '{"resource_url": "https://test.shipstationurl.com", "resource_type": "SHIP_NOTIFY"}'
			#frappe.request.url = "http://deverp.metactical.com/api/method/metactical.api.shipstation.orders_shipped_webhook?settingid=" + self.settingId.name
			frappe.request = Request('Post', url, data=data)
			orders_shipped_webhook()
			
			#Verify the delivery note is submitted and the shipment data has been saved
			shipment = shipment_json.get("shipments")[0]
			delivery_note_name = frappe.db.get_value("Delivery Note", {"pick_list": shipment.get("orderKey")})
			delivery_note = frappe.get_doc("Delivery Note", delivery_note_name)
			
			self.assertEqual(delivery_note.docstatus, 1)
			self.assertEqual(delivery_note.transporter, self.supplier)
			self.assertEqual(delivery_note.lr_no, "7302361059843272")
			self.assertEqual(delivery_note.ais_package_weight, "192.0 ounces")
			self.assertEqual(delivery_note.lr_date, datetime.date(datetime(2021, 9, 27)))
			self.assertEqual(delivery_note.ais_shipment_cost, 22.25)
			self.assertEqual(delivery_note.ais_package_size, "30.0l x 10.0w x 10.0h")
			self.assertEqual(delivery_note.ais_updated_by_shipstation, 1)

	@patch('metactical.api.shipstation.requests')
	def test_multiple_settings(self, requests_mock):
		def handle_post(url, auth, json):
			auth1 = (self.settingId.api_key, self.settingId.get_password('api_secret'))
			auth2 = (second_setting.api_key, second_setting.get_password('api_secret'))

			if auth == auth1:
				response_mock = Mock()
				response_mock.status_code = 200
				response_mock.json.return_value = {'orderId': '_Test_orderId1'}
				return response_mock
			elif auth == auth2:
				response_mock = Mock()
				response_mock.status_code = 200
				response_mock.json.return_value = {'orderId': '_Test_orderId2'}
				return response_mock
			elif auth == ('bad_auth_key', 'bad_auth_secret'):
				# Simulate a 400 Bad Request error for invalid credentials
				response_mock = Mock()
				response_mock.status_code = 400
				response_mock.text = "Bad Request"
				return response_mock
			elif auth == ('maintenance_auth_key', 'maintenance_auth_secret'):
				# Simulate a 503 Service Unavailable error for maintenance
				response_mock = Mock()
				response_mock.status_code = 503
				response_mock.text = "Service Unavailable"
				return response_mock
			else:
				response_mock = Mock()
				response_mock.status_code = 200
				response_mock.json.return_value = {'orderId': '_Test_otherId'}
				return response_mock

		# Add second setting
		shipstation_settings = frappe.new_doc("Shipstation Settings")
		shipstation_settings.update({
			"api_key": '_Test_98980898989890',
			"api_secret": '98989898989898',
			"shipstation_user": "Administrator"
		})
		
		# Map lead source
		shipstation_settings.append("store_mapping", {
			"source": self.lead_source.name,
			"store_id": "_Test_Store_ID"
		})
		
		# Map transporter
		shipstation_settings.append("transporter_mapping", {
			"transporter": self.supplier,
			"carrier_code": "canada_post"
		})
		second_setting = shipstation_settings.insert(ignore_permissions=True)
		
		# Test creating ShipStation orders
		requests_mock.post = Mock(side_effect=handle_post)

		# Test valid case
		create_shipstation_orders(self.delivery_note)
		
		# Verify the delivery note has been saved with the 2 orderIds
		orderIds = []
		delivery_note = frappe.get_doc('Delivery Note', self.delivery_note)
		for row in delivery_note.ais_shipstation_order_ids:
			orderIds.append(row.shipstation_order_id)
		
		assert '_Test_orderId1' in orderIds
		assert '_Test_orderId2' in orderIds

		# Test 400 Bad Request case
		with patch.object(self.settingId, 'api_key', new='bad_auth_key'), \
			patch.object(self.settingId, 'get_password', return_value='bad_auth_secret'):
			try:
				create_shipstation_orders(self.delivery_note)
			except Exception as e:
				assert isinstance(e, requests.exceptions.HTTPError)
				assert "400" in str(e)

		# Test 503 Service Unavailable case
		with patch.object(self.settingId, 'api_key', new='maintenance_auth_key'), \
			patch.object(self.settingId, 'get_password', return_value='maintenance_auth_secret'):
			try:
				create_shipstation_orders(self.delivery_note)
			except Exception as e:
				assert isinstance(e, requests.exceptions.HTTPError)
				assert "503" in str(e)
		
	@patch('metactical.api.shipstation.requests')
	def test_multiple_settings_webhook(self, requests_mock):
		def handle_get(url, auth):
			with open (os.path.join(os.path.dirname(__file__), 'test_data', 'shipments.json')) as shipment_json:
				shipment_json = json.load(shipment_json)
				shipment = shipment_json.get("shipments")[0]
				shipment["orderKey"] = self.pick_list
				shipment["orderNumber"] = self.pick_list
			response_mock = Mock()
			response_mock.status_code = 200
			response_mock.json.return_value = shipment_json
			return response_mock
			
		def handle_delete(url, auth):
			#if called with the webhook authentication raise an error
			webhook_auth = (self.settingId.api_key, self.settingId.get_password('api_secret'))
			if auth == webhook_auth:
				raise RuntimeError("Requests delete called with webhook settings")
			else:
				response_mock = Mock()
				response_mock.status_code = 200
				return response_mock
		
		#Add second setting
		shipstation_settings = frappe.new_doc("Shipstation Settings")
		shipstation_settings.update({
			"api_key": '_Test_98980898989890',
			"api_secret": '98989898989898',
			"shipstation_user": "Administrator"
		})
		
		#Map lead source
		shipstation_settings.append("store_mapping", {
			"source": self.lead_source.name,
			"store_id": "_Test_Store_ID"
		})
		
		#Map transporter
		shipstation_settings.append("transporter_mapping", {
			"transporter": self.supplier,
			"carrier_code": "canada_post"
		})
		second_setting = shipstation_settings.insert(ignore_permissions=True)
		
		#Add the two settings (orderIds) to the delivery note
		delivery_note = frappe.get_doc('Delivery Note', self.delivery_note)
		order_table = frappe.new_doc('Shipstation Order ID', delivery_note, 'ais_shipstation_order_ids')
		order_table.update({
						'settings_id': self.settingId.name,
						'shipstation_order_id': '_Test_orderId'
					})
		order_table.save()
		order_table = frappe.new_doc('Shipstation Order ID', delivery_note, 'ais_shipstation_order_ids')
		order_table.update({
						'settings_id': second_setting.name,
						'shipstation_order_id': '_Test_orderId2'
					})
		order_table.save()
		
		#Mock the request URL
		url = "http://deverp.metactical.com/api/method/metactical.api.shipstation.orders_shipped_webhook?settingid=" + self.settingId.name
		data = '{"resource_url": "https://test.shipstationurl.com", "resource_type": "SHIP_NOTIFY"}'
		#frappe.request.url = "http://deverp.metactical.com/api/method/metactical.api.shipstation.orders_shipped_webhook?settingid=" + self.settingId.name
		frappe.request = Request('Post', url, data=data)
		
		requests_mock.get = Mock(side_effect=handle_get)
		requests_mock.delete = Mock(side_effect=handle_delete)
		orders_shipped_webhook()
		
		#Assert delete called with second authentication settings
		auth = (second_setting.api_key, second_setting.get_password('api_secret'))
		requests_mock.delete.assert_called_with('https://ssapi.shipstation.com/orders/_Test_orderId2', auth=auth)
		
		#Verify the delivery note is submitted and the shipment data has been saved
		delivery_note_name = frappe.db.get_value("Delivery Note", {"pick_list": self.pick_list})
		delivery_note = frappe.get_doc("Delivery Note", delivery_note_name)
		
		self.assertEqual(delivery_note.docstatus, 1)
		self.assertEqual(delivery_note.transporter, self.supplier)
		self.assertEqual(delivery_note.lr_no, "7302361059843272")
		self.assertEqual(delivery_note.ais_package_weight, "192.0 ounces")
		self.assertEqual(delivery_note.lr_date, datetime.date(datetime(2021, 9, 27)))
		self.assertEqual(delivery_note.ais_shipment_cost, 22.25)
		self.assertEqual(delivery_note.ais_package_size, "30.0l x 10.0w x 10.0h")
		self.assertEqual(delivery_note.ais_updated_by_shipstation, 1)