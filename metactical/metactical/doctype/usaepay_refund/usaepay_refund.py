# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from metactical.custom_scripts.payment_entry.payment_entry import make_refund, void_payment

class USAePayRefund(Document):
	def on_submit(self):
		if self.status and self.status == "Pending":
			make_refund(self.name, self.payment_entry)
  
@frappe.whitelist()
def void_useapay_payment(refund_name):
	try:
		refund_doc = frappe.get_doc("USAePay Refund", refund_name)
		if refund_doc.status == "Refunded":
			frappe.throw("This refund has already been processed.")
	
	
		original_usaepay_transaction_key = frappe.db.get_value("Sales Order", refund_doc.sales_order, "neb_usaepay_transaction_key")
		if not original_usaepay_transaction_key:
			frappe.throw("No USAePay transaction key found for the associated Sales Order.")
	 
		payment_entry = frappe.get_doc("Payment Entry", {"reference_no": original_usaepay_transaction_key})
		if payment_entry and payment_entry.paid_amount != refund_doc.amount_to_refund:
			frappe.throw("The refund amount does not match the original payment amount. Please void the original payment from it's Payment Entry")
   
		if not payment_entry:
			frappe.throw("No Payment Entry found for the associated USAePay transaction key.")
	
		void_payment(payment_entry.name)
		create_comment(payment_entry, refund_doc)
  
		refund_doc.status = "Voided"
		refund_doc.save(ignore_permissions=True)
		refund_doc.submit()

		frappe.response["message"] = "Payment voided successfully."
		frappe.response["status"] = "success"
	except Exception as e:
		frappe.log_error(title="Error voiding USAePay payment", message=frappe.get_traceback())
		frappe.response["message"] = f"Error voiding payment: {str(e)}"
		frappe.response["status"] = "error"
  
  
def create_comment(payment_entry, refund_doc):
    
	comment_content = f"Payment voided due to refund request: {refund_doc.name}. Refund amount: {payment_entry.paid_amount}."
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Comment",
		"reference_doctype": "Payment Entry",
		"reference_name": payment_entry.name,
		"content": comment_content
	}).insert(ignore_permissions=True)