import frappe
import requests
from frappe import _, get_desk_link, bold
import xmltodict
from requests.auth import _basic_auth_str
from frappe.utils import get_files_path
from six import string_types
import ast


class CanadaPost():
    def __init__(self) -> None:
        self.settings = frappe.get_cached_doc('Canada Post', 'Canada Post')
        if any([not self.settings.get(field) for field in ("enabled", "api_key", "api_secret", "customer_number", "contract_number")]):
            frappe.throw(_("Please Complete Canada Post Settings {}").format(
                bold(get_desk_link(self.settings.doctype, self.settings.doctype))))
        self._init_session()

    def __exit__(self) -> None:
        self.sess.close()

    def _init_session(self):
        self.sess = requests.Session()
        self.set_default_headers()

    def set_default_headers(self):
        self.sess.headers = {
            'Accept': 'application/vnd.cpc.shipment-v8+xml',
            'Content-Type': 'application/vnd.cpc.shipment-v8+xml',
            'Accept-language': 'en-CA',
            'Authorization': _basic_auth_str(self.settings.api_key, self.settings.get_password("api_secret"))
        }
        self.sess.verify = False

    def xml_to_json(self, data):
        return xmltodict.parse(data)

    def json_to_xml(self, data):
        return xmltodict.unparse(data, pretty=True)

    def get_context(self, name, context=None):
        doc = frappe.get_doc('Shipment', name)
        if context:
            doc.update(context)
        delivery_address_doc = frappe.get_doc(
            'Address', doc.delivery_address_name).as_dict()
        pickup_address_doc = frappe.get_doc(
            'Address', doc.pickup_address_name).as_dict()
        pickup_person_doc = frappe.get_doc(
            'User', doc.pickup_contact_person).as_dict()
        delivery_contact_doc = frappe.get_doc(
            'Contact', doc.delivery_contact_name).as_dict()
        return {
            "doc": doc.as_dict(),
            "settings": self.settings.as_dict(),
            "delivery_address_doc": delivery_address_doc,
            "pickup_address_doc": pickup_address_doc,
            "delivery_contact_doc": delivery_contact_doc,
            "pickup_contact_person_doc": pickup_person_doc
        }

    def get_rate(self, name, context=None):
        body = frappe.render_template(
            "metactical/utils/shipping/templates/canada_post/request/get_rate.xml", self.get_context(name, context))
        response = self.get_response("/rs/ship/price", body, {'Accept': 'application/vnd.cpc.ship.rate-v4+xml',
                                                              'Content-Type': 'application/vnd.cpc.ship.rate-v4+xml'})
        res = []
        if response and response['price-quotes'] and response['price-quotes']['price-quote']:
            for pq in response['price-quotes']['price-quote']:
                res.append({
                    'carrier_service': pq['service-code'],
                    'service_name': pq['service-name'],
                    'base': pq['price-details']['base'],
                    'shipment_amount': pq['price-details']['due'],
                    'guaranteed_delivery': pq['service-standard']['guaranteed-delivery'],
                    'expected_transit_time': pq['service-standard']['expected-transit-time'],
                    'expected_delivery_date': pq['service-standard']['expected-delivery-date'],
                })
        return res

    def create_shipping(self, name, context=None):
        if context and isinstance(context, string_types) and context.startswith('{'):
            context = ast.literal_eval(context)
        body = frappe.render_template(
            "metactical/utils/shipping/templates/canada_post/request/create_shipment.xml", self.get_context(name, context))
        response = self.get_response(
            f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/shipment", body)
        doc = frappe.get_doc('Shipment', name)
        if context:
            doc.update(context)
        doc.db_set('shipment_id', response['shipment-info']['shipment-id'])
        doc.db_set('awb_number', response['shipment-info']['tracking-pin'])
        doc.set('carrier', 'Canada Post')
        doc.set('carrier_status', response['shipment-info']['shipment-status'])
        doc.set('service_provider', 'Canada Post')
        # Download Label
        for link in response['shipment-info']['links']['link']:
            if link['@rel'] == "price":
                doc.set('tracking_url', link['@href'])
            elif link['@rel'] == "price":
                res = self.get_response(link['@href'], None, {'Accept': link['@media-type'],
                                                              'Content-Type': link['@media-type']}, method='GET')
                if res:
                    doc.set('shipment_amount',
                            res['shipment-price']['due-amount'])
            elif link['@rel'] == "label":
                res = self.get_response(link['@href'], None, {'Accept': link['@media-type'],
                                                              'Content-Type': link['@media-type']}, return_request=True, method='GET')
                self.write_file(doc, res)

        doc.save()
        return doc.as_dict()

    def write_file(self, doc, res):
        file_path = get_files_path(f"{doc.shipment_id}.pdf", is_private=True)
        with open(file_path) as f:
            f.write(res.content)
            f.close()
        file_doc = frappe.new_doc('File')
        file_doc.update({
            'file_name': f"{doc.shipment_id}.pdf",
            'file_url': f"private/files/{doc.shipment_id}.pdf",
            'is_private': 1,
            'folder': 'Home/Attachments',
            'attached_to_doctype': doc.doctype,
            'attached_to_name': doc.name,
            'file_size': len(res.content)
        })
        file_doc.insert(ignore_permissions=True)

    def get_response(self, url, body, headers=None, return_request=False, method='POST', retry=False):
        if headers:
            self.sess.headers.update(headers)
        try:
            r = self.sess.request(method, url if url.startswith(
                'https://') else f'{self.settings.host}{url}', data=body)
            r.raise_for_status()
            if r.status_code == 200:
                if return_request:
                    return r
                return self.xml_to_json(r.content)
        except requests.exceptions.SSLError:
            if not retry:
                self.get_response(url, body, headers,
                                  return_request, method, True)
        except:
            frappe.throw(r.content, title=r.status_code)
