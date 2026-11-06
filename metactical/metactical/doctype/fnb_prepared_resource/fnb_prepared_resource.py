import frappe
from frappe import _
from frappe.model.document import Document


class FnBPreparedResource(Document):
	def validate(self):
		company = frappe.db.get_value("POS Profile", self.pos_profile, "company")
		if self.cost_account and frappe.db.get_value("Account", self.cost_account, "company") != company:
			frappe.throw(_("{0} does not belong to company {1}").format(self.cost_account, company))
		if not frappe.db.exists("Product Bundle", {"new_item_code": self.recipe_item, "disabled": 0}):
			frappe.throw(_("{0} has no enabled Product Bundle (recipe)").format(self.recipe_item))
		if frappe.db.get_value("Stock Entry Type", self.stock_entry_type, "purpose") != "Material Issue":
			frappe.throw(_("{0} is not a Material Issue stock entry type").format(self.stock_entry_type))
		if (self.portions_per_batch or 0) < 1:
			frappe.throw(_("Portions per batch must be at least 1"))
