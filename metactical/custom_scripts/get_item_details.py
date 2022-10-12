
import json

import frappe
from frappe import _, throw
from frappe.model.meta import get_field_precision
from frappe.utils import add_days, add_months, cint, cstr, flt, getdate
from six import iteritems, string_types

from erpnext import get_company_currency
from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
	get_pricing_rule_for_item,
	set_transaction_type,
)
from erpnext.setup.doctype.brand.brand import get_brand_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from erpnext.setup.utils import get_exchange_rate
from erpnext.stock.doctype.batch.batch import get_batch_no
from erpnext.stock.doctype.item.item import get_item_defaults, get_uom_conv_factor
from erpnext.stock.doctype.item_manufacturer.item_manufacturer import get_item_manufacturer_part_no
from erpnext.stock.doctype.price_list.price_list import get_price_list_details

sales_doctypes = ["Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice"]
purchase_doctypes = [
	"Material Request",
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
]
from erpnext.stock.get_item_details import update_stock, set_valuation_rate, process_args, process_string_args, \
	get_item_code, validate_item_details, get_basic_details, get_item_warehouse, update_barcode_value, get_barcode_data, \
	get_item_tax_info, get_item_tax_template, _get_item_tax_template, is_within_valid_range, get_item_tax_map, calculate_service_end_date, \
	get_default_income_account, get_default_expense_account, get_default_discount_account, get_default_deferred_account, get_default_cost_center, \
	get_default_supplier, get_price_list_rate, insert_item_price, get_item_price, get_price_list_rate_for, check_packing_list, \
	validate_conversion_rate, get_party_item_code, get_pos_profile_item_details, get_pos_profile, get_serial_nos_by_fifo, get_serial_no_batchwise, \
	get_conversion_factor, get_projected_qty, get_company_total_stock, get_serial_no_details, get_bin_details_and_serial_nos, \
	get_batch_qty_and_serial_no, get_batch_qty, apply_price_list, apply_price_list_on_item, get_price_list_currency_and_exchange_rate, \
	get_default_bom, get_valuation_rate, get_gross_profit, get_serial_no, update_party_blanket_order, get_blanket_order_details, \
	get_so_reservation_for_item, get_reserved_qty_for_so
	
@frappe.whitelist()
def get_item_details(args, doc=None, for_validate=False, overwrite_warehouse=True):
	"""
	args = {
	        "item_code": "",
	        "warehouse": None,
	        "customer": "",
	        "conversion_rate": 1.0,
	        "selling_price_list": None,
	        "price_list_currency": None,
	        "plc_conversion_rate": 1.0,
	        "doctype": "",
	        "name": "",
	        "supplier": None,
	        "transaction_date": None,
	        "conversion_rate": 1.0,
	        "buying_price_list": None,
	        "is_subcontracted": "Yes" / "No",
	        "ignore_pricing_rule": 0/1
	        "project": ""
	        "set_warehouse": ""
	}
	"""

	args = process_args(args)
	for_validate = process_string_args(for_validate)
	overwrite_warehouse = process_string_args(overwrite_warehouse)
	item = frappe.get_cached_doc("Item", args.item_code)
	validate_item_details(args, item)

	out = get_basic_details(args, item, overwrite_warehouse)

	if isinstance(doc, string_types):
		doc = json.loads(doc)

	if doc and doc.get("doctype") == "Purchase Invoice":
		args["bill_date"] = doc.get("bill_date")

	if doc:
		args["posting_date"] = doc.get("posting_date")
		args["transaction_date"] = doc.get("transaction_date")

	get_item_tax_template(args, item, out)
	out["item_tax_rate"] = get_item_tax_map(
		args.company,
		args.get("item_tax_template")
		if out.get("item_tax_template") is None
		else out.get("item_tax_template"),
		as_json=True,
	)

	get_party_item_code(args, item, out)

	set_valuation_rate(out, args)

	update_party_blanket_order(args, out)

	out.update(get_price_list_rate(args, item))

	if args.customer and cint(args.is_pos):
		out.update(get_pos_profile_item_details(args.company, args, update_data=True))

	if (
		args.get("doctype") == "Material Request"
		and args.get("material_request_type") == "Material Transfer"
	):
		out.update(get_bin_details(args.item_code, args.get("from_warehouse")))

	elif out.get("warehouse"):
		if doc and doc.get("doctype") == "Purchase Order":
			# calculate company_total_stock only for po
			bin_details = get_bin_details(args.item_code, out.warehouse, args.company)
		else:
			bin_details = get_bin_details(args.item_code, out.warehouse)

		out.update(bin_details)

	# update args with out, if key or value not exists
	for key, value in iteritems(out):
		if args.get(key) is None:
			args[key] = value

	data = get_pricing_rule_for_item(args, out.price_list_rate, doc, for_validate=for_validate)

	out.update(data)

	update_stock(args, out)

	if args.transaction_date and item.lead_time_days:
		out.schedule_date = out.lead_time_date = add_days(args.transaction_date, item.lead_time_days)

	if args.get("is_subcontracted") == "Yes":
		out.bom = args.get("bom") or get_default_bom(args.item_code)

	get_gross_profit(out)
	if args.doctype == "Material Request":
		out.rate = args.rate or out.price_list_rate
		out.amount = flt(args.qty) * flt(out.rate)

	return out
	
def get_basic_details(args, item, overwrite_warehouse=True):
	"""
	:param args: {
	                "item_code": "",
	                "warehouse": None,
	                "customer": "",
	                "conversion_rate": 1.0,
	                "selling_price_list": None,
	                "price_list_currency": None,
	                "price_list_uom_dependant": None,
	                "plc_conversion_rate": 1.0,
	                "doctype": "",
	                "name": "",
	                "supplier": None,
	                "transaction_date": None,
	                "conversion_rate": 1.0,
	                "buying_price_list": None,
	                "is_subcontracted": "Yes" / "No",
	                "ignore_pricing_rule": 0/1
	                "project": "",
	                barcode: "",
	                serial_no: "",
	                currency: "",
	                update_stock: "",
	                price_list: "",
	                company: "",
	                order_type: "",
	                is_pos: "",
	                project: "",
	                qty: "",
	                stock_qty: "",
	                conversion_factor: "",
	                against_blanket_order: 0/1
	        }
	:param item: `item_code` of Item object
	:return: frappe._dict
	"""

	if not item:
		item = frappe.get_doc("Item", args.get("item_code"))

	if item.variant_of:
		item.update_template_tables()

	item_defaults = get_item_defaults(item.name, args.company)
	item_group_defaults = get_item_group_defaults(item.name, args.company)
	brand_defaults = get_brand_defaults(item.name, args.company)

	defaults = frappe._dict(
		{
			"item_defaults": item_defaults,
			"item_group_defaults": item_group_defaults,
			"brand_defaults": brand_defaults,
		}
	)

	warehouse = get_item_warehouse(item, args, overwrite_warehouse, defaults)

	if args.get("doctype") == "Material Request" and not args.get("material_request_type"):
		args["material_request_type"] = frappe.db.get_value(
			"Material Request", args.get("name"), "material_request_type", cache=True
		)

	expense_account = None

	if args.get("doctype") == "Purchase Invoice" and item.is_fixed_asset:
		from erpnext.assets.doctype.asset_category.asset_category import get_asset_category_account

		expense_account = get_asset_category_account(
			fieldname="fixed_asset_account", item=args.item_code, company=args.company
		)

	# Set the UOM to the Default Sales UOM or Default Purchase UOM if configured in the Item Master
	if not args.get("uom"):
		if args.get("doctype") in sales_doctypes:
			args.uom = item.sales_uom if item.sales_uom else item.stock_uom
		elif (args.get("doctype") in ["Purchase Order", "Purchase Receipt", "Purchase Invoice"]) or (
			args.get("doctype") == "Material Request" and args.get("material_request_type") == "Purchase"
		):
			args.uom = item.purchase_uom if item.purchase_uom else item.stock_uom
		else:
			args.uom = item.stock_uom

	if args.get("batch_no") and item.name != frappe.get_cached_value(
		"Batch", args.get("batch_no"), "item"
	):
		args["batch_no"] = ""

	out = frappe._dict(
		{
			"item_code": item.name,
			"item_name": item.item_name,
			"description": cstr(item.description).strip(),
			"image": cstr(item.image).strip(),
			"warehouse": warehouse,
			"income_account": get_default_income_account(
				args, item_defaults, item_group_defaults, brand_defaults
			),
			"expense_account": expense_account
			or get_default_expense_account(args, item_defaults, item_group_defaults, brand_defaults),
			"discount_account": get_default_discount_account(args, item_defaults),
			"cost_center": get_default_cost_center(
				args, item_defaults, item_group_defaults, brand_defaults
			),
			"has_serial_no": item.has_serial_no,
			"has_batch_no": item.has_batch_no,
			"batch_no": args.get("batch_no"),
			"uom": args.uom,
			"min_order_qty": flt(item.min_order_qty) if args.doctype == "Material Request" else "",
			"qty": flt(args.qty) or 1.0,
			"stock_qty": flt(args.qty) or 1.0,
			"price_list_rate": 0.0,
			"base_price_list_rate": 0.0,
			"rate": 0.0,
			"base_rate": 0.0,
			"amount": 0.0,
			"base_amount": 0.0,
			"net_rate": 0.0,
			"net_amount": 0.0,
			"discount_percentage": 0.0,
			"discount_amount": 0.0,
			"supplier": get_default_supplier(args, item_defaults, item_group_defaults, brand_defaults),
			"update_stock": args.get("update_stock")
			if args.get("doctype") in ["Sales Invoice", "Purchase Invoice"]
			else 0,
			"delivered_by_supplier": item.delivered_by_supplier
			if args.get("doctype") in ["Sales Order", "Sales Invoice"]
			else 0,
			"is_fixed_asset": item.is_fixed_asset,
			"last_purchase_rate": item.last_purchase_rate
			if args.get("doctype") in ["Purchase Order"]
			else 0,
			"transaction_date": args.get("transaction_date"),
			"against_blanket_order": args.get("against_blanket_order"),
			"bom_no": item.get("default_bom"),
			"weight_per_unit": args.get("weight_per_unit") or item.get("weight_per_unit"),
			"weight_uom": args.get("weight_uom") or item.get("weight_uom"),
			"grant_commission": item.get("grant_commission"),
		}
	)

	if item.get("enable_deferred_revenue") or item.get("enable_deferred_expense"):
		out.update(calculate_service_end_date(args, item))

	# calculate conversion factor
	if item.stock_uom == args.uom:
		out.conversion_factor = 1.0
	else:
		out.conversion_factor = args.conversion_factor or get_conversion_factor(item.name, args.uom).get(
			"conversion_factor"
		)

	args.conversion_factor = out.conversion_factor
	out.stock_qty = out.qty * out.conversion_factor
	args.stock_qty = out.stock_qty

	# calculate last purchase rate
	if args.get("doctype") in purchase_doctypes:
		from erpnext.buying.doctype.purchase_order.purchase_order import item_last_purchase_rate

		out.last_purchase_rate = item_last_purchase_rate(
			args.name, args.conversion_rate, item.name, out.conversion_factor
		)

	# if default specified in item is for another company, fetch from company
	for d in [
		["Account", "income_account", "default_income_account"],
		["Account", "expense_account", "default_expense_account"],
		["Cost Center", "cost_center", "cost_center"],
		["Warehouse", "warehouse", ""],
	]:
		if not out[d[1]]:
			out[d[1]] = frappe.get_cached_value("Company", args.company, d[2]) if d[2] else None

	for fieldname in ("item_name", "item_group", "brand", "stock_uom"):
		out[fieldname] = item.get(fieldname)

	if args.get("manufacturer"):
		part_no = get_item_manufacturer_part_no(args.get("item_code"), args.get("manufacturer"))
		if part_no:
			out["manufacturer_part_no"] = part_no
		else:
			out["manufacturer_part_no"] = None
			out["manufacturer"] = None
	else:
		data = frappe.get_value(
			"Item", item.name, ["default_item_manufacturer", "default_manufacturer_part_no"], as_dict=1
		)

		if data:
			out.update(
				{
					"manufacturer": data.default_item_manufacturer,
					"manufacturer_part_no": data.default_manufacturer_part_no,
				}
			)

	child_doctype = args.doctype + " Item"
	meta = frappe.get_meta(child_doctype)
	if meta.get_field("barcode"):
		update_barcode_value(out)

	if out.get("weight_per_unit"):
		out["total_weight"] = out.weight_per_unit * out.stock_qty

	return out

def update_barcode_value(out):
	barcode_data = get_barcode_data([out])

	# If item has one barcode then update the value of the barcode field
	if barcode_data and len(barcode_data.get(out.item_code)) > 0:
		out["barcode"] = barcode_data.get(out.item_code)[0]
		
@frappe.whitelist()
def get_bin_details(item_code, warehouse, company=None):
	bin_details = frappe.db.get_value(
		"Bin",
		{"item_code": item_code, "warehouse": warehouse},
		["projected_qty", "actual_qty", "reserved_qty"],
		as_dict=True,
		cache=True,
	) or {"projected_qty": 0, "actual_qty": 0, "reserved_qty": 0}
	bin_details['sal_reserved_qty'] = bin_details['reserved_qty']
	if company:
		bin_details["company_total_stock"] = get_company_total_stock(item_code, company)
	return bin_details
