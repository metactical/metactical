import frappe

def validate(self, method):
	if len(self.phone_nos) > 0:
		for row in self.phone_nos:
			allowed = "1234567890-+()"
			if not all(digit in allowed for digit in row.phone):
				frappe.throw('Only numbers and characters +-() allowed in phone number field')
