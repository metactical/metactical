"""An in-memory stand-in for the parts of frappe / erpnext the Item Merge package calls.

Lets the flow tests run the real family / merge / jobs / websites code without a bench. It models
only what those modules touch, including a simplified CustomItem rename hook (history row, stock
moved, supplier rows appended, website specs replaced), so the tests exercise the same sequence a
merge goes through on a site. Never installed when the real frappe is importable.
"""
import copy
import datetime
import json
import re
import sys
import types

CHILD_TABLES = {
	"Item": {"attributes": "Item Variant Attribute", "supplier_items": "Item Supplier", "barcodes": "Item Barcode",
			 "neb_website_specifications": "MT Item Website Specification",
			 "custom_neb_website_deduct_qty": "Website Deduct Qty", "item_detail": "Item Detail"},
	"Item Merge Job": {"pairs": "Item Merge Job Pair", "leftovers": "Item Merge Job Leftover", "changes": "Item Merge Job Change"},
	"Item Attribute": {"item_attribute_values": "Item Attribute Value"},
	"Pricing Rule": {"items": "Pricing Rule Item Code"},
}
CHILD_PARENT = {child: (parent, field) for parent, tables in CHILD_TABLES.items() for field, child in tables.items()}


class _dict(dict):
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			return None

	def __setattr__(self, key, value):
		self[key] = value

	def update(self, *args, **kwargs):
		super().update(*args, **kwargs)
		return self


class ValidationError(Exception):
	pass


class LinkExistsError(ValidationError):
	pass


class Doc(_dict):
	"""A document: fields plus child tables (lists of Doc)."""

	def as_dict(self):
		return _dict({k: ([_dict(c) for c in v] if isinstance(v, list) else v) for k, v in self.items()})

	def set(self, field, value):
		if field in CHILD_TABLES.get(self["doctype"], {}):
			self[field] = []
			for row in value or []:
				self.append(field, row)
		else:
			self[field] = value

	def append(self, field, row):
		child = Doc({**dict(row), "doctype": CHILD_TABLES[self["doctype"]][field], "parentfield": field,
					 "parenttype": self["doctype"]})
		child.setdefault("name", None)
		self.setdefault(field, []).append(child)
		return child

	def get(self, key, default=None):
		return dict.get(self, key, default)

	def _assign(self):
		for field in CHILD_TABLES.get(self["doctype"], {}):
			for i, row in enumerate(self.get(field) or [], 1):
				row["doctype"] = CHILD_TABLES[self["doctype"]][field]
				row["parent"], row["parentfield"], row["parenttype"], row["idx"] = self["name"], field, self["doctype"], i
				if not row.get("name"):
					row["name"] = FRAPPE.new_id()

	def insert(self, ignore_permissions=False):
		dt = self["doctype"]
		if not self.get("name"):
			if dt == "Item":
				self["name"] = self["item_code"]
			elif dt == "Item Merge Job":
				self["name"] = f"IMJ-{FRAPPE.counter('job'):04d}"
			else:
				self["name"] = FRAPPE.new_id()
		if self["name"] in FRAPPE.db_rows(dt):
			raise ValidationError(f"{dt} {self['name']} already exists")
		self.setdefault("owner", FRAPPE.session.user)
		self.setdefault("creation", FRAPPE.now())
		for field, meta in FRAPPE.defaults.get(dt, {}).items():
			self.setdefault(field, meta)
		self._assign()
		FRAPPE.hooks_validate(self)
		FRAPPE.db_rows(dt)[self["name"]] = copy.deepcopy(self)
		return self

	def save(self, ignore_permissions=False):
		self._assign()
		FRAPPE.hooks_validate(self)
		FRAPPE.saves.append((self["doctype"], self["name"]))
		FRAPPE.db_rows(self["doctype"])[self["name"]] = copy.deepcopy(self)
		return self

	def reload(self):
		fresh = FRAPPE.get_doc(self["doctype"], self["name"])
		self.clear()
		self.update(fresh)

	def add_comment(self, comment_type, text):
		FRAPPE.comments.append((self["doctype"], self["name"], text))

	def get_password(self, field, raise_exception=True):
		return self.get(field)


class FakeFrappe(types.ModuleType):
	_fake = True
	ValidationError = ValidationError
	LinkExistsError = LinkExistsError
	_dict = _dict

	def __init__(self):
		super().__init__("frappe")
		self.reset()

	# ---------- state ----------
	def reset(self):
		self.DB = {}
		self._counters = {}
		self.session = _dict(user="merge@example.com")
		self.comments, self.enqueued, self.published, self.saves, self.errors = [], [], [], [], []
		self.defaults = {"Item Merge Job": {"log": "", "steps": "[]"}}
		self.fail_save = {}  # (doctype, name) -> message, raised by save/insert
		self.clock = datetime.datetime(2026, 9, 15, 9, 0, 0)

	def counter(self, key):
		self._counters[key] = self._counters.get(key, 0) + 1
		return self._counters[key]

	def new_id(self):
		return f"row{self.counter('row')}"

	def now(self):
		self.clock += datetime.timedelta(seconds=1)
		return self.clock

	def db_rows(self, doctype):
		return self.DB.setdefault(doctype, {})

	def hooks_validate(self, doc):
		msg = self.fail_save.get((doc["doctype"], doc["name"]))
		if msg:
			raise ValidationError(msg)

	# ---------- documents ----------
	def get_doc(self, doctype, name=None):
		if isinstance(doctype, dict):
			doc = Doc({k: v for k, v in doctype.items() if k not in CHILD_TABLES.get(doctype["doctype"], {})})
			for field in CHILD_TABLES.get(doctype["doctype"], {}):
				doc.set(field, doctype.get(field) or [])
			return doc
		row = self.db_rows(doctype).get(name)
		if row is None:
			raise ValidationError(f"{doctype} {name} not found")
		return copy.deepcopy(row)

	def new_doc(self, doctype):
		return self.get_doc({"doctype": doctype})

	def _records(self, doctype):
		if doctype in CHILD_PARENT:
			parent, field = CHILD_PARENT[doctype]
			return [_dict(r) for p in self.db_rows(parent).values() for r in p.get(field) or []]
		return [_dict({k: v for k, v in r.items() if not isinstance(v, list)}) for r in self.db_rows(doctype).values()]

	@staticmethod
	def _match(row, filters):
		if isinstance(filters, str):
			return row.get("name") == filters
		items = filters.items() if isinstance(filters, dict) else [(f[-3], f[-2:]) for f in filters]
		for field, cond in items:
			op, val = (cond if isinstance(cond, (list, tuple)) else ("=", cond))
			have = row.get(field)
			if op == "=" and not (have == val or (val in (0, None, "") and not have)):
				return False
			if op == "!=" and have == val:
				return False
			if op == "in" and have not in val:
				return False
			if op == "not in" and have in val:
				return False
			if op == "like" and not re.fullmatch(re.escape(val).replace("%", ".*"), str(have or ""), re.I):
				return False
			if op == "is" and (val == "set") != bool(have):
				return False
		return True

	def get_all(self, doctype, filters=None, fields=None, order_by=None, group_by=None, pluck=None,
				limit_page_length=None, limit=None, distinct=False, **kw):
		rows = [r for r in self._records(doctype) if self._match(r, filters or {})]
		if order_by:
			field, _, direction = order_by.partition(" ")
			rows.sort(key=lambda r: (r.get(field) is None, r.get(field) or ""), reverse=direction.strip().lower() == "desc")
		if pluck:
			out = [r.get(pluck) for r in rows]
			if distinct:
				out = list(dict.fromkeys(out))
			return out[:limit_page_length] if limit_page_length else out
		fields = fields or ["name"]
		if group_by:
			groups = {}
			for r in rows:
				groups.setdefault(tuple(r.get(g.strip()) for g in group_by.split(",")), []).append(r)
			out = [self._project(members, fields) for members in groups.values()]
		else:
			out = [self._project([r], fields, single=True) for r in rows]
		return out[:limit_page_length] if limit_page_length else out

	@staticmethod
	def _project(members, fields, single=False):
		out = _dict()
		for f in fields:
			if f == "*":
				out.update(members[0])
				continue
			expr, _, alias = f.partition(" as ")
			m = re.fullmatch(r"(count|sum)\((\w+)\)", expr.strip())
			if m and not single:
				out[alias] = len(members) if m.group(1) == "count" else sum(x.get(m.group(2)) or 0 for x in members)
			elif m:
				out[alias] = 1 if m.group(1) == "count" else members[0].get(m.group(2)) or 0
			else:
				out[(alias or expr).strip()] = members[0].get(expr.strip())
		return out

	get_list = get_all

	# ---------- rename / delete, with a simplified CustomItem hook ----------
	def rename_doc(self, doctype, old, new, merge=False, **kw):
		assert doctype == "Item"
		items = self.db_rows("Item")
		if old not in items:
			raise ValidationError(f"Item {old} not found")
		if merge and new not in items:
			raise ValidationError(f"Item {new} does not exist to merge into")
		if not merge and new in items:
			raise ValidationError(f"Item {new} already exists")
		od = items[old]
		if merge:
			nd = items[new]
			for f in ("stock_uom", "is_stock_item", "has_batch_no", "has_serial_no"):
				if (od.get(f) or 0) != (nd.get(f) or 0):
					raise ValidationError(f"{f} differs between {old} and {new}")
			have = {(s.get("supplier"), s.get("supplier_part_no")) for s in nd.get("supplier_items") or []}
			for s in od.get("supplier_items") or []:
				if (s.get("supplier"), s.get("supplier_part_no")) not in have:
					Doc(nd).append("supplier_items", {"supplier": s.get("supplier"), "supplier_part_no": s.get("supplier_part_no")})
			nd["neb_website_specifications"] = copy.deepcopy(od.get("neb_website_specifications") or [])
			nd["ifw_retailskusuffix"] = od.get("ifw_retailskusuffix")  # Item Merge Settings overwrite
			Doc(nd)._assign()
			del items[old]
		else:
			doc = items.pop(old)
			doc["name"] = doc["item_code"] = new
			Doc(doc)._assign()
			items[new] = doc
		for it in items.values():
			if it.get("variant_of") == old:
				it["variant_of"] = new
		for dt in ("Bin", "Stock Ledger Entry", "Item Price", "Repost Item Valuation"):
			for r in self.db_rows(dt).values():
				if r.get("item_code") == old:
					r["item_code"] = new
		self.get_doc({"doctype": "Item Merge History", "old_item_code": old, "new_item_code": new,
					  "old_item": json.dumps({k: v for k, v in od.items() if not isinstance(v, list)}, default=str)}).insert()
		return new

	def delete_doc(self, doctype, name, **kw):
		if doctype == "Item":
			for rule in self.db_rows("Pricing Rule").values():
				if any(r.get("item_code") == name for r in rule.get("items") or []):
					raise LinkExistsError(f'Cannot delete or cancel because Item <a href="/app/item/{name}">{name}</a> '
										  f'is linked with Pricing Rule <a href="/app/pricing-rule/{rule["name"]}">{rule["name"]}</a>')
		self.db_rows(doctype).pop(name, None)

	# ---------- misc api ----------
	def enqueue(self, method, queue="default", timeout=None, event=None, is_async=True, job_name=None, now=False,
				enqueue_after_commit=False, *, on_success=None, on_failure=None, at_front=False, job_id=None,
				deduplicate=False, **kwargs):
		"""Same signature as frappe.enqueue: only **kwargs reach the job function."""
		self.enqueued.append((method, kwargs))

	def publish_realtime(self, event, message=None, user=None, **kw):
		self.published.append((event, message, user))

	def log_error(self, title=None, message=None):
		self.errors.append((title, message))

	def get_traceback(self):
		import traceback
		return traceback.format_exc()

	def throw(self, msg, exc=ValidationError, title=None):
		raise exc(msg)

	def only_for(self, roles):
		return None

	def parse_json(self, value):
		return json.loads(value) if isinstance(value, str) else value

	def whitelist(self, *a, **k):
		return lambda fn: fn

	def cache(self):
		return None


class FakeDB:
	def __init__(self, f):
		self.f = f

	def exists(self, doctype, name_or_filters=None):
		if isinstance(name_or_filters, str) or name_or_filters is None:
			return name_or_filters if name_or_filters in self.f.db_rows(doctype) else None
		rows = self.f.get_all(doctype, filters=name_or_filters, pluck="name")
		return rows[0] if rows else None

	def get_value(self, doctype, name_or_filters, fieldname="name", as_dict=False):
		rows = [r for r in self.f._records(doctype) if self.f._match(r, name_or_filters)]
		if not rows:
			return None
		r = rows[0]
		if isinstance(fieldname, (list, tuple)):
			return _dict({k: r.get(k) for k in fieldname}) if as_dict else tuple(r.get(k) for k in fieldname)
		return r.get(fieldname)

	def set_value(self, doctype, name, field, value=None, update_modified=True):
		values = field if isinstance(field, dict) else {field: value}
		if doctype in CHILD_PARENT:
			parent, table = CHILD_PARENT[doctype]
			for p in self.f.db_rows(parent).values():
				for row in p.get(table) or []:
					if row.get("name") == name:
						row.update(copy.deepcopy(values))
			return
		self.f.db_rows(doctype)[name].update(copy.deepcopy(values))

	def count(self, doctype, filters=None):
		return len(self.f.get_all(doctype, filters=filters or {}, pluck="name"))

	def commit(self):
		pass

	def rollback(self, save_point=None):
		pass

	def savepoint(self, name):
		pass

	def delete(self, doctype, filters=None):
		for name in self.f.get_all(doctype, filters=filters or {}, pluck="name"):
			self.f.db_rows(doctype).pop(name, None)


def install():
	"""Put fake frappe / erpnext modules in sys.modules. Returns the fake frappe."""
	global FRAPPE
	FRAPPE = FakeFrappe()
	FRAPPE.db = FakeDB(FRAPPE)

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = FRAPPE.now
	utils.cint = lambda v: int(float(v or 0))
	utils.strip_html = lambda s: re.sub(r"<[^>]+>", "", s or "")
	utils.escape_html = lambda s: s
	utils.time_diff_in_seconds = lambda a, b: (a - b).total_seconds()
	background_jobs = types.ModuleType("frappe.utils.background_jobs")
	background_jobs.is_job_enqueued = lambda job_id: FRAPPE.alive_jobs is None or job_id in FRAPPE.alive_jobs
	FRAPPE.alive_jobs = None
	utils.background_jobs = background_jobs
	FRAPPE.utils = utils
	FRAPPE._ = lambda s: s

	def create_variant(item, args):
		template = FRAPPE.get_doc("Item", item)
		args = json.loads(args) if isinstance(args, str) else args
		variant = FRAPPE.new_doc("Item")
		variant.update(variant_of=item, item_group=template.item_group, stock_uom=template.stock_uom,
					   is_stock_item=template.is_stock_item, has_variants=0,
					   supplier_items=[], neb_website_specifications=[], custom_neb_website_deduct_qty=[])
		for s in template.get("supplier_items") or []:  # variants copy the template's supplier rows
			variant.append("supplier_items", {"supplier": s.supplier, "supplier_part_no": s.supplier_part_no})
		variant.set("attributes", [{"attribute": a.attribute, "attribute_value": args.get(a.attribute)}
								   for a in template.get("attributes") or []])
		return variant

	item_variant = types.ModuleType("erpnext.controllers.item_variant")
	item_variant.create_variant = create_variant
	erpnext = types.ModuleType("erpnext")
	controllers = types.ModuleType("erpnext.controllers")
	erpnext.controllers, controllers.item_variant = controllers, item_variant

	s3 = types.ModuleType("metactical.custom_scripts.utils.s3_image_api")
	s3.load_data_from_sb = lambda item_code: FRAPPE.loaded_from_sb.append(item_code) or [{"message": "<span>loaded</span>"}]
	FRAPPE.loaded_from_sb = []

	sys.modules.update({"frappe": FRAPPE, "frappe.utils": utils, "frappe.utils.background_jobs": background_jobs,
						"erpnext": erpnext, "erpnext.controllers": controllers, "erpnext.controllers.item_variant": item_variant,
						"metactical.custom_scripts.utils.s3_image_api": s3})
	return FRAPPE


FRAPPE = None
