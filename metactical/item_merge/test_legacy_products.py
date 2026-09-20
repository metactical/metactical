# Copyright (c) 2026, Storebuilder Commerce Inc and Contributors
# See license.txt
"""The legacy Storebuilder products a merge consolidates away.

Everything here turns on one thing being right: a slug that does not resolve must never reach a
job, because the drop it would issue deletes a live product. The websites are stubbed - what is
under test is how their answers are read, not that they answer.
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from metactical.item_merge import catalogue, jobs, legacy_products

PRICE_LIST = "RET - Camo"
OTHER_PRICE_LIST = "RET - Gorilla"
# Rows name a website the way an operator does: its Lead Source. The API settings are still keyed
# by price list, and legacy_products resolves one to the other.
SITE = "Website - Camo"
OTHER_SITE = "Website - Gorilla"
SETTINGS = "Storebuilder Sync Settings"


def _answer(status_code=200, url=None):
	"""A stand-in for requests.get.

	It echoes back the URL it was asked for, because that is what a request that was not redirected
	does - and the check compares the two. A test that wants a redirect names the landing URL.
	"""
	def get(asked, **kwargs):
		response = MagicMock()
		response.status_code = status_code
		response.url = url or asked
		return response
	return get


def _response(status_code=200, json_data=None):
	response = MagicMock()
	response.status_code = status_code
	response.text = str(json_data)
	if json_data is None:
		response.json.side_effect = ValueError("no json")
	else:
		response.json.return_value = json_data
	return response


class TestLegacyProducts(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# The lookup endpoint, on one website only: a site with no row is its own case below. The
		# slug check needs no configuration at all - it goes to the storefront.
		settings = frappe.get_single(SETTINGS)
		cls.kept = {legacy_products.LOOKUP_FIELD: len(settings.get(legacy_products.LOOKUP_FIELD))}
		for field in cls.kept:
			settings.append(field, {"api_url": "https://example.test/" + field, "price_list": PRICE_LIST,
									"api_key": "test-key", "enabled": 1})
		settings.save(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		# Nothing in here may reach the live websites. The check is a plain GET at a storefront, so
		# any test that saves a slug would otherwise really call camouflage.ca - slow, flaky, and
		# answering differently depending on what is published that day. The default answer is a
		# live page; the tests that care about a 404, a redirect or an outage patch over it.
		patcher = patch.object(legacy_products.requests, "get", side_effect=_answer(200))
		patcher.start()
		self.addCleanup(patcher.stop)

	@classmethod
	def tearDownClass(cls):
		settings = frappe.get_single(SETTINGS)
		for field, keep in cls.kept.items():
			settings.set(field, settings.get(field)[:keep])
		settings.save(ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	# ---------- lookup: External ID -> slug ----------

	def test_lookup_returns_the_slug_the_website_has(self):
		found = _response(200, {"externalId": "ZZVAR-1", "slug": "zz-var-1"})
		with patch.object(legacy_products.requests, "get", return_value=found):
			row = legacy_products.lookup(["ZZVAR-1"], [SITE])["rows"][0]
		self.assertEqual(row["status"], "found")
		self.assertEqual(row["slug"], "zz-var-1")

	def test_lookup_sends_the_item_code_as_the_external_id(self):
		found = _response(200, {"externalId": "ZZVAR-1", "slug": "zz-var-1"})
		with patch.object(legacy_products.requests, "get", return_value=found) as get:
			legacy_products.lookup(["ZZVAR-1"], [SITE])
		self.assertIn("external_id=ZZVAR-1", get.call_args[0][0])

	def test_a_404_means_the_operator_must_supply_the_slug(self):
		with patch.object(legacy_products.requests, "get", return_value=_response(404, {})):
			row = legacy_products.lookup(["ZZVAR-1"], [SITE])["rows"][0]
		self.assertEqual(row["status"], "not_mapped")
		self.assertEqual(row["slug"], "")

	def test_a_product_with_no_url_is_not_treated_as_found(self):
		with patch.object(legacy_products.requests, "get", return_value=_response(200, {"externalId": "ZZVAR-1"})):
			row = legacy_products.lookup(["ZZVAR-1"], [SITE])["rows"][0]
		self.assertEqual(row["status"], "error")
		self.assertEqual(row["slug"], "")

	def test_a_website_with_no_lookup_row_is_reported_not_called(self):
		with patch.object(legacy_products.requests, "get") as get:
			row = legacy_products.lookup(["ZZVAR-1"], [OTHER_SITE])["rows"][0]
		get.assert_not_called()
		self.assertEqual(row["status"], "not_configured")

	def test_one_row_per_product_and_website(self):
		found = _response(200, {"externalId": "x", "slug": "s"})
		with patch.object(legacy_products.requests, "get", return_value=found):
			rows = legacy_products.lookup(["ZZVAR-1", "ZZVAR-2"], [SITE, OTHER_SITE])["rows"]
		self.assertEqual(len(rows), 4)
		self.assertEqual({(r["product"], r["lead_source"]) for r in rows},
						 {("ZZVAR-1", SITE), ("ZZVAR-1", OTHER_SITE),
						  ("ZZVAR-2", SITE), ("ZZVAR-2", OTHER_SITE)})

	# ---------- check: a request to the storefront itself ----------

	def test_the_page_url_is_the_domain_and_the_slug(self):
		self.assertEqual(legacy_products.page_url("camouflage.ca", "qwer1234"),
						 "https://camouflage.ca/qwer1234")
		self.assertEqual(legacy_products.page_url("camouflage.ca", "/qwer1234/"),
						 "https://camouflage.ca/qwer1234")
		# A slug is a path, so its separators survive and only what cannot go in one is escaped.
		self.assertEqual(legacy_products.page_url("camouflage.ca", "hats/boonie hat"),
						 "https://camouflage.ca/hats/boonie%20hat")

	def test_the_check_asks_the_storefront_for_the_page(self):
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)) as get:
			result = legacy_products.check([{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])
		self.assertEqual(get.call_args[0][0], "https://camouflage.ca/qwer1234")
		self.assertTrue(result["ok"])
		self.assertEqual(result["rows"][0]["state"], "live")

	def test_a_404_is_refused(self):
		"""A slug with no page behind it would drop the wrong product, or nothing at all."""
		with patch.object(legacy_products.requests, "get", side_effect=_answer(404)):
			verdict = legacy_products.accept(
				[{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])
		self.assertEqual(verdict["keep"], [])
		self.assertEqual(len(verdict["problems"]), 1)
		self.assertIn("https://camouflage.ca/qwer1234", verdict["problems"][0])

	def test_a_live_page_is_saved_as_verified(self):
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)):
			verdict = legacy_products.accept(
				[{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])
		self.assertEqual((verdict["problems"], verdict["warnings"]), ([], []))
		self.assertEqual(verdict["keep"][0]["verified"], 1)

	def test_a_redirect_to_another_page_is_not_a_live_product_page(self):
		"""A store that sends a dead slug to its homepage answers 200 for anything."""
		with patch.object(legacy_products.requests, "get",
						  side_effect=_answer(200, url="https://www.camouflage.ca/")):
			row = legacy_products.check([{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])["rows"][0]
		self.assertEqual(row["state"], "redirected")
		self.assertFalse(row["reached"])
		self.assertIn("redirects to", row["note"])

	def test_the_www_redirect_every_store_does_is_not_a_redirect(self):
		"""catalogue strips www from the domain and these stores send the apex there, so comparing
		whole URLs would call every single live page a redirect."""
		with patch.object(legacy_products.requests, "get",
						  side_effect=_answer(200, url="https://www.camouflage.ca/qwer1234")):
			row = legacy_products.check([{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])["rows"][0]
		self.assertEqual(row["state"], "live")
		self.assertTrue(row["reached"])

	def test_a_server_error_is_a_warning_not_a_verdict(self):
		with patch.object(legacy_products.requests, "get", side_effect=_answer(503)):
			verdict = legacy_products.accept(
				[{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])
		self.assertEqual(verdict["problems"], [])
		self.assertIn("503", verdict["warnings"][0])
		self.assertEqual(verdict["keep"][0]["verified"], 0)

	def test_an_unreachable_website_is_a_warning(self):
		with patch.object(legacy_products.requests, "get", side_effect=OSError("no route to host")):
			verdict = legacy_products.accept(
				[{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])
		self.assertEqual(verdict["problems"], [])
		self.assertEqual(len(verdict["warnings"]), 1)
		self.assertEqual(verdict["keep"][0]["verified"], 0)

	def test_the_check_sends_a_browser_user_agent(self):
		"""A missing User-Agent is the first thing a CDN turns away."""
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)) as get:
			legacy_products.check([{"product": "ZZVAR-1", "lead_source": SITE, "slug": "qwer1234"}])
		self.assertIn("Mozilla", get.call_args[1]["headers"]["User-Agent"])

	# ---------- plan: the grid, with nothing asked of the websites ----------

	def test_the_grid_is_built_without_calling_anything(self):
		"""Typing the slugs in has to work with no lookup API configured anywhere, so the screen's
		starting point must not depend on one."""
		with patch.object(legacy_products.requests, "get") as get:
			plan = legacy_products.plan(["ZZVAR-1", "ZZVAR-2"])
		get.assert_not_called()
		self.assertEqual(len(plan["rows"]), 2 * len(plan["lead_sources"]))
		self.assertTrue(all(r["slug"] == "" for r in plan["rows"]))

	def test_the_grid_says_what_each_website_can_do(self):
		plan = legacy_products.plan(["ZZVAR-1"])
		rows = {r["lead_source"]: r for r in plan["rows"]}
		self.assertTrue(rows[SITE]["can_look_up"])
		self.assertTrue(rows[SITE]["can_verify"])
		self.assertFalse(rows[OTHER_SITE]["can_look_up"])
		# Every storefront with a domain can be checked now; no API row is needed for that.
		self.assertTrue(rows[OTHER_SITE]["can_verify"])
		self.assertTrue(plan["any_lookup"])
		# The websites are the Lead Sources with a domain, not the price lists.
		self.assertIn(SITE, plan["lead_sources"])

	# ---------- the register ----------

	def test_a_slug_the_website_will_not_serve_is_never_written(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		with patch.object(legacy_products.requests, "get", side_effect=_answer(404)):
			result = legacy_products.save("ZZ-TEST-TEMPLATE",
										  [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "nope"}])
		self.assertEqual(result["written"], 0)
		self.assertEqual(len(result["problems"]), 1)
		self.assertEqual(legacy_products.saved(["ZZVAR-1"]), {})

	def test_a_good_slug_is_written_and_read_back(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)):
			result = legacy_products.save("ZZ-TEST-TEMPLATE",
										  [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "zz-one"}])
		self.assertEqual(result["written"], 1)

		row = legacy_products.saved(["ZZVAR-1"])[("ZZVAR-1", SITE)]
		self.assertEqual(row.slug, "zz-one")
		self.assertEqual(row.verified, 1)
		self.assertEqual(row.state, "Live")

	def test_saving_the_same_website_twice_updates_rather_than_duplicates(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)):
			legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "one"}])
			legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "two"}])
		saved = legacy_products.saved(["ZZVAR-1"])
		self.assertEqual(len(saved), 1)
		self.assertEqual(saved[("ZZVAR-1", SITE)].slug, "two")

	def test_three_websites_are_one_record_with_three_rows(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		sites = ["Website - Camo", "Website - Gorilla", "Website - RAS"]
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)):
			legacy_products.save("ZZ-TEST-TEMPLATE",
								 [{"product": "ZZVAR-1", "lead_source": ls, "slug": "zz-" + ls[-4:]}
								  for ls in sites])

		self.assertEqual(frappe.db.count(legacy_products.REGISTER, {"item_code": "ZZVAR-1"}), 1)
		doc = frappe.get_doc(legacy_products.REGISTER, "ZZVAR-1")
		self.assertEqual(sorted(r.lead_source for r in doc.websites), sorted(sites))
		# Each row carries the price list its drop will travel by.
		self.assertTrue(all(r.price_list for r in doc.websites))

	def test_two_items_cannot_claim_the_same_slug_on_one_website(self):
		"""Two drops for one product: the second could never be confirmed, and whichever item is
		wrong takes a live product down with it."""
		self.addCleanup(self._clear, "ZZVAR-1")
		self.addCleanup(self._clear, "ZZVAR-2")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "shared"}])

		result = legacy_products.save("ZZ-TEST-TEMPLATE",
									  [{"product": "ZZVAR-2", "lead_source": SITE, "slug": "shared"}])
		self.assertEqual(result["written"], 0)
		self.assertIn("ZZVAR-1", result["problems"][0])
		self.assertFalse(frappe.db.exists(legacy_products.REGISTER, "ZZVAR-2"))

	def test_the_same_slug_on_a_different_website_is_fine(self):
		"""The same product really is at the same slug on two stores more often than not."""
		self.addCleanup(self._clear, "ZZVAR-1")
		self.addCleanup(self._clear, "ZZVAR-2")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "shared"}])
		result = legacy_products.save("ZZ-TEST-TEMPLATE",
									  [{"product": "ZZVAR-2", "lead_source": OTHER_SITE, "slug": "shared"}])
		self.assertEqual(result["written"], 1)
		self.assertEqual(result["problems"], [])

	def test_an_item_can_re_save_its_own_slug(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "mine"}])
		result = legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "mine"}])
		self.assertEqual(result["problems"], [])
		self.assertEqual(result["written"], 1)

	def test_two_items_colliding_inside_one_save_are_caught(self):
		"""Neither is written yet, so the database cannot be what notices."""
		self.addCleanup(self._clear, "ZZVAR-1")
		self.addCleanup(self._clear, "ZZVAR-2")
		result = legacy_products.save("ZZ-TEST-TEMPLATE", [
			{"product": "ZZVAR-1", "lead_source": SITE, "slug": "same"},
			{"product": "ZZVAR-2", "lead_source": SITE, "slug": "same"},
		])
		self.assertEqual(result["written"], 0)
		self.assertEqual(len(result["problems"]), 2)

	def test_a_refusal_does_not_delete_what_was_already_there(self):
		"""A refused row is not a deleted one - a typo must not take a good slug down with it."""
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "good"}])

		with patch.object(legacy_products.requests, "get", side_effect=_answer(404)):
			result = legacy_products.save("ZZ-TEST-TEMPLATE",
										  [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "typo"}])
		self.assertEqual(len(result["problems"]), 1)
		row = legacy_products.saved(["ZZVAR-1"])[("ZZVAR-1", SITE)]
		self.assertEqual(row.slug, "good")
		self.assertEqual(row.state, "Live")

	def test_a_saved_slug_that_has_since_died_is_marked_not_found(self):
		"""Kept, because removing it would lose the only handle on the product - but the record must
		not go on claiming the page is live."""
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "gone"}])

		with patch.object(legacy_products.requests, "get", side_effect=_answer(404)):
			legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "gone"}])
		row = legacy_products.saved(["ZZVAR-1"])[("ZZVAR-1", SITE)]
		self.assertEqual(row.slug, "gone")
		self.assertEqual(row.state, "Not Found")
		self.assertEqual(row.verified, 0)

	def test_a_refusal_on_one_website_still_saves_the_others(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		answers = {"https://camouflage.ca/bad": 404}

		def get(url, **kwargs):
			return _answer(answers.get(url, 200))(url, **kwargs)

		with patch.object(legacy_products.requests, "get", side_effect=get):
			result = legacy_products.save("ZZ-TEST-TEMPLATE", [
				{"product": "ZZVAR-1", "lead_source": SITE, "slug": "bad"},
				{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": "fine"},
			])
		self.assertEqual(result["written"], 1)
		self.assertEqual(len(result["problems"]), 1)
		self.assertEqual(sorted(legacy_products.saved(["ZZVAR-1"])), [("ZZVAR-1", OTHER_SITE)])

	def test_the_record_is_named_after_the_item(self):
		"""One record per item, so the item code is the name and a second one cannot be created."""
		self.addCleanup(self._clear, "ZZVAR-1")
		with patch.object(legacy_products.requests, "get", side_effect=_answer(200)):
			legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "one"}])
		self.assertTrue(frappe.db.exists(legacy_products.REGISTER, "ZZVAR-1"))

	def test_clearing_every_slug_removes_the_record(self):
		"""The operator deciding the item was never on that website has to be able to say so - and
		an empty record left behind would count as an answer when it is not one."""
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": "zz"}])
		result = legacy_products.save("ZZ-TEST-TEMPLATE",
									  [{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": ""}])
		self.assertEqual(result["removed"], 1)
		self.assertEqual(legacy_products.saved(["ZZVAR-1"]), {})
		self.assertFalse(frappe.db.exists(legacy_products.REGISTER, "ZZVAR-1"))
		self.assertEqual(legacy_products.covered(["ZZVAR-1"]), set())

	def test_clearing_one_website_leaves_the_others(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		both = [{"product": "ZZVAR-1", "lead_source": SITE, "slug": "keep"},
				{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": "drop"}]
		legacy_products.save("ZZ-TEST-TEMPLATE", both)
		legacy_products.save("ZZ-TEST-TEMPLATE",
							 [both[0], {"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": ""}])

		doc = frappe.get_doc(legacy_products.REGISTER, "ZZVAR-1")
		self.assertEqual([(r.lead_source, r.slug) for r in doc.websites], [(SITE, "keep")])

	def test_the_grid_shows_what_is_already_saved(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": "zz"}])
		plan = legacy_products.plan(["ZZVAR-1", "ZZVAR-2"])
		rows = {(r["product"], r["lead_source"]): r for r in plan["rows"]}
		self.assertEqual(rows[("ZZVAR-1", OTHER_SITE)]["slug"], "zz")
		self.assertEqual(rows[("ZZVAR-1", SITE)]["slug"], "")
		self.assertEqual(plan["without_slug"], ["ZZVAR-2"])

	def test_the_queue_reads_the_register_not_the_browser(self):
		"""The slugs are recorded on the Variants screen, screens and possibly days before this."""
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": "zz"}])
		rows = jobs._legacy_rows([{"old": "ZZVAR-1", "new": "ZZNEW-1"}], ["ZZVAR-9"])
		self.assertEqual([(r["product"], r["lead_source"], r["price_list"], r["slug"]) for r in rows],
						 [("ZZVAR-1", OTHER_SITE, OTHER_PRICE_LIST, "zz")])

	def test_an_item_with_nothing_registered_drops_nothing(self):
		self.assertEqual(jobs._legacy_rows([{"old": "ZZVAR-NOTHING", "new": "ZZNEW-1"}], []), [])

	# ---------- "not on any website": the only way past the block for an unpublished item ----------

	def test_marking_not_published_accounts_for_an_item(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		self.assertNotIn("ZZVAR-1", legacy_products.covered(["ZZVAR-1"]))

		legacy_products.not_published("ZZVAR-1")
		self.assertIn("ZZVAR-1", legacy_products.covered(["ZZVAR-1"]))

		plan = legacy_products.plan(["ZZVAR-1"])
		self.assertEqual(plan["not_published"], ["ZZVAR-1"])
		self.assertEqual(plan["without_slug"], [])

	def test_marking_not_published_can_be_undone(self):
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.not_published("ZZVAR-1")
		legacy_products.not_published("ZZVAR-1", on=False)
		self.assertEqual(legacy_products.covered(["ZZVAR-1"]), set())

	def test_recording_a_slug_retires_the_marker(self):
		"""An item with a product on a website is published, whatever was ticked earlier."""
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.not_published("ZZVAR-1")
		legacy_products.save("ZZ-TEST-TEMPLATE", [{"product": "ZZVAR-1", "lead_source": OTHER_SITE, "slug": "zz"}])

		plan = legacy_products.plan(["ZZVAR-1"])
		self.assertEqual(plan["not_published"], [])
		self.assertEqual(plan["without_slug"], [])

	def test_a_not_published_item_drops_nothing(self):
		"""It accounts for the item; it is not a product, so there is nothing to issue a drop for."""
		self.addCleanup(self._clear, "ZZVAR-1")
		legacy_products.not_published("ZZVAR-1")
		self.assertEqual(jobs._legacy_rows([{"old": "ZZVAR-1", "new": "ZZNEW-1"}], []), [])

	def _clear(self, item_code):
		if frappe.db.exists(legacy_products.REGISTER, item_code):
			frappe.delete_doc(legacy_products.REGISTER, item_code, force=True, ignore_permissions=True)
		frappe.db.commit()


class TestLegacyDrops(FrappeTestCase):
	"""issue_drops: what actually reaches Item Drop and Create Log."""

	def _job(self, rows):
		job = frappe.get_doc({
			"doctype": "Item Merge Job", "job_type": "Merge", "template": "ZZ-TEST-TEMPLATE",
			"status": "Queued", "total": 0, "processed": 0, "steps": "[]", "legacy_products": rows,
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(lambda: self._delete_job(job.name))
		return job

	def _storefront_without_a_price_list(self):
		"""A Lead Source an operator can name but nothing can be routed to."""
		name = "_Test Legacy No Price List"
		if not frappe.db.exists("Lead Source", name):
			# Copy the mandatory company fields off a real one rather than inventing a company.
			like = frappe.db.get_value("Lead Source", {"custom_neb_price_list": ["is", "set"]},
									   ["neb_company", "neb_company_address"], as_dict=True) or {}
			frappe.get_doc({"doctype": "Lead Source", "source_name": name,
							"lead_source_domain": "nowhere.example",
							"neb_company": like.get("neb_company"),
							"neb_company_address": like.get("neb_company_address")}).insert(ignore_permissions=True)
			frappe.db.commit()
			self.addCleanup(lambda: (frappe.delete_doc("Lead Source", name, force=True, ignore_permissions=True),
									 frappe.db.commit()))
		catalogue.clear()
		self.addCleanup(catalogue.clear)
		return name

	def _delete_job(self, name):
		for row in frappe.get_all("Item Merge Job Legacy Product", filters={"parent": name}, pluck="drop_log"):
			if row and frappe.db.exists("Item Drop and Create Log", row):
				frappe.delete_doc("Item Drop and Create Log", row, force=True, ignore_permissions=True)
		frappe.delete_doc("Item Merge Job", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_a_drop_is_issued_with_skip_recreate(self):
		job = self._job([{"product": "ZZVAR-1", "lead_source": SITE, "price_list": PRICE_LIST, "site": "camouflage.ca",
						  "slug": "zz-legacy-one", "source": "Lookup", "verified": 1, "status": "Validated"}])
		counts = legacy_products.issue_drops(job)
		self.assertEqual(counts["issued"], 1)

		job.reload()
		row = job.legacy_products[0]
		self.assertEqual(row.status, "Issued")

		drop = frappe.get_doc("Item Drop and Create Log", row.drop_log)
		self.assertEqual(drop.skip_recreate, 1)
		self.assertEqual(drop.status, "Issued")
		self.assertEqual(drop.slug, "zz-legacy-one")
		# The legacy code, not the survivor: the confirmation groups logs by product, and these
		# must not join a real drop and create on the template that survived.
		self.assertEqual(drop.product, "ZZVAR-1")
		self.assertEqual(drop.price_list, PRICE_LIST)

	def test_a_slug_a_live_item_still_publishes_is_left_alone(self):
		"""The website steps fill the survivor's Item Detail rows from a Metabase copy just before
		this runs. If that copy handed it a legacy slug, dropping it would delete the product the
		merge has only just consolidated into."""
		item = frappe.db.get_value("Item", {}, "name")
		owned = frappe.get_doc({"doctype": "Item Detail", "parent": item, "parenttype": "Item",
								"parentfield": "item_detail", "idx": 999, "price_list": PRICE_LIST,
								"slug": "zz-survivor-slug"})
		owned.insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(lambda: (frappe.db.delete("Item Detail", {"name": owned.name}), frappe.db.commit()))

		job = self._job([{"product": "ZZVAR-7", "lead_source": SITE, "slug": "zz-survivor-slug",
						  "source": "Lookup", "verified": 1, "status": "Validated"}])
		counts = legacy_products.issue_drops(job)

		self.assertEqual(counts, {"issued": 0, "skipped": 1, "failed": 0})
		self.assertFalse(frappe.db.exists("Item Drop and Create Log", {"product": "ZZVAR-7"}))
		job.reload()
		self.assertEqual(job.legacy_products[0].status, "Skipped")
		self.assertIn(item, job.legacy_products[0].message)

	def test_the_price_list_is_derived_from_the_website(self):
		"""Rows name a Lead Source; the drop travels by price list, and the confirmation matches on
		it. Losing it would issue a drop nothing could ever confirm."""
		job = self._job([{"product": "ZZVAR-1", "lead_source": SITE, "slug": "zz-derived",
						  "source": "Manual", "verified": 0, "status": "Validated"}])
		self.assertEqual(legacy_products.issue_drops(job)["issued"], 1)
		job.reload()
		self.assertEqual(frappe.db.get_value("Item Drop and Create Log", job.legacy_products[0].drop_log,
											 "price_list"), PRICE_LIST)

	def test_a_website_with_no_price_list_fails_rather_than_looking_dropped(self):
		site = self._storefront_without_a_price_list()
		job = self._job([{"product": "ZZVAR-1", "lead_source": site, "slug": "zz",
						  "source": "Manual", "verified": 0, "status": "Validated"}])
		self.assertEqual(legacy_products.issue_drops(job), {"issued": 0, "skipped": 0, "failed": 1})
		job.reload()
		self.assertEqual(job.legacy_products[0].status, "Failed")
		self.assertIn("no price list", job.legacy_products[0].message)

	def test_issuing_twice_does_not_drop_twice(self):
		"""Resume re-runs the step, and a second DropProductMessage for a product that is already
		gone is noise the sites have to answer for."""
		job = self._job([{"product": "ZZVAR-1", "lead_source": SITE, "slug": "zz-legacy-one",
						  "source": "Lookup", "verified": 1, "status": "Validated"}])
		legacy_products.issue_drops(job)
		job.reload()
		self.assertEqual(legacy_products.issue_drops(job)["issued"], 0)
		self.assertEqual(frappe.db.count("Item Drop and Create Log", {"product": "ZZVAR-1"}), 1)
