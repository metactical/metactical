# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as _app_version

app_name = "metactical"
app_title = "Metactical"
app_publisher = "Techlift Technologies"
app_description = "Metactical Custom ERPNext App"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "palash@techlift.in"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = ["/assets/css/metactical.css", "/assets/metactical/css/metactical_task.css"]
app_include_js = ["/assets/js/metactical.min.js", "/assets/metactical/js/metactical_kanban_custom.js"]

# include js, css files in header of web template
# web_include_css = "/assets/metactical/css/metactical.css"
web_include_css = [
	"/assets/metactical/node_modules/intl-tel-input/build/css/intlTelInput.css", 
	"/assets/metactical/css/metactical_time_tracker.css"
]
# web_include_js = "/assets/metactical/js/metactical.js"
web_include_js = "/assets/metactical/node_modules/intl-tel-input/build/js/intlTelInput.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Sales Order" : "custom_scripts/sales_order/sales_order.js",
	"Pick List": "custom_scripts/pick_list/pick_list.js",
	"Stock Entry": "custom_scripts/stock_entry/stock_entry.js",
	"Sales Invoice": "custom_scripts/sales_invoice/sales_invoice.js",
	"Purchase Order": "custom_scripts/purchase_order/purchase_order.js",
	"Material Request": "custom_scripts/material_request/material_request.js",
	"Payment Entry": "custom_scripts/payment_entry/payment_entry.js",
	"Employee": "custom_scripts/employee/employee.js",
	"Stock Reconciliation": "custom_scripts/stock_reconciliation/stock_reconciliation.js",
	"Purchase Receipt": "custom_scripts/purchase_receipt/purchase_receipt.js",
	"Customer": "custom_scripts/customer/customer.js",
	"Shipment": "custom_scripts/shipment/shipment.js",
	"Delivery Note": "custom_scripts/delivery_note/delivery_note.js",
	"Project": "custom_scripts/project/project.js",
	"Task": "custom_scripts/task/task.js",
}
# doctype_js = {"doctype" : "public/js/doctype.js"}
#doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
doctype_list_js = {
	"Stock Reconciliation": "custom_scripts/stock_reconciliation/stock_reconciliation_list.js",
	"Task": "custom_scripts/task/task_list.js",
	"Project": "custom_scripts/project/project_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "metactical.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "metactical.install.before_install"
# after_install = "metactical.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "metactical.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"End of Day Closing": "metactical.metactical.doctype.end_of_day_closing.end_of_day_closing.get_permission_query_conditions"
}

#
has_permission = {
	"End of Day Closing": "metactical.metactical.doctype.end_of_day_closing.end_of_day_closing.has_permission"
}


# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Purchase Order": {
		"after_insert": "metactical.barcode_generator.generate",
		"validate": "metactical.barcode_generator.po_validate",
	},
	"Delivery Note": {
		"on_update": "metactical.custom_scripts.delivery_note.delivery_note.on_update",
		"on_trash": "metactical.custom_scripts.delivery_note.delivery_note.on_trash",
		"on_cancel": "metactical.custom_scripts.delivery_note.delivery_note.on_cancel",
		"on_submit": "metactical.custom_scripts.delivery_note.delivery_note.on_submit"
	},
	"Address": {
		"validate": "metactical.custom_scripts.address.address.validate"
	},
	"Contact": {
		"validate": "metactical.custom_scripts.contact.contact.validate"
	},
	"Shipment": {
		"validate": "metactical.custom_scripts.shipment.shipment.validate",
		"before_cancel": "metactical.custom_scripts.shipment.shipment.before_cancel",
	},
	"Task": {
		"before_insert": "metactical.custom_scripts.task.task.set_start_date"
	}, 
	"Project": {
		"on_update": "metactical.custom_scripts.project.project.on_update"
	}
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Sales Invoice": "metactical.custom_scripts.sales_invoice.sales_invoice.CustomSalesInvoice",
	"Pick List": "metactical.custom_scripts.pick_list.pick_list.CustomPickList",
	"Quotation": "metactical.custom_scripts.quotation.quotation.CustomQuotation",
	"Sales Order": "metactical.custom_scripts.sales_order.sales_order.SalesOrderCustom",
	"Packing Slip": "metactical.custom_scripts.packing_slip.packing_slip.CustomPackingSlip",
	"Stock Reconciliation": "metactical.custom_scripts.stock_reconciliation.stock_reconciliation.CustomStockReconciliation",
	"Purchase Order": "metactical.custom_scripts.purchase_order.purchase_order.CustomPurchaseOrder",
	"Purchase Receipt": "metactical.custom_scripts.purchase_receipt.purchase_receipt.CustomPurchaseReceipt",
	"Purchase Invoice": "metactical.custom_scripts.purchase_invoice.purchase_invoice.CustomPurchaseInvoice",
	"Stock Entry": "metactical.custom_scripts.stock_entry.stock_entry.CustomStockEntry",
	"Material Request": "metactical.custom_scripts.material_request.material_request.CustomMaterialRequest"
}

# Scheduled Tasks
# ---------------

scheduler_events = {
# 	"all": [
# 		"metactical.tasks.all"
# 	],
	"daily": [
		"metactical.reserved_calculation.recalculate_reserved_qty"
	],
#	"hourly": [
#		"metactical.api.shipstation.sync_shipping_status"
#	],
# 	"weekly": [
# 		"metactical.tasks.weekly"
# 	]
# 	"monthly": [
# 		"metactical.tasks.monthly"
# 	],
	"cron": {
		"15 * * * *": [
			"metactical.custom_scripts.frappe/document.clear_queues_docs"
		]
	}
}

# Testing
# -------

# before_tests = "metactical.install.before_tests"

# Migrating
after_migrate = "metactical.migrate.after_migrate"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.selling.doctype.sales_order.sales_order.create_pick_list": "metactical.custom_scripts.pick_list.pick_list.create_pick_list",
	"frappe.utils.print_format.download_pdf": "metactical.print_format.download_pdf",
	#"erpnext.controllers.accounts_controller.update_child_qty_rate": "metactical.custom_scripts.sales_order_item.sales_order_item.update_child_qty_rate",
	"erpnext.stock.doctype.pick_list.pick_list.create_delivery_note": "metactical.custom_scripts.pick_list.pick_list.create_delivery_note",
	"erpnext.stock.get_item_details.get_item_details": "metactical.custom_scripts.get_item_details.get_item_details",
	"erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice": "metactical.custom_scripts.sales_order.sales_order.make_sales_invoice",
	"erpnext.stock.doctype.pick_list.pick_list.PickList.set_item_locations": "metactical.custom_scripts.pick_list.pick_list.CustomPickList.set_item_locations",
	"erpnext.setup.utils.get_exchange_rate": "metactical.custom_scripts.setup.utils.get_exchange_rate"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
#override_doctype_dashboards = {
 	#"Task": "metactical.task.get_dashboard_data"
#}

#Fixtures
fixtures = [{
		"dt": "Custom Field",
		"filters": [["name", "in", [
			'Stock Settings-ais_default_price_list',
			'Stock Settings-ais_sales_report_settings'
		]]]
	},
	{
		"dt": "Kanban Board",
		"filters": [["name", "in", [
			"Buying Board",
			"Projects Status"
		]]]
	}
]

#For using in print format
jenv = {
	"methods": [
		"get_po_items:metactical.custom_scripts.purchase_order.purchase_order.get_po_items",
		"get_pr_items:metactical.custom_scripts.purchase_receipt.purchase_receipt.get_pr_items",
		"get_barcode:metactical.barcode_generator.get_barcode",
		"si_mode_of_payment:metactical.custom_scripts.sales_invoice.sales_invoice.si_mode_of_payment"
	]
}


