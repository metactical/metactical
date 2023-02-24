# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost


class Manifest(Document):
    def validate(self):
        self.sync_address()
    
    def sync_address(self):
        address = set(x.pickup_address for x in self.get('items', default=[]) if x.pickup_address)
        # Remove Unwanted Address.
        exists = []
        to_be_remove = []
        for x in self.get('manifests', default=[]):
            exists.append(x.address)
            if x.address not in address:
                to_be_remove.append(x)
        for rx in to_be_remove:
            self.remove(rx)
        # Added new on
        for add in address:
            if add not in exists:
                self.append('manifests', {'address': add})

    @frappe.whitelist()
    def get_shipments(self):
        if not (self.from_date and self.to_date):
            frappe.throw(_("From Date and To Date are Mandatory"))
        for row in frappe.get_all('Shipment', [['pickup_date', '>=', self.from_date],
                                               ['pickup_date', '<=', self.to_date], ['Canada Post Shipment', 'shipment_id', 'is', 'set']],
                                  ['name as shipment', '`tabCanada Post Shipment`.name as row_name', '`tabCanada Post Shipment`.shipment_id']):
            self.append('items', row)
        return self.as_dict()

    @frappe.whitelist()
    def create_manifest(self):
        cp = CanadaPost()
        files = []
        for addr in self.get('manifests', default=[]):
            if addr.manifest:
                continue
            items = [x.shipment for x in self.get('items', {'pickup_address': addr.address})]
            if items:
                files.extend(cp.create_manifest(items, self, addr))
        self.save()
        return files
