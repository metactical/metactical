# Copyright (c) 2026, International Camouflage Ltd
"""End-to-end arithmetic on real ICL numbers.

Everything here comes from live production data rather than invented figures,
so a change that breaks how ICL actually prices will fail here rather than in
front of a buyer.
"""

import unittest

from metactical.pricing.costing import build_price_line, landed_cost, landed_in_currency

# Observed on prod 2026-09-17
CONDOR_DUTY = 13.83      # average ifw_duty_rate across Condor items
PO_RATE = 1.3875         # conversion_rate stamped on a real Condor PO
CONDOR_CAMO = 3.42       # median markup, SUP - Condor Outdoor -> RET - Camo
CONDOR_USA = 1.67        # median markup, SUP - Condor Outdoor -> RET - CamoUSA


class TestCondorCostIncrease(unittest.TestCase):
	"""A Condor item whose cost rises USD 21.00 -> 24.00 (the +14% case ICL hits)."""

	def setUp(self):
		self.old = landed_cost(21.00, CONDOR_DUTY, PO_RATE)
		self.new = landed_cost(24.00, CONDOR_DUTY, PO_RATE)

	def test_landed_in_cad_is_what_the_grid_shows(self):
		# 21.00 x 1.1383 x 1.3875 = 33.17 CAD
		self.assertAlmostEqual(self.old["company_ccy"], 33.17, places=2)
		self.assertAlmostEqual(self.new["company_ccy"], 37.91, places=2)

	def test_cad_banner_price_rises_and_holds_its_margin(self):
		old_landed = landed_in_currency(self.old, "CAD", "USD", "CAD")
		new_landed = landed_in_currency(self.new, "CAD", "USD", "CAD")
		line = build_price_line(
			price_list="RET - Camo", list_currency="CAD",
			old_price=113.99, old_landed=old_landed, new_landed=new_landed,
			markup=CONDOR_CAMO, rounding="0.99", min_margin_pct=40,
		)
		self.assertEqual(line["action"], "Update")
		self.assertGreater(line["new_price"], 113.99)
		self.assertTrue(str(line["new_price"]).endswith(".99"))
		self.assertFalse(line["below_floor"])

	def test_usd_banner_never_round_trips_through_cad(self):
		# RET - CamoUSA is USD against a USD supplier: duty applies, FX does not
		new_landed = landed_in_currency(self.new, "USD", "USD", "CAD")
		self.assertAlmostEqual(new_landed, 27.32, places=2)
		line = build_price_line(
			price_list="RET - CamoUSA", list_currency="USD",
			old_price=44.99, old_landed=landed_in_currency(self.old, "USD", "USD", "CAD"),
			new_landed=new_landed, markup=CONDOR_USA, rounding="0.99",
		)
		self.assertEqual(line["action"], "Update")
		self.assertGreater(line["new_price"], new_landed)

	def test_franchise_list_must_clear_landed_cost(self):
		new_landed = landed_in_currency(self.new, "USD", "USD", "CAD")
		line = build_price_line(
			price_list="RET - CamoFRN - USD", list_currency="USD",
			old_price=26.99, old_landed=landed_in_currency(self.old, "USD", "USD", "CAD"),
			new_landed=new_landed, markup=1.20, rounding="0.99", min_margin_pct=40,
		)
		# exempt from the 40% floor, but the suggestion still has to clear cost
		self.assertTrue(line["low_margin_exempt"])
		self.assertGreater(line["new_price"], new_landed)


class TestCondorCostDecrease(unittest.TestCase):
	"""With suggested prices off, retail holds when a cost falls."""

	def test_price_held_margin_improves(self):
		old = landed_cost(24.00, CONDOR_DUTY, PO_RATE)
		new = landed_cost(21.00, CONDOR_DUTY, PO_RATE)
		line = build_price_line(
			price_list="RET - Camo", list_currency="CAD",
			old_price=129.99,
			old_landed=old["company_ccy"], new_landed=new["company_ccy"],
			markup=CONDOR_CAMO, rounding="0.99", cost_went_down=True, use_suggested=False,
		)
		self.assertEqual(line["action"], "Hold")
		self.assertEqual(line["new_price"], 129.99)
		self.assertGreater(line["margin_delta_pct"], 0)
		# the suggestion is still calculated, so a buyer can take it knowingly
		self.assertIsNotNone(line["suggested_price"])


if __name__ == "__main__":
	unittest.main()
