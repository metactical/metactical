import frappe
import json
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from erpnext.stock.doctype.item.item import Item
import datetime

class CustomItem(Item):
    def before_rename(self, old_item_code, new_item_code, merge=False):
        super().before_rename(old_item_code, new_item_code, merge)

        if merge:
            self.remove_price_lists(old_item_code)

            # Fetch the old item document
            old_item = frappe.get_doc("Item", old_item_code)
            new_item = frappe.get_doc("Item", new_item_code)

            # Fields to copy if they don't exist in the new item
            fields_to_copy = [
                "ifw_location", "ifw_duty_rate", "customs_tariff_number", "neb_variantavailabilityrule",
                "brand", "ifw_item_notes", "asi_item_class", "country_of_origin"
            ]

            for field in fields_to_copy:
                if not getattr(new_item, field, None):
                    setattr(new_item, field, getattr(old_item, field, None))

            # Append supplier items from old item to new item if they don't exist
            if hasattr(old_item, "supplier_items"):
                existing_suppliers = {item.supplier for item in new_item.supplier_items}
                for supplier_item in old_item.supplier_items:
                    if supplier_item.supplier not in existing_suppliers:
                        new_item.append("supplier_items", supplier_item)

            # Save the updated new item
            new_item.save()

    def sanitize(self, obj):
        """Recursively convert datetime and date objects to string."""
        
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(obj, datetime.datetime) else obj.strftime('%Y-%m-%d')
        
        if isinstance(obj, list):
            return [self.sanitize(x) for x in obj]
        
        if isinstance(obj, dict):
            return {k: self.sanitize(v) for k, v in obj.items()}
        
        return obj
        
    def after_rename(self, old_item_code, new_item_code, merge=False):
        super().after_rename(old_item_code, new_item_code, merge)
        new_item = frappe.get_doc("Item", new_item_code)
        if merge:
            self.remove_price_lists(old_item_code)
            old_item = frappe.get_doc("Item", old_item_code)
        else:
            old_item = new_item
            old_item.item_code = old_item_code
        
        item_merge_history = frappe.new_doc("Item Merge History")
        item_merge_history.old_item_code = old_item_code
        item_merge_history.new_item_code = new_item_code
        
        item_merge_history.old_item = self.sanitize(old_item.as_dict())
        item_merge_history.new_item = self.sanitize(new_item.as_dict())
        
        item_merge_history.insert(ignore_permissions=True)
        
        if merge:
            self.copy_barcodes(old_item_code, new_item_code)

            if old_item.variant_of:
                remaining_variants = frappe.db.count("Item", filters={"variant_of": old_item.variant_of, "name": ["!=", old_item_code]})
                if remaining_variants == 0 or remaining_variants is None:  
                    try:
                        frappe.db.delete("Item", old_item.variant_of)
                    except Exception as e:
                        frappe.msgprint("Error deleting the template item after merge: {0}".format(str(e)))
                        frappe.log_error(title="Error deleting parent item after merge", message=frappe.get_traceback())

        frappe.db.commit()
        
    def copy_barcodes(self, old_item_code, new_item_code):
        old_barcodes = frappe.get_all("Item Barcode", filters={"parent": old_item_code}, fields=["barcode", "name"])
        new_barcodes = frappe.get_all("Item Barcode", filters={"parent": new_item_code}, fields=["barcode"])
        
        existing_barcodes = {barcode.barcode for barcode in new_barcodes}
        
        for barcode in old_barcodes:
            if barcode.barcode not in existing_barcodes:
                frappe.db.delete("Item Barcode", barcode.name)
                new_barcode = frappe.new_doc("Item Barcode")
                new_barcode.parent = new_item_code
                new_barcode.parenttype = "Item"
                new_barcode.parentfield = "barcodes"
                new_barcode.barcode = barcode.barcode
                try:
                    new_barcode.insert(ignore_permissions=True)
                except Exception as e:
                    frappe.log_error(title="Error copying barcode during item merge", message=frappe.get_traceback())
        
    def remove_price_lists(self, old_item_code):
        price_lists = frappe.get_all("Item Price", filters={"item_code": old_item_code}, fields=["name"])
        for price in price_lists:
            try:
                frappe.db.delete("Item Price", price.name)
                frappe.db.commit()
            except Exception as e:
                frappe.log_error(title="Error deleting Item Price during item merge", message=frappe.get_traceback())

    def validate(self):
        super().validate()
        if not frappe.flags.get("item_from_excel"):
            frappe.flags.in_import = False

        load_tags(self)

        if not self.description or self.description.strip() == '<div class="ql-editor read-mode"><p><br></p></div>':
            self.description = self.item_name

    def on_update(self):
        super().on_update()
        # check website specification values
        validate_website_specifications(self)
        sync_website_specifications(self)
        validate_item_group(self)

        # Trigger update for item inventory output if deduct_qty has been updated
        # Retrieve the document state before the update
        doc_before_update = self.get_doc_before_save()
        original_deduct_qty = doc_before_update.custom_neb_website_deduct_qty if doc_before_update else []
        original_deduct_dict = {lead.lead_source: lead.qty for lead in original_deduct_qty} if original_deduct_qty else {}
        current_lead_sources = []
        removed_lead_sources = []

        # Flag to track if deduct_qty has been updated
        deduct_qty_updated = False

        # Determine if the deduct_qty field has been updated
        if original_deduct_qty != self.custom_neb_website_deduct_qty:
            if not original_deduct_qty or not self.custom_neb_website_deduct_qty:
                deduct_qty_updated = True
            elif len(original_deduct_qty) != len(self.custom_neb_website_deduct_qty):
                deduct_qty_updated = True
            else:
                for source in self.custom_neb_website_deduct_qty:
                    current_lead_sources.append(source.lead_source)

                    if (source.lead_source in original_deduct_dict.keys() and
                        original_deduct_dict[source.lead_source] != source.qty):
                        deduct_qty_updated = True
                        break
                    elif source.lead_source not in original_deduct_dict.keys():
                        deduct_qty_updated = True
                        break
                    
        if len(self.custom_neb_website_deduct_qty) and not current_lead_sources:
            current_lead_sources = [source.lead_source for source in self.custom_neb_website_deduct_qty]

        # Trigger update if deduct_qty was changed
        if deduct_qty_updated or removed_lead_sources:
            is_product_bundle = frappe.db.exists('Product Bundle', self.item_code)
            if is_product_bundle:
                all_bins = get_all_bins_for_product_bundle(self.item_code)
                update_item_inventory_output(item_code=self.item_code, net_available_bins=all_bins, bundle=True, voucher_type=self.doctype)
            else:
                frappe.enqueue(update_item_inventory_output, item_code=self.item_code, voucher_type=self.doctype, queue='default')
                
def load_tags(doc):
    """
    Load tags for the item based on the website specifications.
    """
    
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
    
@frappe.whitelist()
def update_child_table(item_names, child_table, child_table_field, updates, updating=False):
    item_names = json.loads(item_names)
    updates = json.loads(updates)
    
    total_updated_items = 0
    
    if updating:
        # clear the child table for each selected item and then add the updates
        for item_name in item_names:
            item = frappe.get_doc("Item", item_name)
            item.set(child_table_field, [])
            
            for update in updates:
                new_row = item.append(child_table_field, {})
                for key, value in update.items():
                    if key in ["name", "idx"]:
                        continue
                    
                    setattr(new_row, key, value)
                    
            item.save()
            item.reload()
            total_updated_items += 1

    else:
        if child_table == "MT Item Website Specification":
            for item_name in item_names:
                # if the label exists, update the description, else add a new row
                item = frappe.get_doc("Item", item_name)
                for update in updates:
                    found = False
                    for spec in item.neb_website_specifications:
                        if spec.label == update['label']:
                            spec.description = update['description'] if "description" in update else ""
                            spec.mandatory = update['mandatory'] if "mandatory" in update else 0
                            found = True
                            break
                    
                    if not found:       
                        new_spec = item.append("neb_website_specifications", {})
                        new_spec.label = update['label']
                        new_spec.mandatory = update['mandatory'] if "mandatory" in update else 0
                        new_spec.description = update['description'] if "description" in update else ""

                item.save()
                item.reload()
                total_updated_items += 1
                
        elif child_table == "Months List":
            for item_name in item_names:
                # if the month exists, continue, else add a new row
                item = frappe.get_doc("Item", item_name)
                exitsing_months = [month.month for month in item.months_to_reorder]
                for update in updates:
                    if update['month'] not in exitsing_months:
                        new_month = item.append("months_to_reorder", {})
                        new_month.month = update['month']
                        
                item.save()
                item.reload()
                total_updated_items += 1
        else:
            # add a new row with the updates to the child table for each selected item
            for item_name in item_names:
                
                item = frappe.get_doc("Item", item_name)
                new_row = item.append(child_table_field, {})
                for key, value in updates[0].items():
                    if key in ["name", "idx"]:
                        continue
                    
                    setattr(new_row, key, value)
                item.save()
                item.reload()
                total_updated_items += 1
                
    return total_updated_items