# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import shutil
import barcode
from pathlib import Path
import pyqrcode
from frappe.utils import cstr
from io import BytesIO
from barcode.writer import ImageWriter
import base64


def generate(self, method):
	site = cstr(frappe.local.site)
	code = self.name
	name_tobe = code+".svg"
	check_file = Path(site+"/public/files/"+name_tobe)
	if not check_file.is_file():
		bar = barcode.get('code128', str(code))
		result = bar.save(code)
		shutil.move(result, site+'/public/files')

def po_validate(self, method):
	self.customer_address=None
	for d in self.items:
		if d.sales_order:
			self.customer_address = frappe.db.get_value("Sales Order", d.sales_order, "address_display")
			break

@frappe.whitelist()
def get_barcode(name):
	rv = BytesIO()
	barcode.get('code128', name).write(rv, options={"write_text": False})
	bstring = rv.getvalue()
	return bstring.decode('ISO-8859-1')

def get_barcode_for_print_format(name, height=9, module_width=0.23):
	rv = BytesIO()
	# options = {
	# 	"write_text": True,  # Do not write text below the barcode
	# 	"module_height": height,  # Height of the barcode
	# 	"dpi": 96,  # DPI for the image
	# 	"font_size": 6,  # Since we are not writing text
	# 	"module_width": module_width,  # Adjust to fit unit as you mentioned `Fit`
	# 	"quiet_zone": 0,  # Quiet zone width in mm
	# 	"text_distance": 2.2,  # Padding between barcode and text
	# 	"background": "#ffffff",  # Background color
	# 	"foreground": "#000000"  # Barcode color
	# }

	# # Use ImageWriter to generate a PNG
	# CODE128 = barcode.get_barcode_class('code128')
	# code128 = CODE128(name, writer=ImageWriter())
	
	# # Save barcode image to memory (BytesIO)
	# buffer = BytesIO()
	# code128.write(buffer)
	
	# # Convert to base64
	# base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
	
	# return base64_image


	# Use ImageWriter to generate a PNG
	CODE128 = barcode.get_barcode_class('code128')
	code128 = CODE128(name, writer=ImageWriter())
	
	# Define writer options (customize size, text, etc.)
	options = {
		"write_text": True,  # Do not write text below the barcode
		"module_height": 6,  # Height of the barcode
		"dpi": 500,  # DPI for the image
		"font_size": 6,  # Since we are not writing text
		"quiet_zone": 0,  # Quiet zone width in mm
		"text_distance": 2.4,  # Padding between barcode and text
		"margin_top": 1,  # Margin around the barcode
		"margin_bottom": -1,  # Margin around the barcode
		"background": "#ffffff",  # Background color
		"foreground": "#000000",  # Barcode color
		# "format": "png"  # Output format
	}
	
	# Save barcode image to memory (BytesIO)
	buffer = BytesIO()
	code128.write(buffer, options)  # Pass options when writing

	# clean barcode image from memory (BytesIO)
	rv = buffer.getvalue()
	buffer.close()

	# Convert to base64
	base64_image = base64.b64encode(rv).decode('utf-8')
	
	return base64_image