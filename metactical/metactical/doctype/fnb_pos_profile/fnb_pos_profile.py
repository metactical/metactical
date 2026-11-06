import frappe
from frappe import _
from frappe.model.document import Document


class FnBPOSProfile(Document):
	def validate(self):
		company = frappe.db.get_value("POS Profile", self.pos_profile, "company")
		if self.tips_payable_account and frappe.db.get_value("Account", self.tips_payable_account, "company") != company:
			frappe.throw(_("{0} does not belong to company {1}").format(self.tips_payable_account, company))
		if self.menu and frappe.db.get_value("FnB Menu", self.menu, "disabled"):
			frappe.throw(_("Menu {0} is disabled").format(self.menu))
		defaults = [row for row in self.order_types if row.is_default]
		if len(defaults) > 1:
			frappe.throw(_("Only one order type can be the default"))
		if self.order_types and not defaults:
			self.order_types[0].is_default = 1
		labels = [row.label.strip() for row in self.order_types]
		if len(labels) != len(set(labels)):
			frappe.throw(_("Order type labels must be unique"))
		for field in ("tip_presets", "discount_presets"):
			parse_percent_list(self.get(field), field)

	def on_update(self):
		from metactical.custom_scripts.utils.fnb_sync import refresh_item_webhook_condition
		refresh_item_webhook_condition()


def parse_percent_list(value, field="value"):
	"""'10, 15,20' -> [10, 15, 20]; anything else is an error the user can fix."""
	out = []
	for part in (value or "").split(","):
		part = part.strip()
		if not part:
			continue
		try:
			n = float(part)
		except ValueError:
			frappe.throw(_("{0}: '{1}' is not a number").format(field, part))
		out.append(int(n) if n.is_integer() else n)
	return out
