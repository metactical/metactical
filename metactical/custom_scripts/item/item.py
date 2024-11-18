import frappe
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

def on_update(doc, method):
    # Retrieve the document state before the update
    doc_before_update = doc.get_doc_before_save()
    original_deduct_qty = doc_before_update.custom_neb_website_deduct_qty
    original_deduct_dict = {lead.lead_source: lead.qty for lead in original_deduct_qty} if original_deduct_qty else {}
    current_lead_sources = []
    removed_lead_sources = []

    # Flag to track if deduct_qty has been updated
    deduct_qty_updated = False

    # Determine if the deduct_qty field has been updated
    if original_deduct_qty != doc.custom_neb_website_deduct_qty:
        if not original_deduct_qty or not doc.custom_neb_website_deduct_qty:
            deduct_qty_updated = True
        elif len(original_deduct_qty) != len(doc.custom_neb_website_deduct_qty):
            deduct_qty_updated = True
        else:
            for source in doc.custom_neb_website_deduct_qty:
                current_lead_sources.append(source.lead_source)

                if (source.lead_source in original_deduct_dict.keys() and
                    original_deduct_dict[source.lead_source] != source.qty):
                    deduct_qty_updated = True
                    break
                elif source.lead_source not in original_deduct_dict.keys():
                    deduct_qty_updated = True
                    break

    if len(doc.custom_neb_website_deduct_qty) and not current_lead_sources:
        current_lead_sources = [source.lead_source for source in doc.custom_neb_website_deduct_qty]

    # Trigger update if deduct_qty was changed
    if deduct_qty_updated:
        frappe.msgprint("Updating item inventory output due to changes in deduct_qty.")
        frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, queue='default')

    # Check for removed lead sources and trigger updates for them
    elif removed_lead_sources:
        frappe.msgprint(f"Updating item inventory output for removed lead sources: {removed_lead_sources}")
        frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, queue='default')
