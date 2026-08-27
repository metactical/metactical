import time

import frappe
from frappe.utils import get_link_to_form
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle

# Item save fires an on_update webhook that (re)creates the item in the target system.
# That webhook runs in its own background job, so firing the inventory update right after
# item.save() can race it there and land on an item that doesn't exist yet. Delay the
# inventory update so the item webhook has time to land first.
INVENTORY_SYNC_DELAY_SECONDS = 10


def sync_s3_images(item_code, user=None):
    """Re-push the product's images by re-saving its S3 Uploader record.

    Nothing on the record changes — the save exists only to fire its on_update webhook, which
    runs on every save regardless of what was modified.
    """
    s3_record = frappe.db.get_value(
        "S3 Product Image Meta Data", {"nat_product_template": item_code}, "name"
    )

    if not s3_record:
        message = f"We don't have an S3 Uploader record for {item_code}, so its images were not synced."
        if user:
            frappe.publish_realtime("msgprint", message=message, user=user)
        return

    try:
        s3_doc = frappe.get_doc("S3 Product Image Meta Data", s3_record)
        s3_doc.save(ignore_permissions=True)

        # Say why the record was touched — the save changes nothing on it, so the timeline
        # would otherwise show an unexplained version bump.
        s3_doc.add_comment(
            "Comment",
            "Triggered from Drop and Create in Websites on {0}.".format(
                get_link_to_form("Item", item_code)
            )
        )

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            title="SB-Item Image Sync Error",
            message=f"Failed to re-sync S3 images for {item_code}: {str(e)} \n{frappe.get_traceback()}"
        )


@frappe.whitelist()
def receive_deletion_message(parsedContent):
    try:
        lead_source = parsedContent.get("publisher_site")

        price_list = frappe.db.get_value(
            "Lead Source",
            {"name": lead_source},
            "custom_neb_price_list"
        )
        slug = parsedContent.get("Entity").get("urlSlug") if parsedContent.get("Entity") else None
        
        item_deletion_log = frappe.db.get_value("Item Drop and Create Log", {"slug": slug, "status": "Issued", "deleted": 0, "price_list": price_list}, ["product", "owner", "name"], as_dict=True)
        if not item_deletion_log:
            frappe.log_error(
                title="SB-Item Deletion Log Not Found",
                message=f"No matching Item Drop and Create Log found for slug: {slug} and price_list: {price_list}"
            )
            return False


        item_code = item_deletion_log.product
        user = item_deletion_log.owner
        
        if not item_code or not price_list:
            frappe.log_error(
                title="SB-Item Deletion Message Error",
                message="Missing item_code or price_list in the message."
            )
            return False

        lock_key = f"item_deletion:{item_code}"

        with frappe.cache().lock(lock_key, timeout=60, blocking_timeout=60):
            frappe.db.commit()  
            
            all_logs = frappe.get_all(
                "Item Drop and Create Log",
                filters={"product": item_code, "status": "Issued", "deleted": 0, "price_list": price_list},
                order_by="creation asc",
                fields=["name", "price_list"]
            )

            for log in all_logs:
                if log.price_list == price_list:
                    doc = frappe.get_doc("Item Drop and Create Log", log.name)
                    doc.deleted = 1
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
                    break

            remaining_logs = frappe.get_all(
                "Item Drop and Create Log",
                filters={"product": item_code, "status": "Issued", "deleted": 0},
                pluck="name"
            )

            if not remaining_logs:
                completion_message = f"Item Deletion for {item_code} is completed in all price lists."
                frappe.publish_realtime("msgprint", message=completion_message, user=user)
                
                variants = frappe.get_all(
                    "Item",
                    filters={"variant_of": item_code},
                    pluck="name"
                )

                # Save every variant first (fast, no per-item wait), then wait once for the
                # item webhook to land, then sync inventory for all of them.
                pending_inventory_syncs = []
                for variant in variants:
                    item = frappe.get_doc("Item", variant)
                    item.save()

                    # Webhooks queue on frappe.db.after_commit and aren't actually enqueued
                    # until the next commit. Without this, the item's on_update webhook can
                    # still be sitting unenqueued when the delayed inventory sync below runs,
                    # so it gets no real head start.
                    frappe.db.commit()

                    is_product_bundle = frappe.db.exists('Product Bundle', item.item_code)
                    if is_product_bundle:
                        pending_inventory_syncs.append({
                            "item_code": item.item_code,
                            "net_available_bins": get_all_bins_for_product_bundle(item.item_code),
                            "bundle": True,
                            "voucher_type": item.doctype,
                        })
                    else:
                        pending_inventory_syncs.append({
                            "item_code": item.item_code,
                            "voucher_type": item.doctype,
                        })

                if pending_inventory_syncs:
                    time.sleep(INVENTORY_SYNC_DELAY_SECONDS)

                for sync_kwargs in pending_inventory_syncs:
                    if sync_kwargs.get("bundle"):
                        # Must run standalone (not frappe.enqueue) for bundles.
                        update_item_inventory_output(**sync_kwargs)
                    else:
                        frappe.enqueue(
                            update_item_inventory_output,
                            queue='default',
                            **sync_kwargs,
                        )

                sync_s3_images(item_code, user=user)

                all_logs = frappe.get_all(
                    "Item Drop and Create Log",
                    filters={"product": item_code, "status": "Issued", "deleted": 1},
                    order_by="creation asc",
                    fields=["name"]
                )

                for log in all_logs:
                    frappe.db.set_value("Item Drop and Create Log", log.name, "status", "Re-Created")
                    frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            title="SB-Item Deletion Message Processing Error",
            message=f"Error processing deletion message: {str(e)} \nContent: {parsedContent}"
        )
        return False