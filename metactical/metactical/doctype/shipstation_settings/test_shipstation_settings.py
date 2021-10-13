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

class TestShipstationSettings(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		
		#Import custom fields
		import_doc(path=frappe.get_app_path("metactical", "metactical/doctype/shipstation_settings/test_data/custom_field.json"),
			ignore_links=True, overwrite=True)
			
		frappe.reload_doctype("Delivery Note")
		
		#So it doesn't raise insuficient stock error
		frappe.db.set_value("Stock Settings", None, "allow_negative_stock", 1)
		
		self.setup_shipstation()
		self.create_delivery_note()
		
	def setup_shipstation(self):
		#Create lead source
		lead_source = frappe.get_doc({
			"doctype": "Lead Source",
			"source_name": "_Test_Lead_Source"
		})
		self.lead_source = lead_source.insert(ignore_if_duplicate=True)
		
		shipstation_settings = frappe.new_doc("Shipstation Settings")
		shipstation_settings.update({
			"api_key": '_Test_98980898989898',
			"api_secret": '98989898989898',
		})
		
		#Map lead source
		shipstation_settings.append("store_mapping", {
			"source": lead_source.name,
			"store_id": "_Test_Store_ID"
		})
		
		#Map transporter
		shipstation_settings.append("transporter_mapping", {
			"transporter": "_Test Supplier",
			"carrier_code": "canada_post"
		})
		
		self.settingId = shipstation_settings.insert(ignore_permissions=True)
		
	def create_delivery_note(self):
		#Create customer
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "_Test Customer",
			"customer_type": "Individual",
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory"
		}).save(ignore_permissions=True)
		
		#Create Pick List
		pick_list = frappe.get_doc({
			"doctype": "Pick List",
			"docname": "_Test Pick List",
			"company": "_Test Company"
		}).insert(ignore_if_duplicate=True)
		self.pick_list = pick_list.name
		
		#Create Delivery Note
		#import_doc(path=frappe.get_app_path("metactical", "metactical/doctype/shipstation_settings/test_data/delivery_note.json"),
		#	ignore_links=True, overwrite=True)
		delivery_note = frappe.get_doc({
			"doctype": "Delivery Note",
			"company": "_Test Company",
			"customer": "_Test Customer",
			"currency": "USD",
			"conversion_rate": 1,
			"selling_price_list": "Standard Selling",
			"price_list_currency": "USD",
			"plc_conversion_rate": 1,
			"pick_list": self.pick_list,
			"source": self.lead_source.name
		})
		delivery_note.append("items", {
			"item_code": "_Test Item",
			"item_name": "_Test Item",
			"description": "_Test Item",
			"qty": 1,
			"stock_uom": "_Test UOM",
			"uom": "_Test UOM",
			"conversion_factor": 1
		})
		self.delivery_note = delivery_note.insert(ignore_permissions=True)
		
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
			self.assertEqual(delivery_note.transporter, "_Test Supplier")
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
			else:
				response_mock = Mock()
				response_mock.status_code = 200
				response_mock.json.return_value = {'orderId': '_Test_otherId'}
				return response_mock
				
		
		#Add second setting
		shipstation_settings = frappe.new_doc("Shipstation Settings")
		shipstation_settings.update({
			"api_key": '_Test_98980898989890',
			"api_secret": '98989898989898',
		})
		
		#Map lead source
		shipstation_settings.append("store_mapping", {
			"source": self.lead_source.name,
			"store_id": "_Test_Store_ID"
		})
		
		#Map transporter
		shipstation_settings.append("transporter_mapping", {
			"transporter": "_Test Supplier",
			"carrier_code": "canada_post"
		})
		second_setting = shipstation_settings.insert(ignore_permissions=True)
		
		#Test creating shipstation orders
		requests_mock.post = Mock(side_effect=handle_post)
		create_shipstation_orders(self.delivery_note.name)
		
		#Verify the delivery note has been saved with the 2 orderIds
		orderIds = []
		delivery_note = frappe.get_doc('Delivery Note', self.delivery_note.name)
		for row in delivery_note.ais_shipstation_order_ids:
			orderIds.append(row.shipstation_order_id)
		
		assert '_Test_orderId1' in orderIds
		assert '_Test_orderId2' in orderIds
		
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
		})
		
		#Map lead source
		shipstation_settings.append("store_mapping", {
			"source": self.lead_source.name,
			"store_id": "_Test_Store_ID"
		})
		
		#Map transporter
		shipstation_settings.append("transporter_mapping", {
			"transporter": "_Test Supplier",
			"carrier_code": "canada_post"
		})
		second_setting = shipstation_settings.insert(ignore_permissions=True)
		
		#Add the two settings (orderIds) to the delivery note
		delivery_note = frappe.get_doc('Delivery Note', self.delivery_note.name)
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
		self.assertEqual(delivery_note.transporter, "_Test Supplier")
		self.assertEqual(delivery_note.lr_no, "7302361059843272")
		self.assertEqual(delivery_note.ais_package_weight, "192.0 ounces")
		self.assertEqual(delivery_note.lr_date, datetime.date(datetime(2021, 9, 27)))
		self.assertEqual(delivery_note.ais_shipment_cost, 22.25)
		self.assertEqual(delivery_note.ais_package_size, "30.0l x 10.0w x 10.0h")
		self.assertEqual(delivery_note.ais_updated_by_shipstation, 1)
