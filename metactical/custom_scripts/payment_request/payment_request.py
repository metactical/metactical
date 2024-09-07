import frappe
from frappe import _
from frappe.utils import flt
from erpnext.accounts.doctype.payment_request.payment_request import get_gateway_details, get_amount, get_party_bank_account, get_existing_payment_request_amount
from metactical.custom_scripts.utils.metactical_utils import get_customer_address
from urllib.parse import urlencode

@frappe.whitelist(allow_guest=True)
def make_payment_request(**args):
	"""Make payment request"""

	args = frappe._dict(args)

	ref_doc = frappe.get_doc(args.dt, args.dn)
	gateway_account = get_gateway_details(args) or frappe._dict()

	grand_total = get_amount(ref_doc, gateway_account.get("payment_account"))
	if args.loyalty_points and args.dt == "Sales Order":
		from erpnext.accounts.doctype.loyalty_program.loyalty_program import validate_loyalty_points

		loyalty_amount = validate_loyalty_points(ref_doc, int(args.loyalty_points))
		frappe.db.set_value(
			"Sales Order", args.dn, "loyalty_points", int(args.loyalty_points), update_modified=False
		)
		frappe.db.set_value(
			"Sales Order", args.dn, "loyalty_amount", loyalty_amount, update_modified=False
		)
		grand_total = grand_total - loyalty_amount

	bank_account = (
		get_party_bank_account(args.get("party_type"), args.get("party"))
		if args.get("party_type")
		else ""
	)

	existing_payment_request = None
	if args.order_type == "Shopping Cart":
		existing_payment_request = frappe.db.get_value(
			"Payment Request",
			{"reference_doctype": args.dt, "reference_name": args.dn, "docstatus": ("!=", 2)},
		)

	if existing_payment_request:
		frappe.db.set_value(
			"Payment Request", existing_payment_request, "grand_total", grand_total, update_modified=False
		)
		pr = frappe.get_doc("Payment Request", existing_payment_request)
	else:
		if args.order_type != "Shopping Cart":
			existing_payment_request_amount = get_existing_payment_request_amount(args.dt, args.dn)

			if existing_payment_request_amount:
				grand_total -= existing_payment_request_amount

		pr = frappe.new_doc("Payment Request")
		
		pr.update(
			{
				"payment_gateway_account": gateway_account.get("name"),
				"payment_gateway": gateway_account.get("payment_gateway"),
				"payment_account": gateway_account.get("payment_account"),
				"payment_channel": gateway_account.get("payment_channel"),
				"payment_request_type": args.get("payment_request_type"),
				"currency": ref_doc.currency,
				"grand_total": grand_total,
				"mode_of_payment": args.mode_of_payment,
				"email_to": args.recipient_id or ref_doc.owner,
				"subject": _("Payment Request for {0}").format(args.dn),
				"message": gateway_account.get("message") or get_email_content(ref_doc, grand_total),
				"reference_doctype": args.dt,
				"reference_name": args.dn,
				"party_type": args.get("party_type") or "Customer",
				"party": args.get("party") or ref_doc.get("customer"),
				"bank_account": bank_account,
			}
		)

		if args.order_type == "Shopping Cart" or args.mute_email:
			pr.flags.mute_email = True

		if args.submit_doc:
			pr.insert(ignore_permissions=True)
			pr.submit()

	if args.order_type == "Shopping Cart":
		frappe.db.commit()
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = pr.get_payment_url()

	if args.return_doc:
		return pr

	return pr.as_dict()

def get_email_content(ref_doc, amount):
	payment_form_url = frappe.db.get_single_value("Metactical Settings", "payment_form_url")
	customer_address = get_customer_address(ref_doc.customer)

	if not customer_address.get("billing") and not customer_address.get("shipping"):
		frappe.throw(_("Please set billing or shipping address for the customer"))

	billing_address = map_fields_to_address(customer_address.get("billing"), "Billing")
	shipping_address = map_fields_to_address(customer_address.get("shipping"), "Shipping")

	address = ""
	if billing_address:
		address = billing_address
		if shipping_address:
			address += f"&{shipping_address}"
	elif shipping_address:
		address = shipping_address

	payment_url = f"{payment_form_url}?{address}&UMamount={flt(amount)}&UMinvoice={ref_doc.name}"

	return frappe.render_template(
		"""{% if doc.contact_person -%}
			<p>Dear {{ doc.customer }},</p>
			{%- else %}<p>Hello,</p>{% endif %}

			<p>{{ _("Requesting payment against {0} {1} for amount $ <b>{2}</b>").format(doc.doctype,
				doc.name, amount) }}</p>

			<a href="{{ payment_url }}">{{ _("Make Payment") }}</a>
			<p></p>

			<p>{{ _("If you have any questions, please get back to us.") }}</p>

			<p>{{ _("Thank you for your business!") }}</p>
			""",
			dict(doc=ref_doc, payment_url=payment_url, amount=amount),
		)

def map_fields_to_address(address, address_type):
    if not address:
        return ""

    if address_type == "Billing":
        mapped_object = {
            'UMbillstreet': address.get('address_line1', ""),
            'UMbillfname': address.get('first_name', ""),
            'UMbilllname': address.get('last_name', ""),
            'UMbillstreet2': address.get('address_line2', ""),
            'UMbillcity': address.get('city', ""),
            'UMbillstate': address.get('state', ""),
            'UMbillcountry': address.get('country', ""),
            'UMbillphone': address.get('phone', ""),
            'UMbillcompany': address.get('company') if address.get('company') else address.get('ais_company', ""),
            'UMbillzip': address.get('pincode', "")
        }
    elif address_type == "Shipping":
        mapped_object = {
            'UMshipstreet': address.get('address_line1', ""),
            'UMshipfname': address.get('first_name', ""),
            'UMshiplname': address.get('last_name', ""),
            'UMshipstreet2': address.get('address_line2', ""),
            'UMshipcity': address.get('city', ""),
            'UMshipstate': address.get('state', ""),
            'UMshipcountry': address.get('country', ""),
            'UMshipphone': address.get('phone', ""),
            'UMshipcompany': address.get('company') if address.get('company') else address.get('ais_company', ""),
            'UMshipzip': address.get('pincode', "")
        }

    search_params = urlencode(mapped_object)
    return search_params