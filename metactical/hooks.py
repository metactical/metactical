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
# app_include_css = "/assets/metactical/css/metactical.css"
# app_include_js = "/assets/metactical/js/metactical.js"

# include js, css files in header of web template
# web_include_css = "/assets/metactical/css/metactical.css"
# web_include_js = "/assets/metactical/js/metactical.js"

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
	"Employee": "custom_scripts/employee/employee.js"
}
# doctype_js = {"doctype" : "public/js/doctype.js"}
#doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
doctype_list_js = {
	"Stock Reconciliation": "custom_scripts/stock_reconciliation/stock_reconciliation_list.js",
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

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }


# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Purchase Order": {
		"after_insert": "metactical.barcode_generator.generate",
		"validate": "metactical.barcode_generator.po_validate",
	},
	"Pick List": {
		"before_save": "metactical.custom_scripts.pick_list.pick_list.custom_on_save",
		"validate": "metactical.custom_scripts.pick_list.pick_list.custom_on_save",
		"on_submit": "metactical.custom_scripts.pick_list.pick_list.on_submit",
		"on_cancel": "metactical.custom_scripts.pick_list.pick_list.on_cancel",
	},
	"Sales Invoice": {
		"before_save": "metactical.custom_scripts.sales_invoice.sales_invoice.before_save",
		"before_cancel": "metactical.custom_scripts.sales_invoice.sales_invoice.before_cancel"
	},
	"Delivery Note": {
		"on_update": "metactical.custom_scripts.delivery_note.delivery_note.on_update",
		"on_trash": "metactical.custom_scripts.delivery_note.delivery_note.on_trash",
		"on_cancel": "metactical.custom_scripts.delivery_note.delivery_note.on_cancel",
		"on_submit": "metactical.custom_scripts.delivery_note.delivery_note.on_submit"
	},
	"Stock Entry": {
		"validate": "metactical.custom_scripts.stock_entry.stock_entry.validate",
		"on_submit": "metactical.custom_scripts.stock_entry.stock_entry.on_submit"
	},
	"Material Request": {
		"before_save": "metactical.custom_scripts.material_request.material_request.before_save"
	},
	"Address": {
		"validate": "metactical.custom_scripts.address.address.validate"
	},
	"Contact": {
		"validate": "metactical.custom_scripts.contact.contact.validate"
	},
	#"Purchase Receipt": {
	#	"validate": "metactical.custom_scripts.purchase_receipt.purchase_receipt.validate"
	#}
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
# 	"hourly": [
# 		"metactical.tasks.hourly"
# 	],
# 	"weekly": [
# 		"metactical.tasks.weekly"
# 	]
# 	"monthly": [
# 		"metactical.tasks.monthly"
# 	]
}

# Testing
# -------

# before_tests = "metactical.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.selling.doctype.sales_order.sales_order.create_pick_list": "metactical.custom_scripts.pick_list.pick_list.create_pick_list",
	"frappe.utils.print_format.download_pdf": "metactical.print_format.download_pdf",
	"erpnext.controllers.accounts_controller.update_child_qty_rate": "metactical.custom_scripts.sales_order_item.sales_order_item.update_child_qty_rate",
	"erpnext.stock.doctype.pick_list.pick_list.create_delivery_note": "metactical.custom_scripts.pick_list.pick_list.create_delivery_note",
	"erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry": "metactical.custom_scripts.payment_entry.payment_entry.get_payment_entry"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
#override_doctype_dashboards = {
 	#"Task": "metactical.task.get_dashboard_data"
#}

#Fixtures
fixtures = ["Custom Field", "Property Setter"]

#For using in print format
jenv = {
	"methods": [
		"get_po_items:metactical.custom_scripts.purchase_order.purchase_order.get_po_items",
		"get_pr_items:metactical.custom_scripts.purchase_receipt.purchase_receipt.get_pr_items",
		"get_barcode:metactical.barcode_generator.get_barcode",
		"si_mode_of_payment:metactical.custom_scripts.sales_invoice.sales_invoice.si_mode_of_payment"
	]
}


