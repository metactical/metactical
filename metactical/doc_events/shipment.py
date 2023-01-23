import frappe
from frappe import _


def validate(doc, method=None):
    for parcel in doc.shipment_parcel:
        if parcel.weight > 32:
            frappe.throw(_("Weight doesn't allow more than 32 Kg"))
