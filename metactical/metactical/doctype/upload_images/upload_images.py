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
from frappe.utils import cstr


class UploadImages(Document):	
	
	def on_submit(self):
		#msystem_path = "site1.local"
		msystem_path = cstr(frappe.local.site)
		file_attachment = self.attachment
		file_path  = msystem_path + file_attachment
		df = pd.read_excel(r""+file_path)
		colum_list = []
		mcol_name = "RetailSKUSuffix"
		mcol_iamge = "Images"
		colum_list = df.columns.ravel()
		d_url  = self.url
		override = self.override_images
		if len(colum_list) > 1 and colum_list[0] == mcol_name and  colum_list[1] == mcol_iamge:
			enqueue("metactical_custom.metactical_custom.doctype.upload_images.upload_images.background_job", df=df, override=override, d_url=d_url, queue='long' ,  timeout=1500)
			frappe.msgprint("Queued for Uploading Images, Track here <a href='/desk#background_jobs' target='_blank'>Background Jobs</a> or Check for Errors here <a href='/desk#List/Error Log/List' target='_blank'>Error Log</a> ")
		else:
			frappe.throw("Required columns are missing or misplaced 1st column must be RetailSKUSuffix, 2nd column must be Images")

def background_job(df, override , d_url):
	# frappe.msgprint("In -1 ")
	sku_list = []
	img_list = []
	new_img_list = []
	mdict = {}
	sku_list = df['RetailSKUSuffix'].tolist()
	img_list = df['Images'].tolist()
	# new_img_list = []
	# for i in img_list:
	# 	if not "|" in i:
	# 		mlink = d_url+i
	# 		new_img_list.append(mlink)
	# 	else:
	# 		break_img_url = i.split("|")
	# 		mlink = d_url+break_img_url[0]
	# 		new_img_list.append(mlink)	
	merge  =zip(sku_list,img_list)
	mdict = dict(merge)

	for k , v in mdict.items():
		print(v)
		k=str(k)
		v=str(v)
		if k and v and v != "NULL" and "." in v:
			if "|" in str(v):
				v = str(v).split("|")[0]
			v = d_url+v
			if not override:
				if not frappe.db.get_value("Item", {"ifw_retailskusuffix": k}, "image"):
					frappe.db.set_value("Item", {"ifw_retailskusuffix": k}, "image", v)
					frappe.msgprint("Privous Image was not in in Record")
			else:
				frappe.msgprint("Image is Already exist")
				frappe.db.set_value("Item", {"ifw_retailskusuffix": k}, "image", v)
				frappe.msgprint("Over Ride ")
