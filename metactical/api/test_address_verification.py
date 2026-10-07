# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# See license.txt

from __future__ import unicode_literals
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from metactical.api.address_verification import (
	AddressSubmissionResult,
	CanaddrPermissionError,
	CanaddrValidationError,
	submit_address,
	verify_shipping_address,
)


def _mock_response(status_code=200, json_data=None, text=""):
	response = MagicMock()
	response.status_code = status_code
	response.text = text
	response.json.return_value = json_data or {}
	if status_code >= 400:
		response.raise_for_status.side_effect = Exception("HTTP {0}".format(status_code))
	else:
		response.raise_for_status.return_value = None
	return response


class TestSubmitAddress(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_single("Address Verification Settings")
		settings.base_url = "https://address.storebuilder.com"
		settings.api_key = "test-api-key"
		settings.timeout = 10
		settings.save(ignore_permissions=True)

	@patch("metactical.api.address_verification.requests.post")
	def test_success_insert(self, mock_post):
		mock_post.return_value = _mock_response(
			201,
			{
				"id": "abc123",
				"number": "123",
				"street": "Test Street",
				"unit": None,
				"city": "Toronto",
				"province": "Ontario",
				"postal_code": "M4C1A1",
				"source": "Melissa",
				"duplicate": False,
			},
		)

		result = submit_address("123", "Test Street", "Toronto", "Ontario", "M4C1A1")

		self.assertIsInstance(result, AddressSubmissionResult)
		self.assertEqual(result.id, "abc123")
		self.assertFalse(result.duplicate)
		mock_post.assert_called_once()

	@patch("metactical.api.address_verification.requests.post")
	def test_success_duplicate(self, mock_post):
		mock_post.return_value = _mock_response(
			201,
			{
				"id": "abc123",
				"number": "123",
				"street": "Test Street",
				"unit": None,
				"city": "Toronto",
				"province": "Ontario",
				"postal_code": "M4C1A1",
				"source": "Melissa",
				"duplicate": True,
			},
		)

		result = submit_address("123", "Test Street", "Toronto", "Ontario", "M4C1A1")

		self.assertTrue(result.duplicate)
		mock_post.assert_called_once()

	@patch("metactical.api.address_verification.requests.post")
	def test_403_raises_permission_error_without_retry(self, mock_post):
		mock_post.return_value = _mock_response(403, {"error": "forbidden"}, text="forbidden")

		with self.assertRaises(CanaddrPermissionError):
			submit_address("123", "Test Street", "Toronto", "Ontario", "M4C1A1")

		mock_post.assert_called_once()

	@patch("metactical.api.address_verification.requests.post")
	def test_422_raises_validation_error_without_retry(self, mock_post):
		mock_post.return_value = _mock_response(
			422, {"error": "unrecognized province"}, text="unrecognized province"
		)

		with self.assertRaises(CanaddrValidationError):
			submit_address("123", "Test Street", "Toronto", "Bad Province", "M4C1A1")

		mock_post.assert_called_once()

	@patch("metactical.api.address_verification.time.sleep")
	@patch("metactical.api.address_verification.requests.post")
	def test_5xx_exhausts_retries(self, mock_post, mock_sleep):
		mock_post.return_value = _mock_response(500, {"error": "server error"}, text="server error")

		with self.assertRaises(Exception):
			submit_address("123", "Test Street", "Toronto", "Ontario", "M4C1A1")

		self.assertEqual(mock_post.call_count, 3)


class TestVerifyShippingAddressCanaddrSubmission(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_single("Address Verification Settings")
		settings.enabled = 1
		settings.base_url = "https://address.storebuilder.com"
		settings.api_key = "test-api-key"
		settings.timeout = 10
		settings.enable_melissa_fallback = 1
		settings.melissa_key = "test-melissa-key"
		settings.save(ignore_permissions=True)

		cls.address = frappe.get_doc({
			"doctype": "Address",
			"address_title": "Canaddr Submission Test Address",
			"address_type": "Billing",
			"address_line1": "123 Test Street",
			"city": "Toronto",
			"state": "Ontario",
			"pincode": "M4C1A1",
			"country": "Canada",
		}).insert(ignore_permissions=True)

		cls.customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Canaddr Submission Test Customer",
		}).insert(ignore_permissions=True)

		item_code = frappe.db.get_value("Item", {"disabled": 0}, "name")
		if not item_code:
			raise Exception("No enabled Item found in this site to build a test Sales Order")

		cls.sales_order = frappe.get_doc({
			"doctype": "Sales Order",
			"customer": cls.customer.name,
			"shipping_address_name": cls.address.name,
			"delivery_date": frappe.utils.add_days(frappe.utils.nowdate(), 7),
			"items": [{"item_code": item_code, "qty": 1, "rate": 1}],
		}).insert(ignore_permissions=True)

	def setUp(self):
		frappe.db.delete("Canaddr Submission Log")
		frappe.db.delete("Melissa Log")

	@staticmethod
	def _verify_response():
		return _mock_response(200, {"match_level": "postal_verified"})

	@staticmethod
	def _unverified_response():
		return _mock_response(200, {"match_level": "unverified"})

	@staticmethod
	def _fully_verified_response():
		return _mock_response(200, {"match_level": "fully_verified"})

	@staticmethod
	def _melissa_verified_response():
		return _mock_response(200, {"Records": [{"Results": "AV25"}]}, text='{"Records": [{"Results": "AV25"}]}')

	@staticmethod
	def _melissa_weak_response():
		return _mock_response(200, {"Records": [{"Results": "AV11"}]}, text='{"Records": [{"Results": "AV11"}]}')

	@staticmethod
	def _canaddr_success_response():
		return _mock_response(
			201,
			{
				"id": "abc123",
				"number": "123",
				"street": "Test Street",
				"unit": None,
				"city": "Toronto",
				"province": "Ontario",
				"postal_code": "M4C1A1",
				"source": "Melissa",
				"duplicate": False,
			},
		)

	@patch("metactical.api.address_verification.requests.post")
	def test_melissa_verified_from_postal_verified_triggers_submission(self, mock_post):
		mock_post.side_effect = [
			self._verify_response(),
			self._melissa_verified_response(),
			self._canaddr_success_response(),
		]

		verify_shipping_address(self.sales_order.name)

		self.assertEqual(mock_post.call_count, 3)
		address_status = frappe.db.get_value("Address", self.address.name, "custom_ais_address_verified")
		address_entity = frappe.db.get_value("Address", self.address.name, "custom_ais_validation_entity")
		self.assertEqual(address_status, "Validated")
		self.assertEqual(address_entity, "Melissa")
		self.assertEqual(frappe.db.count("Canaddr Submission Log"), 1)
		log = frappe.get_last_doc("Canaddr Submission Log")
		self.assertEqual(log.status, "Success")

	@patch("metactical.api.address_verification.requests.post")
	def test_melissa_verified_from_unverified_triggers_submission(self, mock_post):
		mock_post.side_effect = [
			self._unverified_response(),
			self._melissa_verified_response(),
			self._canaddr_success_response(),
		]

		verify_shipping_address(self.sales_order.name)

		self.assertEqual(mock_post.call_count, 3)
		address_status = frappe.db.get_value("Address", self.address.name, "custom_ais_address_verified")
		self.assertEqual(address_status, "Validated")
		self.assertEqual(frappe.db.count("Canaddr Submission Log"), 1)

	@patch("metactical.api.address_verification.time.sleep")
	@patch("metactical.api.address_verification.requests.post")
	def test_submission_failure_does_not_break_verification_result(self, mock_post, mock_sleep):
		mock_post.side_effect = [
			self._verify_response(),
			self._melissa_verified_response(),
			_mock_response(500, {"error": "server error"}, text="server error"),
			_mock_response(500, {"error": "server error"}, text="server error"),
			_mock_response(500, {"error": "server error"}, text="server error"),
		]

		verify_shipping_address(self.sales_order.name)

		address_status = frappe.db.get_value("Address", self.address.name, "custom_ais_address_verified")
		address_entity = frappe.db.get_value("Address", self.address.name, "custom_ais_validation_entity")
		self.assertEqual(address_status, "Validated")
		self.assertEqual(address_entity, "Melissa")
		log = frappe.get_last_doc("Canaddr Submission Log")
		self.assertEqual(log.status, "Error")

	@patch("metactical.api.address_verification.requests.post")
	def test_storebuilder_fully_verified_does_not_call_submit(self, mock_post):
		mock_post.side_effect = [self._fully_verified_response()]

		verify_shipping_address(self.sales_order.name)

		mock_post.assert_called_once()
		self.assertEqual(frappe.db.count("Canaddr Submission Log"), 0)

	@patch("metactical.api.address_verification.requests.post")
	def test_melissa_weak_match_does_not_call_submit(self, mock_post):
		mock_post.side_effect = [
			self._unverified_response(),
			self._melissa_weak_response(),
		]

		verify_shipping_address(self.sales_order.name)

		self.assertEqual(mock_post.call_count, 2)
		self.assertEqual(frappe.db.count("Canaddr Submission Log"), 0)
