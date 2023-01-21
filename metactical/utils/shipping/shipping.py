from metactical.utils.shipping.canada_post import CanadaPost
import frappe


@frappe.whitelist()
def get_rate(name, provider='Canada Post', context=None):
    if provider=="Canada Post":
        cp = CanadaPost()
        response = cp.get_rate(name, context)
        return response


@frappe.whitelist()
def create_shipping(name, provider='Canada Post', carrier_service=None):
    if provider=="Canada Post":
        cp = CanadaPost()
        response = cp.create_shipping(name, carrier_service)
        return response


@frappe.whitelist()
def avoid_shpment(name, provider='Canada Post', shipments_name=None):
    if provider=="Canada Post":
        cp = CanadaPost()
        response = cp.avoid_shpment(name, shipments_name)
        return response
