# -*- coding: utf-8 -*-
# Copyright (c) 2026, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class WarehouseUserPermissions(Document):
	pass


def get_setting_name(user):
	return frappe.db.get_value("Warehouse User Permissions", {"user": user})


def has_permitted_warehouses(setting_name, fieldname):
	"""Return True if the user has at least one warehouse configured for fieldname."""
	return bool(
		frappe.db.exists("User Permitted Warehouse", {"parent": setting_name, "parentfield": fieldname})
	)


def is_warehouse_permitted(warehouse, setting_name, fieldname):
	"""Return True if *warehouse* is equal to, or a descendant of, any warehouse stored in
	*fieldname* for this permission record.

	Uses Nested Set lft/rgt to handle group warehouses without expanding them in Python.
	A single SQL query is sufficient regardless of how many leaves the group has.
	"""
	result = frappe.db.sql(
		"""
		SELECT 1
		FROM `tabUser Permitted Warehouse` upw
		JOIN `tabWarehouse` pw ON pw.name = upw.warehouse
		JOIN `tabWarehouse` tw ON tw.name = %s
		WHERE upw.parent = %s
		  AND upw.parentfield = %s
		  AND tw.lft >= pw.lft
		  AND tw.rgt <= pw.rgt
		LIMIT 1
		""",
		(warehouse, setting_name, fieldname),
	)
	return bool(result)


def search_permitted_warehouses(setting_name, fieldname, txt, page_len=20):
	"""Return leaf warehouse names the user may use, filtered by *txt*.

	Uses a Nested Set JOIN so group warehouses stored in the permission table
	automatically cover all their descendants — no Python-side expansion needed.
	"""
	return frappe.db.sql(
		"""
		SELECT DISTINCT tw.name
		FROM `tabUser Permitted Warehouse` upw
		JOIN `tabWarehouse` pw ON pw.name = upw.warehouse
		JOIN `tabWarehouse` tw
		  ON tw.lft >= pw.lft AND tw.rgt <= pw.rgt
		WHERE upw.parent = %s
		  AND upw.parentfield = %s
		  AND tw.is_group = 0
		  AND tw.disabled = 0
		  AND tw.name LIKE %s
		ORDER BY tw.name
		LIMIT %s
		""",
		(setting_name, fieldname, "%%%s%%" % txt, page_len),
	)
