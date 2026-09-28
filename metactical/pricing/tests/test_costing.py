# Copyright (c) 2026, International Camouflage Ltd
"""Unit tests for the Price Revision maths. No site, no frappe, just numbers.

	python -m pytest apps/metactical/metactical/pricing/tests/ -q
"""

import unittest

from metactical.pricing.costing import (
	apply_rounding,
	build_price_line,
	landed_cost,
	landed_in_currency,
	margin_pct,
	suggest_markup,
	suggest_preserve_margin,
)


class TestLandedCost(unittest.TestCase):
	def test_duty_and_fx_compound(self):
		# USD 10.00, 14% duty, bought at 1.3875 -> USD 11.40 -> CAD 15.82
		r = landed_cost(10, 14, 1.3875)
		self.assertAlmostEqual(r["supplier_ccy"], 11.40, places=2)
		self.assertAlmostEqual(r["company_ccy"], 15.8175, places=4)

	def test_no_duty_no_fx(self):
		r = landed_cost(10, 0, 1)
		self.assertEqual(r["supplier_ccy"], 10.0)
		self.assertEqual(r["company_ccy"], 10.0)

	def test_missing_values_are_zero_not_crashes(self):
		r = landed_cost(None, None, None)
		self.assertEqual(r["supplier_ccy"], 0.0)
		self.assertEqual(r["company_ccy"], 0.0)

	def test_freight_is_not_included(self):
		# guards the decision — no freight component anywhere
		self.assertAlmostEqual(landed_cost(100, 0, 1)["company_ccy"], 100.0)


class TestCurrencySelection(unittest.TestCase):
	def setUp(self):
		self.landed = landed_cost(10, 14, 1.3875)

	def test_cad_list_uses_company_currency(self):
		v = landed_in_currency(self.landed, "CAD", "USD", "CAD")
		self.assertAlmostEqual(v, 15.8175, places=4)

	def test_usd_list_against_usd_supplier_skips_fx(self):
		# RET - CamoUSA priced off a USD supplier must not round-trip through CAD
		v = landed_in_currency(self.landed, "USD", "USD", "CAD")
		self.assertAlmostEqual(v, 11.40, places=2)

	def test_third_currency_is_refused_not_guessed(self):
		self.assertIsNone(landed_in_currency(self.landed, "AED", "USD", "CAD"))


class TestMargin(unittest.TestCase):
	def test_basic(self):
		self.assertAlmostEqual(margin_pct(100, 40), 60.0)

	def test_zero_price_is_unknown_not_zero(self):
		self.assertIsNone(margin_pct(0, 40))

	def test_selling_below_cost_is_negative(self):
		self.assertAlmostEqual(margin_pct(30, 40), -33.3333, places=3)


class TestRounding(unittest.TestCase):
	def test_rounds_up_to_x99(self):
		self.assertEqual(apply_rounding(42.30, "0.99"), 42.99)

	def test_always_rounds_up_never_to_nearest(self):
		# 42.10 sits nearer 41.99, but rounding a suggested price DOWN hands
		# back the margin the cost increase was meant to recover
		self.assertEqual(apply_rounding(42.10, "0.99"), 42.99)

	def test_a_price_already_on_the_ending_is_left_alone(self):
		self.assertEqual(apply_rounding(42.99, "0.99"), 42.99)

	def test_x95(self):
		self.assertEqual(apply_rounding(42.60, "0.95"), 42.95)

	def test_whole(self):
		self.assertEqual(apply_rounding(42.60, "whole"), 43.0)

	def test_none_leaves_it_alone(self):
		self.assertEqual(apply_rounding(42.61, "none"), 42.61)

	def test_never_goes_negative_on_small_prices(self):
		self.assertGreaterEqual(apply_rounding(0.40, "0.99"), 0)


class TestSuggestions(unittest.TestCase):
	def test_preserve_margin_holds_the_percentage(self):
		# 60% margin at cost 40 -> cost 50 should land near 124.99
		out = suggest_preserve_margin(100, 40, 50, "none")
		self.assertAlmostEqual(out, 125.0, places=2)
		self.assertAlmostEqual(margin_pct(out, 50), 60.0, places=6)

	def test_preserve_margin_needs_a_starting_price(self):
		self.assertIsNone(suggest_preserve_margin(0, 40, 50))

	def test_markup(self):
		self.assertEqual(suggest_markup(10, 3.42, "0.99"), 34.99)

	def test_markup_of_zero_is_no_suggestion(self):
		self.assertIsNone(suggest_markup(10, 0))


class TestPriceLine(unittest.TestCase):
	def base(self, **kw):
		args = dict(
			price_list="RET - Camo",
			list_currency="CAD",
			old_price=100.0,
			old_landed=40.0,
			new_landed=50.0,
			markup=None,
			rounding="0.99",
			min_margin_pct=None,
			cost_went_down=False,
		)
		args.update(kw)
		return build_price_line(**args)

	def test_cost_up_proposes_an_increase(self):
		line = self.base()
		self.assertEqual(line["action"], "Update")
		self.assertGreater(line["new_price"], 100.0)

	def test_cost_down_holds_the_price_when_suggestions_are_off(self):
		line = self.base(new_landed=30.0, cost_went_down=True, use_suggested=False)
		self.assertEqual(line["action"], "Hold")
		self.assertEqual(line["new_price"], 100.0)
		self.assertGreater(line["new_margin_pct"], line["old_margin_pct"])

	def test_matrix_beats_preserve_margin_when_present(self):
		# landed 50 x 3.0 = 150.00, rounded up to the next .99 ending
		line = self.base(markup=3.0)
		self.assertEqual(line["suggested_by_matrix"], 150.99)
		self.assertEqual(line["suggested_price"], 150.99)
		self.assertIsNotNone(line["suggested_by_margin"])  # still shown for comparison

	def test_below_floor_is_flagged_and_sent_to_review(self):
		# a 33% margin today, and a thin markup: both suggestions sit under 40%
		line = self.base(old_price=60.0, old_landed=40.0, markup=1.2, min_margin_pct=40)
		self.assertTrue(line["below_floor"])
		self.assertEqual(line["action"], "Review")

	def test_held_price_under_floor_stays_held(self):
		line = self.base(markup=1.2, min_margin_pct=70, cost_went_down=True, use_suggested=False)
		self.assertTrue(line["below_floor"])
		self.assertEqual(line["action"], "Hold")

	def test_franchise_list_is_exempt_from_the_floor(self):
		line = self.base(price_list="RET - CamoFRN - USD", list_currency="USD",
		                 markup=1.2, min_margin_pct=40)
		self.assertTrue(line["low_margin_exempt"])
		self.assertFalse(line["below_floor"])

	def test_franchise_list_still_cannot_price_below_landed(self):
		# exempt from the floor, never exempt from selling under cost
		# already selling under cost, so neither markup nor margin clears landed
		line = self.base(price_list="RET - CamoFRN - USD", list_currency="USD",
		                 old_price=45.0, old_landed=50.0, new_landed=60.0,
		                 markup=0.9, min_margin_pct=40)
		self.assertEqual(line["action"], "Review")

	def test_cost_rise_never_suggests_a_lower_price(self):
		# an item priced well above the usual markup keeps its margin
		line = self.base(old_price=140.99, old_landed=34.55, new_landed=50.09, markup=1.79)
		self.assertGreaterEqual(line["suggested_price"], 140.99)
		self.assertEqual(line["suggested_price"], line["suggested_by_margin"])

	def test_cost_rise_lifts_an_item_below_the_norm(self):
		line = self.base(old_price=55.0, old_landed=45.0, new_landed=50.0, markup=1.8)
		self.assertEqual(line["suggested_price"], line["suggested_by_matrix"])

	def test_no_old_price_and_no_matrix_needs_a_human(self):
		line = self.base(old_price=0, old_landed=0)
		self.assertEqual(line["action"], "Review")

	def test_item_not_on_list_is_priced_from_the_markup(self):
		line = self.base(old_price=0, old_landed=0, markup=2.0)
		self.assertEqual(line["action"], "Update")
		self.assertEqual(line["new_price"], line["suggested_by_matrix"])
		self.assertIn("Not on this list yet", line["note"])

	def test_item_not_on_list_even_when_cost_fell(self):
		# the hold rule keeps an existing price; there is none to keep
		line = self.base(old_price=0, old_landed=0, markup=2.0, cost_went_down=True)
		self.assertEqual(line["action"], "Update")

	def test_cost_down_takes_the_suggestion_when_on(self):
		# keep-margin price: 60% margin on 30 is 30 / 0.4 = 75 -> 75.99, lower than today's 100
		line = self.base(new_landed=30.0, cost_change="down")
		self.assertEqual(line["action"], "Update")
		self.assertEqual(line["new_price"], 75.99)

	def test_cost_down_never_suggests_a_higher_price(self):
		# a big markup would raise it; a falling cost never does
		line = self.base(new_landed=30.0, cost_change="down", markup=4.0)
		self.assertLessEqual(line["suggested_price"], 100.0)

	def test_unchanged_cost_always_holds(self):
		line = self.base(new_landed=40.0, cost_change="same", markup=4.0)
		self.assertEqual(line["action"], "Hold")
		self.assertEqual(line["new_price"], 100.0)

	def test_cost_up_holds_when_suggestions_are_off(self):
		line = self.base(use_suggested=False)
		self.assertEqual(line["action"], "Hold")
		self.assertEqual(line["new_price"], 100.0)
		self.assertIsNotNone(line["suggested_price"])

	def test_new_listing_waits_for_a_person_when_suggestions_are_off(self):
		line = self.base(old_price=0, old_landed=0, markup=2.0, use_suggested=False)
		self.assertEqual(line["action"], "Review")
		self.assertEqual(line["new_price"], 0.0)

	def test_margin_delta_is_reported(self):
		line = self.base()
		self.assertIsNotNone(line["margin_delta_pct"])


if __name__ == "__main__":
	unittest.main()
