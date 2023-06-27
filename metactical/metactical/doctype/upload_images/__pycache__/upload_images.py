# -*- coding: utf-8 -*-
# Copyright (c) 2021, shahid and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
# import frappe
from frappe.model.document import Document
import csv
import pandas as pd
import xlrd
import frappe
from pathlib import Path
from frappe.utils.background_jobs import enqueue


class UploadImages(Document):	
	
	def on_submit(self):
		msystem_path = "site1.local"
		file_attachment = self.attachment
		file_path  = msystem_path + file_attachment
		df = pd.read_excel(r""+file_path)
		colum_list = []
		mcol_name = "RetailSKUSuffix"
		mcol_iamge = "Images"
		colum_list = df.columns.ravel()
		d_url  = self.url
		override = self.override_images
		if colum_list[0] == mcol_name and  colum_list[1] == mcol_iamge:
			frappe.msgprint("Records are  uploading in Background Job ")
			#enqueue("metactical_custom.metactical_custom.doctype.upload_images.upload_images.background_job", df=df, override=override, d_url=d_url, queue='long' ,  timeout=1500)
		else:
			frappe.throw("Missing: RetailSKUSuffix | Images")

def background_job(df, override , d_url):
	frappe.msgprint("In -1 ")
	sku_list = []
	img_list = []
	new_img_list = []
	mdict = {}
	sku_list = df['RetailSKUSuffix'].tolist()
	img_list = df['Images'].tolist()
	new_img_list = []
	for i in img_list:
		if not "|" in i:
			mlink = d_url+i
			new_img_list.append(mlink)
		else:
			break_img_url = i.split("|")
			mlink = d_url+break_img_url[0]
			new_img_list.append(mlink)	
	merge  =zip(sku_list,new_img_list)
	mdict = dict(merge)

	for k , v in mdict.items():
		print(v)
		if override:
			if not frappe.db.get_value("Item", {"ifw_retailskusuffix": k}, "image"):
				frappe.db.set_value("Item", {"ifw_retailskusuffix": k}, "image", v)
				frappe.msgprint("Privous Image was not in in Record")
		else:
			print(" ")
			frappe.msgprint("Image is Already exist")
			frappe.db.set_value("Item", {"ifw_retailskusuffix": k}, "image", v)
			frappe.msgprint("Over Ride ")
