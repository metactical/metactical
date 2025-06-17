import frappe
import json
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle

def validate(doc, method):
    load_tags(doc)

def on_update(doc, method):
    # check website specification values
    validate_website_specifications(doc)
    sync_website_specifications(doc)
    validate_item_group(doc)

    # Trigger update for item inventory output if deduct_qty has been updated
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
            
def load_tags(doc):
    """
    Load tags for the item based on the website specifications.
    """
    if not doc.neb_website_specifications:
        return
    
    tags = doc.sb_tags
    doc.sb_tags = []
    tags_list = []
    
    for tag in tags:
        if not tag.label and not tag.description:
            if tag.sb_tag not in tags_list:
                doc.append("sb_tags", {
                    "sb_tag": tag.sb_tag,
                    "label": tag.label,
                    "description": tag.description,
                })
                tags_list.append(tag.sb_tag)

    for spec in doc.neb_website_specifications:
        if spec.label and spec.description:
            tag = get_sb_tag(spec.label, spec.description)
            if tag and tag not in tags_list:
                doc.append("sb_tags", {
                    "sb_tag": tag,
                    "label": spec.label,
                    "description": spec.description,
                })
    
def validate_website_specifications(doc):
    for spec in doc.neb_website_specifications:
        if not spec.label:
            frappe.throw("<b>Label</b> is required for Website Specification at row <b>{0}</b>".format(spec.idx))
        if spec.mandatory and not spec.description:
            frappe.throw("<b>Description</b> is required for Website Specification at row <b>{0}</b>".format(spec.idx))
    
def sync_website_specifications(doc):
    doc_before_update = doc.get_doc_before_save()
    if not doc_before_update:
        original_website_specifications = []
    else:
        original_website_specifications = doc_before_update.neb_website_specifications

    if not original_website_specifications and not doc.neb_website_specifications:
        return

    original_website_specifications_dict = {spec.label: {"description": spec.description} for spec in original_website_specifications} if original_website_specifications else {}
    current_website_specifications = {spec.label: {"description": spec.description} for spec in doc.neb_website_specifications} if doc.neb_website_specifications else {}

    # Check for removed/updated website specifications
    removed_website_specifications = []
    for old_label, old_description in original_website_specifications_dict.items():
        found = False
        for current_label, current_description in current_website_specifications.items():
            if old_label == current_label and old_description["description"] == current_description["description"]:
                found = True
                break

        if not found:
            removed_website_specifications.append(old_label)

    # Check for added website specifications
    added_website_specifications = []
    for current_label, current_description in current_website_specifications.items():
        found = False
        for old_label, old_description in original_website_specifications_dict.items():
            if old_label == current_label and old_description["description"] == current_description["description"]:
                found = True
                break

        if not found:
            added_website_specifications.append(current_label)

    # recreate the website specifications in the "Website Item" doctype if there is a change in the Item form
    if added_website_specifications or removed_website_specifications:
        website_items = frappe.get_all("Website Item", filters={"item_code": doc.item_code}, fields=["name"])
        if website_items:
            for item in website_items:
                website_item = frappe.get_doc("Website Item", item.name)
                website_item.neb_website_specifications = []
                website_item.website_specifications = []
                website_item.save()

                for spec in doc.neb_website_specifications:
                    website_spec = frappe.new_doc("MT Item Website Specification")
                    website_spec.label = spec.label
                    website_spec.description = spec.description
                    website_spec.mandatory = spec.mandatory
                    website_spec.parent = website_item.name
                    website_spec.parenttype = website_item.doctype
                    website_spec.parentfield = "neb_website_specifications"
                    website_spec.save()

                    main_website_spec = frappe.new_doc("Item Website Specification")
                    main_website_spec.label = spec.label
                    main_website_spec.description = spec.description
                    main_website_spec.parent = website_item.name
                    main_website_spec.parenttype = website_item.doctype
                    main_website_spec.parentfield = "website_specifications"
                    main_website_spec.save()

def validate_item_group(doc):
    if doc.item_group:
        is_item_group = frappe.db.get_value("Item Group", doc.item_group, "is_group")
        if is_item_group:
            frappe.throw("Item Group <b>{0}</b> is a group. Please select a non-group item group.".format(doc.item_group))
        
@frappe.whitelist()
def get_website_specification_description_options(labels):
    labels = json.loads(labels)
    return frappe.db.get_all("Website Spec Label Descriptions", filters={"parent": ["in", labels]}, fields=["description", "parent"])
        
@frappe.whitelist()
def copy_specification_from_item_group(item_group):
    web_spec_labels = frappe.db.get_all(
        "MT Item Website Specification", filters={"parent": item_group}, fields=["label", "mandatory"]
        )
    
    for spec in web_spec_labels:
        if spec.label:
            website_spec = frappe.get_doc("Website Specification Label", spec.label)
            descriptions = [desc.description for desc in website_spec.descriptions]    
            
            spec.descriptions = descriptions
                        
    return web_spec_labels

@frappe.whitelist()
def get_website_label_descriptions(label):
    frappe.msgprint(label)
    desc =  frappe.db.get_list(
        "Website Specification Label", filters={"label": label}
        )
    
    frappe.msgprint(desc)
    
@frappe.whitelist()
def get_sb_tag(label, description):
    sb_tag = frappe.db.get_all(
        "Website Spec Label Descriptions",
        filters={"parent": label, "description": description},
        fields=["sb_tag"]
    )
    if sb_tag:
        return sb_tag[0].sb_tag
    else:
        return None