import frappe
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime, cint
from frappe import _, msgprint, is_whitelisted
from metactical.custom_scripts.utils.metactical_utils import queue_action, post_to_rocket_chat
from frappe.model.docstatus import DocStatus

class CustomPurchaseReceipt(PurchaseReceipt):
	def validate(self):
		super(CustomPurchaseReceipt, self).validate()
		if self.purchase_order:
			for d in self.items:
				d.purchase_order = self.purchase_order

		self.validate_barcodes()
		self.validate_accepted_warehouse_permission()

	def validate_accepted_warehouse_permission(self):
		# Metactical Customization: Validate that user has permission to use the accepted warehouse
		user = frappe.session.user
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			settings = frappe.get_doc("Warehouse User Permissions", setting_exists)
			permitted_warehouses = [row.warehouse for row in settings.purchase_receipt_accepted_warehouse]

			if permitted_warehouses:
				if self.set_warehouse and self.set_warehouse not in permitted_warehouses:
					frappe.throw("Warehouse {} not in list of warehouse allowed for user {}".format(self.set_warehouse, user))

				for row in self.items:
					# Metactical Customization: Purchase Receipt Item's "Accepted Warehouse"
					# field's actual fieldname is "warehouse" (label is "Accepted Warehouse")
					if row.warehouse and row.warehouse not in permitted_warehouses:
						frappe.throw("Warehouse {} not in list of warehouse allowed for user {}".format(row.warehouse, user))

	def validate_barcodes(self):
		for item in self.items:
			if not item.barcode:
				barcode = frappe.db.get_value("Item Barcode", {"parent": item.item_code}, "barcode")
				if barcode:	
					item.barcode = barcode
     
	def save(self):
		if self.docstatus == DocStatus.submitted() and len(self.items) > 100 and \
			self.ais_queue_status and self.ais_queue_status != "Queued":
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is \
					any issue on processing in background, the system will add a comment \
					about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=2000)
		else:
			super().save()

	def before_submit(self):
		self.barcode_check()

	def barcode_check(self):
		for item in self.items:
			barcode_exists = frappe.db.exists("Item Barcode", {"parent": item.item_code})
			if not barcode_exists:
				frappe.throw(f"Error: Please add a barcode for item {item.item_code}")

	def on_submit(self):
		super(CustomPurchaseReceipt, self).on_submit()
		post_rc_message(self)
		
def post_rc_message(doc):
	if not doc.is_return and doc.company == "International Camouflage Ltd":
		active_warehouse = "W01-WHS-Active Stock - ICL"
		po = frappe.get_doc("Purchase Order", doc.purchase_order)

		# Some POs don't have set_warehouse set on the header, so fall back to
		# checking each item's Target Warehouse.
		is_active = po.set_warehouse == active_warehouse
		if not po.set_warehouse:
			is_active = any(item.warehouse == active_warehouse for item in po.items)

		if is_active:
			frappe.enqueue(
				send_pdf_to_rocket_chat,
				name=doc.name
			)

def validate(self, method):
	if self.set_warehouse:
		for item in self.items:
			if item.warehouse != self.set_warehouse:
				item.warehouse = self.set_warehouse
			
@frappe.whitelist()
def get_accepted_warehouse(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Warehouse User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabUser Permitted Warehouse`
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='purchase_receipt_accepted_warehouse'""",
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})

		if not setting_exists or not warehouses:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses

@frappe.whitelist()
def get_pr_items(docname):
	items = []
	added_items = []
	doc = frappe.get_doc('Purchase Receipt', docname)
	for item in doc.items:
		if item.item_code not in added_items:
			items.append(item)
			added_items.append(item.item_code)
		else:
			for i in items:
				if i.item_code == item.item_code:
					i.update({
						'qty': i.qty + item.qty
					})
	return items


@frappe.whitelist()
def get_print_format(docname):
	doc = frappe.get_doc('Purchase Receipt', docname)
	return frappe.get_print(doctype=doc.doctype, name=doc.name, print_format="Purchase Receipt Barcode - V2", no_letterhead=0)


@frappe.whitelist()
def send_pdf_to_rocket_chat(name):
    try:
        doc = frappe.get_doc("Purchase Receipt", name)

        html = frappe.get_print(
            "Purchase Receipt",
            name,
            print_format="PR Report V5",
            no_letterhead=0,
        )
        pdf_content = frappe.utils.pdf.get_pdf(html)

        supplier = frappe.get_doc("Supplier", doc.supplier)
        po = doc.purchase_order
        if supplier.country == "China":
            filename = f"China PO-{po}.pdf"
        else:
            filename = f"{supplier.name} PO-{po}.pdf"

        post_to_rocket_chat(
            doc=doc,
            msg=None,
            attachment=pdf_content,
            filename=filename,
        )
    except Exception:
        frappe.log_error(
            title="Rocket Chat PDF Upload Failed",
            message=frappe.get_traceback(),
        )