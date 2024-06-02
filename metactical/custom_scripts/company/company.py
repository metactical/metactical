import frappe
from frappe import _
from erpnext.setup.doctype.company.company import Company

class CustomCompany(Company):
	def validate(self):
		# Metactical Customization: If user not Administrator, then raise exception
		if frappe.session.user != "Administrator":
			frappe.throw(_("Only the Administrator account can create or update Company records."))
		super(CustomCompany, self).validate()