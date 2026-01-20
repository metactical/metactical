import frappe
from frappe.contacts.doctype.address.address import Address
from frappe import _, throw
from frappe.model.naming import make_autoname
from frappe.utils import cstr
import re

class CustomAddress(Address):
	def autoname(self):
		if not self.address_title:
			if self.links:
				self.address_title = self.links[0].link_name

		if self.address_title:
			self.name = cstr(self.address_title).strip()
			if frappe.db.exists("Address", self.name):
				self.name = make_autoname(
					cstr(self.address_title).strip() + "-.#",
					ignore_validate=True,
				)
		else:
			throw(_("Address Title is mandatory."))
   
   
	def normalize_phone(self, phone):
		# Remove everything except digits
		return re.sub(r"\D", "", phone)

	def validate(self):
		super(CustomAddress, self).validate()
		
		if self.phone:
			self.neb_mobile_not_formatted = self.normalize_phone(self.phone)
			allowed = "1234567890-+()"
			if not all(digit in allowed for digit in self.phone):
				frappe.throw('Only numbers and characters +-() allowed in phone number field')