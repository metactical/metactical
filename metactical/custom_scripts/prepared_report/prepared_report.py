import frappe
from frappe.core.doctype.prepared_report.prepared_report import PreparedReport, generate_report
from frappe.utils.background_jobs import enqueue 

class CustomPreparedReport(PreparedReport):
    # Metactical Customization: Changed the timeout value from 1500 to 6000
    def after_insert(self):
        enqueue(
			generate_report,
			queue="long",
			prepared_report=self.name,
			timeout=6000,
			enqueue_after_commit=True,
		)