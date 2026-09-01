import frappe


@frappe.whitelist()
def get_storage_bin(bin_number):
    """
    Returns full details for a single Storage Bin including its size catalogue entry
    and current warehouse record — all in one round trip.

    PPS calls this the first time it encounters a bin that is not yet in its local
    database. After storing the result PPS needs no further ERP calls for that bin
    unless the bin moves to a different warehouse.
    """
    if not bin_number:
        frappe.throw("bin_number is required", frappe.ValidationError)

    try:
        bin_doc = frappe.get_doc("Storage Bin", bin_number)
    except frappe.DoesNotExistError:
        frappe.throw(f"Storage Bin '{bin_number}' not found", frappe.DoesNotExistError)

    size_payload = None
    if bin_doc.get("bin_size"):
        try:
            s = frappe.get_doc("Storage Bin Size", bin_doc.bin_size)
            size_payload = {
                "size_name": s.size_name,
                "description": s.description,
                "disabled": int(s.disabled or 0),
                "length_cm": float(s.length_cm or 0),
                "width_cm": float(s.width_cm or 0),
                "height_cm": float(s.height_cm or 0),
                "volume_cm3": float(s.volume_cm3 or 0),
                "usable_factor": float(s.usable_factor or 0),
                "max_weight_kg": float(s.max_weight_kg or 0),
            }
        except frappe.DoesNotExistError:
            pass

    warehouse_payload = None
    if bin_doc.get("current_warehouse"):
        try:
            w = frappe.get_doc("Warehouse", bin_doc.current_warehouse)
            warehouse_payload = {
                "name": w.name,
                "warehouse_name": w.warehouse_name,
                "parent_warehouse": w.parent_warehouse,
                "is_group": int(w.is_group or 0),
                "company": w.company,
                "disabled": int(w.disabled or 0),
                "modified": str(w.modified) if w.modified else None,
            }
        except frappe.DoesNotExistError:
            pass

    return {
        "bin": {
            "bin_number": bin_doc.bin_number,
            "bin_size": bin_doc.bin_size,
            "status": bin_doc.status,
            "current_warehouse": bin_doc.current_warehouse,
            "current_rack": bin_doc.get("current_rack"),
            "last_moved": str(bin_doc.last_moved) if bin_doc.get("last_moved") else None,
            "last_moved_by": bin_doc.get("last_moved_by"),
            "notes": bin_doc.get("notes"),
            "contents": [
                {
                    "item_code": row.item_code,
                    "item_name": row.item_name,
                    "qty": float(row.qty or 0),
                    "uom": row.uom,
                    "purchase_receipt": row.get("purchase_receipt"),
                }
                for row in (bin_doc.get("contents") or [])
            ],
        },
        "size": size_payload,
        "warehouse": warehouse_payload,
    }
