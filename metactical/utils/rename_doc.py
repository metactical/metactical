# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
from types import NoneType
from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.utils.data import sbool
from frappe.utils.scheduler import is_scheduler_inactive
from frappe.model.rename_doc import validate_rename

if TYPE_CHECKING:
	from frappe.model.meta import Meta


@frappe.whitelist()
def update_document_title(
	*,
	doctype: str,
	docname: str,
	title: str | None = None,
	name: str | None = None,
	merge: bool = False,
	enqueue: bool = False,
	**kwargs,
) -> str:
	"""
	Update the name or title of a document. Returns `name` if document was renamed,
	`docname` if renaming operation was queued.

	:param doctype: DocType of the document
	:param docname: Name of the document
	:param title: New Title of the document
	:param name: New Name of the document
	:param merge: Merge the current Document with the existing one if exists
	:param enqueue: Enqueue the rename operation, title is updated in current process
	"""

	
	# to maintain backwards API compatibility
	updated_title = kwargs.get("new_title") or title
	updated_name = kwargs.get("new_name") or name
	print("renaming called")

	# TODO: omit this after runtime type checking (ref: https://github.com/frappe/frappe/pull/14927)
	for obj in [docname, updated_title, updated_name]:
		if not isinstance(obj, str | NoneType):
			frappe.throw(f"{obj=} must be of type str or None")

	# handle bad API usages
	merge = sbool(merge)
	enqueue = sbool(enqueue)

	doc = frappe.get_doc(doctype, docname)
	doc.check_permission(permtype="write")

	title_field = doc.meta.get_title_field()

	title_updated = updated_title and (title_field != "name") and (updated_title != doc.get(title_field))
	name_updated = updated_name and (updated_name != doc.name)

	queue = kwargs.get("queue") or "long"
 
	print("renaming called from the utility customization")

	if name_updated:
		if enqueue and not is_scheduler_inactive():
			current_name = doc.name

			# before_name hook may have DocType specific validations or transformations
			transformed_name = doc.run_method("before_rename", current_name, updated_name, merge)
			if isinstance(transformed_name, dict):
				transformed_name = transformed_name.get("new")
			transformed_name = transformed_name or updated_name

			# run rename validations before queueing
			# use savepoints to avoid partial renames / commits
			validate_rename(
				doctype=doctype,
				old=current_name,
				new=transformed_name,
				meta=doc.meta,
				merge=merge,
				save_point=True,
			)

			doc.queue_action("rename", name=transformed_name, merge=merge, timeout=36000)
		else:
			doc.rename(updated_name, merge=merge)

	if title_updated:
		try:
			doc.reload()
			setattr(doc, title_field, updated_title)
			doc.save()
			frappe.msgprint(_("Saved"), alert=True, indicator="green")
		except Exception as e:
			if frappe.db.is_duplicate_entry(e):
				frappe.throw(
					_("{0} {1} already exists").format(doctype, frappe.bold(docname)),
					title=_("Duplicate Name"),
					exc=frappe.DuplicateEntryError,
				)
			raise

	return doc.name

