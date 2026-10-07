import frappe


def execute():
	"""Large revisions now run in the background, so the item cap can rise."""
	s = frappe.get_single("ICL Pricing Settings")
	changed = False
	if (s.max_items or 0) <= 1000:
		s.max_items = 5000
		changed = True
	for field, value in (("background_threshold", 300), ("batch_size", 250), ("batch_pause_ms", 250)):
		if not s.get(field):
			s.set(field, value)
			changed = True
	if changed:
		s.save(ignore_permissions=True)
