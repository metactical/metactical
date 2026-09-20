# Copyright (c) 2026, Storebuilder Commerce Inc and Contributors
# See license.txt
"""The confirmation side of a drop: what happens once a website says the product is gone.

Normally the product is pushed straight back - the re-create is the item.save() loop in
receive_deletion_message, one save per variant, each re-firing the Item webhooks. A drop that a
variant merge asked for must not do that: the product it would push back no longer exists.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from metactical.custom_scripts.utils import item_rmq_api

DOCTYPE = "Item Drop and Create Log"
LEAD_SOURCE = "Website - Camo"
PRICE_LIST = "RET - Camo"


class TestItemDropandCreateLog(FrappeTestCase):
	def setUp(self):
		# The re-create also re-pushes the images; counting the calls is how these tests tell a
		# re-create apart from a plain drop without needing an item that has variants.
		self.synced = []
		self._real_sync = item_rmq_api.sync_s3_images
		item_rmq_api.sync_s3_images = lambda item_code, user=None: self.synced.append(item_code)
		self.addCleanup(self._restore)
		self.logs = []
		self.addCleanup(self._delete_logs)

	def _restore(self):
		item_rmq_api.sync_s3_images = self._real_sync

	def _delete_logs(self):
		for name in self.logs:
			if frappe.db.exists(DOCTYPE, name):
				frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _log(self, product, slug, skip_recreate=0, price_list=PRICE_LIST):
		doc = frappe.get_doc({"doctype": DOCTYPE, "product": product, "item_name": product,
							  "price_list": price_list, "slug": slug, "status": "Issued",
							  "skip_recreate": skip_recreate}).insert(ignore_permissions=True)
		frappe.db.commit()
		self.logs.append(doc.name)
		return doc

	def _confirm(self, slug, lead_source=LEAD_SOURCE):
		item_rmq_api.receive_deletion_message({"publisher_site": lead_source, "Entity": {"urlSlug": slug}})

	def test_skip_recreate_drops_without_pushing_the_product_back(self):
		log = self._log("ZZDROP-1", "zz-drop-one", skip_recreate=1)
		self._confirm("zz-drop-one")

		log.reload()
		self.assertEqual(log.deleted, 1)
		self.assertEqual(log.status, "Dropped")
		self.assertEqual(self.synced, [])

	def test_an_ordinary_drop_still_re_creates(self):
		log = self._log("ZZDROP-2", "zz-drop-two", skip_recreate=0)
		self._confirm("zz-drop-two")

		log.reload()
		self.assertEqual(log.deleted, 1)
		self.assertEqual(log.status, "Re-Created")
		self.assertEqual(self.synced, ["ZZDROP-2"])

	def test_the_batch_waits_for_every_website(self):
		first = self._log("ZZDROP-3", "zz-drop-three-camo", skip_recreate=1)
		second = self._log("ZZDROP-3", "zz-drop-three-gorilla", skip_recreate=1, price_list="RET - Gorilla")

		self._confirm("zz-drop-three-camo")
		first.reload()
		self.assertEqual(first.deleted, 1)
		self.assertEqual(first.status, "Issued")  # still waiting on the other site

		self._confirm("zz-drop-three-gorilla", lead_source="Website - Gorilla")
		first.reload()
		second.reload()
		self.assertEqual([first.status, second.status], ["Dropped", "Dropped"])
		self.assertEqual(self.synced, [])

	def test_a_mixed_batch_re_creates(self):
		"""Nothing here produces a half-skipped batch, so one means something else wrote into it.
		Re-creating is the older, safer answer."""
		skipped = self._log("ZZDROP-4", "zz-drop-four-camo", skip_recreate=1)
		plain = self._log("ZZDROP-4", "zz-drop-four-gorilla", skip_recreate=0, price_list="RET - Gorilla")

		self._confirm("zz-drop-four-camo")
		self._confirm("zz-drop-four-gorilla", lead_source="Website - Gorilla")

		skipped.reload()
		plain.reload()
		self.assertEqual([skipped.status, plain.status], ["Re-Created", "Re-Created"])
		self.assertEqual(self.synced, ["ZZDROP-4"])
