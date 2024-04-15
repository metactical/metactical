import frappe

@frappe.whitelist()
def delete_checklist_group(docname):
    try:
        checklist_items = frappe.get_all("Task Checklist", filters={"parent_checklist": docname}, fields=["name"])
        for item in checklist_items:
            frappe.delete_doc("Task Checklist", item.name)

        frappe.delete_doc("Task Checklist", docname)
        frappe.response["success"] = True
    except Exception as e:
        frappe.db.rollback()
        frappe.response["success"] = False
        frappe.response["error"] = str(e)
    
@frappe.whitelist()
def delete_checklist_item(docname):
    try:
        frappe.delete_doc("Task Checklist", docname)
        frappe.response["success"] = True
    except Exception as e:
        frappe.db.rollback()
        frappe.response["success"] = False
        frappe.response["error"] = str(e)

@frappe.whitelist()
def add_checklist_item(parent, title, due_date=None):
    try:
        checklist_item = frappe.new_doc("Task Checklist")
        checklist_item.update({
            "parent": parent,
            "parent_checklist": parent,
            "title": title,
            "due_date": due_date
        })
        checklist_item.save()
        frappe.response["success"] = True
    except Exception as e:
        frappe.db.rollback()
        frappe.response["success"] = False
        frappe.response["error"] = str(e)

@frappe.whitelist()
def update_checklist_item_status(name, value):
    try:
        frappe.db.set_value("Task Checklist", name, "is_completed", value)
        frappe.response["success"] = True
    except Exception as e:
        frappe.db.rollback()
        frappe.response["success"] = False
        frappe.response["error"] = str(e)

@frappe.whitelist()
def update_checklist_item(name, title, assign_to=None, due_date=None):
    try:
        task_checklist = frappe.get_doc("Task Checklist", name)
        task_checklist.title = title
        task_checklist.due_date = due_date
        task_checklist.assign_to = assign_to
        if not assign_to:
            task_checklist.first_name = ""
            
        task_checklist.save()
        frappe.db.commit()
        frappe.response["success"] = True
        frappe.response["first_name"] = task_checklist.first_name if assign_to else ""
    except Exception as e:
        frappe.db.rollback()
        frappe.response["success"] = False
        frappe.response["error"] = str(e)