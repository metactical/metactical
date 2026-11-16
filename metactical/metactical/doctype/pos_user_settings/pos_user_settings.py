# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import uuid
import base64
from io import BytesIO
from frappe.model.document import Document

class POSUserSettings(Document):
	pass

@frappe.whitelist()
def generate_badge(docname):
	"""Generate badge ID once. Raises if one already exists."""
	doc = frappe.get_doc("POS User Settings", docname)

	if doc.badge_id:
		frappe.throw("Badge ID already exists. Use Download Badge to get the badge.")

	# 22-char base64url UUID (128-bit, URL-safe, no padding)
	badge_id = base64.urlsafe_b64encode(uuid.uuid4().bytes).rstrip(b"=").decode()
	doc.badge_id = badge_id
	doc.save(ignore_permissions=False)

	return _badge_data(doc)


@frappe.whitelist()
def get_badge(docname):
	"""Return QR + user info for an existing badge ID."""
	doc = frappe.get_doc("POS User Settings", docname)

	if not doc.badge_id:
		frappe.throw("No Badge ID found. Generate a badge first.")

	return _badge_data(doc)


def _badge_data(doc):
	user = frappe.db.get_value(
		"User",
		doc.user,
		["first_name", "last_name", "user_image"],
		as_dict=True,
	) or {}

	return {
		"badge_id": doc.badge_id,
		"qr_code": _make_qr_png(doc.badge_id),
		"first_name": user.get("first_name") or "",
		"last_name": user.get("last_name") or "",
		"user_image": user.get("user_image") or "",
	}


def _make_qr_png(data, scale=6):
	try:
		import pyqrcode
		qr = pyqrcode.create(str(data), error="M", mode="binary")
		buf = BytesIO()
		qr.png(buf, scale=scale, quiet_zone=2)
		return base64.b64encode(buf.getvalue()).decode("utf-8")
	except Exception:
		return ""
