import frappe
import json
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from frappe.utils import add_months, today
from math import sqrt
from collections import defaultdict
from erpnext.stock.doctype.item.item import Item


class CustomItem(Item):
    def before_rename(self, old_item_code, new_item_code, merge=False):
        super().before_rename(old_item_code, new_item_code, merge)

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

        # Append barcodes from old item to new item
        if hasattr(old_item, "barcodes"):
            existing_barcodes = {barcode.barcode for barcode in new_item.barcodes}
            for barcode in old_item.barcodes:
                if barcode.barcode not in existing_barcodes:                
                    new_item.append("barcodes", barcode)

        # Append supplier items from old item to new item if they don't exist
        if hasattr(old_item, "supplier_items"):
            existing_suppliers = {item.supplier for item in new_item.supplier_items}
            for supplier_item in old_item.supplier_items:
                if supplier_item.supplier not in existing_suppliers:
                    new_item.append("supplier_items", supplier_item)

        # Save the updated new item
        new_item.save()

    def validate(self):
        load_tags(self)

    def on_update(self):
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

        # Trigger update if deduct_qty was changed
        if deduct_qty_updated or removed_lead_sources:
            is_product_bundle = frappe.db.exists('Product Bundle', self.item_code)
            if is_product_bundle:
                all_bins = get_all_bins_for_product_bundle(self.item_code)
                update_item_inventory_output(item_code=self.item_code, net_available_bins=all_bins, bundle=True, voucher_type=self.doctype)
            else:
                frappe.enqueue(update_item_inventory_output, item_code=self.item_code, queue='default')
                
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


@frappe.whitelist()
def safety_stock():
    """
    Recalculate safety stock for all stock items with asi_item_class set,
    based on last 24 months of sales.
    """
    # 1) Look back 24 months from today
    start_date = add_months(today(), -24)

    # 2) Get all stock items that have a class defined
    items = frappe.get_all(
        "Item",
        filters={
            "is_stock_item": 1,
            "disabled": 0,
            "asi_item_class": ["is", "set"],
        },
        fields=["name", "item_name", "asi_item_class", "safety_stock"],
    )

    if not items:
        return {"updated": 0, "message": "No items with asi_item_class found."}

    # 3) Pull monthly sales qty for last 24 months (Sales Invoices)
    sales_rows = frappe.db.sql(
        """
        SELECT
            sii.item_code,
            DATE_FORMAT(si.posting_date, '%%Y-%%m-01') AS month_start,
            SUM(sii.qty) AS qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.posting_date >= %s
        GROUP BY sii.item_code, month_start
        """,
        (start_date,),
        as_dict=True,
    )

    # 4) Arrange as: monthly_qty[item_code][month] = qty
    monthly_qty = defaultdict(lambda: defaultdict(float))
    for row in sales_rows:
        monthly_qty[row.item_code][row.month_start] += float(row.qty or 0)

    updated = 0
    

    # 5) For each item: compute stats + safety stock
    for item in items:
        # if item.asi_item_class is None or item.asi_item_class == "CY" or item.asi_item_class == "CZ":
        #     continue
        item_code = item.name  # in Item, name == item_code
        item_class = (item.asi_item_class or "").strip().upper()

        months_dict = monthly_qty.get(item_code, {})

        if not months_dict:
            # No sales history → you can choose to set 0 or skip
            continue

        # --- WEIGHTED AVERAGE USING 50/30/15/5 MODEL ---

        # Sort months oldest → newest
        months_sorted = sorted(months_dict.keys())
        values = [months_dict[m] for m in months_sorted]
        n = len(values)
        if n == 0:
            continue

        # helper to slice safely from the end
        def last_n(vals, count, offset_from_end=0):
            """
            Take `count` values ending at position n - offset_from_end.
            offset_from_end=0 → last `count`
            offset_from_end=3 → the `count` before last 3, etc.
            """
            if not vals:
                return []
            end = max(0, len(vals) - offset_from_end)
            start = max(0, end - count)
            return vals[start:end]

        # groups relative to most recent months
        last3  = last_n(values, 3, offset_from_end=0)   # last 3 months
        prev3  = last_n(values, 3, offset_from_end=3)   # months -4 to -6
        prev6  = last_n(values, 6, offset_from_end=6)   # months -7 to -12
        prev12 = last_n(values, 12, offset_from_end=12) # months -13 to -24

    
        group_weights = {
            "last3": 0.50,
            "prev3": 0.30,
            "prev6": 0.15,
            "prev12": 0.05,
        }

        weighted_sum = 0.0
        weight_denominator = 0.0

        if last3:
            weighted_sum += group_weights["last3"] * (sum(last3) / len(last3))
            weight_denominator += group_weights["last3"]

        if prev3:
            weighted_sum += group_weights["prev3"] * (sum(prev3) / len(prev3))
            weight_denominator += group_weights["prev3"]

        if prev6:
            weighted_sum += group_weights["prev6"] * (sum(prev6) / len(prev6))
            weight_denominator += group_weights["prev6"]

        if prev12:
            weighted_sum += group_weights["prev12"] * (sum(prev12) / len(prev12))
            weight_denominator += group_weights["prev12"]

        # final weighted average (fallback if denominator=0, e.g. very few months)
        if weight_denominator > 0:
            avg = weighted_sum / weight_denominator
        else:
            avg = sum(values) / float(n)
            

        # Std dev (using the same avg as reference, unweighted variance)
        if n > 1:
            mean = avg
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std_dev = sqrt(variance)
        else:
            std_dev = 0

        max_demand = max(values)

        
        new_safety_stock = calculate_safety_stock(
            item_class=item_class,
            avg_demand=avg,
            std_dev=std_dev,
            max_demand=max_demand,
        )

        # Update only if different (avoid unnecessary writes)
        if (item.safety_stock or 0) != new_safety_stock:
            frappe.db.set_value(
                "Item",
                item_code,
                "safety_stock",
                new_safety_stock,
                update_modified=False,
            )
            updated += 1

    frappe.db.commit()

    return {"updated": updated}


def calculate_safety_stock(item_class, avg_demand, std_dev, max_demand):
    """
    item_class: combined ABC-XYZ like 'AX', 'BY', 'CZ' from asi_item_class
    """
    if not item_class or not avg_demand or avg_demand <= 0:
        return 0

    classification = item_class.strip().upper()
    if len(classification) < 2:
        return 0

    abc_class = classification[0]   # A / B / C

    # Z-scores by classification (for std dev formulas)
    z_scores = {
        'AX': 2.33,  # 99%
        'AY': 2.00,  # 97.7%
        'AZ': 1.65,  # 95%
        'BX': 1.65,  # 95%
        'BY': 1.65,  # 95%
        'BZ': 1.28,  # 90%
        'CX': 1.28,  # 90%
        # 'CY': 1.04,  # 85%
        # 'CZ': 0.84,  # 80%
    }

    z = z_scores.get(classification, 1.65)  # default ~95% if unknown class

    # 1) Std deviation method for AX, AY, BX, BY
    if classification in ['AX', 'AY', 'BX', 'BY']:
        safety_stock = z * (std_dev or 0)

    # 2) Max-based method for AZ, BZ
    elif classification in ['AZ', 'BZ']:
        if max_demand is None:
            max_demand = avg_demand
        factor = 0.75 if abc_class == 'A' else 0.50
        safety_stock = max(0, (max_demand - avg_demand) * factor)

    # 3) Simple percentage of average for CX, CY, CZ
    else:
        # factors = {'CX': 0.20, 'CY': 0.25, 'CZ': 0.30}
        factors = {'CX': 0.20}
        factor = factors.get(classification, 0.25)
        safety_stock = avg_demand * factor

    return round(safety_stock)