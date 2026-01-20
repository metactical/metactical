import frappe
import re

BATCH_SIZE = 5000

def normalize(phone):
    if not phone:
        return None
    return re.sub(r"\D", "", phone)

def execute():
    frappe.db.auto_commit_on_many_writes = True

    total = frappe.db.count("Address", filters={"phone": ["!=", ""]})
    print(f"Total records to process: {total}")

    offset = 0

    while True:
        records = frappe.db.get_all(
            "Address",
            fields=["name", "phone", "neb_mobile_not_formatted"],
            filters={"phone": ["!=", ""]},
            limit=BATCH_SIZE,
            limit_start=offset
        )

        if not records:
            break

        for row in records:
            cleaned = normalize(row.phone)

            if cleaned and cleaned != row.neb_mobile_not_formatted:
                frappe.db.set_value(
                    "Address",
                    row.name,
                    "neb_mobile_not_formatted",
                    cleaned,
                    update_modified=False
                )

        frappe.db.commit()
        print(f"Processed {offset + len(records)} records...")

        offset += BATCH_SIZE

    print("Done.")
