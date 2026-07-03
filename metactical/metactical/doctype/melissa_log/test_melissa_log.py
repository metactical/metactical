# Copyright (c) 2026, Storebuilder Commerce Inc and Contributors
# See license.txt

from __future__ import unicode_literals
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from metactical.api.address_verification import verify_with_melissa


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


class TestMelissaLog(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.address = frappe.get_doc({
			"doctype": "Address",
			"address_title": "Melissa Log Test Address",
			"address_type": "Billing",
			"address_line1": "123 Test Street",
			"city": "Toronto",
			"state": "Ontario",
			"pincode": "M4C1A1",
			"country": "Canada",
		}).insert(ignore_permissions=True)

	def setUp(self):
		# FrappeTestCase only rolls back at class teardown, not per test, so
		# clear out rows between tests to keep each test's assertions isolated.
		frappe.db.delete("Melissa Log")

	@patch("metactical.api.address_verification.requests.post")
	def test_fully_verified_creates_success_log(self, mock_post):
		mock_post.return_value = _mock_response(
			200,
			{"Records": [{"Results": "AV25"}]},
			text='{"Records": [{"Results": "AV25"}]}',
		)

		result = verify_with_melissa(self.address, "test-key", 10)

		self.assertEqual(result, ("fully_verified", True, "Address fully verified"))
		mock_post.assert_called_once()

		logs = frappe.get_all(
			"Melissa Log",
			fields=["status", "match_level", "verified", "address", "http_status_code", "request", "response"],
		)
		self.assertEqual(len(logs), 1)
		log = logs[0]
		self.assertEqual(log.status, "Success")
		self.assertEqual(log.match_level, "fully_verified")
		self.assertEqual(log.verified, 1)
		self.assertEqual(log.address, self.address.name)
		self.assertEqual(log.http_status_code, 200)

		# Full request/response payloads are captured, not just a summary.
		sent = json.loads(log.request)
		self.assertEqual(sent["Records"][0]["AddressLine1"], "123 Test Street")
		self.assertEqual(json.loads(log.response)["Records"][0]["Results"], "AV25")

	@patch("metactical.api.address_verification.requests.post")
	def test_partial_match_creates_unverified_success_log(self, mock_post):
		mock_post.return_value = _mock_response(
			200,
			{"Records": [{"Results": "AV11,AE02"}]},
			text='{"Records": [{"Results": "AV11,AE02"}]}',
		)

		result = verify_with_melissa(self.address, "test-key", 10)

		self.assertIsNotNone(result)
		level, verified, detail = result
		self.assertEqual(level, "postal_verified")
		self.assertFalse(verified)

		log = frappe.get_last_doc("Melissa Log")
		self.assertEqual(log.status, "Success")
		self.assertEqual(log.match_level, "postal_verified")
		self.assertEqual(log.verified, 0)
		self.assertIn("street name could not be matched", log.detail)

	@patch("metactical.api.address_verification.requests.post")
	def test_no_records_creates_unverified_log_and_returns_none(self, mock_post):
		mock_post.return_value = _mock_response(200, {"Records": []}, text='{"Records": []}')

		result = verify_with_melissa(self.address, "test-key", 10)

		self.assertIsNone(result)

		log = frappe.get_last_doc("Melissa Log")
		self.assertEqual(log.status, "Success")
		self.assertEqual(log.match_level, "unverified")
		self.assertEqual(log.detail, "No records returned by Melissa")

	@patch("metactical.api.address_verification.requests.post")
	def test_network_failure_creates_error_log(self, mock_post):
		mock_post.side_effect = ConnectionError("boom")

		with patch("metactical.api.address_verification.frappe.log_error") as mock_log_error:
			result = verify_with_melissa(self.address, "test-key", 10)

		self.assertIsNone(result)
		mock_log_error.assert_called_once()

		log = frappe.get_last_doc("Melissa Log")
		self.assertEqual(log.status, "Error")
		self.assertIn("ConnectionError", log.error)

	@patch("metactical.api.address_verification.requests.post")
	def test_http_error_status_is_logged(self, mock_post):
		mock_post.return_value = _mock_response(
			401, {"error": "unauthorized"}, text='{"error": "unauthorized"}'
		)

		with patch("metactical.api.address_verification.frappe.log_error"):
			result = verify_with_melissa(self.address, "test-key", 10)

		self.assertIsNone(result)

		log = frappe.get_last_doc("Melissa Log")
		self.assertEqual(log.status, "Error")
		self.assertEqual(log.http_status_code, 401)
		self.assertEqual(log.response, '{"error": "unauthorized"}')

	def test_missing_address_line1_does_not_call_melissa_or_log(self):
		bad_address = {"name": "no-address-line1"}
		with patch("metactical.api.address_verification.requests.post") as mock_post:
			result = verify_with_melissa(bad_address, "test-key", 10)

		mock_post.assert_not_called()
		self.assertIsNone(result)
		self.assertEqual(frappe.db.count("Melissa Log"), 0)

	def test_sales_order_name_is_recorded_on_log(self):
		existing_so = frappe.get_all("Sales Order", limit=1, pluck="name")
		if not existing_so:
			self.skipTest("No existing Sales Order in this site to link against")

		with patch("metactical.api.address_verification.requests.post") as mock_post:
			mock_post.return_value = _mock_response(
				200, {"Records": [{"Results": "AV25"}]}, text="{}"
			)
			verify_with_melissa(self.address, "test-key", 10, sales_order_name=existing_so[0])

		log = frappe.get_last_doc("Melissa Log")
		self.assertEqual(log.sales_order, existing_so[0])
