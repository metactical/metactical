# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class SBTag(Document):
	def after_rename(self, old_name, new_name, merge=False):
		merge_history = frappe.get_doc({
			'doctype': 'SB Tag Merge History',
			'old_sb_tag': old_name,
			'new_sb_tag': new_name,
			'action': 'Rename' if not merge else 'Merge'
		})
		merge_history.insert(ignore_permissions=True)
		
	def on_trash(self):
		merge_history = frappe.get_doc({
			'doctype': 'SB Tag Merge History',
			'old_sb_tag': self.name,
			'new_sb_tag': "",
			'action': 'Delete'
		})
		merge_history.insert(ignore_permissions=True)
		frappe.db.commit()

