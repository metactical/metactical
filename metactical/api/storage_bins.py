import frappe


@frappe.whitelist()
def get_storage_bin(bin_number):
    """
    Returns full details for a single Storage Bin including its linked size record,
    merged into one flat response object that matches what PPS expects.

    PPS calls this the first time it encounters a bin it doesn't have locally.
    """
    if not bin_number:
        frappe.throw("bin_number is required", frappe.ValidationError)

    try:
        bin_doc = frappe.get_doc("Storage Bin", bin_number)
    except frappe.DoesNotExistError:
        frappe.throw(f"Storage Bin '{bin_number}' not found", frappe.DoesNotExistError)

    size_label = None
    length_cm = width_cm = height_cm = max_weight_kg = None

    if bin_doc.get("bin_size"):
        try:
            s = frappe.get_doc("Storage Bin Size", bin_doc.bin_size)
            size_label = s.size_name
            length_cm = float(s.length_cm or 0)
            width_cm = float(s.width_cm or 0)
            height_cm = float(s.height_cm or 0)
            max_weight_kg = float(s.max_weight_kg or 0)
        except frappe.DoesNotExistError:
            pass

    return {
        "name": bin_doc.name,
        "bin_number": bin_doc.bin_number,
        "status": bin_doc.status,
        "current_warehouse": bin_doc.current_warehouse,
        "rack": bin_doc.get("current_rack"),
        "contents": bin_doc.get("notes") or "",
        "storage_bin_size": bin_doc.get("bin_size"),
        "size_label": size_label,
        "length_cm": length_cm,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "max_weight_kg": max_weight_kg,
    }
