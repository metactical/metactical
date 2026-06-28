# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import flt, getdate


def ensure_list(value):
	if not value:
		return []

	if isinstance(value, (list, tuple, set)):
		return [item for item in value if item]

	return [value]


def get_filter_date_range(value):
	date_range = ensure_list(value)
	if not date_range:
		return None, None

	from_date = date_range[0] if len(date_range) > 0 else None
	to_date = date_range[1] if len(date_range) > 1 else from_date
	return from_date, to_date


def get_item_creation_condition(item_alias, date_range):
	from_date, to_date = get_filter_date_range(date_range)
	conditions = []
	params = []

	if from_date:
		conditions.append(f"DATE({item_alias}.creation) >= %s")
		params.append(from_date)

	if to_date:
		conditions.append(f"DATE({item_alias}.creation) <= %s")
		params.append(to_date)

	if not conditions:
		return "", []

	return f" AND {' AND '.join(conditions)}", params


def sanitize_price_list_fieldname(price_list):
	return price_list.lower().replace("-", "").replace("  ", "_").replace(" ", "_")


def get_profit_margin_fieldname(price_list):
	return f"{sanitize_price_list_fieldname(price_list)}_profit_margin"


def is_supplier_cost_price_list(price_list):
	return (price_list or "").strip().upper().startswith("SUP")


def parse_amount(value):
	if value in (None, "", "N/A"):
		return None

	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def get_usd_to_cad_exchange_rate(transaction_date=None):
	cache = getattr(frappe.flags, "item_price_excel_v2_exchange_rate_cache", None)
	if cache is None:
		cache = {}
		frappe.flags.item_price_excel_v2_exchange_rate_cache = cache

	cache_key = str(getdate(transaction_date)) if transaction_date else "__default__"
	if cache_key not in cache:
		cache[cache_key] = parse_amount(get_exchange_rate("USD", "CAD", transaction_date))

	return cache[cache_key]


def normalize_currency(currency, price_list=None):
	normalized_currency = (currency or "").strip().upper()
	if normalized_currency in {"USD", "CAD"}:
		return normalized_currency

	price_list_name = (price_list or "").upper()
	if "USD" in price_list_name:
		return "USD"
	if "CAD" in price_list_name:
		return "CAD"

	return normalized_currency or None


def convert_amount(amount, from_currency, to_currency, exchange_rate=None):
	numeric_amount = parse_amount(amount)
	from_currency = normalize_currency(from_currency)
	to_currency = normalize_currency(to_currency)
	exchange_rate = parse_amount(exchange_rate)

	if numeric_amount is None or not from_currency or not to_currency:
		return None

	if from_currency == to_currency:
		return numeric_amount

	if exchange_rate in (None, 0):
		return None

	if from_currency == "USD" and to_currency == "CAD":
		return numeric_amount * exchange_rate

	if from_currency == "CAD" and to_currency == "USD":
		return numeric_amount / exchange_rate

	return None


def get_duty_multiplier(duty_rate):
	return 1 + (flt(duty_rate) / 100)


def calculate_current_actual_costs(cost_amount, cost_currency, duty_rate, exchange_rate=None):
	base_cost = parse_amount(cost_amount)
	normalized_currency = normalize_currency(cost_currency)
	exchange_rate = parse_amount(exchange_rate)
	if base_cost is None or not normalized_currency:
		return None, None

	if normalized_currency == "CAD":
		current_actual_cost_cad = base_cost
		current_actual_cost_usd = (
			current_actual_cost_cad / exchange_rate if exchange_rate not in (None, 0) else None
		)
	elif normalized_currency == "USD":
		current_actual_cost_usd = base_cost * get_duty_multiplier(duty_rate)
		current_actual_cost_cad = (
			current_actual_cost_usd * exchange_rate if exchange_rate not in (None, 0) else None
		)
	else:
		return None, None

	return current_actual_cost_usd, current_actual_cost_cad


def calculate_profit_margin(price_rate, price_currency, current_actual_cost_usd, current_actual_cost_cad):
	price_amount = parse_amount(price_rate)
	normalized_currency = normalize_currency(price_currency)

	if price_amount is None or not normalized_currency:
		return None

	if normalized_currency == "USD":
		actual_cost = parse_amount(current_actual_cost_usd)
	elif normalized_currency == "CAD":
		actual_cost = parse_amount(current_actual_cost_cad)
	else:
		return None

	if actual_cost in (None, 0):
		return None

	return ((price_amount - actual_cost) / actual_cost) * 100


def get_displayed_price_lists(price_lists, supplier_price_lists=None, show_cost_column=False):
	supplier_price_lists = ensure_list(supplier_price_lists)
	displayed_price_lists = []

	if not show_cost_column:
		displayed_price_lists.extend(
			[price_list for price_list in supplier_price_lists if not is_supplier_cost_price_list(price_list)]
		)

	for price_list in price_lists:
		if is_supplier_cost_price_list(price_list):
			continue

		if price_list not in displayed_price_lists:
			displayed_price_lists.append(price_list)

	return displayed_price_lists


def select_lowest_cost_entry(price_entries, preferred_supplier=None, exchange_rate=None):
	if not price_entries:
		return None, None, "not_found"

	candidate_entries = price_entries
	if preferred_supplier:
		preferred_entries = [entry for entry in price_entries if entry.get("supplier") == preferred_supplier]
		if preferred_entries:
			candidate_entries = preferred_entries

	lowest_cost = None
	lowest_cost_currency = None
	lowest_comparable_cost = None
	lowest_cost_source = "not_found"

	for entry in candidate_entries:
		price_rate = parse_amount(entry.get("rate"))
		price_currency = normalize_currency(entry.get("currency"), entry.get("price_list"))
		comparable_cost = price_rate
		if price_currency == "USD":
			converted_cost = convert_amount(price_rate, "USD", "CAD", exchange_rate)
			if converted_cost is not None:
				comparable_cost = converted_cost

		if price_rate is None or comparable_cost is None:
			continue

		if lowest_comparable_cost is None or comparable_cost < lowest_comparable_cost:
			lowest_cost = price_rate
			lowest_cost_currency = price_currency
			lowest_comparable_cost = comparable_cost
			lowest_cost_source = f"sup_price_list:{entry.get('price_list')}"
			if entry.get("supplier"):
				lowest_cost_source += f" supplier:{entry.get('supplier')}"

	return lowest_cost, lowest_cost_currency, lowest_cost_source


def get_lowest_supplier_cost(item_code, suppliers=None, transaction_date=None):
	supplier_names = [supplier.get("supplier") for supplier in suppliers or [] if supplier.get("supplier")]
	filters = {
		"item_code": item_code,
		"buying": 1,
		"price_list": ["like", "SUP%"],
	}

	if supplier_names:
		filters["supplier"] = ["in", supplier_names]

	item_prices = frappe.get_all(
		"Item Price",
		filters=filters,
		fields=["price_list_rate", "currency", "price_list", "supplier"],
	)

	if not item_prices and supplier_names:
		filters.pop("supplier", None)
		item_prices = frappe.get_all(
			"Item Price",
			filters=filters,
			fields=["price_list_rate", "currency", "price_list", "supplier"],
		)

	return select_lowest_cost_entry(
		[
			{
				"rate": item_price.get("price_list_rate"),
				"currency": item_price.get("currency"),
				"price_list": item_price.get("price_list"),
				"supplier": item_price.get("supplier"),
			}
			for item_price in item_prices
		],
		exchange_rate=get_usd_to_cad_exchange_rate(transaction_date),
	)


def get_cost_entry_for_row(item, buying_item_prices_dict, costs=None):
	item_code = item.get("item_code")
	precomputed_cost = (costs or {}).get((item.get("parent"), item_code)) or (costs or {}).get(item_code)
	if precomputed_cost:
		return (
			precomputed_cost.get("amount"),
			precomputed_cost.get("currency"),
			precomputed_cost.get("source") or "sales_order_supplier_cost",
		)

	return select_lowest_cost_entry(
		buying_item_prices_dict.get(item_code, []),
		preferred_supplier=item.get("supplier"),
		exchange_rate=get_usd_to_cad_exchange_rate(item.get("transaction_date")),
	)

def execute(filters=None):
	filters = filters or {}
	purchase_orders = ensure_list(filters.get("purchase_order"))
	supplier = filters.get("supplier") or None
	sales_orders = ensure_list(filters.get("sales_order"))
	price_lists = ensure_list(filters.get("price_list"))
	date_item_created = filters.get("date_item_created")
	supplier_price_lists = []
	costs = {}

	if not supplier and not purchase_orders and not sales_orders:
		return [], []

	if supplier:
		supplier_price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")
		if supplier_price_list:
			supplier_price_lists = [supplier_price_list]
			price_lists.extend(supplier_price_lists)

	elif purchase_orders:
		supplier_price_lists = [
			item[0]
			for item in frappe.db.get_values("Purchase Order", {"name": ["in", purchase_orders]}, "buying_price_list")
			if item[0]
		]
		price_lists.extend(supplier_price_lists)
	
	elif sales_orders:
		for so in sales_orders:
			sales_order = frappe.get_doc("Sales Order", so)
			items = sales_order.items
			for item in items:
				suppliers = frappe.get_all(
					"Item Supplier",
					filters={"parent": item.item_code, "parenttype": "Item"},
					fields=["supplier"],
				)

				cost_amount, cost_currency, cost_source = get_lowest_supplier_cost(
					item.item_code,
					suppliers,
					transaction_date=sales_order.transaction_date,
				)
				costs[(so, item.item_code)] = {
					"amount": cost_amount,
					"currency": cost_currency,
					"source": cost_source,
				}

	price_lists = list(dict.fromkeys([price_list for price_list in price_lists if price_list]))
	supplier_price_lists = list(
		dict.fromkeys([price_list for price_list in supplier_price_lists if price_list])
	)

	columns = get_columns(price_lists, supplier_price_lists, sales_orders, purchase_orders)
	data = get_data(
		supplier,
		purchase_orders,
		sales_orders,
		price_lists,
		supplier_price_lists,
		date_item_created,
		costs,
	)
	return columns, data

def get_data(
	supplier,
	purchase_orders,
	sales_orders,
	price_lists,
	supplier_price_lists=None,
	date_item_created=None,
	costs=None,
):
	items_list = []
	items = []
	show_cost_column = bool(sales_orders)
	displayed_price_lists = get_displayed_price_lists(price_lists, supplier_price_lists, show_cost_column)
	item_creation_condition, item_creation_params = get_item_creation_condition("i", date_item_created)

	if supplier:
		items = frappe.db.sql(
			f"""
				SELECT
					isup.parent AS item_code,
					isup.supplier,
					i.variant_of,
					i.ifw_retailskusuffix,
					i.item_name,
					i.ifw_duty_rate,
					isup.supplier_part_no,
					i.item_group,
					i.image,
					i.brand,
					i.creation
				FROM `tabItem Supplier` isup
				JOIN `tabItem` i ON i.name = isup.parent
				WHERE isup.supplier = %s{item_creation_condition}
			""",
			[supplier, *item_creation_params],
			as_dict=True,
		)

		items_list = [item["item_code"] for item in items]
	elif purchase_orders:
		items = frappe.db.sql(
			f"""
				SELECT
					poi.item_code,
					i.variant_of,
					i.ifw_retailskusuffix,
					i.item_name,
					poi.parent,
					p.supplier,
					p.transaction_date,
					i.ifw_duty_rate,
					p.buying_price_list,
					isup.supplier_part_no,
					i.item_group,
					i.image,
					i.brand,
					i.creation
				FROM `tabPurchase Order Item` poi
				JOIN `tabPurchase Order` p ON p.name = poi.parent
				JOIN `tabItem` i ON i.name = poi.item_code
				LEFT JOIN `tabItem Supplier` isup ON isup.parent = i.name AND isup.supplier = p.supplier
				WHERE poi.parent IN %s{item_creation_condition}
			""",
			tuple([tuple(purchase_orders), *item_creation_params]),
			as_dict=True,
		)

		items_list = [item["item_code"] for item in items]

	elif sales_orders:
		items = frappe.db.sql(
			f"""
				SELECT
					soi.item_code,
					i.variant_of,
					i.ifw_retailskusuffix,
					i.item_name,
					soi.parent,
					so.transaction_date,
					i.ifw_duty_rate,
					(
						SELECT isup.supplier_part_no
						FROM `tabItem Supplier` isup
						WHERE isup.parent = i.name
						ORDER BY isup.idx ASC
						LIMIT 1
					) AS supplier_part_no,
					i.item_group,
					i.image,
					i.brand,
					i.creation
				FROM `tabSales Order Item` soi
				JOIN `tabSales Order` so ON so.name = soi.parent
				JOIN `tabItem` i ON i.name = soi.item_code
				WHERE soi.parent IN %s{item_creation_condition}
			""",
			tuple([tuple(sales_orders), *item_creation_params]),
			as_dict=True,
		)

		items_list = [item["item_code"] for item in items]

	if not items_list:
		return []
	
	
	item_prices = []
	if price_lists:
		item_prices = frappe.get_all(
			"Item Price",
			filters={"price_list": ["in", price_lists], "item_code": ["in", list(dict.fromkeys(items_list))]},
			fields=["item_code", "price_list_rate", "price_list", "currency"],
		)

	buying_item_prices = frappe.get_all(
		"Item Price",
		filters={
			"item_code": ["in", list(dict.fromkeys(items_list))],
			"buying": 1,
			"price_list": ["like", "SUP%"],
		},
		fields=["item_code", "price_list_rate", "price_list", "currency", "supplier"],
	)

	item_prices_dict = {}
	for item_price in item_prices:
		if item_price["item_code"] not in item_prices_dict:
			item_prices_dict[item_price["item_code"]] = {}
		item_prices_dict[item_price["item_code"]][item_price["price_list"]] = {
			"rate": item_price.get("price_list_rate"),
			"currency": normalize_currency(item_price.get("currency"), item_price.get("price_list")),
		}

	buying_item_prices_dict = {}
	for item_price in buying_item_prices:
		if item_price["item_code"] not in buying_item_prices_dict:
			buying_item_prices_dict[item_price["item_code"]] = []
		buying_item_prices_dict[item_price["item_code"]].append(
			{
				"rate": item_price.get("price_list_rate"),
				"currency": normalize_currency(item_price.get("currency"), item_price.get("price_list")),
				"price_list": item_price.get("price_list"),
				"supplier": item_price.get("supplier"),
			}
		)
	
	# Prepare data for the report
	data = []
	for item in items:
		exchange_rate = get_usd_to_cad_exchange_rate(item.get("transaction_date"))
		cost_amount, cost_currency, cost_source = get_cost_entry_for_row(
			item,
			buying_item_prices_dict,
			costs,
		)
		current_actual_cost_usd, current_actual_cost_cad = calculate_current_actual_costs(
			cost_amount,
			cost_currency,
			item.get("ifw_duty_rate"),
			exchange_rate,
		)
		
		row = {
			"purchase_order": item["parent"] if "parent" in item else "",
			"erpsku": item["item_code"],
			"templatesku": item["variant_of"],
			"retail_sku": item["ifw_retailskusuffix"],
			"item_name": item["item_name"],
			"item_group": item.get("item_group") or "",
			"image": item.get("image") or "",
			"brand": item.get("brand") or "",
			"supplier_part_number": item.get("supplier_part_no") or "",
			"date_item_created": getdate(item["creation"]) if item.get("creation") else "",
			"ifw_duty_rate": item["ifw_duty_rate"],
			"cost": flt(cost_amount, 2) if parse_amount(cost_amount) is not None else "",
			"current_actual_cost_usd": flt(current_actual_cost_usd, 2) if current_actual_cost_usd is not None else "",
			"current_actual_cost_cad": flt(current_actual_cost_cad, 2) if current_actual_cost_cad is not None else "",
		}

		for price_list in displayed_price_lists:
			price_list_column = sanitize_price_list_fieldname(price_list)
			profit_margin_column = get_profit_margin_fieldname(price_list)
			price_entry = item_prices_dict.get(item["item_code"], {}).get(price_list)

			if price_entry:
				row[price_list_column] = price_entry.get("rate", "")
				profit_margin = calculate_profit_margin(
					price_entry.get("rate"),
					price_entry.get("currency"),
					current_actual_cost_usd,
					current_actual_cost_cad,
				)
				row[profit_margin_column] = flt(profit_margin, 2) if profit_margin is not None else ""
			else:
				row[price_list_column] = ""
				row[profit_margin_column] = ""

		data.append(row)

	return data


def get_columns(price_lists, supplier_price_lists, sales_orders, purchase_orders):
	columns = []
	show_cost_column = bool(sales_orders)
	displayed_price_lists = get_displayed_price_lists(price_lists, supplier_price_lists, show_cost_column)

	if purchase_orders or sales_orders:
		columns.append({
			"label": "Purchase Order" if purchase_orders else "Sales Order" if sales_orders else "",
			"fieldtype": "Link",
			"fieldname": "purchase_order",
			"options": "Purchase Order" if purchase_orders else "Sales Order" if sales_orders else ""
		})

	columns.extend([{
		"label": "ERPSKU",
		"fieldtype": "Data",
		"fieldname": "erpsku",
		"width": 120
	},
	{
		"label": "TemplateSKU",
		"fieldtype": "Data",
		"fieldname": "templatesku",
		"width": 120
	},
	{
		"label": "Retail SKU",
		"fieldtype": "Data",
		"fieldname": "retail_sku",
		"width": 120
	},
	{
		"label": "Item Name",
		"fieldtype": "Data",
		"fieldname": "item_name",
		"width": 120
	},
	{
		"label": "Item Group",
		"fieldtype": "Data",
		"fieldname": "item_group",
		"width": 140
	},
	{
		"label": "Image",
		"fieldtype": "Attach Image",
		"fieldname": "image",
		"width": 120
	},
	{
		"label": "Item Brand",
		"fieldtype": "Data",
		"fieldname": "brand",
		"width": 120
	},
	{
		"label": "Supplier Part Number",
		"fieldtype": "Data",
		"fieldname": "supplier_part_number",
		"width": 150
	},
	{
		"label": "Date Item Created",
		"fieldtype": "Date",
		"fieldname": "date_item_created",
		"width": 130
	},
	{
		"label": "Duty Rate",
		"fieldtype": "Float",
		"fieldname": "ifw_duty_rate",
		"width": 120
	}])

	columns.append({
		"label": "Cost",
		"fieldtype": "Float",
		"fieldname": "cost",
		"width": 120
	})
	columns.append({
		"label": "Current Actual Cost (USD)",
		"fieldtype": "Float",
		"fieldname": "current_actual_cost_usd",
		"width": 170
	})

	columns.append({
		"label": "Current Actual Cost (CAD)",
		"fieldtype": "Float",
		"fieldname": "current_actual_cost_cad",
		"width": 170
	})

	for price_list in displayed_price_lists:
		price_list_column = sanitize_price_list_fieldname(price_list)
		columns.append({
			"label": price_list,
			"fieldtype": "Data",
			"fieldname": price_list_column,
			"width": 120,
		})
		columns.append({
			"label": f"{price_list} % Profit Margin",
			"fieldtype": "Float",
			"fieldname": get_profit_margin_fieldname(price_list),
			"width": 170,
			"default": ""
		})

	return columns
