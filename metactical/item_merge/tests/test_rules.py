"""Offline tests for the Item Merge logic that needs no database.

`rules` and `pairing` are deliberately free of frappe so they can be tested without a bench - the
module docstring has said so since the start, and until now there were no tests to show for it.
Run with: bench --site <site> run-tests --app metactical --module metactical.item_merge.tests.test_rules
or, with no bench at all: python -m unittest metactical.item_merge.tests.test_rules
"""
import unittest

from metactical.item_merge import attribute_ai, pairing, rules


class TestCodes(unittest.TestCase):
	def test_base_code_drops_trailing_colour_letters(self):
		self.assertEqual(rules.base_code("RVX4184BLK"), "RVX4184")
		self.assertEqual(rules.base_code("RVX4184"), "RVX4184")

	def test_base_code_keeps_a_code_with_no_digits(self):
		self.assertEqual(rules.base_code("BLACK"), "BLACK")

	def test_check_code_rejects_what_cannot_be_an_item_code(self):
		for bad in ("a b", "a/b", "a\\b", "a%b", "a#b", "a?b"):
			with self.assertRaises(rules.UserError):
				rules.check_code(bad)
		self.assertEqual(rules.check_code("CAR103334-BLK-0001"), "CAR103334-BLK-0001")

	def test_build_code_refuses_an_abbreviation_that_cannot_go_in_a_code(self):
		abbr = {"Colour": {"Black": "BLK"}, "Size": {"Large": "L G"}}
		self.assertEqual(rules.build_code("T", ["Colour"], {"Colour": "Black"}, abbr), "T-BLK")
		with self.assertRaises(rules.UserError):
			rules.build_code("T", ["Size"], {"Size": "Large"}, abbr)

	def test_build_code_strips_an_abbreviation_that_carries_its_own_dash(self):
		self.assertEqual(
			rules.build_code("T", ["Colour"], {"Colour": "Black"}, {"Colour": {"Black": "-001"}}),
			"T-001")

	def test_check_attributes_refuses_the_legacy_one(self):
		with self.assertRaises(rules.UserError):
			rules.check_attributes(["Variant Number"], legacy="Variant Number")
		with self.assertRaises(rules.UserError):
			rules.check_attributes(["A", "A"])
		with self.assertRaises(rules.UserError):
			rules.check_attributes([])
		self.assertEqual(rules.check_attributes(["A", "B"]), ["A", "B"])


class TestSettings(unittest.TestCase):
	def test_a_transacted_new_item_locks_its_settings(self):
		issues, fixes = rules.settings_diff({"stock_uom": "Nos"}, {"stock_uom": "Box"}, new_ledger=3)
		self.assertTrue(issues)
		self.assertEqual(fixes, {})

	def test_an_untouched_new_item_can_be_fixed(self):
		issues, fixes = rules.settings_diff({"stock_uom": "Nos"}, {"stock_uom": "Box"}, new_ledger=0)
		self.assertEqual(issues, [])
		self.assertEqual(fixes, {"stock_uom": "Nos"})

	def test_preflight_fixes_only_the_known_is_stock_item_trap(self):
		issues, fixes = rules.preflight({"is_stock_item": 1}, {"is_stock_item": 0})
		self.assertEqual((issues, fixes), ([], {"is_stock_item": 1}))
		issues, _ = rules.preflight({"has_batch_no": 1}, {"has_batch_no": 0})
		self.assertTrue(issues)


class TestSuppliers(unittest.TestCase):
	def test_a_blank_part_number_loses_to_a_real_one(self):
		kept = rules.dedupe_suppliers([{"supplier": "A", "supplier_part_no": ""},
									   {"supplier": "A", "supplier_part_no": "X1"}])
		self.assertEqual(kept, [{"supplier": "A", "supplier_part_no": "X1"}])

	def test_a_lone_blank_row_is_kept(self):
		rows = [{"supplier": "A", "supplier_part_no": ""}]
		self.assertEqual(rules.dedupe_suppliers(rows), rows)


class TestPricingRuleBlocker(unittest.TestCase):
	def test_reads_the_rule_name_out_of_the_refusal(self):
		self.assertEqual(
			rules.pricing_rule_blocker("Cannot delete, linked with Pricing Rule <a>PRLE-0042</a>"),
			"PRLE-0042")

	def test_none_when_something_else_blocks(self):
		self.assertIsNone(rules.pricing_rule_blocker("linked with Sales Order SO-1"))


class TestPlanPairs(unittest.TestCase):
	"""The matching, conflict and ambiguity logic the AI deliberately does not do."""

	TEMPLATE = {"name": "T", "attributes": [
		{"attribute": "Variant Number", "numeric_values": 1},
		{"attribute": "Colour", "attribute_value": None},
		{"attribute": "Size", "attribute_value": None}]}

	def new(self, code, colour, size):
		return {"name": code, "item_name": code, "attributes": [
			{"attribute": "Colour", "attribute_value": colour},
			{"attribute": "Size", "attribute_value": size}]}

	def old(self, code, name):
		return {"name": code, "item_name": name, "variant_of": "T",
				"attributes": [{"attribute": "Variant Number", "attribute_value": "1"}]}

	def test_ai_values_are_used_and_beat_the_name(self):
		variants = [self.new("N1", "Olive", "Large"),
					self.old("O1", "Pant - nonsense wording - whatever")]
		plan = pairing.plan_pairs(self.TEMPLATE, variants,
								  values={"O1": {"Colour": "Olive", "Size": "Large"}})
		self.assertEqual([(p["old"], p["new"]) for p in plan["pairs"]], [("O1", "N1")])

	def test_falls_back_to_the_name_when_the_ai_said_nothing(self):
		variants = [self.new("N1", "Olive", "Large"), self.old("O1", "Pant - OD - L")]
		plan = pairing.plan_pairs(self.TEMPLATE, variants, values={})
		self.assertEqual([(p["old"], p["new"]) for p in plan["pairs"]], [("O1", "N1")])

	def test_a_value_no_new_variant_carries_is_refused_not_paired(self):
		variants = [self.new("N1", "Olive", "Large"), self.old("O1", "Pant - OD - L")]
		plan = pairing.plan_pairs(self.TEMPLATE, variants,
								  values={"O1": {"Colour": "Purple", "Size": "Large"}})
		self.assertEqual(plan["pairs"], [])
		self.assertEqual(len(plan["unmatched"]), 1)
		self.assertIn("Purple", plan["unmatched"][0]["reason"])

	def test_two_olds_on_one_new_is_a_conflict_and_neither_is_paired(self):
		variants = [self.new("N1", "Olive", "Large"),
					self.old("O1", "Pant - OD - L"), self.old("O2", "Pant - Olive Drab - Large")]
		plan = pairing.plan_pairs(self.TEMPLATE, variants, values={})
		self.assertEqual(plan["pairs"], [])
		self.assertEqual(len(plan["conflicts"]), 1)
		self.assertEqual(sorted(plan["conflicts"][0]["olds"]), ["O1", "O2"])

	def test_only_an_empty_unmatched_old_is_a_leftover(self):
		variants = [self.new("N1", "Olive", "Large"), self.old("O1", "Pant - Purple - L")]
		plan = pairing.plan_pairs(self.TEMPLATE, variants, emptiness={"O1": True}, values={})
		self.assertEqual([r["old"] for r in plan["leftovers"]], ["O1"])
		self.assertEqual(plan["blocked"], [])

	def test_a_new_variant_nothing_pairs_to_is_reported(self):
		variants = [self.new("N1", "Olive", "Large"), self.new("N2", "Black", "Small")]
		plan = pairing.plan_pairs(self.TEMPLATE, variants, values={})
		self.assertEqual(plan["unused_new"], ["N1", "N2"])


class TestShortNames(unittest.TestCase):
	"""What the AI is actually shown. The prompt is the part that was wrong, not the model."""

	ALLOWED = {"Colour": {"Shadow", "Black"}, "Size": {"30 x 30", "30 x 32"}}

	def olds(self, *names):
		return [{"name": "V%d" % i, "item_name": n} for i, n in enumerate(names)]

	def test_a_one_colour_family_keeps_its_colour(self):
		"""The bug: every variant of a per-colour template shares the colour, so it lands in the
		common prefix and used to be stripped as style - leaving the model to read a colour out of
		"30 x 30", which it correctly answered null for."""
		olds = self.olds("Work Pant - Shadow - 30 x 30", "Work Pant - Shadow - 30 x 32")
		short = attribute_ai._short_names(olds, self.ALLOWED)
		self.assertEqual(sorted(short.values()), ["Shadow - 30 x 30", "Shadow - 30 x 32"])

	def test_the_style_is_still_stripped(self):
		olds = self.olds("Work Pant - Shadow - 30 x 30", "Work Pant - Black - 30 x 32")
		short = attribute_ai._short_names(olds, self.ALLOWED)
		self.assertEqual(sorted(short.values()), ["Black - 30 x 32", "Shadow - 30 x 30"])

	def test_an_alias_in_the_prefix_is_kept_too(self):
		"""OD means Olive, so it is an answer and must not be mistaken for style."""
		allowed = {"Colour": {"Olive"}, "Size": {"Large", "Small"}}
		olds = self.olds("Tac Pant - OD - L", "Tac Pant - OD - S")
		short = attribute_ai._short_names(olds, allowed)
		self.assertEqual(sorted(short.values()), ["OD - L", "OD - S"])

	def test_without_allowed_values_nothing_is_protected(self):
		olds = self.olds("Work Pant - Shadow - 30 x 30", "Work Pant - Shadow - 30 x 32")
		self.assertEqual(sorted(attribute_ai._short_names(olds).values()),
						 ["30 x 30", "30 x 32"])

	def test_a_single_variant_is_left_whole(self):
		olds = self.olds("Work Pant - Shadow - 30 x 30")
		self.assertEqual(list(attribute_ai._short_names(olds, self.ALLOWED).values()),
						 ["Work Pant - Shadow - 30 x 30"])


if __name__ == "__main__":
	unittest.main()
