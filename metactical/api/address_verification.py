# -*- coding: utf-8 -*-
# Verify the Canadian addresses in the database against the Storebuilder
# Canadian Address Verification API and report how many were verified along
# with the average confidence score.
#
# Run with:
#   bench --site <site> execute "metactical.api.address_verification.verify_addresses"
#
# Optional keyword arguments (pass via --kwargs):
#   limit   - verify only the first N addresses instead of the whole database;
#             useful for testing. Defaults to None (all Canadian addresses).
#   verbose - print the request payload sent and the response received for each
#             address; useful for testing. Defaults to False.
#   log_unverified - write each unverified address to a log file in the bench
#             logs folder (logs/address_verification_unverified.log). Any log
#             from a previous run is deleted first. Defaults to False.
#
# Example:
#   bench --site <site> execute "metactical.api.address_verification.verify_addresses" \
#       --kwargs "{'limit': 5, 'verbose': True, 'log_unverified': True}"

from __future__ import unicode_literals
import json
import os
import frappe
import requests
from tqdm import tqdm


@frappe.whitelist()
def verify_shipping_address(sales_order_name):
	"""Verify the shipping address on a Sales Order.

	Routes to the Storebuilder/Melissa API when Address Verification Settings
	has ``enabled`` checked; otherwise delegates to the existing ShipStation
	verification so behaviour is unchanged for sites that haven't opted in.
	"""
	settings = frappe.get_single("Address Verification Settings")

	if not settings.enabled:
		from metactical.api.shipstation import verify_shipping_address as _ss_verify
		_ss_verify(sales_order_name)
		return

	# --- Storebuilder / Melissa path ---
	sales_order = frappe.get_doc("Sales Order", sales_order_name)
	if not sales_order.shipping_address_name:
		frappe.throw("No shipping address is set on this Sales Order.")

	address = frappe.get_doc("Address", sales_order.shipping_address_name)
	payload = build_address_payload(address)
	if not payload:
		frappe.throw("Shipping address is missing Address Line 1, which is required for verification.")

	base_url = (settings.base_url or "").rstrip("/")
	api_key = settings.get_password("api_key")
	timeout = settings.timeout or 10

	if not base_url or not api_key:
		frappe.throw("Please set the Base URL and API Key in Address Verification Settings.")

	validation_status = "Validation Failed"
	validation_entity = "Storebuilder"
	validation_warning = ""

	try:
		response = requests.post(
			"{0}/api/verify".format(base_url),
			json=payload,
			headers={"X-API-Key": api_key},
			timeout=timeout,
		)
		response.raise_for_status()
		data = response.json()
	except Exception:
		frappe.log_error(
			title="Address Verification - Storebuilder request failed",
			message="Sales Order: {0}\n{1}".format(sales_order_name, frappe.get_traceback()),
		)
		frappe.throw("Address verification failed. See the Error Log for details.")

	match_level = data.get("match_level", "unverified")
	melissa_key = settings.get_password("melissa_key") if settings.enable_melissa_fallback else None

	if match_level in ("fully_verified", "street_verified"):
		validation_status = "Validated"
		validation_entity = "Storebuilder"
	elif match_level == "postal_verified":
		validation_status = "Validation Warning"
		validation_entity = "Storebuilder"
		validation_warning = "Only postal code was verified"

		if melissa_key:
			melissa_result = verify_with_melissa(address, melissa_key, timeout)
			if melissa_result:
				melissa_level, melissa_verified, melissa_detail = melissa_result
				if melissa_verified:
					# Melissa confirms the address despite Storebuilder's postal-only match.
					validation_status = "Validated"
					validation_entity = "Melissa"
					validation_warning = ""
	else:
		if melissa_key:
			melissa_result = verify_with_melissa(address, melissa_key, timeout)
			if melissa_result:
				melissa_level, melissa_verified, melissa_detail = melissa_result
				validation_entity = "Melissa"
				if melissa_verified:
					validation_status = "Validated"
				elif melissa_level != "unverified":
					validation_status = "Validation Warning"
					validation_warning = melissa_detail

	if validation_status in ("Validation Failed", "Validation Warning"):
		frappe.log_error(
			title="Address Verification - Unverified Address",
			message="Sales Order: {so}\nAddress: {addr}\nStatus: {status}\nEntity: {entity}\nWarning: {warning}".format(
				so=sales_order_name,
				addr=sales_order.shipping_address_name,
				status=validation_status,
				entity=validation_entity,
				warning=validation_warning,
			),
		)

	field_values = {
		"custom_ais_address_verified": validation_status,
		"custom_ais_validation_entity": validation_entity,
		"custom_ais_validation_warning": validation_warning,
	}
	frappe.db.set_value("Address", sales_order.shipping_address_name, field_values)
	frappe.db.set_value("Sales Order", sales_order_name, field_values)
	frappe.msgprint("Shipping Address {0}".format(validation_status))

# Unverified addresses are logged here, relative to the bench logs folder.
UNVERIFIED_LOG_NAME = "address_verification_unverified.log"

MELISSA_API_URL = "https://address.melissadata.net/V3/WEB/GlobalAddress/doGlobalAddress"

# Maps Melissa AV result codes to the internal match-level vocabulary.
# Per Melissa's code definitions: AV11/AV21/AV22 only confirm state/city level,
# AV13/AV23 confirm the street name, AV14 confirms the street number, and
# AV24/AV25 confirm the premise (house/unit) - i.e. a full match. AV11-AV13
# and AV21-AV22 are partial matches and must NOT be treated as fully verified.
_MELISSA_AV_LEVELS = {
	"AV11": "postal_verified",  # state level only
	"AV12": "postal_verified",  # city level only
	"AV13": "street_verified",  # street name confirmed, no number
	"AV14": "street_verified",  # street number confirmed
	"AV21": "postal_verified",  # state level only
	"AV22": "postal_verified",  # city level only
	"AV23": "street_verified",  # street level confirmed
	"AV24": "fully_verified",  # premise (house/building) confirmed
	"AV25": "fully_verified",  # premise unit confirmed
}

# Only these levels represent a genuine full/street-level match. Anything else
# (postal_verified, or no AV code at all) must not be reported as verified.
_MELISSA_VERIFIED_LEVELS = {"fully_verified", "street_verified"}

# Used to pick the strongest match level when a response contains multiple AV codes.
_MELISSA_LEVEL_RANK = {
	"unverified": 0,
	"postal_verified": 1,
	"street_verified": 2,
	"fully_verified": 3,
}

# Human-readable summary of what was actually confirmed at each match level.
_MELISSA_LEVEL_DESCRIPTIONS = {
	"unverified": "Address could not be verified",
	"postal_verified": "Only the city/postal code was verified; the street could not be confirmed",
	"street_verified": "Only the street was verified; the premise (house/unit number) could not be confirmed",
	"fully_verified": "Address fully verified",
}

# Human-readable reasons for Melissa AE (address error) result codes.
_MELISSA_AE_DESCRIPTIONS = {
	"AE01": "missing or incorrect postal code",
	"AE02": "street name could not be matched (no match or multiple matches)",
	"AE03": "street direction/suffix matches multiple addresses",
	"AE05": "not enough information to match a single address",
	"AE07": "not enough address details were provided",
	"AE08": "premise unit number could not be found",
	"AE09": "premise unit number is missing",
	"AE10": "street number could not be found",
	"AE11": "street number is missing",
	"AE12": "PO/RR/HC box number could not be found",
	"AE13": "PO/RR/HC box number is missing",
	"AE14": "private mail box number is missing",
}


def build_melissa_payload(address, melissa_key):
	"""Build the Melissa Global Address API request body from an ERPNext Address.

	Returns None when AddressLine1 is missing (required by the API).
	"""
	address_line1 = address.get("address_line1")
	if not address_line1:
		return None
	record = {
		"RecordID": address.get("name"),
		"AddressLine1": address_line1,
		"Locality": address.get("city") or "",
		"AdministrativeArea": address.get("state") or "",
		"PostalCode": address.get("pincode") or "",
		"Country": address.get("country") or "Canada",
	}
	address_line2 = address.get("address_line2")
	if address_line2:
		record["AddressLine2"] = address_line2
	return {
		"CustomerID": melissa_key,
		"TransmissionReference": address.get("name"),
		"Records": [record],
	}


def verify_with_melissa(address, melissa_key, timeout):
	"""Call the Melissa Global Address API and return (match_level, verified, detail) or None.

	Returns None on network/HTTP errors (already logged). verified is True only
	when the strongest AV code in the response confirms street level or better
	(fully_verified/street_verified); state/city-only matches (e.g. AV11, AV12)
	are reported as postal_verified and are not considered verified. detail is a
	human-readable summary of what was (or wasn't) confirmed, including any AE
	(address error) codes returned alongside the AV codes.
	"""
	payload = build_melissa_payload(address, melissa_key)
	if not payload:
		return None
	try:
		response = requests.post(
			MELISSA_API_URL,
			json=payload,
			headers={"Content-Type": "application/json", "Accept": "application/json"},
			timeout=timeout,
		)
		response.raise_for_status()
		data = response.json()
	except Exception:
		frappe.log_error(
			title="Address Verification - Melissa request failed",
			message="Address: {0}\n{1}".format(
				address.get("name"), frappe.get_traceback()
			),
		)
		return None

	records = data.get("Records") or []
	if not records:
		return None

	result_codes = [c.strip() for c in (records[0].get("Results") or "").split(",") if c.strip()]

	best_level = "unverified"
	ae_codes = []
	for code in result_codes:
		if code.startswith("AE"):
			ae_codes.append(code)
			continue
		level = _MELISSA_AV_LEVELS.get(code)
		if level is None and code.startswith("AV"):
			level = "postal_verified"
		if level and _MELISSA_LEVEL_RANK[level] > _MELISSA_LEVEL_RANK[best_level]:
			best_level = level

	detail = _MELISSA_LEVEL_DESCRIPTIONS[best_level]
	ae_reasons = [_MELISSA_AE_DESCRIPTIONS.get(code, code) for code in ae_codes]
	if ae_reasons:
		detail = "{0} ({1})".format(detail, "; ".join(ae_reasons))

	return (best_level, best_level in _MELISSA_VERIFIED_LEVELS, detail)


def build_address_payload(address):
	"""Build the structured request payload from the ERPNext Address fields.

	Maps the ERPNext fields to the API's structured input format. Empty fields
	are omitted. Returns None when address_line_1 is missing, since the API
	requires it for the structured format.
	"""
	field_map = {
		"address_line_1": address.get("address_line1"),
		"address_line_2": address.get("address_line2"),
		"city": address.get("city"),
		"province": address.get("state"),
		"postal_code": address.get("pincode"),
	}
	payload = {key: value for key, value in field_map.items() if value}
	if not payload.get("address_line_1"):
		return None
	return payload


def verify_addresses(limit=None, verbose=False, log_unverified=False):
	"""Loop over Canadian addresses, verify each via the API and report results.

	Report only -- no Address records are modified. Returns a dict with the
	number of addresses checked, the number verified, the average confidence
	score and the number of weak matches.

	Pass ``limit`` to only verify the first N addresses -- useful for testing
	without hitting the whole database. Pass ``verbose`` to print the request
	and response payload for each address. Pass ``log_unverified`` to write each
	unverified address to logs/address_verification_unverified.log (any log from
	a previous run is deleted first), e.g.:
	    bench --site <site> execute \\
	        "metactical.api.address_verification.verify_addresses" \\
	        --kwargs "{'limit': 10, 'verbose': True, 'log_unverified': True}"
	"""
	limit = int(limit) if limit else None
	verbose = bool(verbose)
	log_unverified = bool(log_unverified)
	settings = frappe.get_single("Address Verification Settings")
	base_url = (settings.base_url or "").rstrip("/")
	api_key = settings.get_password("api_key")
	timeout = settings.timeout or 10
	weak_threshold = settings.weak_match_threshold or 0.75

	if not base_url or not api_key:
		frappe.throw(
			"Please set the Base URL and API Key in Address Verification Settings."
		)

	headers = {"X-API-Key": api_key}

	addresses = frappe.get_all(
		"Address",
		filters={"country": "Canada"},
		fields=["name", "address_line1", "address_line2", "city", "state", "pincode"],
		limit=limit,
	)

	# Set up the unverified-address log: delete any log from a previous run so
	# the file always reflects the latest run only.
	log_file = None
	log_path = None
	if log_unverified:
		log_path = os.path.join(frappe.utils.get_bench_path(), "logs", UNVERIFIED_LOG_NAME)
		if os.path.exists(log_path):
			os.remove(log_path)
		log_file = open(log_path, "w")

	total_checked = 0
	verified_count = 0
	weak_matches = 0
	confidence_sum = 0.0
	confidence_count = 0
	match_levels = {
		"fully_verified": 0,
		"street_verified": 0,
		"postal_verified": 0,
		"unverified": 0,
	}

	for address in tqdm(addresses, desc="Verifying addresses", unit="address"):
		payload = build_address_payload(address)
		if not payload:
			continue

		total_checked += 1
		if verbose:
			tqdm.write("\n>>> {0}".format(address.get("name")))
			tqdm.write("    sent    : {0}".format(json.dumps(payload)))
		try:
			response = requests.post(
				"{0}/api/verify".format(base_url),
				json=payload,
				headers=headers,
				timeout=timeout,
			)
			response.raise_for_status()
			data = response.json()
		except Exception:
			if verbose:
				tqdm.write("    error   : {0}".format(frappe.get_traceback().strip().splitlines()[-1]))
			frappe.log_error(
				title="Address Verification failed",
				message="Address: {0}\n{1}".format(
					address.get("name"), frappe.get_traceback()
				),
			)
			continue

		if verbose:
			tqdm.write("    received: {0}".format(json.dumps(data)))

		if data.get("verified"):
			verified_count += 1

		match_level = data.get("match_level")
		if match_level not in match_levels:
			match_level = "unverified"
		match_levels[match_level] += 1

		if log_file and match_level == "unverified":
			log_file.write(
				"{0}\t{1}\n".format(address.get("name"), json.dumps(payload))
			)

		confidence = data.get("confidence")
		if confidence is not None:
			confidence_sum += confidence
			confidence_count += 1
			if confidence < weak_threshold:
				weak_matches += 1

	if log_file:
		log_file.close()

	average_confidence = (
		round(confidence_sum / confidence_count, 4) if confidence_count else 0.0
	)

	result = {
		"total_checked": total_checked,
		"verified_count": verified_count,
		"average_confidence": average_confidence,
		"weak_matches": weak_matches,
		"fully_verified": match_levels["fully_verified"],
		"street_verified": match_levels["street_verified"],
		"postal_verified": match_levels["postal_verified"],
		"unverified": match_levels["unverified"],
	}

	print(
		"\nAddress verification complete:\n"
		"  Addresses checked      : {total_checked}\n"
		"  Verified               : {verified_count}\n"
		"  Average confidence     : {average_confidence}\n"
		"  Weak matches           : {weak_matches}\n"
		"  By match level:\n"
		"    fully_verified       : {fully_verified}\n"
		"    street_verified      : {street_verified}\n"
		"    postal_verified      : {postal_verified}\n"
		"    unverified           : {unverified}".format(**result)
	)

	if log_path:
		print("  Unverified addresses logged to: {0}".format(log_path))

	return result
