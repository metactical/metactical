"""Offline tests for metactical.item_merge.rules. No bench, no network.

Cases come from families worked on the dev site (UF96760-01, CND101259/CND101260, RVX4184).
Run from the app repo root:  python -m unittest discover -s metactical/item_merge/tests -t . -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))
from metactical.item_merge import rules  # noqa: E402
from metactical.item_merge.rules import UserError  # noqa: E402

SIZE = "Size - Clothing - XS to 8XL"
COLOUR = "Colour - Clothing - PS"
ACTUAL = "Colour - Actual"


class BuildCode(unittest.TestCase):
	def test_joins_abbreviations(self):
		abbr = {COLOUR: {"Black": "001"}, SIZE: {"XSmall": "0002"}}
		self.assertEqual(rules.build_code("RVX4184", [COLOUR, SIZE], {COLOUR: "Black", SIZE: "XSmall"}, abbr), "RVX4184-001-0002")

	def test_dash_in_abbreviation_never_doubles(self):
		abbr = {ACTUAL: {"Black": "-001"}, SIZE: {"XSmall": "0002"}}
		self.assertEqual(rules.build_code("RVX4184BLK", [ACTUAL, SIZE], {ACTUAL: "Black", SIZE: "XSmall"}, abbr), "RVX4184BLK-001-0002")

	def test_spaces_in_abbreviation_refused(self):
		with self.assertRaisesRegex(UserError, "can't go in an item code"):
			rules.build_code("RVX4184", [ACTUAL], {ACTUAL: "Camo - Woodland"}, {ACTUAL: {"Camo - Woodland": "Camo - Wood"}})

	def test_missing_abbreviation_refused(self):
		with self.assertRaisesRegex(UserError, "No abbreviation"):
			rules.build_code("RVX4184", [COLOUR], {COLOUR: "Black"}, {COLOUR: {"Black": None}})

	def test_code_part_and_check_code(self):
		self.assertEqual(rules.code_part("Coyo Brn", "Coyote Brown"), "CoyoBrn")
		self.assertEqual(rules.code_part("", "Olive / Drab"), "OliveDrab")
		with self.assertRaisesRegex(UserError, "can't be an item code"):
			rules.check_code("UF 1")
		self.assertEqual(rules.check_code("UF96760-01"), "UF96760-01")


class AttributesAndNames(unittest.TestCase):
	def test_attribute_rules(self):
		for attrs, msg in (([], "one or two"), ([COLOUR, COLOUR], "different"), (["Variant Number"], "being replaced"),
						   ([COLOUR, SIZE, "X"], "one or two")):
			with self.assertRaisesRegex(UserError, msg):
				rules.check_attributes(attrs)

	def test_loose_match_needs_a_whole_word_prefix_and_no_tie(self):
		allowed = {"Olive", "Olive Green", "Navy"}
		self.assertEqual(rules.resolve_loose("Olive Green Drab", allowed, {}), "Olive Green")
		self.assertIsNone(rules.resolve_loose("Olivedrab", allowed, {}))
		self.assertIsNone(rules.resolve_loose("Midnight", allowed, {}))

	def test_typos_and_longer_names_are_read(self):
		allowed = {ACTUAL: {"Olive", "Midnight Navy", "Black"}, SIZE: {"Small", "XSmall"}}
		self.assertEqual(rules.read_values({"item_name": "Vest - Olive Drap - S"}, [ACTUAL, SIZE], allowed),
						 {ACTUAL: "Olive", SIZE: "Small"})
		self.assertEqual(rules.read_values({"item_name": "Vest - Midnight Navy Blue - XS"}, [ACTUAL, SIZE], allowed),
						 {ACTUAL: "Midnight Navy", SIZE: "XSmall"})

	def test_colour_from_the_legacy_template_suffix(self):
		allowed = {COLOUR: {"Black", "Camo - Woodland"}, SIZE: {"Small"}}
		doc = {"item_name": "RavenX Classic Ops T-Shirt - Small", "variant_of": "RVX4184WLD"}
		self.assertEqual(rules.read_values(doc, [COLOUR, SIZE], allowed), {COLOUR: "Camo - Woodland", SIZE: "Small"})
		self.assertIsNone(rules.read_values({"item_name": "Shirt - Purple - Small", "variant_of": "X1"}, [COLOUR, SIZE], allowed))

	def test_style_name_drops_values_of_the_chosen_attributes(self):
		olds = [{"item_name": f"RavenX Classic Ops T-Shirt - Black - {s}"} for s in ("XSmall", "Small")]
		allowed = {COLOUR: {"Black"}}
		self.assertEqual(rules.style_name({"name": "RVX4184", "item_name": "T"}, olds, allowed), "RavenX Classic Ops T-Shirt")
		self.assertEqual(rules.style_name({"name": "RVX4184", "item_name": "Template name"}, [], allowed), "Template name")

	def test_product_name_and_base_sku(self):
		self.assertEqual(rules.product_name("Class B Men'S Uniform Shirt - Black - Small"), "Class B Men'S Uniform Shirt")
		self.assertEqual(rules.base_sku("CND101259-002-0001-tempt"), "CND101259")
		self.assertEqual(rules.base_code("RVX4184BLK"), "RVX4184")
		self.assertEqual(rules.base_code("ABC"), "ABC")


class TemplateMergeSafeguards(unittest.TestCase):
	"""CND101259-002-0001-tempt on dev: men's and women's shirts merged into one template by mistake."""

	def test_different_products_and_mixed_groups(self):
		c = rules.consolidation_summary([
			{"item_code": "CND101259-002-0001-tempt", "item_name": "Class B Men'S Uniform Shirt - Black - Small",
			 "group_counts": {"01-01-05 - Button-Up Shirts": 2}, "variant_count": 2},
			{"item_code": "CND101260-002-0001-tempt", "item_name": "Class B Women'S Uniform Shirt - Black - XSmall",
			 "group_counts": {"01-01-01 - T-Shirts": 1}, "variant_count": 1}])
		self.assertTrue(c["different_products"])
		self.assertEqual(c["product_names"], ["Class B Men'S Uniform Shirt", "Class B Women'S Uniform Shirt"])
		self.assertTrue(c["blocked"])
		self.assertEqual([t["base_sku"] for t in c["templates"]], ["CND101259", "CND101260"])
		self.assertIn("01-01-01 - T-Shirts: CND101260-002-0001-tempt (1)", c["block_reason"])

	def test_one_product_one_group_passes(self):
		c = rules.consolidation_summary([
			{"item_code": "RVX4184BLK", "item_name": "RavenX Classic Ops T-Shirt - Black", "group_counts": {"T-Shirts": 6}},
			{"item_code": "RVX4184WLD", "item_name": "RavenX Classic Ops T-Shirt - Woodland", "group_counts": {"T-Shirts": 6}}])
		self.assertFalse(c["different_products"])
		self.assertFalse(c["blocked"])
		self.assertEqual(c["block_reason"], "")


class Settings(unittest.TestCase):
	def test_fixable_only_while_new_has_no_ledger(self):
		old, new = {"stock_uom": "Nos", "is_stock_item": 1}, {"stock_uom": "Nos", "is_stock_item": 0}
		self.assertEqual(rules.settings_diff(old, new, 0), ([], {"is_stock_item": 1}))
		issues, fixes = rules.settings_diff(old, new, 5)
		self.assertEqual(fixes, {})
		self.assertIn("already has stock history", issues[0])

	def test_preflight_fixes_only_the_known_trap(self):
		self.assertEqual(rules.preflight({"is_stock_item": 1}, {"is_stock_item": 0}), ([], {"is_stock_item": 1}))
		issues, _ = rules.preflight({"is_stock_item": 0, "stock_uom": "Nos"}, {"is_stock_item": 1, "stock_uom": "Box"})
		self.assertEqual(len(issues), 2)


class Suppliers(unittest.TestCase):
	def test_blank_part_number_dropped_when_the_supplier_has_one(self):
		rows = [{"supplier": "Condor", "supplier_part_no": None, "name": "a"},
				{"supplier": "Condor", "supplier_part_no": "101260-002", "name": "b"},
				{"supplier": "Condor", "supplier_part_no": "101260-002", "name": "c"},
				{"supplier": "Other", "supplier_part_no": "", "name": "d"}]
		self.assertEqual([r["name"] for r in rules.dedupe_suppliers(rows)], ["b", "d"])


class PricingRuleBlocker(unittest.TestCase):
	def test_reads_the_rule_from_the_refusal(self):
		msg = 'Cannot delete or cancel because Item <a href="/app/item/X">X</a> is linked with Pricing Rule <a href="/app/pricing-rule/PRLE-0042">PRLE-0042</a>'
		self.assertEqual(rules.pricing_rule_blocker(msg), "PRLE-0042")
		self.assertIsNone(rules.pricing_rule_blocker("Cannot delete: linked with Sales Order SO-1"))


class ItemChanges(unittest.TestCase):
	FAMILY = {"A-1": {"item_name": "Shirt - S", "ifw_retailskusuffix": "A1S"},
			  "A-2": {"item_name": "Shirt - M", "ifw_retailskusuffix": "A1M"}}

	def test_only_real_changes_become_rows(self):
		rows, problems = rules.plan_changes("A", self.FAMILY, [
			{"item_code": "A-1", "new_code": "A1S", "item_name": "Shirt - S", "retail_sku": "A1S"},
			{"item_code": "A-2", "item_name": "Shirt - Medium"}])
		self.assertEqual(problems, [])
		self.assertEqual(rows, [{"item_code": "A-1", "new_code": "A1S", "new_item_name": None, "new_retail_sku": None},
								{"item_code": "A-2", "new_code": None, "new_item_name": "Shirt - Medium", "new_retail_sku": None}])

	def test_refusals(self):
		_, problems = rules.plan_changes("A", self.FAMILY, [
			{"item_code": "B-1", "item_name": "x"},
			{"item_code": "A-1", "new_code": "A 1", "item_name": " "},
			{"item_code": "A-2", "retail_sku": "A1S"}])
		self.assertTrue(any("not a variant" in p for p in problems))
		self.assertTrue(any("can't be an item code" in p for p in problems))
		self.assertTrue(any("item name is empty" in p for p in problems))
		self.assertTrue(any("retail SKU A1S would be on more than one variant" in p for p in problems))

	def test_swapping_skus_between_variants_is_allowed(self):
		_, problems = rules.plan_changes("A", self.FAMILY, [{"item_code": "A-1", "retail_sku": "A1M"},
															 {"item_code": "A-2", "retail_sku": "A1S"}])
		self.assertEqual(problems, [])

	def test_pair_edits(self):
		problems = rules.pair_edit_problems([{"new": "N1", "item_name": "", "retail_sku": "S"},
											 {"new": "N2", "item_name": "x", "retail_sku": "S"}])
		self.assertEqual(problems, ["N1: item name is empty", "retail SKU S is used on more than one new variant"])


if __name__ == "__main__":
	unittest.main()
