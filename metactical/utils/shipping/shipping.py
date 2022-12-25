from metactical.utils.shipping.canada_post import CanadaPost
import frappe


@frappe.whitelist()
def get_rate(name, provider='Canada Post', context=None):
    if provider=="Canada Post":
        cp = CanadaPost()
        response = cp.get_rate(name, context)
        return response


@frappe.whitelist()
def create_shipping(name, provider='Canada Post', sercie_code=None):
    return True
    if provider=="Canada Post":
        cp = CanadaPost()
        response = cp.create_shipping(name, {'service_code': sercie_code} if sercie_code else None)
        return response