# Copyright (c) 2026, Techlift Technologies and contributors
# For license information, please see license.txt

"""Update Item profiles (weights, sizes, country, supplier part numbers...) from a supplier's file,
using that supplier's Supplier Import Profile.

Each file row is matched to one Item by the profile's primary match (barcode or supplier part
number), and if that finds nothing, by its fallback match. An item found by the fallback also gets
the primary value added, e.g. the file's barcode, so the next import matches it directly.

Values are written straight to the database. Item.save() is deliberately avoided: its on_update
pushes to websites, inventory output and the S3 image queue, which is far too much to set off for
thousands of items at once just to correct weights or a country.

Every row that is not fully imported comes back as a result saying why and what was done instead.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

BATCH_SIZE = 500

NOT_IMPORTED = "Not Imported"
WITH_ISSUES = "Imported With Issues"

BARCODE = "Barcode"
PART_NO = "Supplier Part Number"

LB_TO_KG = 0.45359237
INCH_TO_CM = 2.54

# A converted weight is only right alongside its unit
UNIT_FIELDS = {("lb to kg", "weight_per_unit"): ("weight_uom", "Kg")}


def get_profile(supplier):
	if not frappe.db.exists("Supplier Import Profile", supplier):
		frappe.throw(_("There is no Supplier Import Profile for {0}. Create one before importing.").format(
			frappe.bold(supplier)))
	profile = frappe.get_doc("Supplier Import Profile", supplier)
	if not profile.enabled:
		frappe.throw(_("The Supplier Import Profile for {0} is disabled.").format(frappe.bold(supplier)))
	return profile


def get_header_map(data, profile):
	"""Map header names to column indexes, making sure every column the profile needs is there."""
	if not data:
		frappe.throw(_("The Excel File is empty."))

	columns = {}
	for idx, header in enumerate(data[0]):
		header = str(header).strip() if header is not None else ""
		if header and header not in columns:
			columns[header] = idx

	missing = [col for col in profile.required_columns() if col not in columns]
	if missing:
		frappe.throw(_("The file is missing column(s) required by the {0} profile: {1}").format(
			profile.supplier, ", ".join(missing)))
	return columns


def clean_text(value):
	"""Cell value as text: Excel hands numbers back as floats, so 10002.0 becomes 10002."""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	return str(value).strip()


def normalize(match_on, value):
	if match_on == BARCODE:
		# UPC-A, EAN-13 and numeric cells differ only by leading zeros
		return clean_text(value).lstrip("0")
	# Part numbers are compared the way the database does, ignoring case
	return clean_text(value).upper()


class SupplierImporter:
	def __init__(self, profile, columns, dry_run=False):
		self.profile = profile
		self.supplier = profile.supplier
		self.columns = columns
		self.dry_run = dry_run

		# (match_on, file column), primary first
		self.matches = [(profile.primary_match_on, profile.primary_match_column)]
		if profile.fallback_match_on:
			self.matches.append((profile.fallback_match_on, profile.fallback_match_column))
		match_columns = dict(self.matches)
		self.barcode_column = match_columns.get(BARCODE)

		self.item_maps = [m for m in profile.mappings if m.target_doctype == "Item"]
		self.supplier_maps = [m for m in profile.mappings
							  if m.target_doctype == "Item Supplier" and m.target_field != "supplier_part_no"]
		part_no_map = next((m for m in profile.mappings
							if m.target_doctype == "Item Supplier" and m.target_field == "supplier_part_no"), None)
		self.part_no_column = match_columns.get(PART_NO) or (part_no_map.file_column if part_no_map else None)

		self.results = []
		self.samples = []
		self.counts = {"total": 0, "updated": 0, "unchanged": 0, "with_issues": 0, "not_imported": 0}
		self.seen_keys = {}
		self.seen_items = {}
		self.countries = {}
		self.index = {match_on: self.build_index(match_on) for match_on in (BARCODE, PART_NO)}

	# ---- matching ------------------------------------------------------------------------------

	def build_index(self, match_on):
		"""Normalized value -> set of Item names, for the whole file in one query."""
		if match_on == BARCODE:
			rows = frappe.db.sql("""select barcode as k, parent from `tabItem Barcode`
				where parenttype = 'Item'""", as_dict=True)
		else:
			rows = frappe.db.sql("""select supplier_part_no as k, parent from `tabItem Supplier`
				where parenttype = 'Item' and supplier = %s""", self.supplier, as_dict=True)

		index = {}
		for row in rows:
			key = normalize(match_on, row.k)
			if key:
				index.setdefault(key, set()).add(row.parent)
		return index

	def describe(self, match_on, value):
		if match_on == BARCODE:
			return _("barcode {0}").format(value)
		return _("{0} part no {1}").format(self.supplier, value)

	def match_row(self, row, row_no):
		"""Return (item_code, match_on) or record why the row cannot be imported."""
		values = [(match_on, clean_text(self.cell(row, column))) for match_on, column in self.matches]
		if not any(value for _m, value in values):
			blank = [c for _m, c in self.matches]
			message = _("{0} is blank in the file") if len(blank) == 1 else _("{0} are blank in the file")
			self.add_result(row_no, row, None, NOT_IMPORTED, message.format(_(" and ").join(blank)),
							_("Row not imported"))
			return None, None

		for match_on, value in values:
			key = (match_on, normalize(match_on, value))
			if key[1] and key in self.seen_keys:
				first = self.seen_keys[key]
				self.add_result(row_no, row, None, NOT_IMPORTED,
								_("Duplicate {0} in the file (first seen on row {1})").format(
									self.describe(match_on, value), first),
								_("Row not imported; row {0} was used").format(first))
				return None, None
		for match_on, value in values:
			if value:
				self.seen_keys[(match_on, normalize(match_on, value))] = row_no

		not_found = []
		for match_on, value in values:
			if not value:
				continue
			item_codes = self.index[match_on].get(normalize(match_on, value))
			if not item_codes:
				not_found.append(self.describe(match_on, value))
				continue
			if len(item_codes) > 1:
				self.add_result(row_no, row, None, NOT_IMPORTED,
								_("{0} is on more than one item: {1}").format(
									upper_first(self.describe(match_on, value)), ", ".join(sorted(item_codes))),
								_("Row not imported; remove the duplicate first"))
				return None, None

			item_code = next(iter(item_codes))
			if item_code in self.seen_items:
				self.add_result(row_no, row, item_code, NOT_IMPORTED,
								_("Item {0} was already updated from row {1}").format(item_code, self.seen_items[item_code]),
								_("Row not imported"))
				return None, None
			self.seen_items[item_code] = row_no
			return item_code, match_on

		self.add_result(row_no, row, None, NOT_IMPORTED,
						_("No item found with {0}").format(_(" or ").join(not_found)),
						_("Row not imported"))
		return None, None

	# ---- conversion ----------------------------------------------------------------------------

	def resolve_country(self, code):
		code = code.upper()
		if code not in self.countries:
			import pycountry

			name = None
			country = None
			if len(code) == 3:
				country = pycountry.countries.get(alpha_3=code)
			elif len(code) == 2:
				country = pycountry.countries.get(alpha_2=code)
			if country:
				name = frappe.db.get_value("Country", {"code": country.alpha_2.lower()}, "name")
			if not name:
				# Already a Country name, e.g. "Canada"
				name = frappe.db.get_value("Country", code.title(), "name")
			self.countries[code] = name
		return self.countries[code]

	def convert(self, mapping, raw):
		"""Return (value, problem). value is None when nothing should be written."""
		column = mapping.file_column
		text = clean_text(raw)
		if not text:
			return None, _("{0} is blank in the file").format(column)

		conversion = mapping.conversion
		if conversion in ("lb to kg", "inch to cm"):
			try:
				number = float(text)
			except ValueError:
				return None, _("{0} '{1}' is not a number").format(column, text)
			if number <= 0:
				return None, _("{0} is {1} in the file").format(column, text)
			if conversion == "lb to kg":
				return round(number * LB_TO_KG, 3), None
			return round(number * INCH_TO_CM, 2), None

		if conversion == "Country Code to Country":
			name = self.resolve_country(text)
			if not name:
				return None, _("{0} '{1}' does not match any Country in the ERP").format(column, text)
			return name, None

		fieldtype = frappe.get_meta(mapping.target_doctype).get_field(mapping.target_field).fieldtype
		if fieldtype in ("Float", "Currency", "Percent"):
			try:
				return float(text), None
			except ValueError:
				return None, _("{0} '{1}' is not a number").format(column, text)
		if fieldtype in ("Int", "Check"):
			return cint(text), None
		return text, None

	@staticmethod
	def same(old, new):
		if isinstance(new, float):
			return abs(flt(old) - new) < 0.0005
		return (old or "") == new

	# ---- per batch lookups ---------------------------------------------------------------------

	def load_items(self, item_codes):
		fields = {"name"}
		for m in self.item_maps:
			fields.add(m.target_field)
			if (m.conversion, m.target_field) in UNIT_FIELDS:
				fields.add(UNIT_FIELDS[(m.conversion, m.target_field)][0])
		items = {d.name: d for d in frappe.get_all(
			"Item", filters={"name": ["in", item_codes]}, fields=list(fields))}

		supplier_fields = {"name", "parent", "idx", "supplier_part_no"} | {m.target_field for m in self.supplier_maps}
		supplier_rows = {}
		for d in frappe.get_all("Item Supplier",
				filters={"parent": ["in", item_codes], "parenttype": "Item", "supplier": self.supplier},
				fields=list(supplier_fields), order_by="idx asc"):
			supplier_rows.setdefault(d.parent, []).append(d)

		max_idx = {}
		for doctype in ("Item Supplier", "Item Barcode"):
			max_idx[doctype] = dict(frappe.db.sql(f"""select parent, max(idx) from `tab{doctype}`
				where parenttype = 'Item' and parent in %s group by parent""", (tuple(item_codes),)))

		defaults = {}
		for d in frappe.get_all("Item Default",
				filters={"parent": ["in", item_codes], "parenttype": "Item"},
				fields=["parent", "default_supplier"]):
			if d.default_supplier:
				defaults.setdefault(d.parent, set()).add(d.default_supplier)

		return items, supplier_rows, max_idx, defaults

	# ---- run -----------------------------------------------------------------------------------

	def run(self, rows, first_row_no=2, sample_size=0):
		self.sample_size = sample_size
		for start in range(0, len(rows), BATCH_SIZE):
			self.run_batch(rows[start:start + BATCH_SIZE], first_row_no + start)
			if not self.dry_run:
				frappe.db.commit()
		self.results.sort(key=lambda r: r["row_no"])
		return self

	def cell(self, row, column):
		idx = self.columns[column]
		return row[idx] if idx < len(row) else None

	def run_batch(self, rows, first_row_no):
		matched = []
		for offset, row in enumerate(rows):
			row_no = first_row_no + offset
			if not any(clean_text(v) for v in row):
				continue
			self.counts["total"] += 1
			item_code, matched_by = self.match_row(row, row_no)
			if item_code:
				matched.append((row_no, row, item_code, matched_by))

		if not matched:
			return

		items, supplier_rows, max_idx, defaults = self.load_items(list({m[2] for m in matched}))
		for row_no, row, item_code, matched_by in matched:
			if not self.dry_run:
				frappe.db.savepoint("supplier_import_row")
			try:
				self.import_row(row_no, row, items[item_code], matched_by, supplier_rows.setdefault(item_code, []),
								max_idx, defaults.get(item_code, set()))
			except Exception as e:
				if not self.dry_run:
					frappe.db.rollback(save_point="supplier_import_row")
				frappe.log_error(title=f"Item profile import row {row_no}", message=frappe.get_traceback())
				self.add_result(row_no, row, item_code, NOT_IMPORTED,
								_("Unexpected error: {0}").format(str(e)[:200]),
								_("Row not imported; nothing was changed on the item"), matched_by)

	def import_row(self, row_no, row, item, matched_by, supplier_rows, max_idx, default_suppliers):
		problems, done, changes = [], [], []

		# Barcode: add the file's barcode when the item was found some other way and doesn't have it
		if self.barcode_column:
			problem, note = self.add_barcode(row, item, max_idx)
			if problem:
				problems.append(problem)
			if note:
				done.append(note)

		# Item fields
		item_updates = {}
		for m in self.item_maps:
			value, problem = self.convert(m, self.cell(row, m.file_column))
			if problem:
				problems.append(problem)
				continue
			old = item.get(m.target_field)
			if m.only_if_blank and old:
				continue
			if not self.same(old, value):
				item_updates[m.target_field] = value
				changes.append((m.target_field_label or m.target_field, old, value))
			unit = UNIT_FIELDS.get((m.conversion, m.target_field))
			if unit and item.get(unit[0]) != unit[1]:
				item_updates[unit[0]] = unit[1]
				changes.append((unit[0], item.get(unit[0]), unit[1]))

		# Item Supplier fields, on this supplier's row for the item
		supplier_updates, target_row, new_row = {}, None, None
		if self.part_no_column or self.supplier_maps:
			target_row, new_row, problem, note = self.find_supplier_row(row, item, supplier_rows, default_suppliers, max_idx)
			if problem:
				problems.append(problem)
			if note:
				done.append(note)
			for m in self.supplier_maps:
				value, problem = self.convert(m, self.cell(row, m.file_column))
				if problem:
					problems.append(problem)
					continue
				if new_row is not None:
					new_row[m.target_field] = value
				elif target_row:
					old = target_row.get(m.target_field)
					if not (m.only_if_blank and old) and not self.same(old, value):
						supplier_updates[m.target_field] = value
						changes.append((f"{self.supplier} {m.target_field_label or m.target_field}", old, value))

		if item_updates:
			done.append(_("Updated {0}").format(", ".join(
				f"{field}: {fmt(old)} → {fmt(new)}" for field, old, new in changes
				if not field.startswith(f"{self.supplier} "))))
		if supplier_updates:
			done.append(_("Updated {0} supplier row: {1}").format(self.supplier, ", ".join(
				f"{k} → {fmt(v)}" for k, v in supplier_updates.items())))

		if not self.dry_run:
			if item_updates:
				frappe.db.set_value("Item", item.name, item_updates)
			if supplier_updates:
				frappe.db.set_value("Item Supplier", target_row.name, supplier_updates)
			if new_row is not None:
				self.insert_child(item.name, "Item Supplier", "supplier_items", max_idx,
								  {"supplier": self.supplier, **new_row})

		if self.sample_size and len(self.samples) < self.sample_size and done:
			self.samples.append({
				"row_no": row_no,
				"item_code": item.name,
				"matched_by": matched_by,
				"match_value": clean_text(self.cell(row, self.matches[0][1])),
				"changes": [{"field": f, "old": fmt(o), "new": fmt(n)} for f, o, n in changes],
				"notes": done,
			})

		if problems:
			self.add_result(row_no, row, item.name, WITH_ISSUES, "; ".join(problems),
							"; ".join(done) or _("Nothing else needed changing"), matched_by)
		elif done:
			self.counts["updated"] += 1
		else:
			self.counts["unchanged"] += 1

	def insert_child(self, item_code, doctype, parentfield, max_idx, values):
		idx = cint(max_idx[doctype].get(item_code)) + 1
		max_idx[doctype][item_code] = idx
		frappe.get_doc({
			"doctype": doctype,
			"parent": item_code,
			"parenttype": "Item",
			"parentfield": parentfield,
			"idx": idx,
			**values,
		}).db_insert()
		frappe.db.set_value("Item", item_code, "modified", frappe.utils.now(), update_modified=False)

	def add_barcode(self, row, item, max_idx):
		"""Return (problem, note) after adding the file's barcode to the item if it lacks it."""
		barcode = clean_text(self.cell(row, self.barcode_column))
		key = normalize(BARCODE, barcode)
		if not key:
			return None, None
		owners = self.index[BARCODE].get(key, set())
		if item.name in owners:
			return None, None
		if owners:
			return _("Barcode {0} is already on item {1}, so it was not added").format(
				barcode, ", ".join(sorted(owners))), None

		if not self.dry_run:
			self.insert_child(item.name, "Item Barcode", "barcodes", max_idx, {"barcode": barcode})
		self.index[BARCODE][key] = {item.name}
		return None, _("Added barcode {0}").format(barcode)

	def find_supplier_row(self, row, item, supplier_rows, default_suppliers, max_idx):
		"""Return (existing row, new row dict, problem, note) for this supplier's row on the item.

		The part number decides which row: the one that already has it, else a row of this
		supplier with no part number yet, else a new row - but a new row is only added when the
		item's default supplier is this supplier, so we never attach a supplier to an item that
		buys elsewhere.
		"""
		if not self.part_no_column:
			if supplier_rows:
				return supplier_rows[0], None, None, None
			return None, None, _("Item has no {0} supplier row").format(self.supplier), None

		part_no = clean_text(self.cell(row, self.part_no_column))
		if not part_no:
			return None, None, _("{0} is blank in the file").format(self.part_no_column), None

		key = normalize(PART_NO, part_no)
		for d in supplier_rows:
			if normalize(PART_NO, d.supplier_part_no) == key:
				return d, None, None, None

		owners = self.index[PART_NO].get(key, set()) - {item.name}
		if owners:
			return None, None, _("{0} part no {1} is already on item {2}, so it was not added").format(
				self.supplier, part_no, ", ".join(sorted(owners))), None

		for d in supplier_rows:
			if not d.supplier_part_no:
				if not self.dry_run:
					frappe.db.set_value("Item Supplier", d.name, "supplier_part_no", part_no)
				d.supplier_part_no = part_no
				self.index[PART_NO][key] = {item.name}
				return d, None, None, _("Set {0} part no {1} on the existing {0} supplier row").format(
					self.supplier, part_no)

		if self.supplier not in default_suppliers:
			current = ", ".join(sorted(default_suppliers)) or _("not set")
			return None, None, _("{0} part no {1} is not on the item and the item's default supplier is {2}, not {0}").format(
				self.supplier, part_no, current), None

		others = [d.supplier_part_no for d in supplier_rows]
		supplier_rows.append(frappe._dict(name=None, supplier_part_no=part_no))
		self.index[PART_NO][key] = {item.name}
		note = _("Added {0} supplier row with part no {1}").format(self.supplier, part_no)
		if others:
			note += _(" (item already had {0} part no {1})").format(self.supplier, ", ".join(others))
		return None, {"supplier_part_no": part_no}, None, note

	def add_result(self, row_no, row, item_code, status, reason, action, matched_by=None):
		self.counts["not_imported" if status == NOT_IMPORTED else "with_issues"] += 1
		fallback = clean_text(self.cell(row, self.matches[1][1])) if len(self.matches) > 1 else None
		self.results.append({
			"row_no": row_no,
			"match_value": clean_text(self.cell(row, self.matches[0][1])),
			"fallback_value": fallback,
			"item_code": item_code,
			"matched_by": matched_by,
			"status": status,
			"reason": reason,
			"action_taken": action,
		})


def upper_first(text):
	return text[:1].upper() + text[1:]


def fmt(value):
	if value is None or value == "":
		return "(blank)"
	if isinstance(value, float):
		return f"{value:g}"
	return str(value)
