import frappe
from erpnext.projects.doctype.project.project import create_kanban_board_if_not_exists

def on_update(doc, method):
    create_kanban_board_if_not_exists(doc.name)
