# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as _app_version
import metactical

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
doctype_js = {"Sales Order" : ["public/pick_list.js"]}
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

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
		"before_save": "metactical.pick_list.custom_on_save",
		"validate": "metactical.pick_list.custom_on_save"
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"metactical.tasks.all"
# 	],
# 	"daily": [
# 		"metactical.tasks.daily"
# 	],
# 	"hourly": [
# 		"metactical.tasks.hourly"
# 	],
# 	"weekly": [
# 		"metactical.tasks.weekly"
# 	]
# 	"monthly": [
# 		"metactical.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "metactical.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.selling.doctype.sales_order.sales_order.create_pick_list": "metactical.pick_list.create_pick_list",
	"frappe.utils.print_format.download_pdf": "metactical.print_format.download_pdf"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "metactical.task.get_dashboard_data"
# }


