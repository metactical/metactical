import frappe
import requests
from frappe import _, get_desk_link, bold
import xmltodict
from requests.auth import _basic_auth_str


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
            'Accept': 'application/vnd.cpc.ship.rate-v4+xml',
            'Content-Type': 'application/vnd.cpc.ship.rate-v4+xml',
            'Accept-language': 'en-CA',
            'Authorization':_basic_auth_str(self.settings.api_key, self.settings.get_password("api_secret"))
        }

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
        return {
            "doc": doc.as_dict(),
            "settings": self.settings.as_dict(),
            "delivery_address_doc": delivery_address_doc,
            "pickup_address_doc": pickup_address_doc
        }

    def get_rate(self, name, context=None):
        body = frappe.render_template(
            "metactical/utils/shipping/templates/canada_post/request/get_rate.xml", self.get_context(name, context))
        response =  self.get_response("/rs/ship/price", body)
        res = []
        if response and response['price-quotes'] and response['price-quotes']['price-quote']:
            for pq in response['price-quotes']['price-quote']:
                res.append({
                    'service_code': pq['service-code'],
                    'service_name': pq['service-name'],
                    'base': pq['price-details']['base'],
                    'total': pq['price-details']['due'],
                    'guaranteed_delivery': pq['service-standard']['guaranteed-delivery'],
                    'expected_transit_time': pq['service-standard']['expected-transit-time'],
                    'expected_delivery_date': pq['service-standard']['expected-delivery-date'],
                })
        return res
    
    def create_shipping(self, name, context=None):
        body = frappe.render_template(
            "metactical/utils/shipping/templates/canada_post/request/create_shipment.xml", self.get_context(name, context))
        response =  self.get_response(f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/shipment", body)
        res = []
        # TODO: Update shipment documents.

    def get_response(self, url, body):
        r = self.sess.post(f'{self.settings.host}{url}', body)
        r.raise_for_status()
        if r.status_code==200:
            return self.xml_to_json(r.text)
        else:
            frappe.msgprint(r.text)
