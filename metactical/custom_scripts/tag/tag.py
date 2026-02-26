import frappe
from frappe.desk.doctype.tag.tag import DocTags

@frappe.whitelist()
def add_tag(tag, dt, dn, color=None):
    # check if user has permission to add tags to this document
    if not frappe.has_permission("Tag", "create") and not frappe.db.exists("Tag", tag):
        frappe.throw("Insufficient permission to create Tag")
    elif not frappe.has_permission("Tag Link", "create"):
        frappe.throw("Insufficient permission to add tags to this document")
    else:
        DocTags(dt).add(dn, tag)
        return tag

@frappe.whitelist()
def add_tags(tags, dt, docs, color=None):
    "adds a new tag to a record, and creates the Tag master"
    tags = frappe.parse_json(tags)
    docs = frappe.parse_json(docs)

    if not frappe.has_permission("Tag", "create"):
        for tag in tags:
            if not frappe.db.exists("Tag", tag):
                frappe.throw("Insufficient permission to create Tag: {}".format(tag))

    if not frappe.has_permission("Tag Link", "create"):
        frappe.throw("Insufficient permission to add tags to this document")

    for doc in docs:
        for tag in tags:
            DocTags(dt).add(doc, tag)

@frappe.whitelist()
def remove_tag(tag, dt, dn):
    # check if user has permission to remove tags from this document
    if not frappe.has_permission("Tag Link", "delete"):
        frappe.throw("Insufficient permission to remove tags from this document")
    else:
        DocTags(dt).remove(dn, tag)
        return tag
