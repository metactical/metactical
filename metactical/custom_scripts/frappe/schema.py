from frappe.utils import flt

# Backport of frappe/frappe#33142 (develop/v16). Remove after upgrading to v16.
# Without it, every updatedb() re-applies "default 0" to every decimal column.
def default_changed_for_decimal(self, current_def):
	cur_default = current_def["default"]
	if cur_default == "NULL":
		cur_default = None
	try:
		if cur_default in ("", None) and self.default in ("", None):
			return False
		elif flt(cur_default) == 0.0 and flt(self.default) == 0.0:
			return False
		elif cur_default in ("", None):
			try:
				float(self.default)
				return True
			except ValueError:
				return False
		elif self.default in ("", None):
			return True
		else:
			return float(cur_default) != float(self.default)
	except TypeError:
		return True
