# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class SBTag(Document):
	def on_update(self):
		# When an SB Tag is disabled, unlink it from every item that references it.
		# Done in a background job so disabling a widely-used tag doesn't block the save.
		if self.disabled:
			count = frappe.db.count("Item SB Tag", {"sb_tag": self.name})
			if count:
				frappe.enqueue(
					remove_sb_tag_from_items,
					queue="long",
					enqueue_after_commit=True,
					sb_tag=self.name,
				)
				frappe.msgprint(
					frappe._("Removing this SB Tag from {0} item(s) in the background.").format(count),
					alert=True,
				)

	def after_rename(self, old_name, new_name, merge=False):
		merge_history = frappe.get_doc({
			'doctype': 'SB Tag Merge History',
			'old_sb_tag': old_name,
			'new_sb_tag': new_name,
			'action': 'Rename' if not merge else 'Merge'
		})
		merge_history.insert(ignore_permissions=True)
		frappe.db.commit()
		
	def on_trash(self):

		merge_history = frappe.get_doc({
			'doctype': 'SB Tag Merge History',
			'old_sb_tag': self.name,
			'new_sb_tag': "",
			'action': 'Delete'
		})
		merge_history.insert(ignore_permissions=True)
		frappe.db.commit()


def remove_sb_tag_from_items(sb_tag):
	# Unlink a (now disabled) SB Tag from every item that references it.
	frappe.db.delete("Item SB Tag", {"sb_tag": sb_tag})
	frappe.db.commit()
