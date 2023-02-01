import frappe
from frappe import _
from metactical.utils.shipping.shipping import avoid_shpment


def validate(doc, method=None):
    for parcel in doc.shipment_parcel:
        if parcel.weight > 32:
            frappe.throw(_("Weight doesn't allow more than 32 Kg"))


def before_cancel(doc, method=None):
    if doc.shipments:
        avoid_shpment(doc.name, doc.service_provider, [x.name for x in doc.shipments])
