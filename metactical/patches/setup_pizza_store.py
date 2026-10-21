import frappe
from metactical.pizza_store.config import PIZZA_STORE
from metactical.pizza_store import setup


def execute():
    setup.run(PIZZA_STORE)
    frappe.db.commit()
