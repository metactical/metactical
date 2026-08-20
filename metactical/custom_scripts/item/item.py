import frappe
import json
from frappe.utils import cint
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle
from metactical.metactical.doctype.s3_settings.s3_settings import BASE_PREFIX as S3_BASE_PREFIX
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from erpnext.stock.doctype.item.item import Item
import datetime
import requests
from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost

class CustomItem(Item):
    def before_rename(self, old_item_code, new_item_code, merge=False):
        super().before_rename(old_item_code, new_item_code, merge)

        try:
            field_meta = frappe.get_meta("Item")
            tables = {field.fieldname: field for field in field_meta.fields if field.fieldtype == "Table"}
            
            item_merge_settings = frappe.get_single("Item Merge Settings")
            if merge:
                # Remove Item Inventory Output for old item to avoid unique constraint
                # conflict during update_link_field_values (item_code is both autoname and unique)
                if frappe.db.exists("Item Inventory Output", new_item_code):
                    frappe.delete_doc("Item Inventory Output", new_item_code, ignore_permissions=True, force=True)
                    
                self.copy_barcodes(old_item_code, new_item_code)
                self.copy_suppilier_items(old_item_code, new_item_code)
                self.overwrite_website_specs(old_item_code, new_item_code)
                self.overwrite_item_defaults(old_item_code, new_item_code)
                
                if item_merge_settings.use_old_item_price:
                    self.remove_price_lists(new_item_code)
                else:
                    self.remove_price_lists(old_item_code)

                # Remove Item Inventory Output for old item to avoid unique constraint
                # conflict during update_link_field_values (item_code is both autoname and unique)
                if frappe.db.exists("Item Inventory Output", old_item_code):
                    frappe.delete_doc("Item Inventory Output", old_item_code, ignore_permissions=True, force=True)

                # Fetch the old item document
                old_item = frappe.get_doc("Item", old_item_code)
                new_item = frappe.get_doc("Item", new_item_code)

                # Fields to copy if they don't exist in the new item
                regular_fields_to_copy = [f.field_name for f in item_merge_settings.fields_to_copy]
                regular_fields_to_overwrite = [f.field_name for f in item_merge_settings.fields_to_overwrite]
                # [
                #     "ifw_location", "ifw_duty_rate", "customs_tariff_number", "ifw_product_name_ci", "neb_variantavailabilityrule",
                #     "brand", "ifw_item_notes", "asi_item_class", "country_of_origin", "image", "ifw_retailskusuffix",
                #     "neb_life_cycle_status", "neb_life_cycle_recommended_action", "country_of_origin"
                # ]
                
                for field in regular_fields_to_copy:
                    if not getattr(new_item, field, None):
                        setattr(new_item, field, getattr(old_item, field, None))
                        
                for field in regular_fields_to_overwrite:
                        setattr(new_item, field, getattr(old_item, field, None))

                # Save the updated new item
                new_item.save()
                
        except Exception as e:
            frappe.log_error(title="Error in before_rename of Item", message=frappe.get_traceback())

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

        frappe.flags.renaming = True

        try:
            new_item = frappe.get_doc("Item", new_item_code)
            if merge:
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
                if old_item.variant_of:
                    remaining_variants = frappe.db.count("Item", filters={"variant_of": old_item.variant_of, "name": ["!=", old_item_code]})
                    if remaining_variants == 0 or remaining_variants is None:  
                        try:
                            frappe.db.delete("Item", old_item.variant_of)
                        except Exception as e:
                            frappe.msgprint("Error deleting the template item after merge: {0}".format(str(e)))
                            frappe.log_error(title="Error deleting parent item after merge", message=frappe.get_traceback())

        except Exception as e:
            frappe.log_error(title="Error in after_rename of Item", message=frappe.get_traceback())
        finally:    
            repost_item_valuations = frappe.get_list("Repost Item Valuation", 
                                                    filters={"item_code": new_item_code, "status": "Queued"}, 
                                                    fields=["name", "warehouse"],
                                                    order_by="creation desc"
                                                )
            if not repost_item_valuations:
                return

            for repost_item_valuation in repost_item_valuations:
                if frappe.db.get_value("Warehouse", repost_item_valuation.warehouse, "disabled"):
                    continue
                
                doc = frappe.get_doc("Repost Item Valuation", repost_item_valuation.name)
                try:
                    
                    doc.deduplicate_similar_repost()
                    frappe.enqueue(repost, doc=doc, queue='long')
                except Exception as e:
                    frappe.log_error(title="Error during reposting item valuation after item merge", message=frappe.get_traceback())
                    
            frappe.enqueue(update_item_inventory_output, item_code=self.item_code, voucher_type=self.doctype, queue='long')

    def overwrite_item_defaults(self, old_item_code, new_item_code):
        # overwrite item defaults from old item to new item
        old_defaults = frappe.get_all(
            "Item Default",
            filters={"parent": old_item_code},
            fields=["default_warehouse", "company", "default_supplier"]
        )

        # remove existing defaults from new item to avoid duplicates
        frappe.db.delete("Item Default", {"parent": new_item_code})
        for default in old_defaults:
            try:
                new_default = frappe.get_doc({
                    "doctype": "Item Default",
                    "parent": new_item_code,
                    "parenttype": "Item",
                    "parentfield": "item_defaults",
                    "default_warehouse": default.default_warehouse,
                    "company": default.company,
                    "default_supplier": default.default_supplier
                })
                new_default.insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(
                    title="Error copying item defaults during item merge",
                    message=frappe.get_traceback()
                )            
    
    def overwrite_website_specs(self, old_item_code, new_item_code):
        # overwrite website specifications from old item to new item
        old_specs = frappe.get_all(
            "MT Item Website Specification",
            filters={"parent": old_item_code},
            fields=["label", "description", "mandatory"]
        )

        # remove existing specifications from new item to avoid duplicates
        frappe.db.delete("MT Item Website Specification", {"parent": new_item_code})
        for spec in old_specs:
            try:
                new_spec = frappe.get_doc({
                    "doctype": "MT Item Website Specification",
                    "parent": new_item_code,
                    "parenttype": "Item",
                    "parentfield": "neb_website_specifications",
                    "label": spec.label,
                    "description": spec.description,
                    "mandatory": spec.mandatory
                })
                new_spec.insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(
                    title="Error copying website specifications during item merge",
                    message=frappe.get_traceback()
                )

    def repost_bin_qty(self, item_code):
        bins = frappe.get_all(
            "Bin",
            filters={"item_code": item_code},
            pluck="name",
        )
        for bin_name in bins:
            try:
                frappe.get_doc("Bin", bin_name).recalculate_qty()
            except Exception:
                frappe.log_error(
                    title="Error recalculating bin qty after rename",
                    message=frappe.get_traceback(),
                )
        
    def copy_barcodes(self, old_item_code, new_item_code):
        old_barcodes = frappe.get_all(
            "Item Barcode",
            filters={"parent": old_item_code},
            pluck="barcode"
        )

        new_barcodes = set(frappe.get_all(
            "Item Barcode",
            filters={"parent": new_item_code},
            pluck="barcode"
        ))

        for barcode in old_barcodes:
            if barcode not in new_barcodes:
                frappe.db.delete("Item Barcode", {"parent": old_item_code, "barcode": barcode})
                try:
                    frappe.get_doc({
                        "doctype": "Item Barcode",
                        "parent": new_item_code,
                        "parenttype": "Item",
                        "parentfield": "barcodes",
                        "barcode": barcode
                    }).insert(ignore_permissions=True, ignore_if_duplicate=True)

                except Exception:
                    frappe.log_error(
                        title="Barcode merge error",
                        message=frappe.get_traceback()
                    )

        # optional: remove all barcodes from old item
        frappe.db.delete("Item Barcode", {"parent": old_item_code})

    def copy_suppilier_items(self, old_item_code, new_item_code):
        old_suppliers = frappe.get_all(
            "Item Supplier",
            filters={"parent": old_item_code},
            fields=["supplier", "supplier_part_no"]
        )

        new_suppliers = frappe.get_all(
            "Item Supplier",
            filters={"parent": new_item_code},
            fields=["supplier", "supplier_part_no"]
        )

        # Track:
        # 1. exact matches
        existing_pairs = {
            (d.supplier, d.supplier_part_no) for d in new_suppliers
        }

        # 2. suppliers that already have a part_no
        supplier_with_part_no = {
            d.supplier for d in new_suppliers if d.supplier_part_no
        }

        for d in old_suppliers:
            key = (d.supplier, d.supplier_part_no)

            # Case 1: exact duplicate → skip
            if key in existing_pairs:
                continue

            # Case 2: incoming has NO part_no
            if not d.supplier_part_no:
                # if supplier already has a record WITH part_no → skip
                if d.supplier in supplier_with_part_no:
                    continue

            try:
                frappe.get_doc({
                    "doctype": "Item Supplier",
                    "parent": new_item_code,
                    "parenttype": "Item",
                    "parentfield": "supplier_items",
                    "supplier": d.supplier,
                    "supplier_part_no": d.supplier_part_no
                }).insert(ignore_permissions=True)

                # update trackers
                existing_pairs.add(key)
                if d.supplier_part_no:
                    supplier_with_part_no.add(d.supplier)

            except Exception:
                frappe.log_error(
                    title="Supplier merge error",
                    message=frappe.get_traceback()
                )
                
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

        self.description = self.item_name
            
        if self.request_ai_suggestion and self.drop_and_create_in_websites:
            frappe.throw("You cannot 'Drop and Create in Websites' while requesting AI Suggestion. Please uncheck one of these options or wait until the AI Suggestion is completed.")

        validate_variants_in_websites(self)

    def on_update(self):
        super().on_update()
        
        # check website specification values
        validate_website_specifications(self)
        validate_item_group(self)
        self.update_item_inventory_output()
        self.update_sb_tags()
        
        if self.drop_and_create_in_websites:
            if not self.item_detail:
                frappe.throw("Please add at least one Item Detail to drop and create in websites.")

            # A drop and create re-pushes this product's images from the S3 record. Letting it run
            # while the image import is still writing that record would push a half-built image set.
            active_sync = get_image_sync_flag(self.item_code)
            if active_sync:
                frappe.throw(
                    "Images are still being loaded from Storebuilder for <b>{0}</b> "
                    "(started by {1} at {2}). Please wait for that to finish before "
                    "dropping and re-creating in websites.".format(
                        self.item_code, active_sync.get("user"), active_sync.get("started")
                    )
                )

            self.create_item_deletion_log()
        
        frappe.flags.renaming = False
            
    def update_sb_tags(self):
        item_specs = {
            (row.label, row.description)
            for row in self.neb_website_specifications or []
            if row.label and row.description
        }

        manual_rows = [tag for tag in self.sb_tags if tag.manual_selection]
        manual_tags = {tag.sb_tag for tag in manual_rows if tag.sb_tag}

        self.set("sb_tags", manual_rows)
        
        sb_tags = frappe.get_all("SB Tag", filters={"disabled": 0}, pluck="name")
        for tag_name in sb_tags:
            tag_doc = frappe.get_doc("SB Tag", tag_name)
            tag_specs = {
                (row.label, row.description)
                for row in tag_doc.neb_website_specifications or []
            }

            tag_item_groups = {
                row.item_group
                for row in tag_doc.nat_item_groups or []
                if row.item_group
            }

            tag_brands = {
                row.brand
                for row in tag_doc.nat_brands or []
                if row.brand
            }

            # Map the tag if the item matches on item group OR on brand
            matches_item_group = self.item_group in tag_item_groups
            matches_brand = self.brand in tag_brands

            if not (matches_item_group or matches_brand):
                continue

            if not tag_specs.issubset(item_specs):
                continue

            if tag_doc.name in manual_tags:
                continue

            self.append("sb_tags", {
                "sb_tag": tag_doc.name
            })

        self.update_child_table("sb_tags")

    def update_item_inventory_output(self):
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
                
    def create_item_deletion_log(self):
        existing_active_logs = frappe.db.get_all("Item Drop and Create Log", filters={"product": self.item_code, "status": "Issued"}, pluck="name")
        for log in existing_active_logs:
            try:
                frappe.db.delete("Item Drop and Create Log", log)
            except Exception as e:
                frappe.log_error(title="Error deleting existing Item Drop and Create Log", message=frappe.get_traceback())
        
        for source in self.item_detail:
            if not source.slug:
                frappe.throw("Slug is required for Item Detail with price list <b>{0}</b>".format(source.price_list))
                
            item_deletion_log = frappe.new_doc("Item Drop and Create Log")
            item_deletion_log.product = self.item_code
            item_deletion_log.item_name = self.item_name
            item_deletion_log.price_list = source.price_list
            item_deletion_log.slug = source.slug.rstrip("\r\n")
            item_deletion_log.status = "Issued"
            item_deletion_log.insert(ignore_permissions=True)


        frappe.db.set_value(self.doctype, self.name, "drop_and_create_in_websites", 0)
        self.reload()

def validate_website_specifications(doc):
    for spec in doc.neb_website_specifications:
        if not spec.label:
            frappe.throw("<b>Label</b> is required for Website Specification at row <b>{0}</b>".format(spec.idx))
        if spec.mandatory and not spec.description:
            frappe.throw("<b>Description</b> is required for Website Specification at row <b>{0}</b>".format(spec.idx))
    
@frappe.whitelist()
def has_s3_image_record(item_code):
    """
        Is there an S3 Uploader record whose images a drop and create could re-sync?
    """
    if not frappe.db.get_value("Item", item_code, "has_variants"):
        return True

    return bool(frappe.db.exists("S3 Product Image Meta Data", {"nat_product_template": item_code}))

def validate_item_group(doc):
    if doc.item_group and not frappe.flags.renaming:
        is_item_group = frappe.db.get_value("Item Group", doc.item_group, "is_group")
        if is_item_group:
            frappe.throw("Item Group <b>{0}</b> is a group. Please select a non-group item group.".format(doc.item_group))
        
@frappe.whitelist()
def get_website_specification_description_options(labels):
    labels = json.loads(labels)
    return frappe.db.get_all("Website Spec Label Descriptions", filters={"parent": ["in", labels]}, fields=["description", "parent"], order_by="description asc")
        
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
def get_item_details(item_code):
    try:
        item_detail_apis = frappe.get_all("Item Import Validation", filters={"parentfield": "item_detail_apis"}, fields=["*"])
        item_details = frappe.get_doc("Item", item_code).item_detail
        
        failed_slugs = []
            
        for item_detail in  item_details:
            setting_found = False
            site_name = item_detail.price_list.split("-")[-1].strip()

            for item_detail_api in item_detail_apis:
                if item_detail.price_list == item_detail_api.price_list:
                    setting_found = True
                    url =item_detail_api.api_url + "?slug=" + item_detail.slug
                    
                    response = requests.get(url, headers={"Authorization": "Bearer " + item_detail_api.api_key})
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("Found") == False:
                            failed_slugs.append({
                                "message": f"<span class='text-danger'>Slug {item_detail.slug} not found in {site_name}</span>"
                            })
                                                
                        else:
                            item_detail_doc = frappe.get_doc("Item Detail", item_detail.name)
                            item_detail_doc.item_name = data.get("Name", "")
                            item_detail_doc.description = data.get("Description", "")
                            item_detail_doc.slug = data.get("slug", "")
                            item_detail_doc.productmetasedescription = data.get("ProductMetaSEDescription", "")
                            item_detail_doc.productmetasekeywords = data.get("ProductMetaSEKeywords", "")
                            item_detail_doc.productmetasetitle = data.get("ProductMetaSETitle", "")
                            item_detail_doc.h2 = data.get("h2", "")
                            item_detail_doc.h3 = data.get("h3", "")
                            item_detail_doc.save()    
                            
                            failed_slugs.append({
                                "message": f"<span class='text-success'>Successfully updated details for slug {item_detail.slug} from {site_name}</span>"
                            })

                    else:
                        frappe.msgprint("Failed to fetch details for slug {0} from API {1}. Status code: {2}".format(item_detail.slug, item_detail_api.api_url, response.status_code))
            if not setting_found:
                failed_slugs.append({
                    "message": "<span class='text-warning'>No API setting found for price list {0}</span>".format(item_detail.price_list)
                })
            
                
        return failed_slugs
    except Exception as e:
        frappe.log_error(title="Error in get_item_details API", message=frappe.get_traceback())
        frappe.msgprint("An error occurred while fetching item details. Please check the error log for more information.")


# ---------------------------------------------------------------------------
# Load Data From SB — slugs/descriptions (above) and product images (below)
# ---------------------------------------------------------------------------

# Long enough that it can never expire while a job is genuinely alive (the job's own timeout
# is 1500s), short enough that a worker killed mid-run frees the item without anyone's help.
IMAGE_SYNC_TTL = 1800

# The four sizes an image can exist in. Both the CDN and the S3 bucket lay them out the same
# way — <base>/images/products/<role>/<file> — so one filename from Storebuilder gives us the
# URL to check and the key to write, with no name mapping in between.
IMAGE_ROLES = ("icon", "small", "medium", "large")

# The record stores image paths WITHOUT the bucket's leading "images/" segment, even though the
# object is uploaded to "images/products/<role>/<file>". The uploader page has always done this
# (FileUploader.vue stores `products/${role}/${file}` but PUTs to `${base_prefix}/...`), and every
# stored path follows it, so an import writing the full S3 key here would not match anything.
META_PATH_PREFIX = "products"

CONTENT_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
}


def _sb_site_name(price_list):
    """Readable website name for messages — price lists are named like "RET - Camo"."""
    if not price_list:
        return "(no price list)"
    return frappe.utils.escape_html(price_list.split("-")[-1].strip())


def _image_sync_key(item_code):
    return "sb_image_sync:{0}".format(item_code)


def set_image_sync_flag(item_code, user):
    frappe.cache().set_value(
        _image_sync_key(item_code),
        {"user": user, "started": frappe.utils.now()},
        expires_in_sec=IMAGE_SYNC_TTL,
    )


def get_image_sync_flag(item_code):
    """Who is loading images for this item right now, or None.

    `expires=True` is not optional: without it get_value keeps a copy in frappe.local and
    would keep handing back a flag that Redis has already expired.
    """
    return frappe.cache().get_value(_image_sync_key(item_code), expires=True)


def clear_image_sync_flag(item_code):
    frappe.cache().delete_value(_image_sync_key(item_code))


@frappe.whitelist()
def load_data_from_sb(item_code):
    """What the "Load Data From SB" button calls: slugs/descriptions, plus images.

    The two halves are unrelated, so the image work is queued first and runs in a worker
    while the detail pull happens here. Only the image half is slow enough to collide with
    anything, so it alone owns the in-progress flag.
    """
    active_sync = get_image_sync_flag(item_code)
    if active_sync:
        return [{
            "message": "<span class='text-warning'>Still loading images from Storebuilder for "
                       "this item (started by {0} at {1}). Please wait for it to finish.</span>".format(
                           frappe.utils.escape_html(str(active_sync.get("user") or "")),
                           frappe.utils.escape_html(str(active_sync.get("started") or "")),
                       )
        }]

    user = frappe.session.user
    set_image_sync_flag(item_code, user)

    # Queue before the detail pull, not after: the detail pull is a series of external calls
    # with no timeout, and if it hangs or raises here then an enqueue placed after it never
    # runs — leaving the flag raised for its full TTL with no job behind it to lower it.
    try:
        frappe.enqueue(
            "metactical.custom_scripts.item.item.sync_images_from_sb",
            queue="long",
            timeout=1500,
            job_name="sb-images-{0}".format(item_code),
            item_code=item_code,
            user=user,
        )
    except Exception:
        # Nothing else would ever lower the flag if the job was never queued.
        clear_image_sync_flag(item_code)
        frappe.log_error(title="SB image job not queued", message=frappe.get_traceback())
        raise

    return get_item_details(item_code)


def _content_type_for(filename):
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")


def _s3_object_exists(client, bucket, key):
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def _fetch_sb_product(config, external_id, slug):
    """Ask one website for a product's images. Returns (product, error_message)."""
    body = {"externalId": external_id}
    if slug:
        body["slug"] = slug.strip()

    response = requests.post(
        config.api_url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (config.api_key or ""),
        },
        timeout=(5, 30),
    )
    if response.status_code != 200:
        return None, "returned HTTP {0}".format(response.status_code)

    data = response.json()
    if not data.get("found"):
        return None, "does not have this product"

    products = data.get("products") or []
    if not products:
        return None, "returned no products"

    # externalId and slug are sent together and the endpoint unions them, so more than one
    # product can come back. Prefer the one this website's Item Detail row actually names.
    if slug:
        for product in products:
            if (product.get("slug") or "").strip().lower() == slug.strip().lower():
                return product, None
    for product in products:
        if product.get("externalId") == external_id:
            return product, None
    if len(products) == 1:
        return products[0], None

    return None, "returned {0} products and none matched the slug or external id".format(len(products))


def _collect_website_images(product, cdn_url, s3_client, bucket, stats):
    """Work out which sizes of this product's images exist, uploading any S3 is missing.

    Returns {(sku, order, role): path} for everything found on this website. The variant media
    links are what carry the real ordering — the product-level images all report displayOrder 0
    — so the links, not the image list, drive this.
    """
    images_by_id = {img.get("id"): img for img in (product.get("images") or []) if img.get("id")}
    found = {}

    # Several variants routinely link the same image, and the S3 key depends only on the role
    # and the filename — so resolve each key once per website rather than once per link.
    resolved = {}

    def _resolve(filename, role):
        """Returns the path to store for this size, or None if it is not available."""
        s3_key = "{0}/{1}/{2}".format(S3_BASE_PREFIX, role, filename)
        if s3_key not in resolved:
            available = _transfer_image(s3_key, filename, cdn_url, s3_client, bucket, stats)
            resolved[s3_key] = (
                "{0}/{1}/{2}".format(META_PATH_PREFIX, role, filename) if available else None
            )
        return resolved[s3_key]

    for variant in product.get("variants") or []:
        sku = variant.get("fullRetailSku") or variant.get("retailSkuSuffix")
        if not sku:
            continue

        for link in variant.get("mediaLinks") or []:
            image = images_by_id.get(link.get("productMediaLinkId"))
            if not image:
                stats["broken_links"] += 1
                continue

            filename = image.get("fileName")
            if not filename:
                continue

            order = cint(link.get("displayOrder"))

            for role in IMAGE_ROLES:
                path = _resolve(filename, role)
                if path:
                    found[(sku, order, role)] = path

    return found


def _transfer_image(s3_key, filename, cdn_url, s3_client, bucket, stats):
    """Make sure one size of one image is in S3. Returns True if it is available there."""
    # The key is fully determined by role + filename, so anything already in the bucket is
    # this same image — no reason to pull it down from the CDN and push it straight back up.
    if _s3_object_exists(s3_client, bucket, s3_key):
        stats["skipped"] += 1
        return True

    # The CDN lays images out under the same path the S3 key uses.
    url = "{0}/{1}".format(cdn_url.rstrip("/"), s3_key)
    try:
        response = requests.get(url, timeout=(5, 30))
    except requests.exceptions.RequestException:
        stats["errors"] += 1
        frappe.log_error(title="SB image CDN unreachable", message="{0}\n{1}".format(url, frappe.get_traceback()))
        return False

    if response.status_code == 404:
        # Plenty of products only have some of the four sizes. This is the ordinary case.
        return False
    if response.status_code != 200:
        stats["errors"] += 1
        frappe.log_error(
            title="SB image CDN error",
            message="{0} returned HTTP {1}".format(url, response.status_code),
        )
        return False

    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=response.content,
            ContentType=_content_type_for(filename),
        )
    except Exception:
        stats["errors"] += 1
        frappe.log_error(
            title="SB image S3 upload failed",
            message="key={0}\n{1}".format(s3_key, frappe.get_traceback()),
        )
        return False

    stats["uploaded"] += 1
    return True


def sync_images_from_sb(item_code, user=None):
    """Import this product's images from every website it is published to, into S3.

    For each Item Detail row: ask that website for its images, check which of the four sizes
    exist on its CDN, upload the ones that do, and fold the result into the item's S3 record.

    The merge only ever adds or replaces. A size the CDN did not answer for, a variant the
    website did not mention, and every other website's rows are all left exactly as they
    were — a CDN that is briefly unreachable must not delete good image records.
    """
    # Imported here rather than at module level: the uploader page imports upsert_upload from
    # the doctype module, so pulling both in at import time risks a circular import.
    from metactical.metactical.doctype.s3_product_image_meta_data.s3_product_image_meta_data import (
        _doc_state, upsert_upload,
    )
    from metactical.metactical.page.s3_uploader.s3_uploader import resolve_item_codes

    messages = []
    stats = {"uploaded": 0, "skipped": 0, "errors": 0, "broken_links": 0}

    try:
        template = frappe.get_doc("Item", item_code)
        image_apis = frappe.get_all(
            "Item Import Validation",
            filters={"parentfield": "image_apis", "enabled": 1},
            fields=["*"],
        )
        configs = {row.price_list: row for row in image_apis}

        # One identity for this product across every Storebuilder endpoint, same rule as
        # build_variant_payload uses for papi_validate_variants.
        external_id = template.ifw_retailskusuffix or template.item_code

        settings = frappe.get_single("S3 Settings")
        s3_client = settings.get_client()
        bucket = settings.nat_bucket_name

        found = {}
        for item_detail in template.item_detail:
            site_name = _sb_site_name(item_detail.price_list)

            config = configs.get(item_detail.price_list)
            if not config:
                messages.append(
                    "<span class='text-warning'>No image API configured for price list "
                    "{0}</span>".format(frappe.utils.escape_html(str(item_detail.price_list)))
                )
                continue

            if not config.cdn_url:
                messages.append(
                    "<span class='text-warning'>No CDN URL set for {0}</span>".format(site_name)
                )
                continue

            # nat_site is a Link to Lead Source, so a price list with no website behind it
            # has nowhere to be recorded.
            lead_source = frappe.db.get_value(
                "Lead Source", {"custom_neb_price_list": item_detail.price_list}, "name"
            )
            if not lead_source:
                messages.append(
                    "<span class='text-warning'>No Lead Source is mapped to price list "
                    "{0}</span>".format(frappe.utils.escape_html(str(item_detail.price_list)))
                )
                continue

            try:
                product, error = _fetch_sb_product(config, external_id, item_detail.slug)
            except requests.exceptions.RequestException:
                messages.append(
                    "<span class='text-danger'>{0} could not be reached</span>".format(site_name)
                )
                frappe.log_error(
                    title="SB image fetch failed",
                    message="{0} / {1}\n{2}".format(item_code, item_detail.price_list, frappe.get_traceback()),
                )
                continue
            except ValueError:
                messages.append(
                    "<span class='text-danger'>{0} sent a response we could not read</span>".format(site_name)
                )
                continue

            if error:
                messages.append(
                    "<span class='text-danger'>{0} {1}</span>".format(site_name, error)
                )
                continue

            site_found = _collect_website_images(
                product, config.cdn_url, s3_client, bucket, stats
            )

            # Websites share images, so the same key routinely comes back from more than one of
            # them. Collect the websites per image rather than letting the last one win — a plain
            # update() here would quietly drop every earlier site's tag.
            for key, path in site_found.items():
                entry = found.setdefault(key, {"path": path, "sites": set()})
                entry["path"] = path
                entry["sites"].add(lead_source)

            messages.append(
                "<span class='text-success'>{0}: {1} image files found</span>".format(
                    site_name, len(site_found)
                )
            )

        if found:
            _save_imported_images(item_code, found, _doc_state, upsert_upload, resolve_item_codes)
            messages.append(
                "<span class='text-success'>Saved to the S3 record — {0} uploaded, "
                "{1} already in S3</span>".format(stats["uploaded"], stats["skipped"])
            )
        else:
            messages.append("<span class='text-warning'>No images were found to import</span>")

        if stats["broken_links"]:
            messages.append(
                "<span class='text-warning'>{0} image links pointed at images the website did "
                "not list</span>".format(stats["broken_links"])
            )
        if stats["errors"]:
            messages.append(
                "<span class='text-danger'>{0} images failed — see the Error Log</span>".format(
                    stats["errors"]
                )
            )

    except Exception:
        frappe.log_error(
            title="SB image import failed",
            message="{0}\n{1}".format(item_code, frappe.get_traceback()),
        )
        messages.append(
            "<span class='text-danger'>Image import failed. Please check the Error Log.</span>"
        )
    finally:
        clear_image_sync_flag(item_code)

    if user:
        frappe.publish_realtime(
            "msgprint",
            message="<b>Storebuilder images — {0}</b><br>{1}".format(
                frappe.utils.escape_html(item_code), "<br>".join(messages)
            ),
            user=user,
        )

    return messages


def _save_imported_images(item_code, found, _doc_state, upsert_upload, resolve_item_codes):
    """Fold this run's findings into the item's S3 record, adding and replacing only.

    Starts from whatever the record already holds and lays the new findings over the top, so
    sizes, variants and websites this run said nothing about survive untouched. The whole
    merged picture is then written in one call — upsert_upload rebuilds the child tables from
    what it is given, so handing it one website's images at a time would drop all the others.
    """
    existing = frappe.get_all(
        "S3 Product Image Meta Data",
        filters={"nat_product_template": item_code},
        order_by="creation desc",
        limit=1,
        pluck="name",
    )

    merged = {}
    override = 0
    stored_item_codes = {}
    if existing:
        doc = frappe.get_doc("S3 Product Image Meta Data", existing[0])
        override = cint(doc.nat_override_full_product)
        state = _doc_state(doc)
        merged = {key: dict(value) for key, value in state["images"].items()}
        stored_item_codes = {sku: code for sku, code in state["skus"].items() if code}

    for key, hit in found.items():
        entry = merged.setdefault(key, {"path": hit["path"], "sites": frozenset()})
        entry["path"] = hit["path"]
        entry["sites"] = frozenset(entry.get("sites") or frozenset()) | frozenset(hit["sites"])

    # Storebuilder's SKUs only resolve to an Item when one carries them as its retail SKU, and
    # plenty do not — the mapping on the record may have been set by hand in the uploader. Keep
    # whatever the record already had and let the lookup fill in the gaps, rather than
    # re-deriving the lot and blanking every SKU the lookup cannot match.
    item_of = resolve_item_codes(sorted({sku for sku, _order, _role in merged}))
    item_of.update(stored_item_codes)

    files = [
        {
            "role": role,
            "order": order,
            "path": entry["path"],
            "sites": sorted(entry["sites"]),
            "skuItems": [{"sku": sku, "item_code": item_of.get(sku)}],
        }
        for (sku, order, role), entry in merged.items()
    ]

    return upsert_upload(
        files,
        override_full_product=override,
        template_item=item_code,
        suppress_push=True,
    )


def validate_variants_in_websites(doc):
    """Ask every website this product is published to whether its variants are acceptable.

    Called on each Item save. Warn only, never block: a website being unreachable — or rejecting a
    variant — must not stop anyone saving an item in ERP.
    """
    # Bulk paths would fire a request per row, and nobody is there to read the warnings.
    if (frappe.flags.get("item_from_excel") or frappe.flags.in_import
            or frappe.flags.in_migrate or frappe.flags.in_install):
        return

    template = doc.variant_of or doc.item_code

    # Saving a template cascades into a save of every variant (erpnext's Item.update_variants) and
    # they all resolve to the same family, so validate it once per request.
    validated = frappe.flags.setdefault("variant_validation_done", set())
    if template in validated:
        return

    try:
        variants = frappe.get_all("Item", filters={"variant_of": template}, order_by="name", pluck="name")
        if not variants:
            # A plain item, or a template with no variants yet — nothing to validate.
            return

        validated.add(template)

        # Use the in-flight document when it is the template, so the retail SKU and price lists
        # being validated are the ones the user is saving, not the stored copy.
        template_doc = doc if doc.item_code == template else frappe.get_doc("Item", template)

        # The product is identified by its retail SKU, but most templates carry none — fall
        # back to the item code, which is always set, rather than skipping the validation.
        product_external_id = template_doc.ifw_retailskusuffix or template_doc.item_code

        configs = frappe.get_all(
            "Item Import Validation",
            filters={"parentfield": "variant_validation_apis", "enabled": 1},
            fields=["*"]
        )
        if not configs:
            return

        payload = build_variant_payload(product_external_id, variants, doc)

        problems_by_site = {}
        for item_detail in template_doc.item_detail:
            site_name = item_detail.price_list.split("-")[-1].strip()

            for config in configs:
                if item_detail.price_list == config.price_list:
                    problems = post_variant_validation(config, payload, site_name)
                    if problems:
                        problems_by_site.setdefault(site_name, []).extend(problems)

        if problems_by_site:
            frappe.msgprint(
                format_variant_problems(problems_by_site),
                title="Variants need attention",
                indicator="orange"
            )

    except Exception as e:
        frappe.log_error(title="Error in variant validation API", message=frappe.get_traceback())
        frappe.msgprint("Could not validate the variants against the websites. Please check the error log for more information.")

def build_variant_payload(product_external_id, variants, in_flight_doc=None):
    """Build the papi_validate_variants body for one product.

    `in_flight_doc` is the document being saved; its own values are used in place of the stored
    copy, so the user is warned about the edits they are making rather than the ones on disk.
    """
    variant_payload = []

    for variant_code in variants:
        if in_flight_doc is not None and in_flight_doc.item_code == variant_code:
            variant = in_flight_doc
        else:
            variant = frappe.get_doc("Item", variant_code)

        # Specifications the websites use to tell variants apart: label -> chosen description.
        # Rows with no description carry no selector value, so they are left out.
        specifications = {}
        for spec in variant.get("neb_website_specifications") or []:
            if spec.label and spec.description:
                specifications[spec.label] = spec.description

        variant_payload.append({
            "identifier": variant.item_code,
            "retailSkuSuffix": variant.ifw_retailskusuffix,
            "specifications": specifications
        })

    return {
        "productExternalId": product_external_id,
        "variants": variant_payload
    }

def format_variant_problems(problems_by_site):
    """Render the per-website problems as something readable in a popup.

    One block per website, its problems as a plain list — no error codes, since they say nothing
    the sentence next to them doesn't already say.
    """
    blocks = ["<div style='margin-bottom:6px'>The item was saved, but these websites will not accept its variants:</div>"]

    for site_name, problems in problems_by_site.items():
        # A site can report the same problem several times — once per offending variant — and the
        # messages carry no variant name, so the repeats read as identical lines. Show each once.
        unique_problems = list(dict.fromkeys(problems))

        items = "".join("<li style='margin-bottom:2px'>{0}</li>".format(problem) for problem in unique_problems)
        blocks.append(
            "<div style='margin-bottom:8px'><b>{0}</b>"
            "<ul style='margin:4px 0 0 0; padding-left:18px'>{1}</ul></div>".format(site_name, items)
        )

    return "".join(blocks)

def post_variant_validation(config, payload, site_name):
    """Send one product's variants to one website; return what it objected to, in plain words.

    An empty list means the site is happy — nothing is reported on success, since this runs on
    every save and a confirmation each time would just be noise. The site's name is added by the
    caller, which groups the problems per website.
    """
    try:
        response = requests.post(
            config.api_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + config.api_key
            },
            # This runs inside a save, so a slow site must not hold the user's form open.
            timeout=10
        )
    except Exception as e:
        frappe.log_error(
            title="Variant validation request failed for {0}".format(site_name),
            message=frappe.get_traceback()
        )
        return ["This website could not be reached, so its variants were not checked."]

    if response.status_code != 200:
        frappe.log_error(
            title="Variant validation failed for {0}".format(site_name),
            message="Status: {0}\nResponse: {1}".format(response.status_code, response.text)
        )
        return ["This website returned an error ({0}), so its variants were not checked.".format(response.status_code)]

    try:
        data = response.json() or {}
    except ValueError:
        frappe.log_error(
            title="Variant validation returned invalid JSON for {0}".format(site_name),
            message=response.text
        )
        return ["This website sent back a response we could not read, so its variants were not checked."]

    if data.get("valid"):
        return []

    errors = data.get("errors") or []
    if not errors:
        return ["The variants were rejected, but no reason was given."]

    messages = []
    for error in errors:
        # The Message is a full sentence already; the Code repeats it in shouting case.
        message = error.get("Message") or error.get("message")
        if not message:
            message = "Rejected: {0}".format(error.get("Code") or error.get("code") or "no reason given")
        messages.append(frappe.utils.escape_html(message))

    return messages