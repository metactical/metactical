import frappe
from frappe import _, msgprint, qb, throw
import barcode as _barcode
from io import BytesIO
from frappe.utils import now, flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.selling_controller import SellingController
from erpnext.controllers.stock_controller import StockController
from erpnext.controllers.accounts_controller import AccountsController
from metactical.custom_scripts.utils.metactical_utils import queue_action, check_si_payment_status_for_so
from erpnext.accounts.utils import convert_to_list
from frappe.model.docstatus import DocStatus

class CustomSalesInvoice(SalesInvoice, SellingController, StockController, AccountsController):
	def save(self):
		if self.docstatus == DocStatus.submitted() and len(self.items) > 25 and \
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

	def on_cancel(self):
		# Metactical Customization: Relink payment entries to sales orders when sales invoice is cancelled
		if self.doctype in ["Sales Invoice", "Purchase Invoice"]:
			if frappe.db.get_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice"):
				unlink_ref_doc_from_payment_entries(self)

			elif self.doctype in ["Sales Order", "Purchase Order"]:
				if frappe.db.get_single_value(
					"Accounts Settings", "unlink_advance_payment_on_cancelation_of_order"
				):
					unlink_ref_doc_from_payment_entries(self)

				if self.doctype == "Sales Order":
					self.unlink_ref_doc_from_po()

		# Metactical Customization: prevent cancellation of sales invoice if there are any linked coupon codes
		coupon_codes = frappe.db.get_all("Coupon Code", filters={"custom_sales_invoice": self.name}, fields=["name"])
		if len(coupon_codes) > 0:
			frappe.throw(_("Cannot cancel this invoice as it has linked coupon codes."))
  
		super(CustomSalesInvoice, self).on_cancel()
		
	def before_save(self):
		super(CustomSalesInvoice, self).before_save()
		#Metactical Customization: Add barcode to Sales Invoice
		rv = BytesIO()
		_barcode.get('code128', self.name).write(rv)
		bstring = rv.getvalue()
		self.ais_barcode = bstring.decode('ISO-8859-1')

	def calculate_taxes_and_totals(self):
		from metactical.custom_scripts.controllers.taxes_and_totals import custom_calculate_taxes_and_totals
		custom_calculate_taxes_and_totals(self)

		if self.doctype in (
			"Sales Order",
			"Delivery Note",
			"Sales Invoice",
			"POS Invoice",
		):
			self.calculate_commission()
			self.calculate_contribution()

	def set_status(self, update=False, status=None, update_modified=True):
		super(CustomSalesInvoice, self).set_status(update, status, update_modified)
		
		# Metactical Customization: Added
		if self.status == "Paid" and not self.neb_payment_completed_at:
			self.db_set("neb_payment_completed_at", frappe.utils.getdate(now()), notify=True)
			
			# Metactical Customization: Check if all invoices for the sales order are paid and update sales order
			sales_orders = []
			for row in self.items:
				if row.sales_order and row.sales_order not in sales_orders:
					sales_orders.append(row.sales_order)
			
			for sales_order in sales_orders:
				billing_status = frappe.db.get_value("Sales Order", sales_order, "billing_status")
				if billing_status == "Fully Billed":
					all_invoices_paid = check_si_payment_status_for_so(sales_order)
					if all_invoices_paid:
						frappe.db.set_value("Sales Order", sales_order, "neb_payment_completed_at", frappe.utils.getdate(now()), update_modified=True)
		elif self.status != "Paid" and self.neb_payment_completed_at:
			self.db_set("neb_payment_completed_at", None, notify=True)
   
	def create_offset_journal_entry(self):
		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Journal Entry"
		journal_entry.posting_date = frappe.utils.getdate(now())
		journal_entry.company = self.company
  
		journal_entry.append("accounts", {
			"reference_type": "Sales Invoice",
			"reference_name": self.name,
			"account": self.debit_to,
			"party_type": "Customer",
			"party": self.customer,
			"credit_in_account_currency": self.outstanding_amount
		})
  
		journal_entry.append("accounts", {
			"account": frappe.db.get_value("Account", {"account_name": "Write Off", "company": self.company}, "name"),
			"debit_in_account_currency": self.outstanding_amount
		})

		journal_entry.set_missing_values()
		journal_entry.save()
		journal_entry.submit()
  
def unlink_ref_doc_from_payment_entries(ref_doc):	
	#Check for sales order
	multiple_orders = False
	items = ref_doc.get('items')
	sales_order = items[0].get('sales_order')
	for row in items:
		if row.get('sales_order') is None or row.get('sales_order') != sales_order:
			multiple_orders = True
			break
		
	
	remove_ref_doc_link_from_jv(ref_doc.doctype, ref_doc.name, multiple_orders, ref_doc.items[0].sales_order)
	remove_ref_doc_link_from_pe(ref_doc.doctype, ref_doc.name, None, multiple_orders, ref_doc.items[0].sales_order)

	if multiple_orders == False:
		frappe.db.sql("""update `tabGL Entry`
			set against_voucher_type='Sales Order', against_voucher=%s,
			modified=%s, modified_by=%s
			where against_voucher_type=%s and against_voucher=%s
			and voucher_no != ifnull(against_voucher, '')""",
			(ref_doc.items[0].sales_order, now(), frappe.session.user, ref_doc.doctype, ref_doc.name))
	else:
		frappe.db.sql("""update `tabGL Entry`
			set against_voucher_type=null, against_voucher=null,
			modified=%s, modified_by=%s
			where against_voucher_type=%s and against_voucher=%s
			and voucher_no != ifnull(against_voucher, '')""",
			(now(), frappe.session.user, ref_doc.doctype, ref_doc.name))

	if ref_doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		ref_doc.set("advances", [])

		frappe.db.sql(
			"""delete from `tab{0} Advance` where parent = %s""".format(ref_doc.doctype), ref_doc.name
		)

def remove_ref_doc_link_from_jv(ref_type, ref_no, multiple_orders, sales_order=None):
	linked_jv = frappe.db.sql_list("""select parent from `tabJournal Entry Account`
		where reference_type=%s and reference_name=%s and docstatus < 2""", (ref_type, ref_no))

	if linked_jv:
		frappe.db.sql("""update `tabJournal Entry Account`
			set reference_type=null, reference_name = null,
			modified=%s, modified_by=%s
			where reference_type=%s and reference_name=%s
			and docstatus < 2""", (now(), frappe.session.user, ref_type, ref_no))

		frappe.msgprint(_("Journal Entries {0} are un-linked".format("\n".join(linked_jv))))

def remove_ref_doc_link_from_pe(
	ref_type: str | None = None, ref_no: str | None = None, payment_name: str | None = None, multiple_orders=True, sales_order=None
):
	per = qb.DocType("Payment Entry Reference")
	pay = qb.DocType("Payment Entry")

	linked_pe = (
		qb.from_(per)
		.select(per.parent)
		.where((per.reference_doctype == ref_type) & (per.reference_name == ref_no) & (per.docstatus.lt(2)))
		.run(as_list=1)
	)
	linked_pe = convert_to_list(linked_pe)
	# remove reference only from specified payment
	linked_pe = [x for x in linked_pe if x == payment_name] if payment_name else linked_pe

	if linked_pe:
		# Metactical Customization: Relink sales invoices to sales orders
		if not multiple_orders and sales_order is not None:
			update_query = (
				qb.update(per)
				.set(per.reference_doctype, 'Sales Order')
				.set(per.reference_name, sales_order)
				.set(per.modified, now())
				.set(per.modified_by, frappe.session.user)
				.where(per.docstatus.lt(2) & (per.reference_doctype == ref_type) & (per.reference_name == ref_no))
			)

			if payment_name:
				update_query = update_query.where(per.parent == payment_name)

			update_query.run()
		else:
			update_query = (
				qb.update(per)
				.set(per.allocated_amount, 0)
				.set(per.modified, now())
				.set(per.modified_by, frappe.session.user)
				.where(per.docstatus.lt(2) & (per.reference_doctype == ref_type) & (per.reference_name == ref_no))
			)

			if payment_name:
				update_query = update_query.where(per.parent == payment_name)

			update_query.run()

		for pe in linked_pe:
			try:
				pe_doc = frappe.get_doc("Payment Entry", pe)
				pe_doc.set_amounts()
				pe_doc.clear_unallocated_reference_document_rows()
				pe_doc.validate_payment_type_with_outstanding()
			except Exception:
				msg = _("There were issues unlinking payment entry {0}.").format(pe_doc.name)
				msg += "<br>"
				msg += _("Please cancel payment entry manually first")
				frappe.throw(msg, exc=PaymentEntryUnlinkError, title=_("Payment Unlink Error"))

			qb.update(pay).set(pay.total_allocated_amount, pe_doc.total_allocated_amount).set(
				pay.base_total_allocated_amount, pe_doc.base_total_allocated_amount
			).set(pay.unallocated_amount, pe_doc.unallocated_amount).set(pay.modified, now()).set(
				pay.modified_by, frappe.session.user
			).where(pay.name == pe).run()

		frappe.msgprint(_("Payment Entries {0} are un-linked").format("\n".join(linked_pe)))

@frappe.whitelist()
def create_journal_entry(source_name, bank_cash, amount, purpose, target_doc=None):
	def update_accounts(source_doc, target_doc):
		amount_after_tax = float(amount)
		target_doc.accounts = []
		if purpose == "Create Credit Note and Refund Customer":
			#Add taxes and charges
			for row in source_doc.taxes:
				tax_amount = (float(amount) * float(row.rate))/100
				amount_after_tax = amount_after_tax - tax_amount
				account = frappe.new_doc('Journal Entry Account')
				account.update({
					"account": row.account_head,
					"cost_center": source_doc.items[0].cost_center,
					"project": source_doc.items[0].project,
					"debit_in_account_currency": tax_amount
				})
				target_doc.append("accounts", account)
				
			#For the simplest implementation, we assume all items on the invoice share the same income account
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.items[0].income_account,
				"cost_center": source_doc.items[0].cost_center,
				"project": source_doc.items[0].project,
				"debit_in_account_currency": amount_after_tax
			})
			target_doc.append("accounts", account)
			
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.debit_to,
				"reference_type": "Sales Invoice",
				"party_type": "Customer",
				"party": source_doc.customer,
				"reference_name": source_name,
				"credit_in_account_currency": amount
			})
			target_doc.append("accounts", account)
			
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.debit_to,
				"reference_type": "Sales Invoice",
				"party_type": "Customer",
				"party": source_doc.customer,
				"reference_name": source_name,
				"debit_in_account_currency": amount
			})
			target_doc.append("accounts", account)
		else:
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.debit_to,
				"debit_in_account_currency": amount,
				"party_type": "Customer",
				"party": source_doc.customer,
			})
			target_doc.append("accounts", account)
			
			#If Sales Order entered, then assume advance payment made against Sales Order
			if source_doc.items[0].sales_order:
				target_doc.update({
					"ais_sales_order": source_doc.items[0].sales_order
				})
	
		#For all purposes, add bank/cash account
		account = frappe.new_doc('Journal Entry Account')
		account.update({
			"account": bank_cash,
			"credit_in_account_currency": amount
		})
		target_doc.append("accounts", account)

	target_doc = frappe.new_doc('Journal Entry')
	target_doc.update({
		"voucher_type": "Credit Note"
	})
	source_doc = frappe.get_doc('Sales Invoice', source_name)
	update_accounts(source_doc, target_doc)
	return target_doc

# Metactical Customization: Get mode of payment for the print format		
@frappe.whitelist()
def si_mode_of_payment(name):
	payment_mode = ''
	mode = frappe.db.sql("""SELECT
								pe.mode_of_payment
							FROM
								`tabPayment Entry Reference` per
							LEFT JOIN
								`tabPayment Entry` pe ON pe.name = per.parent
							WHERE
								per.reference_doctype = 'Sales Invoice' AND per.reference_name = %(name)s
								AND pe.docstatus = 1""", {'name': name}, as_dict=1)
	if len(mode) > 0:
		payment_mode = mode[0].mode_of_payment
	return payment_mode

@frappe.whitelist()
def submit_invoice(doc):
	# Metactical Customization: Submit invoice in background if more than 10 items
	doc = frappe.get_doc("Sales Invoice", doc)
	if len(doc.items) > 25:
		msgprint(
			_(
				"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this document and revert to the Draft stage"
			)
		)
		queue_action(doc, "submit", timeout=2000)
	else:
		doc._submit()

@frappe.whitelist()
def make_sales_return(source_name, target_doc=None):

	return make_return_doc("Sales Invoice", source_name, target_doc)

# Metactical Customization: Clear advances table when creating a return sales invoice
def make_return_doc(doctype: str, source_name: str, target_doc=None, return_against_rejected_qty=False):
	from frappe.model.mapper import get_mapped_doc
	from erpnext.controllers.sales_and_purchase_return import get_returned_qty_map_for_row

	company = frappe.db.get_value(doctype, source_name, "company")
	default_warehouse_for_sales_return = frappe.get_cached_value(
		"Company", company, "default_warehouse_for_sales_return"
	)

	if doctype == "Sales Invoice":
		inv_is_consolidated, inv_is_pos = frappe.db.get_value(
			"Sales Invoice", source_name, ["is_consolidated", "is_pos"]
		)
		if inv_is_consolidated and inv_is_pos:
			frappe.throw(
				_("Cannot create return for consolidated invoice {0}.").format(source_name),
				title=_("Cannot Create Return"),
			)

	def set_missing_values(source, target):
		doc = frappe.get_doc(target)
		doc.is_return = 1
		doc.ignore_pricing_rule = 1
		doc.pricing_rules = []
		doc.return_against = source.name
		doc.set_warehouse = ""
		doc.advances = []
		if doctype == "Sales Invoice" or doctype == "POS Invoice":
			doc.advances = []
			doc.is_pos = source.is_pos

			# look for Print Heading "Credit Note"
			if not doc.select_print_heading:
				doc.select_print_heading = frappe.get_cached_value("Print Heading", _("Credit Note"))

		elif doctype == "Purchase Invoice":
			# look for Print Heading "Debit Note"
			doc.select_print_heading = frappe.get_cached_value("Print Heading", _("Debit Note"))
			if source.tax_withholding_category:
				doc.set_onload("supplier_tds", source.tax_withholding_category)
		elif doctype == "Delivery Note":
			# manual additions to the return should hit the return warehous, too
			doc.set_warehouse = default_warehouse_for_sales_return

		for tax in doc.get("taxes") or []:
			if tax.charge_type == "Actual":
				tax.tax_amount = -1 * tax.tax_amount

		if doc.get("is_return"):
			if doc.doctype == "Sales Invoice" or doc.doctype == "POS Invoice":
				doc.consolidated_invoice = ""
				# no copy enabled for party_account_currency
				doc.party_account_currency = source.party_account_currency
				doc.set("payments", [])
				doc.update_billed_amount_in_delivery_note = True
				for data in source.payments:
					paid_amount = 0.00
					base_paid_amount = 0.00
					data.base_amount = flt(
						data.amount * source.conversion_rate, source.precision("base_paid_amount")
					)
					paid_amount += data.amount
					base_paid_amount += data.base_amount
					doc.append(
						"payments",
						{
							"mode_of_payment": data.mode_of_payment,
							"type": data.type,
							"amount": -1 * paid_amount,
							"base_amount": -1 * base_paid_amount,
							"account": data.account,
							"default": data.default,
						},
					)

				if doc.is_pos:
					doc.paid_amount = -1 * source.paid_amount
			elif doc.doctype == "Purchase Invoice":
				doc.paid_amount = -1 * source.paid_amount
				doc.base_paid_amount = -1 * source.base_paid_amount
				doc.payment_terms_template = ""
				doc.payment_schedule = []

		if doc.get("is_return") and hasattr(doc, "packed_items"):
			for d in doc.get("packed_items"):
				d.qty = d.qty * -1

		if doc.get("discount_amount"):
			doc.discount_amount = -1 * source.discount_amount

		if doctype == "Subcontracting Receipt":
			doc.set_warehouse = source.set_warehouse
			doc.supplier_warehouse = source.supplier_warehouse
		else:
			doc.run_method("calculate_taxes_and_totals")

	def update_item(source_doc, target_doc, source_parent):
		target_doc.qty = -1 * source_doc.qty
		target_doc.pricing_rules = None
		if doctype in ["Purchase Receipt", "Subcontracting Receipt"]:
			returned_qty_map = get_returned_qty_map_for_row(
				source_parent.name, source_parent.supplier, source_doc.name, doctype
			)

			if doctype == "Subcontracting Receipt":
				target_doc.received_qty = -1 * flt(source_doc.qty)
			else:
				target_doc.received_qty = -1 * flt(
					source_doc.received_qty - (returned_qty_map.get("received_qty") or 0)
				)
				target_doc.rejected_qty = -1 * flt(
					source_doc.rejected_qty - (returned_qty_map.get("rejected_qty") or 0)
				)

			target_doc.qty = -1 * flt(source_doc.qty - (returned_qty_map.get("qty") or 0))

			if hasattr(target_doc, "stock_qty") and not return_against_rejected_qty:
				target_doc.stock_qty = -1 * flt(
					source_doc.stock_qty - (returned_qty_map.get("stock_qty") or 0)
				)
				target_doc.received_stock_qty = -1 * flt(
					source_doc.received_stock_qty - (returned_qty_map.get("received_stock_qty") or 0)
				)

			if doctype == "Subcontracting Receipt":
				target_doc.subcontracting_order = source_doc.subcontracting_order
				target_doc.subcontracting_order_item = source_doc.subcontracting_order_item
				target_doc.rejected_warehouse = source_doc.rejected_warehouse
				target_doc.subcontracting_receipt_item = source_doc.name
				if return_against_rejected_qty:
					target_doc.qty = -1 * flt(source_doc.rejected_qty - (returned_qty_map.get("qty") or 0))
					target_doc.rejected_qty = 0.0
					target_doc.rejected_warehouse = ""
					target_doc.warehouse = source_doc.rejected_warehouse
					target_doc.received_qty = target_doc.qty
					target_doc.return_qty_from_rejected_warehouse = 1
			else:
				target_doc.purchase_order = source_doc.purchase_order
				target_doc.purchase_order_item = source_doc.purchase_order_item
				target_doc.rejected_warehouse = source_doc.rejected_warehouse
				target_doc.purchase_receipt_item = source_doc.name

			if doctype == "Purchase Receipt" and return_against_rejected_qty:
				target_doc.qty = -1 * flt(source_doc.rejected_qty - (returned_qty_map.get("qty") or 0))
				target_doc.rejected_qty = 0.0
				target_doc.rejected_warehouse = ""
				target_doc.warehouse = source_doc.rejected_warehouse
				target_doc.received_qty = target_doc.qty
				target_doc.return_qty_from_rejected_warehouse = 1

		elif doctype == "Purchase Invoice":
			returned_qty_map = get_returned_qty_map_for_row(
				source_parent.name, source_parent.supplier, source_doc.name, doctype
			)
			target_doc.received_qty = -1 * flt(
				source_doc.received_qty - (returned_qty_map.get("received_qty") or 0)
			)
			target_doc.rejected_qty = -1 * flt(
				source_doc.rejected_qty - (returned_qty_map.get("rejected_qty") or 0)
			)
			target_doc.qty = -1 * flt(source_doc.qty - (returned_qty_map.get("qty") or 0))

			target_doc.stock_qty = -1 * flt(source_doc.stock_qty - (returned_qty_map.get("stock_qty") or 0))
			target_doc.purchase_order = source_doc.purchase_order
			target_doc.purchase_receipt = source_doc.purchase_receipt
			target_doc.rejected_warehouse = source_doc.rejected_warehouse
			target_doc.po_detail = source_doc.po_detail
			target_doc.pr_detail = source_doc.pr_detail
			target_doc.purchase_invoice_item = source_doc.name

		elif doctype == "Delivery Note":
			returned_qty_map = get_returned_qty_map_for_row(
				source_parent.name, source_parent.customer, source_doc.name, doctype
			)
			target_doc.qty = -1 * flt(source_doc.qty - (returned_qty_map.get("qty") or 0))
			target_doc.stock_qty = -1 * flt(source_doc.stock_qty - (returned_qty_map.get("stock_qty") or 0))

			target_doc.against_sales_order = source_doc.against_sales_order
			target_doc.against_sales_invoice = source_doc.against_sales_invoice
			target_doc.so_detail = source_doc.so_detail
			target_doc.si_detail = source_doc.si_detail
			target_doc.expense_account = source_doc.expense_account
			target_doc.dn_detail = source_doc.name
			if default_warehouse_for_sales_return:
				target_doc.warehouse = default_warehouse_for_sales_return
		elif doctype == "Sales Invoice" or doctype == "POS Invoice":
			returned_qty_map = get_returned_qty_map_for_row(
				source_parent.name, source_parent.customer, source_doc.name, doctype
			)
			target_doc.qty = -1 * flt(source_doc.qty - (returned_qty_map.get("qty") or 0))
			target_doc.stock_qty = -1 * flt(source_doc.stock_qty - (returned_qty_map.get("stock_qty") or 0))

			target_doc.sales_order = source_doc.sales_order
			target_doc.delivery_note = source_doc.delivery_note
			target_doc.so_detail = source_doc.so_detail
			target_doc.dn_detail = source_doc.dn_detail
			target_doc.expense_account = source_doc.expense_account

			if doctype == "Sales Invoice":
				target_doc.sales_invoice_item = source_doc.name
			else:
				target_doc.pos_invoice_item = source_doc.name

			if default_warehouse_for_sales_return:
				target_doc.warehouse = default_warehouse_for_sales_return

		if not source_doc.use_serial_batch_fields and source_doc.serial_and_batch_bundle:
			target_doc.serial_no = None
			target_doc.batch_no = None

		if (
			(source_doc.serial_no or source_doc.batch_no)
			and not source_doc.serial_and_batch_bundle
			and not source_doc.use_serial_batch_fields
		):
			target_doc.set("use_serial_batch_fields", 1)

		if source_doc.item_code and target_doc.get("use_serial_batch_fields"):
			item_details = frappe.get_cached_value(
				"Item", source_doc.item_code, ["has_batch_no", "has_serial_no"], as_dict=1
			)

			if not item_details.has_batch_no and not item_details.has_serial_no:
				return

			update_non_bundled_serial_nos(source_doc, target_doc, source_parent)

	def update_non_bundled_serial_nos(source_doc, target_doc, source_parent):
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

		if source_doc.serial_no:
			returned_serial_nos = get_returned_non_bundled_serial_nos(source_doc, source_parent)
			serial_nos = list(set(get_serial_nos(source_doc.serial_no)) - set(returned_serial_nos))
			if serial_nos:
				target_doc.serial_no = "\n".join(serial_nos)

		if source_doc.get("rejected_serial_no"):
			returned_serial_nos = get_returned_non_bundled_serial_nos(
				source_doc, source_parent, serial_no_field="rejected_serial_no"
			)
			rejected_serial_nos = list(
				set(get_serial_nos(source_doc.rejected_serial_no)) - set(returned_serial_nos)
			)
			if rejected_serial_nos:
				target_doc.rejected_serial_no = "\n".join(rejected_serial_nos)

	def get_returned_non_bundled_serial_nos(child_doc, parent_doc, serial_no_field="serial_no"):
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

		return_ref_field = frappe.scrub(child_doc.doctype)
		if child_doc.doctype == "Delivery Note Item":
			return_ref_field = "dn_detail"

		serial_nos = []

		fields = [f"`{'tab' + child_doc.doctype}`.`{serial_no_field}`"]

		filters = [
			[parent_doc.doctype, "return_against", "=", parent_doc.name],
			[parent_doc.doctype, "is_return", "=", 1],
			[child_doc.doctype, return_ref_field, "=", child_doc.name],
			[parent_doc.doctype, "docstatus", "=", 1],
		]

		for row in frappe.get_all(parent_doc.doctype, fields=fields, filters=filters):
			serial_nos.extend(get_serial_nos(row.get(serial_no_field)))

		return serial_nos

	def update_terms(source_doc, target_doc, source_parent):
		target_doc.payment_amount = -source_doc.payment_amount

	def item_condition(doc):
		if return_against_rejected_qty:
			return doc.rejected_qty

		return doc.qty

	doclist = get_mapped_doc(
		doctype,
		source_name,
		{
			doctype: {
				"doctype": doctype,
				"validation": {
					"docstatus": ["=", 1],
				},
			},
			doctype + " Item": {
				"doctype": doctype + " Item",
				"field_map": {"serial_no": "serial_no", "batch_no": "batch_no", "bom": "bom"},
				"postprocess": update_item,
				"condition": item_condition,
			},
			"Payment Schedule": {"doctype": "Payment Schedule", "postprocess": update_terms},
		},
		target_doc,
		set_missing_values,
	)

	return doclist