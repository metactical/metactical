import frappe
from frappe import _
from frappe.model.document import Document


class FnBMenuItem(Document):
	def validate(self):
		if frappe.db.get_value("FnB Menu Category", self.category, "menu") != self.menu:
			frappe.throw(_("Category {0} does not belong to menu {1}").format(self.category, self.menu))
		if not self.sizes and not self.item:
			frappe.throw(_("Set an Item or at least one size"))
		if self.sizes and self.item:
			self.item = None
		seen = set()
		for row in self.sizes:
			if row.size in seen:
				frappe.throw(_("Size {0} is listed twice").format(row.size))
			seen.add(row.size)
		for row in self.modifier_groups:
			if frappe.db.get_value("FnB Modifier Group", row.modifier_group, "menu") != self.menu:
				frappe.throw(_("Modifier group {0} does not belong to menu {1}").format(row.modifier_group, self.menu))
		for row in self.choices:
			if frappe.db.get_value("FnB Menu Category", row.category, "menu") != self.menu:
				frappe.throw(_("Choice category {0} does not belong to menu {1}").format(row.category, self.menu))
