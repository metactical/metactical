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
#
# Example:
#   bench --site <site> execute "metactical.api.address_verification.verify_addresses" \
#       --kwargs "{'limit': 5, 'verbose': True}"

from __future__ import unicode_literals
import json
import frappe
import requests
from tqdm import tqdm


def build_address_string(address):
	"""Build a single address string from the ERPNext Address fields.

	Format: address line 1, address line 2, City/Town, State/Province, Postal Code
	"""
	parts = [
		address.get("address_line1"),
		address.get("address_line2"),
		address.get("city"),
		address.get("state"),
		address.get("pincode"),
	]
	return ", ".join(part for part in parts if part)


def verify_addresses(limit=None, verbose=False):
	"""Loop over Canadian addresses, verify each via the API and report results.

	Report only -- no Address records are modified. Returns a dict with the
	number of addresses checked, the number verified, the average confidence
	score and the number of weak matches.

	Pass ``limit`` to only verify the first N addresses -- useful for testing
	without hitting the whole database. Pass ``verbose`` to print the request
	and response payload for each address, e.g.:
	    bench --site <site> execute \\
	        "metactical.api.address_verification.verify_addresses" \\
	        --kwargs "{'limit': 10, 'verbose': True}"
	"""
	limit = int(limit) if limit else None
	verbose = bool(verbose)
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
		address_string = build_address_string(address)
		if not address_string:
			continue

		total_checked += 1
		payload = {"address": address_string}
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
		if match_level in match_levels:
			match_levels[match_level] += 1
		else:
			match_levels["unverified"] += 1

		confidence = data.get("confidence")
		if confidence is not None:
			confidence_sum += confidence
			confidence_count += 1
			if confidence < weak_threshold:
				weak_matches += 1

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
		"  Addresses checked : {total_checked}\n"
		"  Verified          : {verified_count}\n"
		"  Average confidence: {average_confidence}\n"
		"  Weak matches      : {weak_matches}\n"
		"  By match level:\n"
		"    fully_verified  : {fully_verified}\n"
		"    street_verified : {street_verified}\n"
		"    postal_verified : {postal_verified}\n"
		"    unverified      : {unverified}".format(**result)
	)

	return result
