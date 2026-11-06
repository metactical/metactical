"""Per prepared resource and day: batches cooked, portions produced / consumed / counted, variance and
ingredient cost (FnB Batch + FnB Closing rows + sold items x consumer portions)."""
import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("POS Profile"), "fieldname": "pos_profile", "fieldtype": "Link", "options": "POS Profile", "width": 180},
		{"label": _("Resource"), "fieldname": "resource", "fieldtype": "Link", "options": "FnB Prepared Resource", "width": 220},
		{"label": _("Batches"), "fieldname": "batches", "fieldtype": "Int", "width": 80},
		{"label": _("Produced"), "fieldname": "produced", "fieldtype": "Int", "width": 90},
		{"label": _("Consumed"), "fieldname": "consumed", "fieldtype": "Int", "width": 90},
		{"label": _("Counted"), "fieldname": "counted", "fieldtype": "Int", "width": 90},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Int", "width": 90},
		{"label": _("Ingredient Cost"), "fieldname": "cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Cost / Portion Sold"), "fieldname": "cost_per_portion", "fieldtype": "Currency", "width": 130},
	]
	cond, args = "", {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.pos_profile:
		cond += " and b.pos_profile = %(pos_profile)s"
		args["pos_profile"] = filters.pos_profile
	if filters.resource:
		cond += " and b.resource = %(resource)s"
		args["resource"] = filters.resource
	rows = {}
	for b in frappe.db.sql(f"""
			select date(b.cooked_at) as date, b.pos_profile, b.resource,
				sum(b.qty) as batches, sum(b.portions) as produced, sum(b.cost) as cost
			from `tabFnB Batch` b
			where date(b.cooked_at) between %(from_date)s and %(to_date)s {cond}
			group by date(b.cooked_at), b.pos_profile, b.resource""", args, as_dict=True):
		rows[(str(b.date), b.pos_profile, b.resource)] = dict(b, consumed=0, counted=0, variance=0)
	cond2 = cond.replace("b.pos_profile", "c.pos_profile").replace("b.resource", "cr.resource")
	for c in frappe.db.sql(f"""
			select c.closing_date as date, c.pos_profile, cr.resource,
				sum(cr.portions_consumed) as consumed, sum(cr.portions_counted) as counted, sum(cr.variance) as variance
			from `tabFnB Closing Resource` cr
			join `tabFnB Closing` fc on fc.name = cr.parent
			join `tabEnd of Day Closing` c on c.name = fc.closing_entry
			where c.closing_date between %(from_date)s and %(to_date)s {cond2}
			group by c.closing_date, c.pos_profile, cr.resource""", args, as_dict=True):
		key = (str(c.date), c.pos_profile, c.resource)
		row = rows.setdefault(key, dict(date=c.date, pos_profile=c.pos_profile, resource=c.resource, batches=0, produced=0, cost=0))
		row.update(consumed=cint(c.consumed), counted=cint(c.counted), variance=cint(c.variance))
	data = []
	for key in sorted(rows):
		r = rows[key]
		r["cost_per_portion"] = round(flt(r["cost"]) / r["consumed"], 4) if r.get("consumed") else 0
		data.append(r)
	return columns, data
