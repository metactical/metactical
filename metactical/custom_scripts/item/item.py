import frappe
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle

def on_update(doc, method):
    # Retrieve the document state before the update
    doc_before_update = doc.get_doc_before_save()
    original_deduct_qty = doc_before_update.custom_neb_website_deduct_qty if doc_before_update else []
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
    if deduct_qty_updated or removed_lead_sources:
        is_product_bundle = frappe.db.exists('Product Bundle', doc.item_code)
        if is_product_bundle:
            all_bins = get_all_bins_for_product_bundle(doc.item_code)
            update_item_inventory_output(item_code=doc.item_code, net_available_bins=all_bins, bundle=True, voucher_type=doc.doctype)
        else:
            frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, queue='default')



