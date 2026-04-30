import frappe
from frappe.desk.doctype.tag.tag import Tag
from frappe.desk.doctype.tag.tag import DocTags

class CustomTag(Tag):
    def after_rename(self, old_name, new_name, merge=False):
        parent_after_rename = getattr(super(), "after_rename", None)
        if parent_after_rename:
            parent_after_rename(old_name, new_name, merge)

        enqueue_sync_linked_user_tags(new_name)

    def on_trash(self):
        parent_on_trash = getattr(super(), "on_trash", None)
        if parent_on_trash:
            parent_on_trash()

        self.flags.user_tag_sync_targets = get_linked_docs(self.name)

    def after_delete(self):
        parent_after_delete = getattr(super(), "after_delete", None)
        if parent_after_delete:
            parent_after_delete()

        enqueue_sync_documents_user_tags(
            linked_docs=self.flags.user_tag_sync_targets or [],
            excluded_tags=[self.name],
        )


def enqueue_tag_update(method, **kwargs):
    frappe.enqueue(
        method,
        queue="default",
        enqueue_after_commit=not frappe.flags.in_test,
        now=frappe.flags.in_test,
        **kwargs,
    )


def enqueue_tag_action(action, dt, docs, tags):
    enqueue_tag_update(
        process_tag_action,
        action=action,
        dt=dt,
        docs=docs,
        tags=tags,
    )


def process_tag_action(action, dt, docs, tags):
    doc_tags = DocTags(dt)

    for docname in docs:
        if not frappe.db.exists(dt, docname):
            continue

        for tag in tags:
            if action == "add":
                doc_tags.add(docname, tag)
                add_comment(dt, docname, f" added tag <b>{tag}</b>")
            elif action == "remove":
                doc_tags.remove(docname, tag)
                add_comment(dt, docname, f" removed tag <b>{tag}</b>")
            else:
                frappe.throw(f"Unsupported tag action: {action}")


def enqueue_sync_linked_user_tags(tag_name):
    enqueue_tag_update(
        sync_linked_user_tags,
        tag_name=tag_name,
    )


def enqueue_sync_documents_user_tags(linked_docs, excluded_tags=None):
    enqueue_tag_update(
        sync_documents_user_tags,
        linked_docs=linked_docs,
        excluded_tags=excluded_tags or [],
    )


def sync_linked_user_tags(tag_name):
    sync_documents_user_tags(get_linked_docs(tag_name))


def sync_documents_user_tags(linked_docs, excluded_tags=None):
    for linked_doc in linked_docs:
        sync_document_user_tags(
            linked_doc["document_type"],
            linked_doc["document_name"],
            excluded_tags=excluded_tags,
        )


def get_linked_docs(tag_name):
    linked_docs = frappe.get_all(
        "Tag Link",
        filters={"tag": tag_name},
        fields=["document_type", "document_name"],
        order_by="creation asc",
    )

    return [
        {"document_type": linked_doc.document_type, "document_name": linked_doc.document_name}
        for linked_doc in linked_docs
    ]


def sync_document_user_tags(doctype, docname, excluded_tags=None):
    if not frappe.db.exists(doctype, docname):
        return

    excluded_tags = set(excluded_tags or [])
    current_tags = [
        tag
        for tag in frappe.get_all(
            "Tag Link",
            filters={"document_type": doctype, "document_name": docname},
            pluck="tag",
            order_by="creation asc",
        )
        if tag not in excluded_tags
    ]
    DocTags(doctype).update(docname, current_tags)

@frappe.whitelist()
def add_tag(tag, dt, dn, color=None):
    # check if user has permission to add tags to this document
    if not frappe.has_permission("Tag", "create") and not frappe.db.exists("Tag", tag):
        frappe.throw("Insufficient permission to create Tag")
    elif not frappe.has_permission("Tag Link", "create"):
        frappe.throw("Insufficient permission to add tags to this document")
    else:
        enqueue_tag_action("add", dt, [dn], [tag])
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

    enqueue_tag_action("add", dt, docs, tags)

@frappe.whitelist()
def remove_tag(tag, dt, dn):
    # check if user has permission to remove tags from this document
    if not frappe.has_permission("Tag Link", "delete"):
        frappe.throw("Insufficient permission to remove tags from this document")
    else:
        enqueue_tag_action("remove", dt, [dn], [tag])
        return tag
    
def add_comment(dt, dn, comment_text):
    comment = frappe.new_doc("Comment")
    comment.update(
    {
        "comment_type": "Label",
        "reference_doctype": dt,
        "reference_name": dn,
        "comment_email": frappe.session.user,
        "comment_by": frappe.session.user,
        "content": comment_text,
    })
    comment.insert(ignore_permissions=True)