# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class QBOSyncLog(Document):
    pass


def log_sync(operation, status="Success", records_processed=0,
             records_created=0, records_updated=0, error=None, notes=None):
    frappe.get_doc({
        "doctype": "QBO Sync Log",
        "operation": operation,
        "status": status,
        "records_processed": records_processed,
        "records_created": records_created,
        "records_updated": records_updated,
        "error": error,
        "notes": notes,
    }).insert(ignore_permissions=True)
