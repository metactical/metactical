# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from metactical.utils.shipping.canada_post import CanadaPost
import xmltodict
import requests
from requests.auth import _basic_auth_str

class CanadaPost(Document):
	@property
	def host(self):
		return 'https://ct.soa-gw.canadapost.ca' if self.is_sandbox else 'https://soa-gw.canadapost.ca'
		
@frappe.whitelist()	
def get_manifest():
	customer_number = '0007302361'
	url = f"https://soa-gw.canadapost.ca/rs/{customer_number}/{customer_number}/manifest?start=20230801&end=20230819"
	sess = requests.Session()
	sess.headers = {
		'Accept': 'application/vnd.cpc.manifest-v8+xml',
		'Authorization': _basic_auth_str('342e3ad1fb1d7a2b', 'fa2c1fd0295abcc462a111')
	}
	sess.verify = False
	r = sess.request('GET', url, data="")
	r.raise_for_status()
	if r.status_code == 200:
		return xmltodict.parse(r.content)
		# Get the details of the manifest
	
