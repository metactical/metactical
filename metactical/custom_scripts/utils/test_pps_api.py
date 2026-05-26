# Copyright (c) 2024, Techlift Technologies and Contributors
# See license.txt

import unittest
from unittest.mock import MagicMock, patch
import frappe
from frappe.utils import add_days, nowdate

import metactical.custom_scripts.utils.pps_api as pps_api
from metactical.custom_scripts.utils.pps_api import (
    pack_order,
    flatten_packing_slip_items,
    validate_packing_slips,
    create_pick_list_for_order,
)


def make_test_sales_order(item_list=None):
    """Create and submit a test Sales Order with a shipping address."""
    customer = "CS-25-00099"

    # Ensure a shipping address exists for the customer
    address_name = "CS-25-00117-Shipping"
    if not frappe.db.exists("Address", address_name):
        addr = frappe.get_doc({
            "doctype": "Address",
            "address_title": "_Test PPS Shipping Address",
            "address_type": "Shipping",
            "address_line1": "123 Test Street",
            "city": "Test City",
            "country": "Canada",
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        })
        addr.insert(ignore_permissions=True)

    company = "International Camouflage Ltd"
    company_currency = frappe.get_cached_value("Company", company, "default_currency") or "CAD"

    so = frappe.new_doc("Sales Order")
    so.company = company
    so.customer = customer
    so.currency = company_currency
    so.set("company_currency", company_currency)
    so.conversion_rate = 1
    so.exchange_rate = 1
    so.transaction_date = nowdate()
    so.delivery_date = add_days(nowdate(), 7)
    so.shipping_address_name = address_name
    so.taxes_and_charges = "Alberta - ICL"
    so.source = "Website - Gorilla"

    if item_list:
        for item in item_list:
            so.append("items", item)
    else:
        so.append("items", {
            "item_code": "RFIWPG130-1",
            "warehouse": "R01-Gor-Active Stock - ICL",
            "qty": 2,
            "rate": 100,
        })

    so.set_missing_values()
    so.insert(ignore_permissions=True)
    so.submit()
    return so


class TestFlattenPackingSlipItems(unittest.TestCase):
    def test_single_slip_single_item(self):
        packing_slips = [{
            "items": [{"item_code": "ITEM-001", "quantity": 1, "sales_order_item": "abc123"}]
        }]
        result = flatten_packing_slip_items(packing_slips)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_code"], "ITEM-001")

    def test_multiple_slips_multiple_items(self):
        packing_slips = [
            {"items": [
                {"item_code": "A", "quantity": 1, "sales_order_item": "a1"},
                {"item_code": "B", "quantity": 2, "sales_order_item": "b1"},
            ]},
            {"items": [
                {"item_code": "C", "quantity": 3, "sales_order_item": "c1"},
            ]},
        ]
        result = flatten_packing_slip_items(packing_slips)
        self.assertEqual(len(result), 3)

    def test_empty_packing_slips(self):
        self.assertEqual(flatten_packing_slip_items([]), [])

    def test_slip_with_no_items_key(self):
        result = flatten_packing_slip_items([{"parcel_template": "BOX 1"}])
        self.assertEqual(result, [])


class TestValidatePackingSlips(unittest.TestCase):
    def setUp(self):
        # Mock frappe.db.get_value to avoid hitting the DB in unit tests
        self.patcher = patch("metactical.custom_scripts.utils.pps_api.frappe")
        self.mock_frappe = self.patcher.start()
        self.mock_frappe.db.get_value.return_value = frappe._dict({
            "item_code": "ITEM-001",
            "qty": 5,
        })

    def tearDown(self):
        self.patcher.stop()

    def test_missing_items_in_slip(self):
        packing_slips = [{"items": []}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("no items" in e.lower() for e in errors))

    def test_missing_sales_order_item(self):
        packing_slips = [{"items": [{"item_code": "ITEM-001", "quantity": 1}]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("sales_order_item" in e.lower() for e in errors))

    def test_zero_quantity(self):
        packing_slips = [{"items": [{
            "item_code": "ITEM-001",
            "quantity": 0,
            "sales_order_item": "abc123",
        }]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("quantity" in e.lower() for e in errors))

    def test_negative_quantity(self):
        packing_slips = [{"items": [{
            "item_code": "ITEM-001",
            "quantity": -1,
            "sales_order_item": "abc123",
        }]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("quantity" in e.lower() for e in errors))

    def test_so_item_not_found(self):
        self.mock_frappe.db.get_value.return_value = None
        packing_slips = [{"items": [{
            "item_code": "ITEM-001",
            "quantity": 1,
            "sales_order_item": "missing_id",
        }]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("does not exist" in e.lower() for e in errors))

    def test_item_code_mismatch(self):
        self.mock_frappe.db.get_value.return_value = frappe._dict({
            "item_code": "DIFFERENT-ITEM",
            "qty": 5,
        })
        packing_slips = [{"items": [{
            "item_code": "ITEM-001",
            "quantity": 1,
            "sales_order_item": "abc123",
        }]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("mismatch" in e.lower() for e in errors))

    def test_quantity_exceeds_ordered(self):
        self.mock_frappe.db.get_value.return_value = frappe._dict({
            "item_code": "ITEM-001",
            "qty": 2,
        })
        packing_slips = [{"items": [{
            "item_code": "ITEM-001",
            "quantity": 10,
            "sales_order_item": "abc123",
        }]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertTrue(any("exceeds" in e.lower() for e in errors))

    def test_valid_packing_slip(self):
        packing_slips = [{"items": [{
            "item_code": "ITEM-001",
            "quantity": 2,
            "sales_order_item": "abc123",
        }]}]
        errors = validate_packing_slips(packing_slips, "SO-001")
        self.assertEqual(errors, [])


class TestPackOrderValidation(unittest.TestCase):
    """Unit tests for pack_order input validation (no DB)."""

    def _call_with_form_dict(self, data):
        with patch("metactical.custom_scripts.utils.pps_api.frappe") as mock_frappe:
            mock_frappe.form_dict = data
            mock_frappe._dict = frappe._dict
            # Re-import the function so it picks up the mock
            from metactical.custom_scripts.utils import pps_api
            with patch.object(pps_api, "frappe", mock_frappe):
                return pps_api.pack_order()

    def test_missing_order_id_returns_error(self):
        result = self._call_with_form_dict({"packing_slips": []})
        self.assertEqual(result["status"], "error")
        self.assertIn("Order ID", result["message"])

    def test_missing_packing_slips_returns_error(self):
        result = self._call_with_form_dict({"order_id": "SAL-ORD-2026-00001"})
        self.assertEqual(result["status"], "error")
        self.assertIn("Packing slips", result["message"])

    def test_empty_packing_slips_returns_error(self):
        result = self._call_with_form_dict({
            "order_id": "SAL-ORD-2026-00001",
            "packing_slips": [],
        })
        self.assertEqual(result["status"], "error")
        self.assertIn("Packing slips", result["message"])


class TestPackOrderIntegration(unittest.TestCase):
    """
    Integration tests for pack_order().

    Real SO, Pick List, Delivery Note and Packing Slip documents are created.
    Only call_pps_api_to_pack_order is mocked — it is an external service
    placeholder and not part of the ERPNext document flow.

    frappe.local.form_dict is set directly (the mechanism pack_order reads
    through frappe.form_dict) so we call pack_order() with no extra wrapping.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
        frappe.db.commit()

    def _set_form_dict(self, order_id, packing_slips_payload):
        frappe.local.form_dict = frappe._dict({
            "order_id": order_id,
            "packing_slips": packing_slips_payload,
        })

    def _pack(self, order_id, packing_slips_payload):
        """Set form_dict and call pack_order(), mocking only the external PPS call."""
        self._set_form_dict(order_id, packing_slips_payload)
        with patch.object(pps_api, "call_pps_api_to_pack_order", return_value={"success": True}):
            return pack_order()

    # ------------------------------------------------------------------
    # Happy-path: real documents must exist in DB after each call
    # ------------------------------------------------------------------

    def test_creates_pick_list_in_db(self):
        so = make_test_sales_order()
        payload = [{
            "parcel_template": "BOX 1",
            "dimensions": {"height": 10, "width": 9, "length": 5},
            "weight": 2,
            "items": [{
                "item_code": so.items[0].item_code,
                "quantity": int(so.items[0].qty),
                "sales_order_item": so.items[0].name,
            }],
        }]

        result = self._pack(so.name, payload)

        self.assertEqual(result["status"], "success", result.get("message"))
        self.assertTrue(
            frappe.db.exists("Pick List", result["pick_list"]),
            f"Pick List {result['pick_list']} not found in DB",
        )

    def test_creates_packing_slips_in_db(self):
        so = make_test_sales_order()
        payload = [{
            "parcel_template": "BOX 1",
            "dimensions": {"height": 10, "width": 9, "length": 5},
            "weight"
            "items": [{
                "item_code": so.items[0].item_code,
                "quantity": int(so.items[0].qty),
                "sales_order_item": so.items[0].name,
            }],
        }]

        result = self._pack(so.name, payload)

        self.assertEqual(result["status"], "success", result.get("message"))
        self.assertGreater(len(result["packing_slips"]), 0)
        for ps_name in result["packing_slips"]:
            self.assertTrue(
                frappe.db.exists("Packing Slip", ps_name),
                f"Packing Slip {ps_name} not found in DB",
            )

    def test_two_boxes_creates_two_packing_slips(self):
        """Mirrors the example payload from the spec (two boxes, two items)."""
        so = make_test_sales_order(item_list=[
            {"item_code": "RFIWPG130-1", "warehouse": "R01-Gor-Active Stock - ICL", "qty": 1, "rate": 50},
            {"item_code": "GS101799-6",  "warehouse": "R01-Gor-Active Stock - ICL", "qty": 1, "rate": 75},
        ])

        payload = [
            {
                "parcel_template": "BOX 1",
                "dimensions": {"height": 10, "width": 9, "length": 5},
                "weight": 2,
                "items": [{"item_code": so.items[0].item_code, "quantity": 1, "sales_order_item": so.items[0].name}],
            },
            {
                "parcel_template": "BOX 1",
                "dimensions": {"height": 12, "width": 8, "length": 6},
                "weight": 3,
                "items": [{"item_code": so.items[1].item_code, "quantity": 1, "sales_order_item": so.items[1].name}],
            },
        ]

        result = self._pack(so.name, payload)

        self.assertEqual(result["status"], "success", result.get("message"))
        self.assertTrue(frappe.db.exists("Pick List", result["pick_list"]))
        self.assertEqual(len(result["packing_slips"]), 2)
        for ps_name in result["packing_slips"]:
            self.assertTrue(frappe.db.exists("Packing Slip", ps_name))

    def test_packing_slip_dimensions_saved(self):
        """Verify height/width/length/weight are persisted on the Packing Slip doc."""
        so = make_test_sales_order()
        payload = [{
            "parcel_template": "BOX 1",
            "dimensions": {"height": 15, "width": 11, "length": 8},
            "weight": 4,
            "items": [{
                "item_code": so.items[0].item_code,
                "quantity": int(so.items[0].qty),
                "sales_order_item": so.items[0].name,
            }],
        }]

        result = self._pack(so.name, payload)

        self.assertEqual(result["status"], "success", result.get("message"))
        ps = frappe.get_doc("Packing Slip", result["packing_slips"][0])
        self.assertEqual(ps.custom_neb_box_height, 15)
        self.assertEqual(ps.custom_neb_box_width, 11)
        self.assertEqual(ps.custom_neb_box_length, 8)
        self.assertEqual(ps.gross_weight_pkg, 4)

    # ------------------------------------------------------------------
    # Error-path: failures are injected via mocks, form_dict set directly
    # ------------------------------------------------------------------

    def test_pick_list_failure_propagates(self):
        so = make_test_sales_order()
        self._set_form_dict(so.name, [{
            "parcel_template": "BOX 1",
            "dimensions": {"height": 10, "width": 9, "length": 5},
            "weight": 2,
            "items": [{"item_code": so.items[0].item_code, "quantity": int(so.items[0].qty), "sales_order_item": so.items[0].name}],
        }])

        with patch.object(pps_api, "create_pick_list_for_order",
                          return_value={"success": False, "error": "No stock available"}):
            result = pack_order()

        self.assertEqual(result["status"], "error")
        self.assertIn("No stock available", result["message"])

    def test_pps_api_failure_propagates(self):
        so = make_test_sales_order()
        self._set_form_dict(so.name, [{
            "parcel_template": "BOX 1",
            "dimensions": {"height": 10, "width": 9, "length": 5},
            "weight": 2,
            "items": [{"item_code": so.items[0].item_code, "quantity": int(so.items[0].qty), "sales_order_item": so.items[0].name}],
        }])

        with patch.object(pps_api, "create_pick_list_for_order",
                          return_value={"success": True, "pick_list": "PL-DUMMY"}), \
             patch.object(pps_api, "create_packing_slips", return_value=["PS-DUMMY"]), \
             patch.object(pps_api.frappe, "get_doc", return_value=MagicMock(name="PL-DUMMY")), \
             patch.object(pps_api, "call_pps_api_to_pack_order",
                          return_value={"success": False, "error": "PPS service unavailable"}):
            result = pack_order()

        self.assertEqual(result["status"], "error")
        self.assertIn("PPS service unavailable", result["message"])

    def test_invalid_so_item_in_payload(self):
        so = make_test_sales_order()
        self._set_form_dict(so.name, [{
            "parcel_template": "BOX 1",
            "dimensions": {"height": 10, "width": 9, "length": 5},
            "weight": 2,
            "items": [{"item_code": so.items[0].item_code, "quantity": 1, "sales_order_item": "nonexistent_row_id"}],
        }])

        result = pack_order()

        self.assertEqual(result["status"], "error")
        self.assertIn("does not exist", result["message"])
