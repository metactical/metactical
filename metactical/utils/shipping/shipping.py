from metactical.utils.shipping.canada_post import CanadaPost
import frappe
from frappe.model.mapper import get_mapped_doc


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
        if response:
            doc = frappe.get_doc('Shipment', name)
            for d in frappe.get_all('Delivery Note', [['docstatus', '=', 0],['name', 'in',(x.delivery_note for x in doc.shipment_delivery_note)]], pluck="name"):
                ddoc = frappe.get_doc('Delivery Note', d)
                ddoc.submit()
        return response


@frappe.whitelist()
def avoid_shpment(name, provider='Canada Post', shipments_name=None):
    if provider=="Canada Post":
        cp = CanadaPost()
        response = cp.avoid_shpment(name, shipments_name)
        return response


@frappe.whitelist()
def make_shipment(source_name, target_doc=None):
	def postprocess(source, target):
		user = frappe.db.get_value(
			"User", frappe.session.user, ["email", "full_name", "phone", "mobile_no"], as_dict=1
		)
		target.pickup_contact_email = user.email
		pickup_contact_display = "{}".format(user.full_name)
		if user:
			if user.email:
				pickup_contact_display += "<br>" + user.email
			if user.phone:
				pickup_contact_display += "<br>" + user.phone
			if user.mobile_no and not user.phone:
				pickup_contact_display += "<br>" + user.mobile_no
		target.pickup_contact = pickup_contact_display

		# As we are using session user details in the pickup_contact then pickup_contact_person will be session user
		target.pickup_contact_person = frappe.session.user

		contact = frappe.db.get_value(
			"Contact", source.contact_person, ["email_id", "phone", "mobile_no"], as_dict=1
		)
		delivery_contact_display = "{}".format(source.contact_display)
		if contact:
			if contact.email_id:
				delivery_contact_display += "<br>" + contact.email_id
			if contact.phone:
				delivery_contact_display += "<br>" + contact.phone
			if contact.mobile_no and not contact.phone:
				delivery_contact_display += "<br>" + contact.mobile_no
		target.delivery_contact = delivery_contact_display

		if source.shipping_address_name:
			target.delivery_address_name = source.shipping_address_name
			target.delivery_address = source.shipping_address
		elif source.customer_address:
			target.delivery_address_name = source.customer_address
			target.delivery_address = source.address_display

	doclist = get_mapped_doc(
		"Delivery Note",
		source_name,
		{
			"Delivery Note": {
				"doctype": "Shipment",
				"field_map": {
					"grand_total": "value_of_goods",
					"company": "pickup_company",
					"company_address": "pickup_address_name",
					"company_address_display": "pickup_address",
					"customer": "delivery_customer",
					"contact_person": "delivery_contact_name",
					"contact_email": "delivery_contact_email",
				},
				"validation": {"docstatus": ["<", 2]},
			},
			"Delivery Note Item": {
				"doctype": "Shipment Delivery Note",
				"field_map": {
					"name": "prevdoc_detail_docname",
					"parent": "prevdoc_docname",
					"parenttype": "prevdoc_doctype",
					"base_amount": "grand_total",
				},
			},
		},
		target_doc,
		postprocess,
	)

	return doclist
