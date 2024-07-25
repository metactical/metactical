import frappe
from frappe.email.doctype.auto_email_report.auto_email_report import AutoEmailReport
from frappe.utils import (
	format_time,
	global_date_format,
	now,
	get_url_to_report,
	get_link_to_form
)

import datetime


class CustomAutoEmailReport(AutoEmailReport):
	def get_html_table(self, columns=None, data=None):
		if self.report == "End of Day Report - V4":
			date_time = global_date_format(now()) + " " + format_time(now())
			report_doctype = frappe.db.get_value("Report", self.report, "ref_doctype")

			formatted_date = datetime.datetime.strptime(self.filters.date, "%Y-%m-%d").strftime("%d-%B-%Y")

			return frappe.render_template(
				"frappe/templates/emails/auto_email_report.html",
				{
					"title": self.name + " (" + formatted_date + ")",
					"description": self.description,
					"date_time": date_time,
					"columns": columns,
					"data": data,
					"report_url": get_url_to_report(self.report, self.report_type, report_doctype),
					"report_name": self.report,
					"edit_report_settings": get_link_to_form("Auto Email Report", self.name),
				},
			)
		else:
			return super().get_html_table(columns, data)