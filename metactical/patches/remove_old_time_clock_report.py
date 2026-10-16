import frappe


def execute():
	"""The report was renamed 'Time Tracker V2 Report'; remove the record of the old name (the new one is synced from files)."""
	if frappe.db.exists("Report", "Time Clock Hours"):
		frappe.delete_doc("Report", "Time Clock Hours", force=True, ignore_permissions=True)
