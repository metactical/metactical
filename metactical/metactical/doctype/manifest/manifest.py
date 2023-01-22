# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost


class Manifest(Document):
    @frappe.whitelist()
    def get_shipments(self):
        if not (self.from_date and self.to_date):
            frappe.throw(_("From Date and To Date are Mandatory"))
        for row in frappe.get_all('Shipment', [['pickup_date', '>=', self.from_date],
                                               ['pickup_date', '<=', self.to_date], ['Canada Post Shipment', 'shipment_id', 'is', 'set']],
                                  ['name as shipment', '`tabCanada Post Shipment`.name as row_name', '`tabCanada Post Shipment`.shipment_id']):
            self.append('items', row)
        return self.as_dict()

    def create_manifest(self):
        address_wise_shipments = {}
        for d in frappe.get_all('Shipment', [['name', 'in', (x.shipment for x in self.items)]], ['name', 'pickup_address_name']):
            r = address_wise_shipments.setdefault(d.pickup_address_name, [])
            r.append(d.name)
        cp = CanadaPost()
        files = []
        for key in address_wise_shipments:
            files.extend(cp.create_manifest(address_wise_shipments[key]))
        return files
