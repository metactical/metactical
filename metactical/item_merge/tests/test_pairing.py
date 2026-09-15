"""Offline tests for metactical.item_merge.pairing. No bench, no network.

Real fixtures are pre-merge snapshots of three families merged on dev in Aug 2026,
checked against the old->new pairs Item Merge History actually recorded.
Run from the app repo root:  python -m unittest discover -s metactical/item_merge/tests -t . -v
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
from metactical.item_merge.pairing import clean_code, plan_pairs, resolve, SIZE_ALIASES  # noqa: E402

FIX = HERE / "fixtures"


def load(fam):
	with open(FIX / f"{fam}.items.json", encoding="utf-8") as f:
		docs = json.load(f)
	with open(FIX / f"{fam}.merged.json", encoding="utf-8") as f:
		truth = json.load(f)
	template = next(d for d in docs if d.get("has_variants"))
	variants = [d for d in docs if d.get("variant_of")]
	return template, variants, truth


def item(name, item_name, variant_of="T", attrs=None):
	return {"name": name, "item_name": item_name, "variant_of": variant_of,
			"attributes": [{"attribute": k, "attribute_value": v} for k, v in (attrs or {}).items()]}


SIZE = "Size - Clothing - XS to 8XL"
COLOUR = "Colour - Clothing - PS"


class ColourOnlyFamily(unittest.TestCase):
	"""NPTA12303 on dev: one Colour attribute, and the colour is the last part of the name."""

	def test_colour_is_read_from_the_end_of_the_name(self):
		t = {"name": "NPTA12303-BK-tempt", "attributes": [{"attribute": "Variant Number"}, {"attribute": COLOUR}]}
		variants = [
			item("NPTA12303-BK", "6.5 Inch Kunai Throwing Knife Set w/Ninja Symbol - 3Pcs - Black", attrs={"Variant Number": "1"}),
			item("NPTA12303-RW", "6.5 Inch Kunai Throwing Knife Set w/Ninja Symbol - 3Pcs - Rainbow", attrs={"Variant Number": "2"}),
			item("NPTA12303-BK-tempt-001", "6.5 Inch Kunai Throwing Knife Set w/Ninja Symbol -3Pcs - Black", attrs={COLOUR: "Black"}),
			item("NPTA12303-BK-tempt-Rainbow", "6.5 Inch Kunai Throwing Knife Set w/Ninja Symbol -3Pcs - Rainbow", attrs={COLOUR: "Rainbow"}),
		]
		plan = plan_pairs(t, variants)
		self.assertEqual(sorted((p["old"], p["new"]) for p in plan["pairs"]),
						 [("NPTA12303-BK", "NPTA12303-BK-tempt-001"), ("NPTA12303-RW", "NPTA12303-BK-tempt-Rainbow")])
		self.assertEqual(plan["unmatched"], [])


class RealFamilies(unittest.TestCase):
	"""Pairing must reproduce exactly what was merged by hand, pair for pair."""

	def check(self, fam, expected_pairs):
		template, variants, truth = load(fam)
		plan = plan_pairs(template, variants)
		got = {p["old"]: clean_code(p["new"]) for p in plan["pairs"]}
		want = {o: clean_code(n) for o, n in truth.items()}
		self.assertEqual(got, want)
		self.assertEqual(len(plan["pairs"]), expected_pairs)
		for key in ("conflicts", "ambiguous", "unmatched"):
			self.assertEqual(plan[key], [], f"{fam}: unexpected {key}")

	def test_rvx4183_colour_and_size(self):
		self.check("rvx4183", 12)

	def test_uf2923_size_only_with_xxlarge_alias(self):
		self.check("uf2923", 6)

	def test_gs1233_size_only_with_xl_alias(self):
		self.check("gs1233", 4)


class Traps(unittest.TestCase):
	def template(self, *attrs):
		return {"name": "T", "attributes": [{"attribute": "Variant Number"}]
				+ [{"attribute": a} for a in attrs]}

	def test_never_pairs_by_numeric_suffix(self):
		# Old -0003 is Medium; new -0003 is Small. Suffix matching would cross them.
		news = [item("T-0003", "x", attrs={SIZE: "Small"}), item("T-0004", "x", attrs={SIZE: "Medium"})]
		olds = [item("T-OLD-0003", "Shirt - Medium")]
		plan = plan_pairs(self.template(SIZE), news + olds)
		self.assertEqual(plan["pairs"][0]["new"], "T-0004")

	def test_two_olds_on_one_new_is_refused(self):
		news = [item("T-S", "x", attrs={SIZE: "Small"})]
		olds = [item("A", "Shirt - Small"), item("B", "Shirt - S")]
		plan = plan_pairs(self.template(SIZE), news + olds)
		self.assertEqual(plan["pairs"], [])
		self.assertEqual(sorted(plan["conflicts"][0]["olds"]), ["A", "B"])

	def test_empty_unmatched_is_leftover_but_stocked_is_blocked(self):
		news = [item("T-S", "x", attrs={SIZE: "Small"})]
		olds = [item("GONE", "Shirt - 9XLarge"), item("STOCK", "Shirt - 7XLarge")]
		plan = plan_pairs(self.template(SIZE), news + olds, emptiness={"GONE": True})
		self.assertEqual([u["old"] for u in plan["leftovers"]], ["GONE"])
		self.assertEqual([u["old"] for u in plan["blocked"]], ["STOCK"])

	def test_camo_wording_resolves(self):
		news = [item("T-300-3", "x", attrs={COLOUR: "Camo - Black", SIZE: "Small"})]
		olds = [item("OLD", "Tank Top - Black Camo - Small")]
		plan = plan_pairs(self.template(COLOUR, SIZE), news + olds)
		self.assertEqual(plan["pairs"][0]["new"], "T-300-3")

	def test_colour_falls_back_to_template_suffix(self):
		news = [item("T-001-3", "x", attrs={COLOUR: "Black", SIZE: "Small"})]
		olds = [item("TBLK-0002", "Shirt - Small", variant_of="T1234BLK")]
		plan = plan_pairs(self.template(COLOUR, SIZE), news + olds)
		self.assertEqual(plan["pairs"][0]["new"], "T-001-3")

	def test_colour_mismatch_names_the_colour_not_a_parse_failure(self):
		# RVX4133 on dev: old Black variants, but the template's new variants are other colourways.
		news = [item("T-FRP-1", "x", attrs={COLOUR: "Frost Grey", SIZE: "Small"})]
		olds = [item("TBLK-0002", "Pants - Black - Small", variant_of="T4133BLK")]
		plan = plan_pairs(self.template(COLOUR, SIZE), news + olds)
		self.assertEqual(plan["pairs"], [])
		self.assertIn("'Black' not among new variants", plan["blocked"][0]["reason"])

	def test_style_name_containing_dashes(self):
		news = [item("T-S", "x", attrs={SIZE: "Small"})]
		olds = [item("OLD", "5.11 - Tactical - Shirt - Small")]
		self.assertEqual(plan_pairs(self.template(SIZE), news + olds)["pairs"][0]["new"], "T-S")

	def test_unknown_size_is_not_guessed(self):
		self.assertIsNone(resolve("Huge", {"Small", "Large"}, SIZE_ALIASES))

	def test_clean_code(self):
		self.assertEqual(clean_code("RVX4183---001-0002"), "RVX4183-001-0002")
		self.assertEqual(clean_code("GS1233-01--0003"), "GS1233-01-0003")
		self.assertEqual(clean_code("RVX4176-001-0004"), "RVX4176-001-0004")


if __name__ == "__main__":
	unittest.main()
