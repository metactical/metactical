# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"module_name": "Metactical",
			"color": "grey",
			"icon": "octicon octicon-file-directory",
			"type": "module",
			"label": _("Reports"),
			"icon": "fa fa-list",
			"items": [
				{
					"type": "report",
					"is_query_report": True,
					"name": "POS Discount Report",
					"doctype": "Sales Invoice"
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Stock Reconciliation Report",
					"doctype": "Stock Reconciliation"
				},
				{
					"type": "report",
					"name": "Item-Wise Sales Invoice Report",
					"doctype": "Sales Invoice",
					"is_query_report": True
				},
				{
					"type": "report",
					"name": "Sales Report - Full V3",
					"doctype": "Sales Invoice",
					"is_query_report": True,
					
				},
				{
					"type": "report",
					"name": "Sales Report - Full V4",
					"doctype": "Sales Invoice",
					"is_query_report": True,
					
				},
				{
					"type": "report",
					"name": "Sales Report RASUSA - Full V1",
					"doctype": "Sales Invoice",
					"is_query_report": True
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Payments Status",
					"doctype": "Sales Order",
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Ready to Ship - Orders",
					"doctype": "Sales Order",
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Pick List Status",
					"doctype": "Sales Order",
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Sales Report - Stores",
					"doctype": "Stock Ledger Entry",
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Open Purchase Orders",
					"doctype": "Purchase Order",
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Supplier Status Report",
					"doctype": "Supplier",
				},
				{
					"type": "report",
					"is_query_report": True,
					"name": "Dead Stock Report",
					"doctype": "Sales Invoice",
				},
			]
		},
		{
			"label": _("Metactical Items"),
			"items": [
				{
					"type": "doctype",
					"name": "Item Search Settings",
					"description": _("Item Search Settings.")
				},
				{
					"type": "doctype",
					"name": "Shipstation Settings",
					"description": _("Shipstation Settings")
				},
				{
					"type": "doctype",
					"name": "Shipstation API Requests",
					"description": _("Shipstation API Requests.")
				},
				{
					"type": "page",
					"name": "packing-slip",
					"label": _("Packing Slip"),
					"description": _("Packing Slip Page.")
				},
				{
					"type": "doctype",
					"name": "Upload Images",
					"description": _("Upload Large Images.")
				},
				{
					"type": "doctype",
					"name": "Suspended Invoice",
					"description": _("Suspended Invoice.")
				},
			]
		},
	]
