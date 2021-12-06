import frappe

def validate(self, method):
	if self.phone:
		allowed = "1234567890-+()"
		if not all(digit in allowed for digit in self.phone):
			frappe.throw('Only numbers and characters +-() allowed in phone number field')
