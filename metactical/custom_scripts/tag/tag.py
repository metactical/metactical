import frappe
from frappe.desk.doctype.tag.tag import DocTags

@frappe.whitelist()
def add_tag(tag, dt, dn, color=None):
    # check if user has permission to add tags to this document
    if not frappe.has_permission("Tag Link", "create"):
        frappe.throw("Insufficient permission to add tags to this document")
    else:
        DocTags(dt).add(dn, tag)
        return tag

@frappe.whitelist()
def remove_tag(tag, dt, dn):
    # check if user has permission to remove tags from this document
    if not frappe.has_permission("Tag Link", "delete"):
        frappe.throw("Insufficient permission to remove tags from this document")
    else:
        DocTags(dt).remove(dn, tag)
        return tag
