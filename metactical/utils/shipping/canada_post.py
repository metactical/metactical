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
        if not doc.shipment_parcel:
            frappe.throw(_("Should be min one Shiopment Parcel row"))
        if context:
            doc.update(context)
        doc.shipment_type = self.get_shipment_type(doc.shipment_type)
        delivery_address_doc = frappe.get_doc(
            'Address', doc.delivery_address_name).as_dict()
        pickup_address_doc = frappe.get_doc(
            'Address', doc.pickup_address_name).as_dict()
        pickup_person_doc = frappe.get_doc(
            'User', doc.pickup_contact_person).as_dict()
        delivery_contact_doc = frappe.get_doc(
            'Contact', doc.delivery_contact_name).as_dict()
        delivery_note = frappe.get_doc(
            'Delivery Note', doc.shipment_delivery_note[-1].delivery_note).as_dict()
        return frappe._dict({
            "doc": doc.as_dict(),
            "settings": self.settings.as_dict(),
            "delivery_address_doc": delivery_address_doc,
            "pickup_address_doc": pickup_address_doc,
            "delivery_contact_doc": delivery_contact_doc,
            "pickup_contact_person_doc": pickup_person_doc,
            "delivery_note": delivery_note,
        })

    def get_shipment_type(self, s_type):
        return {
            "Document": "DOC",
            "Commercial Sample": "SAM",
            "Repair or Warranty": "REP",
            "Goods": "SOG",
            "Other": "OTH",
        }[s_type]

    def get_rate(self, name, context=None):
        res = []
        options = {}
        context = self.get_context(name, context)        
        exists = self.existing_shipments(context.doc)
        for parcel in context.doc.shipment_parcel:
            if (parcel.count - exists.get(parcel.name, 0)) <1:
                continue
            context.parcel = parcel
            body = frappe.render_template(
                "metactical/utils/shipping/templates/canada_post/request/get_rate.xml", context)
            response = self.get_response("/rs/ship/price", body, {'Accept': 'application/vnd.cpc.ship.rate-v4+xml',
                                                                  'Content-Type': 'application/vnd.cpc.ship.rate-v4+xml'})
            items = []
            if response and response['price-quotes'] and response['price-quotes']['price-quote']:
                for pq in response['price-quotes']['price-quote']:
                    options[pq['service-code']] = pq['service-name']
                    items.append({
                        'carrier_service': pq['service-code'],
                        'service_name': pq['service-name'],
                        'base': pq['price-details']['base'],
                        'shipment_amount': pq['price-details']['due'],
                        'guaranteed_delivery': pq['service-standard']['guaranteed-delivery'],
                        'expected_transit_time': pq['service-standard']['expected-transit-time'],
                        'expected_delivery_date': pq['service-standard']['expected-delivery-date'],
                    })
            if items:
                res.append({
                    'name': parcel.name,
                    'idx': parcel.idx,
                    'count': parcel.count,
                    'items': items,
                })
        return {'data': res, 'options': [{'key':k, 'val':v} for k,v in options.items()]}

    def create_shipping(self, name, carrier_service):
        if carrier_service is None:
            frappe.throw(_("Service Code Required. please select service"))
        if isinstance(carrier_service, string_types) and carrier_service.startswith('{'):
            carrier_service = ast.literal_eval(carrier_service)
        
        doc=frappe.get_doc('Shipment', name)
        context = self.get_context(name)
        exists = self.existing_shipments(context.doc)
        for parcel in context.doc.shipment_parcel:
            context.parcel = parcel
            context.parcel.carrier_service = carrier_service.get(parcel.name)
            for c in range(parcel.count - exists.get(parcel.name, 0)):
                body = frappe.render_template(
                    "metactical/utils/shipping/templates/canada_post/request/create_shipment.xml", context)
                response = self.get_response(
                    f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/shipment", body)
                row = doc.append('shipments', {
                    'shipment_id':response['shipment-info']['shipment-id'],
                    'awb_number': response['shipment-info']['tracking-pin'],
                    'service_provider': 'Canada Post',
                    'carrier_service': context.parcel.carrier_service,
                    'tracking_status': '',
                    'carrier_status': response['shipment-info']['shipment-status'],
                    'row_id': parcel.name
                })
                for link in response['shipment-info']['links']['link']:
                    rel = 'tracking' if link['@rel'] == "self" else link['@rel']
                    row.set(f'{rel}_url', f'''<link rel="{link['@rel']}" href="{link['@href']}" media-type="{link['@media-type']}"></link>''')
                row.db_insert()
        doc.save()
        return doc.as_dict()
    
    def existing_shipments(self, doc):
        shipments = frappe._dict()
        for d in doc.get('shipments', []):
            if not shipments.get(d.row_id):
                shipments[d.row_id] = 0
            shipments[d.row_id] = shipments[d.row_id]+1
        return shipments

    def get_make_transmit_shipment(self, name):
        context = self.get_context(name)
        body = frappe.render_template(
            "metactical/utils/shipping/templates/canada_post/request/transmit_shipment.xml", context)
        response = self.get_response(
            f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/manifest", body, headers={'Accept': 'application/vnd.cpc.manifest-v8+xml', 'Content-Type': 'application/vnd.cpc.manifest-v8+xml'})
        po_numbers = []
        if response:
            res = self.get_response(response['manifests']['link']['@href'], None, {'Accept': response['manifests']['link']['@media-type'],
                                                                                   'Content-Type': response['manifests']['link']['@media-type']}, method='GET')
            if res:
                po_numbers.append(res['manifest']['po-number'])
    def write_file(self, doc, res, file_name=None):
        if res.status_code!=200:
            return
        if not file_name:
            file_name = doc.shipment_id
        file_path = get_files_path(f"{file_name}.pdf", is_private=True)
        with open(file_path, 'wb') as f:
            f.write(res.content)
            # f.close()
        file_doc = frappe.new_doc('File')
        file_doc.update({
            'file_name': f"{file_name}.pdf",
            'file_url': file_path.replace(frappe.get_site_path(), ''),
            'is_private': 1,
            'folder': 'Home/Attachments',
            'attached_to_doctype': doc.doctype,
            'attached_to_name': doc.name,
            'file_size': len(res.content)
        })
        file_doc.insert(ignore_permissions=True)
    
    def avoid_shpment(self, name, shipments_name):
        if not shipments_name:
            frappe.throw(_("Please select min one shipment"))
        if isinstance(shipments_name, string_types) and shipments_name.startswith('['):
            shipments_name = ast.literal_eval(shipments_name)
        doc = frappe.get_doc('Shipment', name)
        to_be_remove=[]
        for shipment in doc.get('shipments', {'name': ('in', shipments_name or [])}):
            url = self.xml_to_json(shipment.tracking_url)
            res = self.get_response(url['link']['@href'], None, {'Accept': url['link']['@media-type'], 'Content-Type': url['link']['@media-type']}, True, 'DELETE')
            if res.status_code==204:
                to_be_remove.append(shipment)
        for row in to_be_remove:
            doc.remove(row)
        doc.save()
        return doc.as_dict()

    def get_response(self, url, body, headers=None, return_request=False, method='POST', retry=False):
        if headers:
            self.sess.headers.update(headers)
        try:
            r = self.sess.request(method, url if url.startswith(
                'https://') else f'{self.settings.host}{url}', data=body)
            r.raise_for_status()
            if return_request:
                return r
            if r.status_code == 200:
                return self.xml_to_json(r.content)
        except requests.exceptions.SSLError:
            if not retry:
                self.get_response(url, body, headers,
                                  return_request, method, True)
        except:
            res = r.content
            try:
                content = self.xml_to_json(res)
                res = frappe.render_template("""
                    <table class="table table-bordered">
                    <tr>
                        <th>Code</th>
                        <th> Description </th>
                    </tr>
                    {% for message in messages.message %}
                    <tr>
                        <th>{{ message.code }} </th>
                        <td>{{ message.description }} </td>
                    {% endfor %}
                    </table>
                """, content)
            except:
                pass
            frappe.throw(res, title=f"Error from Provider Server, Code: {r.status_code}")
