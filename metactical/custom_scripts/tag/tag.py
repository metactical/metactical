import frappe
from frappe.desk.doctype.tag.tag import DocTags, Tag

class CustomTag(Tag):
    def after_rename(self, old_name, new_name, merge=False):
        _enqueue(_sync_tag_links_user_tags, tag_name=new_name)

    def on_trash(self):
        # Capture before delete cascades the Tag Link rows.
        self.flags.user_tag_sync_targets = _get_linked_docs(self.name)

    def after_delete(self):
        _enqueue(
            _sync_user_tags,
            linked_docs=self.flags.user_tag_sync_targets or [],
            excluded_tags=[self.name],
        )


@frappe.whitelist()
def add_tag(tag, dt, dn, color=None):
    if not frappe.has_permission("Tag", "create") and not frappe.db.exists("Tag", tag):
        frappe.throw("Insufficient permission to create Tag")
    if not frappe.has_permission("Tag Link", "create"):
        frappe.throw("Insufficient permission to add tags to this document")

    _enqueue(_apply_tag_action, action="add", dt=dt, docs=[dn], tags=[tag])
    return tag


@frappe.whitelist()
def add_tags(tags, dt, docs, color=None):
    tags = frappe.parse_json(tags)
    docs = frappe.parse_json(docs)

    if not frappe.has_permission("Tag", "create"):
        for tag in tags:
            if not frappe.db.exists("Tag", tag):
                frappe.throw(f"Insufficient permission to create Tag: {tag}")

    if not frappe.has_permission("Tag Link", "create"):
        frappe.throw("Insufficient permission to add tags to this document")

    _enqueue(_apply_tag_action, action="add", dt=dt, docs=docs, tags=tags)


@frappe.whitelist()
def remove_tag(tag, dt, dn):
    if not frappe.has_permission("Tag Link", "delete"):
        frappe.throw("Insufficient permission to remove tags from this document")

    _enqueue(_apply_tag_action, action="remove", dt=dt, docs=[dn], tags=[tag])
    return tag


def _enqueue(method, **kwargs):
    frappe.enqueue(
        method,
        queue="default",
        enqueue_after_commit=not frappe.flags.in_test,
        now=frappe.flags.in_test,
        **kwargs,
    )


def _apply_tag_action(action, dt, docs, tags):
    doc_tags = DocTags(dt)

    for docname in docs:
        if not frappe.db.exists(dt, docname):
            continue

        for tag in tags:
            if action == "add":
                doc_tags.add(docname, tag)
                _add_comment(dt, docname, f" added tag <b>{tag}</b>")
            elif action == "remove":
                doc_tags.remove(docname, tag)
                _add_comment(dt, docname, f" removed tag <b>{tag}</b>")
            else:
                frappe.throw(f"Unsupported tag action: {action}")


def _sync_tag_links_user_tags(tag_name):
    _sync_user_tags(_get_linked_docs(tag_name))


def _sync_user_tags(linked_docs, excluded_tags=None):
    excluded = set(excluded_tags or [])

    for linked in linked_docs:
        doctype = linked["document_type"]
        docname = linked["document_name"]
        if not frappe.db.exists(doctype, docname):
            continue

        current_tags = [
            tag
            for tag in frappe.get_all(
                "Tag Link",
                filters={"document_type": doctype, "document_name": docname},
                pluck="tag",
                order_by="creation asc",
            )
            if tag not in excluded
        ]
        DocTags(doctype).update(docname, current_tags)


def _get_linked_docs(tag_name):
    return frappe.get_all(
        "Tag Link",
        filters={"tag": tag_name},
        fields=["document_type", "document_name"],
        order_by="creation asc",
    )


def _add_comment(dt, dn, comment_text):
    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Label",
            "reference_doctype": dt,
            "reference_name": dn,
            "comment_email": frappe.session.user,
            "comment_by": frappe.session.user,
            "content": comment_text,
        }
    ).insert(ignore_permissions=True)
