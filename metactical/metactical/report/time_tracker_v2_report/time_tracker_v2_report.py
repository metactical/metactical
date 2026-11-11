"""Hours worked per employee and work day, with country and work zone.

Stored times are server time and stay in their own columns. With "show work zone" on, two more columns give the
same moments as they read on the clock in the employee's work zone (Canada by province, everyone else Pacific),
so an Excel export carries both.
"""

import frappe
import pytz
from frappe import _
from frappe.utils import get_datetime

from metactical.time_tracker import core, locations


def execute(filters=None):
	filters = frappe._dict(filters or {})
	zone_cols = bool(int(filters.get("show_work_zone") or 0))
	server_tz = core.server_tz_name()

	conditions, values = ["l.has_clocked_out = 1", "l.date between %(from_date)s and %(to_date)s"], {
		"from_date": filters.from_date, "to_date": filters.to_date,
	}
	if filters.get("employee"):
		conditions.append("e.name = %(employee)s")
		values["employee"] = filters.employee
	has_region = frappe.get_meta("Employee").has_field("ais_state")
	region_sql = "e.ais_state" if has_region else "null"

	rows = frappe.db.sql(
		f"""select e.name as employee, e.employee_name, e.branch, {region_sql} as region,
			l.date as work_date, l.from_time, l.to_time, l.total_hours, l.auto_closed
		from `tabClockin Log` l
		left join `tabEmployee` e on e.user_id = l.user
		where {' and '.join(conditions)}
		order by e.employee_name, l.date, l.from_time""",
		values,
		as_dict=True,
	)

	wanted = (filters.get("country") or "").upper()
	data = []
	for r in rows:
		country = locations.country_of(r.region) or ("OTHER" if r.region == locations.OTHER else "UNKNOWN")
		if wanted and country != wanted:
			continue
		tz = locations.work_time_zone(r.region, default=server_tz)
		row = {
			"country": country, "region": r.region or "", "work_zone": tz, "employee": r.employee,
			"employee_name": r.employee_name, "branch": r.branch, "work_date": r.work_date,
			"from_time": r.from_time, "to_time": r.to_time, "hours": r.total_hours, "auto_closed": r.auto_closed,
		}
		if zone_cols:
			row["from_local"] = _in_zone(r.from_time, server_tz, tz)
			row["to_local"] = _in_zone(r.to_time, server_tz, tz)
		data.append(row)

	columns = [
		{"label": _("Country"), "fieldname": "country", "fieldtype": "Data", "width": 80},
		{"label": _("State/Province"), "fieldname": "region", "fieldtype": "Data", "width": 100},
		{"label": _("Work Zone"), "fieldname": "work_zone", "fieldtype": "Data", "width": 150},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
		{"label": _("Work Day"), "fieldname": "work_date", "fieldtype": "Date", "width": 100},
		{"label": _("Clock In (server {0})").format(server_tz), "fieldname": "from_time", "fieldtype": "Datetime", "width": 170},
		{"label": _("Clock Out (server {0})").format(server_tz), "fieldname": "to_time", "fieldtype": "Datetime", "width": 170},
	]
	if zone_cols:
		columns += [
			{"label": _("Clock In (work zone)"), "fieldname": "from_local", "fieldtype": "Data", "width": 190},
			{"label": _("Clock Out (work zone)"), "fieldname": "to_local", "fieldtype": "Data", "width": 190},
		]
	columns += [
		{"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Auto Closed"), "fieldname": "auto_closed", "fieldtype": "Check", "width": 90},
	]
	return columns, data


def _in_zone(value, server_tz, tz):
	"""A server-time moment as it reads in `tz`, with the zone abbreviation (e.g. 2026-10-05 05:02 PDT)."""
	if not value:
		return ""
	aware = pytz.timezone(server_tz).localize(get_datetime(value), is_dst=False).astimezone(pytz.timezone(tz))
	return aware.strftime("%Y-%m-%d %H:%M %Z")
