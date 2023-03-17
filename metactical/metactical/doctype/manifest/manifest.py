# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost


class Manifest(Document):
    def validate(self):
        self.sync_warehouse()
    
    def sync_warehouse(self):
        warehouses = set(x.warehouse for x in self.get('items', default=[]) if x.warehouse)
        # Remove Unwanted Address.
        exists = []
        to_be_remove = []
        for x in self.get('manifests', default=[]):
            exists.append(x.warehouse)
            if x.warehouse not in warehouses:
                to_be_remove.append(x)
        for rx in to_be_remove:
            self.remove(rx)
        # Added new on
        for warehosue in warehouses:
            if warehosue not in exists:
                self.append('manifests', {'warehouse': warehosue})

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
        for warehouse in self.get('manifests', default=[]):
            if warehouse.manifest:
                continue
            items = [x.shipment for x in self.get('items', {'warehouse': warehouse.warehouse})]
            if items:
                files.extend(cp.create_manifest(items, self, warehouse))
        self.save()
        return files
