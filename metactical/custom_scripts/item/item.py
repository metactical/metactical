import frappe
import json
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from erpnext.stock.doctype.item.item import Item
import datetime
import requests
from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost, RepostItemValuation

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

            from frappe.utils import add_days, getdate

            warehouses = [r.warehouse for r in repost_item_valuations if r.warehouse]
            warehouse_map = {
                r.name: r
                for r in frappe.get_all("Warehouse", filters={"name": ["in", warehouses]}, fields=["name", "company", "disabled"])
            }
            closing_date_cache = {}

            for repost_item_valuation in repost_item_valuations:
                wh = warehouse_map.get(repost_item_valuation.warehouse)
                if not wh or wh.disabled:
                    continue

                company = wh.company
                if company:
                    if company not in closing_date_cache:
                        closing_date_cache[company] = RepostItemValuation.get_max_period_closing_date(company)
                        
                    max_closing_date = closing_date_cache[company]
                    if max_closing_date and getdate("1900-01-01") <= getdate(max_closing_date):
                        frappe.db.set_value(
                            "Repost Item Valuation",
                            repost_item_valuation.name,
                            "posting_date",
                            add_days(max_closing_date, 1),
                        )

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

        # Image work lives in its own module; item.py just says when.
        from metactical.custom_scripts.utils import s3_image_api
        s3_image_api.queue_retail_sku_change(self)

        self.sync_retail_sku_to_inventory_output()

        if self.drop_and_create_in_websites:
            if not self.item_detail:
                frappe.throw("Please add at least one Item Detail to drop and create in websites.")

            # A drop and create re-pushes this product's images from the S3 record. Letting it run
            # while the image import is still writing that record would push a half-built image set.
            s3_image_api.block_if_image_job_running(self.item_code)

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
                
    def sync_retail_sku_to_inventory_output(self):
        previous = self.get_doc_before_save()
        if not previous:
            return

        new_sku = self.get("ifw_retailskusuffix")
        if previous.get("ifw_retailskusuffix") == new_sku:
            return

        frappe.db.set_value(
            "Item Inventory Output", {"item_code": self.name},
            "ifw_retailskusuffix", new_sku, update_modified=False,
        )

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
                    
                    headers = {
						"Authorization": "Bearer " + item_detail_api.api_key,
					}
                    
                    custom_header = frappe.get_doc("Item Import Validation", item_detail_api.name).get_password("custom_header") if item_detail_api.get("custom_header") else None
                    if custom_header:
                        headers["X-Origin-Verify"] = custom_header
                                            
                    response = requests.get(url, headers=headers)                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("Found") == False:
                            failed_slugs.append({
                                "message": f"<span class='text-danger'>Slug {item_detail.slug} not found in {site_name}</span>"
                            })
                        elif "error" in data:
                            failed_slugs.append({
								"message": f"<span class='text-danger'>Error fetching details for slug {item_detail.slug} from {site_name}: {data.get('error')}</span>"
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
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + config.api_key
    }

    # Stored as a Password field, so it has to be read back with get_password — a plain read
    # returns asterisks. Same header the other two callers of these settings send.
    custom_header = frappe.get_doc("Item Import Validation", config.name).get_password("custom_header") if config.get("custom_header") else None
    if custom_header:
        headers["X-Origin-Verify"] = custom_header

    try:
        response = requests.post(
            config.api_url,
            json=payload,
            headers=headers,
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