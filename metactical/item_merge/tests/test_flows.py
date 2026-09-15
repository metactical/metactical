"""Flow tests: the real family / merge / jobs / websites code against an in-memory frappe.

Skipped on a bench (the real frappe is importable there); run offline from the app repo root:
	python -m unittest discover -s metactical/item_merge/tests -t . -v
"""
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
		for mod in ("family", "merge", "websites", "jobs"):
			sys.modules.pop(f"metactical.item_merge.{mod}", None)
		self.family = importlib.import_module("metactical.item_merge.family")
		self.merge = importlib.import_module("metactical.item_merge.merge")
		self.websites = importlib.import_module("metactical.item_merge.websites")
		self.jobs = importlib.import_module("metactical.item_merge.jobs")
		self.merge.MERGE_SPACING_S = 0
		self.jobs.merge.MERGE_SPACING_S = 0
		self.websites.site_configs = lambda: {}
		self.seed()

	def tearDown(self):
		for mod in ("frappe", "frappe.utils", "frappe.utils.background_jobs", "erpnext", "erpnext.controllers",
					"erpnext.controllers.item_variant", "metactical.custom_scripts.utils.s3_image_api",
					"metactical.item_merge.family", "metactical.item_merge.merge", "metactical.item_merge.websites",
					"metactical.item_merge.jobs"):
			sys.modules.pop(mod, None)

	def run_enqueued(self):
		"""Run the queued jobs the way the worker does: the method with exactly the kwargs that were enqueued."""
		while self.f.enqueued:
			method, kwargs = self.f.enqueued.pop(0)
			getattr(self.jobs, method.rsplit(".", 1)[1])(**kwargs)

	def insert(self, doc):
		return self.f.get_doc(doc).insert()

	def item(self, code, **fields):
		attrs = fields.pop("attrs", {})
		return self.insert({"doctype": "Item", "item_code": code, "item_name": code, "stock_uom": "Nos", "is_stock_item": 1,
							"item_group": "T-Shirts", "has_variants": 0, **fields,
							"attributes": [{"attribute": a, "attribute_value": v} for a, v in attrs.items()]})

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


class WebsitesFlow(FlowBase):
	def setUp(self):
		super().setUp()
		self.sites = {"RET - Camo": {"api_url": "camo", "headers": {}, "site": "camouflage.ca"},
					  "RET - Gorilla": {"api_url": "gorilla", "headers": {}, "site": "gorillasurplus.com"}}
		self.catalogue = {("camo", "RVX4184"): [{"externalId": "RVX4184", "slug": "ravenx-classic-ops-tee",
												 "variants": [{"fullRetailSku": "RVX4184-0001"}, {"fullRetailSku": "RVX4184-0002"}]}]}
		self.websites.site_configs = lambda: self.sites
		self.websites.fetch_products = lambda config, external_id, slug=None: self.catalogue.get((config["api_url"], external_id), [])
		self.insert({"doctype": "Item Price", "item_code": "RVX4184-0001", "price_list": "RET - Gorilla"})

	def test_plan_apply_and_check(self):
		w = self.websites
		plan = {r["price_list"]: r for r in w.plan("RVX4184")["rows"]}
		self.assertEqual((plan["RET - Camo"]["action"], plan["RET - Camo"]["slug"]), ("add", "ravenx-classic-ops-tee"))
		self.assertEqual(plan["RET - Gorilla"]["note"], "not on the website")
		self.assertEqual(plan["RET - RAS"]["note"], "no Item Price on this price list")

		out = w.apply("RVX4184")
		self.assertEqual(self.f.loaded_from_sb, ["RVX4184"])
		self.assertEqual([(r.price_list, r.slug) for r in self.f.get_doc("Item", "RVX4184").item_detail],
						 [("RET - Camo", "ravenx-classic-ops-tee")])
		self.assertTrue(out["check"]["ok"], out["check"])

		# a blank slug row: Load Data From SB must not run
		doc = self.f.get_doc("Item", "RVX4184")
		doc.append("item_detail", {"price_list": "RET - Gorilla", "slug": ""})
		doc.save()
		self.assertIn("blank slug", w.apply("RVX4184")["load_data_from_sb"])
		self.assertEqual(self.f.loaded_from_sb, ["RVX4184"])

	def test_check_flags_external_id_and_count(self):
		self.catalogue[("camo", "RVX4184")] = [{"externalId": "RVX4184BLK", "slug": "ravenx-classic-ops-tee", "variants": []}]
		doc = self.f.get_doc("Item", "RVX4184")
		doc.append("item_detail", {"price_list": "RET - Camo", "slug": "ravenx-classic-ops-tee"})
		doc.save()
		row = self.websites.check("RVX4184")["rows"][0]
		self.assertEqual(row["status"], "mismatch")
		self.assertIn("External ID is 'RVX4184BLK'", row["note"])
		self.assertIn("0 variant(s) on the site vs 2 in ERP", row["note"])

	def test_several_products_are_left_alone(self):
		self.catalogue[("camo", "RVX4184BLK")] = [{"externalId": "RVX4184BLK", "slug": "ravenx-black"}]
		self.insert({"doctype": "Item Merge History", "old_item_code": "RVX4184BLK", "new_item_code": "RVX4184",
					 "old_item": json.dumps({"has_variants": 1})})
		camo = next(r for r in self.websites.plan("RVX4184")["rows"] if r["price_list"] == "RET - Camo")
		self.assertEqual(camo["action"], "skip")
		self.assertIn("several products match", camo["note"])


if __name__ == "__main__":
	unittest.main()
