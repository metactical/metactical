"""Flow tests: the real family / merge / jobs / websites code against an in-memory frappe.

Skipped on a bench (the real frappe is importable there); run offline from the app repo root:
	python -m unittest discover -s metactical/item_merge/tests -t . -v
"""
import contextlib
import importlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

try:
	import frappe as _real  # noqa: F401
	ON_BENCH = not getattr(_real, "_fake", False)
except ImportError:
	ON_BENCH = False

SIZE = "Size - Clothing - XS to 8XL"
COLOUR = "Colour - Clothing - PS"
VN = "Variant Number"


@unittest.skipIf(ON_BENCH, "flow tests use an in-memory frappe; on a bench use the real site instead")
class FlowBase(unittest.TestCase):
	def setUp(self):
		from metactical.item_merge.tests import fake_frappe
		self.f = fake_frappe.install()
		for mod in ("catalogue", "family", "merge", "websites", "jobs"):
			sys.modules.pop(f"metactical.item_merge.{mod}", None)
		# the page API binds `frappe` at import; a copy cached from an earlier test would set its
		# flags on that test's frappe, not this one's. It has to be re-imported, not just dropped
		# from sys.modules: `from pkg import mod` hands back the stale attribute still on pkg.
		sys.modules.pop("metactical.metactical.page.item_merge.item_merge", None)
		self.family = importlib.import_module("metactical.item_merge.family")
		self.merge = importlib.import_module("metactical.item_merge.merge")
		self.websites = importlib.import_module("metactical.item_merge.websites")
		self.jobs = importlib.import_module("metactical.item_merge.jobs")
		self.merge.MERGE_SPACING_S = 0
		self.jobs.merge.MERGE_SPACING_S = 0
		self.catalogue = importlib.import_module("metactical.item_merge.catalogue")
		self.api = importlib.import_module("metactical.metactical.page.item_merge.item_merge")
		self.seed()

	def tearDown(self):
		for mod in ("frappe", "frappe.utils", "frappe.utils.background_jobs", "erpnext", "erpnext.controllers",
					"erpnext.controllers.item_variant", "metactical.custom_scripts.utils.s3_image_api",
					"metactical.item_merge.catalogue", "metactical.item_merge.family",
					"metactical.item_merge.merge", "metactical.item_merge.websites", "metactical.item_merge.jobs",
					"metactical.metactical.page.item_merge.item_merge"):
			sys.modules.pop(mod, None)

	def run_enqueued(self):
		"""Run the queued jobs the way the worker does: the method with exactly the kwargs that were enqueued."""
		while self.f.enqueued:
			method, kwargs = self.f.enqueued.pop(0)
			getattr(self.jobs, method.rsplit(".", 1)[1])(**kwargs)

	@contextlib.contextmanager
	def contended_saves(self, item, merged_away, attempts, errors):
		"""Make saves of `item` fail while the rename hook would still be holding it.

		Only saves that happen after `merged_away` has gone count, so this hits the post-merge
		follow-ups and nothing earlier in the flow. `Doc` is a dict subclass, so the patch has to go
		on the class - assigning doc.save would only write a dict key."""
		from metactical.item_merge.tests import fake_frappe

		real_save = fake_frappe.Doc.save

		def save(doc, *a, **kw):
			if doc["name"] == item and not self.f.db.exists("Item", merged_away):
				attempts.append(doc["name"])
				if len(attempts) <= len(errors):
					raise errors[len(attempts) - 1]
			return real_save(doc, *a, **kw)

		fake_frappe.Doc.save = save
		try:
			yield attempts
		finally:
			fake_frappe.Doc.save = real_save

	def insert(self, doc):
		return self.f.get_doc(doc).insert()

	def item(self, code, **fields):
		"""attrs={attribute: value} for the common case; pass attributes=[…] for full rows (a template
		needs numeric_values/from_range on its legacy attribute, which is how it is recognised)."""
		attrs = fields.pop("attrs", {})
		rows = fields.pop("attributes", None)
		if rows is None:
			rows = [{"attribute": a, "attribute_value": v} for a, v in attrs.items()]
		return self.insert({"doctype": "Item", "item_code": code, "item_name": code, "stock_uom": "Nos", "is_stock_item": 1,
							"item_group": "T-Shirts", "has_variants": 0, **fields, "attributes": rows})

	def seed(self):
		"""RVX4184 as it looked before its merge: Variant Number variants, stock on Black Small only."""
		for g, is_group in (("T-Shirts", 0), ("01 - Products", 1)):
			self.insert({"doctype": "Item Group", "name": g, "is_group": is_group})
		self.insert({"doctype": "Item Attribute", "name": COLOUR, "numeric_values": 0, "item_attribute_values": [
			{"attribute_value": "Black", "abbr": "001"}, {"attribute_value": "Camo - Woodland", "abbr": "312"}]})
		self.insert({"doctype": "Item Attribute", "name": SIZE, "numeric_values": 0, "item_attribute_values": [
			{"attribute_value": "Small", "abbr": "0003"}, {"attribute_value": "Medium", "abbr": "0004"}]})
		self.insert({"doctype": "Item Attribute", "name": VN, "numeric_values": 1, "item_attribute_values": []})
		self.item("RVX4184", item_name="RavenX Classic Ops T-Shirt", has_variants=1, item_group="01 - Products",
				  supplier_items=[{"supplier": "RavenX", "supplier_part_no": None}], attrs={VN: None})
		self.item("RVX4184-0001", item_name="RavenX Classic Ops T-Shirt - Black - Small", variant_of="RVX4184",
				  ifw_retailskusuffix="RVX4184BLK-S", attrs={VN: "1"},
				  supplier_items=[{"supplier": "RavenX", "supplier_part_no": "4184-BLK-S"}],
				  neb_website_specifications=[{"label": "Colour", "description": "Black"}])
		self.item("RVX4184-0002", item_name="RavenX Classic Ops T-Shirt - Black - Medium", variant_of="RVX4184", attrs={VN: "2"})
		self.insert({"doctype": "Bin", "item_code": "RVX4184-0001", "warehouse": "W01", "actual_qty": 7, "stock_value": 70})
		for i in range(3):
			self.insert({"doctype": "Stock Ledger Entry", "item_code": "RVX4184-0001", "is_cancelled": 0})
		self.insert({"doctype": "Pricing Rule", "name": "PRLE-0001", "items": [{"item_code": "RVX4184-0002"}]})
		self.insert({"doctype": "Item Price", "item_code": "RVX4184", "price_list": "RET - Camo"})
		# the websites, as ERPNext holds them: which price lists a merge looks at, and which Lead
		# Source a deduct row points at, are read from here rather than hard-coded
		for source, price_list, domain in (("Website - Camo", "RET - Camo", "camouflage.ca"),
										   ("Website - Gorilla", "RET - Gorilla", "gorillasurplus.com"),
										   ("Website - RAS", "RET - RAS", "replicaairguns.ca")):
			self.insert({"doctype": "Lead Source", "name": source, "custom_neb_price_list": price_list,
						 "lead_source_domain": domain})


class MergeFlow(FlowBase):
	def test_variants_align_merge_end_to_end(self):
		fam, jobs = self.family, self.jobs
		s = fam.suggest_combinations("RVX4184", [COLOUR, SIZE])
		self.assertEqual(s["style_name"], "RavenX Classic Ops T-Shirt")
		self.assertEqual([(c["item_code"], c["suggested"]) for c in s["combinations"]],
						 [("RVX4184-001-0003", True), ("RVX4184-001-0004", False)])

		created = fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": s["combinations"][0]["values"]}])
		self.assertEqual([v["status"] for v in created["variants"]], ["created"])
		t = self.f.get_doc("Item", "RVX4184")
		self.assertEqual(t.item_group, "T-Shirts", "group item group fixed before creating variants")
		self.assertEqual([a.attribute for a in t.attributes], [VN, COLOUR, SIZE])
		new = self.f.get_doc("Item", "RVX4184-001-0003")
		self.assertEqual([a.attribute for a in new.attributes], [COLOUR, SIZE], "Variant Number stripped from the new variant")

		a = fam.alignment("RVX4184")
		self.assertEqual([(r["old"]["item_code"], (r["new"] or {}).get("item_code"), r["status"]) for r in a["rows"]],
						 [("RVX4184-0001", "RVX4184-001-0003", "ready"), ("RVX4184-0002", None, "leftover")])

		pairs = [{"old": "RVX4184-0001", "new": "RVX4184-001-0003", "item_name": "RavenX Classic Ops T-Shirt - Black - Small",
				  "retail_sku": "RVX4184-001-0003"}]
		name = jobs.create_merge_job("RVX4184", pairs, ["RVX4184-0002"], {"sku": "keep", "fix_names": True})
		self.assertEqual(self.f.enqueued[0], ("metactical.item_merge.jobs.run_job", {"merge_job": name}))
		with self.assertRaisesRegex(Exception, "already queued or running"):
			jobs.create_merge_job("RVX4184", pairs, [], {})

		self.run_enqueued()
		job = jobs.job_status(name)
		self.assertEqual(job["status"], "done", job["log"])
		self.assertEqual([p["status"] for p in job["pairs"]], ["ok"])
		self.assertFalse(self.f.db.exists("Item", "RVX4184-0001"))
		after = self.f.get_doc("Item", "RVX4184-001-0003")
		self.assertEqual(after.ifw_retailskusuffix, "RVX4184-001-0003", "SKU typed on the align screen wins over the hook's")
		self.assertEqual([(s.supplier, s.supplier_part_no) for s in after.supplier_items], [("RavenX", "4184-BLK-S")])
		self.assertEqual([(r.lead_source, r.qty) for r in after.custom_neb_website_deduct_qty], [("Website - Camo", 0)])
		self.assertEqual(job["leftovers"], [{"item_code": "RVX4184-0002", "status": "deleted", "message": None}])
		self.assertFalse(self.f.db.exists("Pricing Rule", "PRLE-0001"))
		self.assertEqual(len(json.loads(self.f.get_doc("Item Merge Job", name).deleted_pricing_rules)), 1)
		self.assertEqual([a.attribute for a in self.f.get_doc("Item", "RVX4184").attributes], [COLOUR, SIZE])
		steps = {s["name"]: s["status"] for s in job["steps"]}
		self.assertEqual(steps["Remove Variant Number from template"], "done")
		self.assertEqual(steps["Website slugs"], "skipped", "no Storebuilder API rows configured in this test")
		audit = job["live"]["audit"][0]
		self.assertEqual((audit["expected_qty"], audit["actual_qty"], audit["state"], audit["history"]), (7, 7, "ok", True))
		self.assertTrue(any(e == "item_merge_progress" for e, *_ in self.f.published))
		self.assertTrue(any("merge job" in c[2] for c in self.f.comments))

	def test_failed_pair_stops_the_job_and_resume_finishes_it(self):
		fam, jobs = self.family, self.jobs
		fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}},
													   {"values": {COLOUR: "Black", SIZE: "Medium"}}])
		pairs = [{"old": "RVX4184-0002", "new": "RVX4184-001-0004"}, {"old": "RVX4184-0001", "new": "RVX4184-001-0003"}]

		# a different UOM on a new variant that already has stock history can't be fixed: refused up front
		self.f.db.set_value("Item", "RVX4184-001-0004", "stock_uom", "Box")
		self.insert({"doctype": "Stock Ledger Entry", "name": "sle-new", "item_code": "RVX4184-001-0004", "is_cancelled": 0})
		with self.assertRaisesRegex(Exception, "stock history"):
			jobs.create_merge_job("RVX4184", pairs, [], {})

		# ...and when it only happens after queueing, the pair fails and the job stops before the next pair
		self.f.db.set_value("Item", "RVX4184-001-0004", "stock_uom", "Nos")
		name = jobs.create_merge_job("RVX4184", pairs, [], {})
		self.f.db.set_value("Item", "RVX4184-001-0004", "stock_uom", "Box")
		self.run_enqueued()
		job = jobs.job_status(name, live=False)
		self.assertEqual(job["status"], "failed")
		self.assertEqual([p["status"] for p in job["pairs"]], ["failed", "queued"])
		self.assertIn("stock_uom", job["pairs"][0]["message"])
		self.assertTrue(self.f.db.exists("Item", "RVX4184-0001"), "the job stopped before the second pair")

		self.f.db.set_value("Item", "RVX4184-001-0004", "stock_uom", "Nos")
		jobs.resume(name)
		self.run_enqueued()
		job = jobs.job_status(name, live=False)
		self.assertEqual((job["status"], [p["status"] for p in job["pairs"]]), ("done", ["ok", "ok"]), job["log"])

	def test_follow_up_save_retries_while_the_rename_hook_holds_the_item(self):
		"""The hook keeps writing to the new item after rename_doc returns, so the first save of the
		follow-ups can lose the race. Seen on a bench as a deadlock and as a timestamp mismatch."""
		fam, jobs, merge = self.family, self.jobs, self.merge
		merge.FOLLOW_UP_BACKOFF_S = 0
		fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])

		attempts = []
		errors = [self.f.QueryDeadlockError("1213 deadlock"),
				  self.f.TimestampMismatchError("modified after you opened it")]
		with self.contended_saves("RVX4184-001-0003", "RVX4184-0001", attempts, errors):
			name = jobs.create_merge_job("RVX4184", [{"old": "RVX4184-0001", "new": "RVX4184-001-0003"}], [], {})
			self.run_enqueued()
		job = jobs.job_status(name, live=False)
		self.assertEqual((job["status"], [p["status"] for p in job["pairs"]]), ("done", ["ok"]), job["log"])
		self.assertGreaterEqual(len(attempts), 3, "the first two saves were meant to fail and be retried")
		self.assertTrue(any("rename hook still holds" in line for line in job["log"]), job["log"])
		# the retry re-read the item, so the old item's name still landed on the new one
		self.assertEqual(self.f.get_doc("Item", "RVX4184-001-0003").item_name,
						 "RavenX Classic Ops T-Shirt - Black - Small")

	def test_follow_up_save_gives_up_after_the_last_attempt(self):
		fam, jobs, merge = self.family, self.jobs, self.merge
		merge.FOLLOW_UP_BACKOFF_S = 0
		fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])
		attempts = []
		forever = [self.f.QueryDeadlockError("1213 deadlock")] * (merge.FOLLOW_UP_ATTEMPTS + 2)
		with self.contended_saves("RVX4184-001-0003", "RVX4184-0001", attempts, forever):
			name = jobs.create_merge_job("RVX4184", [{"old": "RVX4184-0001", "new": "RVX4184-001-0003"}], [], {})
			self.run_enqueued()
		job = jobs.job_status(name, live=False)
		self.assertEqual(job["status"], "failed")
		self.assertEqual([p["status"] for p in job["pairs"]], ["failed"])

	def test_interrupted_job_can_resume(self):
		jobs = self.jobs
		self.family.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])
		name = jobs.create_merge_job("RVX4184", [{"old": "RVX4184-0001", "new": "RVX4184-001-0003"}], [], {})
		self.f.db.set_value("Item Merge Job", name, {"status": "Running", "started_on": self.f.now()})
		self.f.clock = self.f.clock.replace(hour=10)
		self.f.alive_jobs = set()
		self.assertEqual(jobs.job_status(name, live=False)["status"], "interrupted")
		self.assertEqual(jobs.resume(name), name)
		self.f.alive_jobs = None
		self.run_enqueued()
		self.assertEqual(jobs.job_status(name, live=False)["status"], "done")


class ChangesFlow(FlowBase):
	def test_rename_and_sku_then_refusals(self):
		fam, jobs = self.family, self.jobs
		name = jobs.create_changes_job("RVX4184", [{"item_code": "RVX4184-0001", "new_code": "RVX4184BLK-S", "retail_sku": "RVX4184BLK-S"},
												  {"item_code": "RVX4184-0002", "item_name": "RavenX Classic Ops T-Shirt - Black - Medium"}])
		job = self.f.get_doc("Item Merge Job", name)
		self.assertEqual(len(job.changes), 1, "an unchanged name is not a change")
		self.run_enqueued()
		status = jobs.job_status(name)
		self.assertEqual(status["status"], "done", status["log"])
		self.assertTrue(self.f.db.exists("Item", "RVX4184BLK-S"))
		self.assertEqual(self.f.get_doc("Item", "RVX4184BLK-S").ifw_retailskusuffix, "RVX4184BLK-S")
		self.assertEqual(status["live"]["items"][0]["item_code"], "RVX4184BLK-S")
		with self.assertRaisesRegex(Exception, "Nothing has changed"):
			jobs.create_changes_job("RVX4184", [{"item_code": "RVX4184-0002", "item_name": "RavenX Classic Ops T-Shirt - Black - Medium"}])
		with self.assertRaisesRegex(Exception, "already exists"):
			jobs.create_changes_job("RVX4184", [{"item_code": "RVX4184-0002", "new_code": "RVX4184"}])
		self.assertEqual(fam.current_codes(["RVX4184-0001"]), {"RVX4184-0001": "RVX4184BLK-S"})


class TemplatesFlow(FlowBase):
	def test_rename_template_and_merge_safeguards(self):
		fam = self.family
		self.item("RVX4184WLD", item_name="RavenX Classic Ops T-Shirt - Woodland", has_variants=1, item_group="T-Shirts")
		self.item("RVX4184WLD-0001", item_name="RavenX Classic Ops T-Shirt - Woodland - Small", variant_of="RVX4184WLD",
				  item_group="Button-Up Shirts")
		self.insert({"doctype": "Item Group", "name": "Button-Up Shirts", "is_group": 0})
		check = fam.consolidation_check("RVX4184", ["RVX4184WLD"])
		self.assertTrue(check["blocked"])
		with self.assertRaisesRegex(Exception, "item groups"):
			fam.consolidate_templates("RVX4184", ["RVX4184WLD"])
		self.f.db.set_value("Item", "RVX4184WLD-0001", "item_group", "T-Shirts")
		result = fam.consolidate_templates("RVX4184", ["RVX4184WLD"], rename_to="RVX4184X")
		self.assertEqual((result["template"], result["variants_moved"], result["renamed_from"]), ("RVX4184X", 1, "RVX4184"))
		self.assertEqual(sorted(fam.variant_codes("RVX4184X")), ["RVX4184-0001", "RVX4184-0002", "RVX4184WLD-0001"])
		with self.assertRaisesRegex(Exception, "Nothing to change"):
			fam.rename_template("RVX4184X")
		r = fam.rename_template("RVX4184X", item_name="RavenX Classic Ops Tee")
		self.assertEqual(r["item_name"], "RavenX Classic Ops Tee")
		found = fam.search_templates(name="classic ops")
		self.assertEqual([(t["item_code"], t["variant_count"]) for t in found], [("RVX4184X", 3)])

	def test_alignment_ships_the_alias_table_the_pairing_used(self):
		"""The align screen's "names differ" check needs the same wordings the server paired with. It
		used to keep its own copy, which had drifted and no longer knew S, M, L or XXS."""
		self.family.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])
		aliases = self.family.alignment("RVX4184")["name_aliases"]
		self.assertEqual(aliases["Small"], ["S"])
		self.assertEqual(aliases["Large"], ["L"])
		self.assertEqual(aliases["XXSmall"], ["XXS"])
		self.assertEqual(aliases["2XLarge"], ["2XL", "XXL", "XXLarge"])
		self.assertEqual(aliases["Camo - Woodland"], ["Woodland", "Woodland Camo"])
		# every alias the pairing knows is offered, so the two can never disagree
		from metactical.item_merge.pairing import COLOUR_ALIASES, SIZE_ALIASES
		self.assertEqual(sum(len(v) for v in aliases.values()), len(SIZE_ALIASES) + len(COLOUR_ALIASES))

	def test_saving_the_template_never_rewrites_its_variants_retail_skus(self):
		"""ERPNext copies every Item Variant Settings field from a template onto its variants on save,
		and that list includes ifw_retailskusuffix. Seen on a bench: creating the new variants (which
		saves the template to add the attributes) reset every old variant's retail SKU to the
		template's, destroying the values the merge is meant to carry."""
		fam = self.family
		before = {c: self.f.get_doc("Item", c).ifw_retailskusuffix for c in ("RVX4184-0001", "RVX4184-0002")}
		self.assertEqual(before["RVX4184-0001"], "RVX4184BLK-S")

		fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])
		after = {c: self.f.get_doc("Item", c).ifw_retailskusuffix for c in before}
		self.assertEqual(after, before, "the template save pushed its own retail SKU onto the variants")
		# the template really was saved - the attributes are on it
		self.assertEqual([a.attribute for a in self.f.get_doc("Item", "RVX4184").attributes], [VN, COLOUR, SIZE])

		# and the same holds for the other template saves in the flow
		fam.rename_template("RVX4184", item_name="RavenX Classic Ops Tee")
		fam.update_template("RVX4184", {"is_stock_item": 1})
		self.assertEqual({c: self.f.get_doc("Item", c).ifw_retailskusuffix for c in before}, before)

	def test_a_code_still_held_by_an_old_variant_is_refused_not_reported_as_existing(self):
		"""The legacy -0001… numbering overlaps the size abbreviations, so a one-attribute family can
		generate the code of an old variant of the same template. Seen on a bench: every such row was
		reported as "exists", which reads as already done while nothing was created."""
		fam = self.family
		# RVX4184-0002 is an old Variant Number variant; ask for it as a new variant's code
		r = fam.create_variants("RVX4184", [COLOUR, SIZE],
								[{"values": {COLOUR: "Black", SIZE: "Small"}, "item_code": "RVX4184-0002"},
								 {"values": {COLOUR: "Black", SIZE: "Medium"}}])
		by_code = {v["item_code"]: v for v in r["variants"]}
		self.assertEqual(by_code["RVX4184-0002"]["status"], "failed")
		self.assertIn("still an old variant", by_code["RVX4184-0002"]["error"])
		# the old variant is untouched, and the row that was fine was still created
		self.assertEqual(self.f.get_doc("Item", "RVX4184-0002").item_name,
						 "RavenX Classic Ops T-Shirt - Black - Medium")
		self.assertEqual(by_code["RVX4184-001-0004"]["status"], "created")

	def test_search_box_dropdowns_offer_only_templates(self):
		fam = self.family
		codes = fam.template_code_options("RVX418")
		self.assertEqual([o["value"] for o in codes], ["RVX4184"])
		self.assertEqual(codes[0]["description"], "RavenX Classic Ops T-Shirt")
		# a variant is not a template, so it is never offered
		self.assertEqual(fam.template_code_options("RVX4184-0001"), [])
		# every word of the name must match, in any order, and each product name appears once
		self.assertEqual([o["value"] for o in fam.template_name_options("ops classic")], ["RavenX Classic Ops T-Shirt"])
		self.assertEqual(fam.template_name_options("fleece vest"), [])
		# an empty term still lists templates, so the box opens with suggestions
		self.assertTrue(fam.template_code_options(""))




class FakeMetabase:
	"""Stands in for Item Merge Settings: answers run_query from canned snapshot rows."""

	def __init__(self, rows=None):
		self.rows = rows or {}
		self.queries = []

	def run_query(self, database_id, sql):
		self.queries.append((database_id, sql))
		if "MAX(ModifiedOn)" in sql:
			return [{"latest": "2026-09-10 04:00:00"}]
		for keys, rows in self.rows.items():
			if all(f"N'{k}'" in sql for k in keys):
				return rows
		return []


class WebsitesFlow(FlowBase):
	"""The website steps read the Storebuilder snapshots in Metabase - there is no other source."""

	DATABASES = {"RET - Camo": 35, "RET - Gorilla": 131}

	def use_metabase(self, rows=None, databases=None):
		mb = FakeMetabase(rows)
		dbs = self.DATABASES if databases is None else databases
		self.websites.metabase = lambda: (mb, dbs)
		return mb

	def product(self, slug, external_id="RVX4184", variants=2, skus="RVX4184-0001|RVX4184-0002", **extra):
		return {"Id": 7, "ExternalId": external_id, "Sku": "SB-4184", "UrlSlug": slug, "IsTrashed": False,
				"Variants": variants, "VariantSkus": skus, **extra}

	def test_plan_apply_and_check(self):
		w = self.websites
		# the snapshot knows the family by a variant's retail SKU, which no External ID lookup would find
		mb = self.use_metabase({("RVX4184BLK-S",): [self.product("ravenx-classic-ops-tee")],
							    # check() asks again by slug, and that answer carries the variants
							    ("ravenx-classic-ops-tee",): [self.product("ravenx-classic-ops-tee")]})
		plan = {r["price_list"]: r for r in w.plan("RVX4184")["rows"]}
		self.assertEqual((plan["RET - Camo"]["action"], plan["RET - Camo"]["slug"]), ("add", "ravenx-classic-ops-tee"))
		self.assertEqual(plan["RET - Camo"]["as_of"], "2026-09-10")
		self.assertEqual(plan["RET - Gorilla"]["note"], "no Item Price on this price list")
		self.assertEqual(plan["RET - RAS"]["note"], "no Item Price on this price list")
		self.assertTrue(mb.queries)

		out = w.apply("RVX4184")
		self.assertEqual(self.f.loaded_from_sb, ["RVX4184"])
		self.assertEqual([(r.price_list, r.slug) for r in self.f.get_doc("Item", "RVX4184").item_detail],
						 [("RET - Camo", "ravenx-classic-ops-tee")])
		self.assertTrue(out["check"]["ok"], out["check"])
		# the template save must not have pushed its fields onto the variants
		self.assertEqual(self.f.get_doc("Item", "RVX4184-0001").ifw_retailskusuffix, "RVX4184BLK-S")

		# a blank slug row: Load Data From SB must not run
		doc = self.f.get_doc("Item", "RVX4184")
		doc.append("item_detail", {"price_list": "RET - Gorilla", "slug": ""})
		doc.save()
		self.assertIn("blank slug", w.apply("RVX4184")["load_data_from_sb"])
		self.assertEqual(self.f.loaded_from_sb, ["RVX4184"])

	def test_check_flags_external_id_and_count_and_dates_the_snapshot(self):
		self.use_metabase({("ravenx-classic-ops-tee",): [self.product("ravenx-classic-ops-tee",
																	  external_id="RVX4184BLK", variants=0, skus="")]})
		doc = self.f.get_doc("Item", "RVX4184")
		doc.append("item_detail", {"price_list": "RET - Camo", "slug": "ravenx-classic-ops-tee"})
		doc.save()
		row = self.websites.check("RVX4184")["rows"][0]
		self.assertEqual(row["status"], "mismatch")
		self.assertIn("External ID is 'RVX4184BLK'", row["note"])
		self.assertIn("0 variant(s) on the site vs 2 in ERP", row["note"])
		self.assertIn("snapshot as of 2026-09-10", row["note"])

	def test_trashed_products_are_ignored(self):
		self.use_metabase({("RVX4184BLK-S",): [dict(self.product("gone"), IsTrashed=True)]})
		camo = next(r for r in self.websites.plan("RVX4184")["rows"] if r["price_list"] == "RET - Camo")
		self.assertEqual((camo["action"], camo["found"]), ("skip", False))
		self.assertIn("not on the website", camo["note"])

	def test_several_products_are_left_alone(self):
		self.use_metabase({("RVX4184",): [self.product("ravenx-black"), self.product("ravenx-olive")]})
		camo = next(r for r in self.websites.plan("RVX4184")["rows"] if r["price_list"] == "RET - Camo")
		self.assertEqual(camo["action"], "skip")
		self.assertIn("several products match", camo["note"])

	def test_a_site_with_no_database_id_is_skipped_not_failed(self):
		self.use_metabase({}, databases={"RET - Gorilla": 131})
		camo = next(r for r in self.websites.plan("RVX4184")["rows"] if r["price_list"] == "RET - Camo")
		self.assertEqual(camo["note"], "no Metabase database id for this website")

	def test_without_metabase_the_website_steps_say_so(self):
		def off():
			raise self.websites.NotConfigured("Metabase is turned off in Item Merge Settings")
		self.websites.metabase = off
		with self.assertRaisesRegex(Exception, "turned off"):
			self.websites.plan("RVX4184")
		# the check degrades to "skipped" rather than blowing up a finished merge
		doc = self.f.get_doc("Item", "RVX4184")
		doc.append("item_detail", {"price_list": "RET - Camo", "slug": "x"})
		doc.save()
		result = self.websites.check("RVX4184")
		self.assertTrue(result["ok"])
		self.assertEqual([r["status"] for r in result["rows"]], ["skipped"])
		self.assertIn("turned off", result["not_configured"])


if __name__ == "__main__":
	unittest.main()


class CatalogueFromErp(FlowBase):
	"""The five price lists, the deduct Lead Source and the legacy attribute used to be literals."""

	def test_price_lists_come_from_the_lead_sources(self):
		self.assertEqual(self.catalogue.price_lists(), ["RET - Camo", "RET - Gorilla", "RET - RAS"])
		self.assertEqual(self.catalogue.lead_source_for("RET - Camo"), "Website - Camo")
		self.assertEqual(self.catalogue.domain_for("RET - Gorilla"), "gorillasurplus.com")
		# a website added in ERPNext is picked up without a code change
		self.insert({"doctype": "Lead Source", "name": "Website - New", "custom_neb_price_list": "RET - New",
					 "lead_source_domain": "https://www.New.example.com/"})
		self.catalogue.clear()
		self.assertIn("RET - New", self.catalogue.price_lists())
		self.assertEqual(self.catalogue.domain_for("RET - New"), "new.example.com")

	def test_deduct_rows_follow_where_the_family_actually_sells(self):
		cat = self.catalogue
		# seeded: an Item Price on RET - Camo only
		self.assertEqual(cat.deduct_lead_sources("RVX4184-0001", "RVX4184"), ["Website - Camo"])
		self.insert({"doctype": "Item Price", "item_code": "RVX4184-0001", "price_list": "RET - Gorilla"})
		self.assertEqual(cat.deduct_lead_sources("RVX4184-0001", "RVX4184"),
						 ["Website - Camo", "Website - Gorilla"])

	def test_the_legacy_attribute_is_read_off_the_template(self):
		cat, fam = self.catalogue, self.family
		self.assertEqual(cat.site_variant_attribute(), VN)
		self.assertEqual(cat.variant_attribute("RVX4184"), VN)

		# a family whose numeric attribute is called something else still works
		self.insert({"doctype": "Item Attribute", "name": "Legacy Number", "numeric_values": 1,
					 "item_attribute_values": []})
		self.item("GS1233", item_name="Field Jacket", has_variants=1,
				  attributes=[{"attribute": "Legacy Number", "numeric_values": 1, "from_range": 0,
							   "to_range": 99, "increment": 1}])
		self.item("GS1233-0001", item_name="Field Jacket - Black - Small", variant_of="GS1233",
				  attrs={"Legacy Number": "1"})
		self.assertEqual(cat.variant_attribute("GS1233"), "Legacy Number")
		# and it is classed as an old variant, not one that already has real attributes
		variants = fam.list_variants("GS1233")["variants"]
		self.assertEqual([(v["item_code"], v["is_new"]) for v in variants], [("GS1233-0001", False)])
		with self.assertRaisesRegex(Exception, "Legacy Number is the attribute being replaced"):
			fam.suggest_combinations("GS1233", ["Legacy Number"])

	def test_the_deduct_row_lands_on_the_merged_item(self):
		fam, jobs = self.family, self.jobs
		fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])
		name = jobs.create_merge_job("RVX4184", [{"old": "RVX4184-0001", "new": "RVX4184-001-0003"}], [], {})
		self.run_enqueued()
		self.assertEqual(jobs.job_status(name, live=False)["status"], "done")
		after = self.f.get_doc("Item", "RVX4184-001-0003")
		self.assertEqual([(r.lead_source, r.qty) for r in after.custom_neb_website_deduct_qty],
						 [("Website - Camo", 0)], "read from the Item Price, not the old hard-coded name")


class NoWebhooks(FlowBase):
	"""Nothing this page writes may push to the websites mid-restructure.

	frappe's run_webhooks returns early when flags.in_import is set, so the page sets it - together
	with item_from_excel, without which CustomItem.validate clears in_import again on every Item
	save. The Webhook records are all disabled on a local bench and enabled on the server, so only a
	test shows this."""

	FLAGS = ("in_import", "item_from_excel")

	def flags_now(self):
		return tuple(bool(self.f.flags.get(f)) for f in self.FLAGS)

	def test_nothing_sets_the_flags_by_default(self):
		self.assertEqual(self.flags_now(), (False, False))

	def test_the_whole_merge_job_runs_with_webhooks_off(self):
		fam, jobs = self.family, self.jobs
		fam.create_variants("RVX4184", [COLOUR, SIZE], [{"values": {COLOUR: "Black", SIZE: "Small"}}])
		name = jobs.create_merge_job("RVX4184", [{"old": "RVX4184-0001", "new": "RVX4184-001-0003"}],
									 ["RVX4184-0002"], {})

		seen = []
		real_save = self.f.get_doc("Item", "RVX4184").__class__.save
		from metactical.item_merge.tests import fake_frappe

		def save(doc, *a, **kw):
			seen.append(self.flags_now())
			return real_save(doc, *a, **kw)
		fake_frappe.Doc.save = save
		try:
			self.run_enqueued()
		finally:
			fake_frappe.Doc.save = real_save

		job = jobs.job_status(name, live=False)
		self.assertEqual(job["status"], "done", job["log"])
		self.assertTrue(seen, "the job saved nothing, so this proves nothing")
		self.assertTrue(all(f == (True, True) for f in seen),
						f"a save ran with the webhooks live: {set(seen)}")
		self.assertTrue(any("webhooks held back" in line for line in job["log"]), job["log"])
		# and the flags are put back, so the next job on this worker is unaffected
		self.assertEqual(self.flags_now(), (False, False))

	def test_the_page_api_sets_and_restores_them(self):
		api = self.api
		seen = []
		from metactical.item_merge.tests import fake_frappe
		real_save = fake_frappe.Doc.save

		def save(doc, *a, **kw):
			seen.append(self.flags_now())
			return real_save(doc, *a, **kw)
		fake_frappe.Doc.save = save
		try:
			api.create_variants(template="RVX4184", attributes=json.dumps([COLOUR, SIZE]),
								combinations=json.dumps([{"values": {COLOUR: "Black", SIZE: "Small"}}]))
		finally:
			fake_frappe.Doc.save = real_save

		self.assertTrue(self.f.db.exists("Item", "RVX4184-001-0003"), "the variant was still created")
		self.assertTrue(all(f == (True, True) for f in seen), f"a save ran with the webhooks live: {set(seen)}")
		self.assertEqual(self.flags_now(), (False, False), "the flags were left set")

	def test_the_flags_are_restored_even_when_the_call_throws(self):
		api = self.api
		with self.assertRaises(Exception):
			api.get_variants(template="NOPE-does-not-exist")
		self.assertEqual(self.flags_now(), (False, False), "a thrown call left the flags set")


class RoleGuard(FlowBase):
	"""Every whitelisted method is reachable by any logged-in user, and most reads use
	frappe.get_all, which applies no permissions - so the role check is the only guard."""

	def setUp(self):
		super().setUp()
		self.f.session.user = "clerk@example.com"  # not Administrator, so only_for really runs

	def test_without_the_role_every_call_is_refused_with_a_useful_message(self):
		self.f.roles = ["Sales User"]
		for call, kwargs in (("get_variants", {"template": "RVX4184"}),
							 ("search_templates", {"sku": "RVX"}),
							 ("queue_merge", {"template": "RVX4184", "pairs": "[]"})):
			with self.assertRaises(Exception) as caught:
				getattr(self.api, call)(**kwargs)
			message = str(caught.exception)
			self.assertIn("Item Manager", message, f"{call} gave no usable reason: {message!r}")
			self.assertIn("System Manager", message, f"{call} did not say who can grant it: {message!r}")

	def test_either_role_is_enough(self):
		for role in ("Item Manager", "System Manager"):
			self.f.roles = [role]
			self.assertEqual(self.api.get_variants(template="RVX4184")["template"]["item_code"], "RVX4184",
							 f"{role} should be allowed")

	def test_the_page_and_the_api_agree_on_who_may_use_it(self):
		"""The Page's roles guard the desk route and ROLES guards the API; they are kept by hand, so
		a drift between them would let someone open a page that refuses every call."""
		import json as _json
		import pathlib
		here = pathlib.Path(self.api.__file__).parent
		page = _json.loads((here / "item_merge.json").read_text())
		self.assertEqual(sorted(r["role"] for r in page["roles"]), sorted(self.api.ROLES))
		js = (here / "item_merge.js").read_text()
		for role in self.api.ROLES:
			self.assertIn(f'"{role}"', js, f"{role} is missing from the page's own check")
