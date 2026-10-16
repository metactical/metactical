import time

import frappe
from frappe.utils import get_link_to_form
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle

# Item save fires an on_update webhook that (re)creates the item in the target system.
# That webhook runs in its own background job, so firing the inventory update right after
# item.save() can race it there and land on an item that doesn't exist yet. Delay the
# inventory update so the item webhook has time to land first.
INVENTORY_SYNC_DELAY_SECONDS = 10
# How long to wait for the remaining sites after the first one confirms its drop. Once this
# elapses the item is re-created with whatever has come back, so a single silent site can't
# hold the product hostage. Kept under the `long` queue's job timeout (1500s) since the
# watchdog sleeps this long inside one job.
RECREATE_TIMEOUT_SECONDS = 60

def _delayed_update_item_inventory_output(**kwargs):
    time.sleep(INVENTORY_SYNC_DELAY_SECONDS)
    update_item_inventory_output(**kwargs)


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
        frappe.log_error(title="SB-Item Image Sync Skipped", message=message)
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


def _completed_batch(item_code):
    """The logs of the drop that has just finished for this product."""
    return frappe.get_all(
        "Item Drop and Create Log",
        filters={"product": item_code, "status": "Issued", "deleted": 1},
        order_by="creation asc",
        fields=["name", "skip_recreate"],
    )


def _batch_skips_recreate(item_code):
    """Was this drop asked for without a re-create?

    Every row has to say so. A mixed batch is not something any code here produces, so it means
    something else wrote into it - re-create, which is the old behaviour, and say so in the log.
    """
    logs = _completed_batch(item_code)
    if not logs:
        return False
    if all(log.skip_recreate for log in logs):
        return True
    if any(log.skip_recreate for log in logs):
        frappe.log_error(
            title="SB-Item Deletion Mixed Skip Recreate",
            message=f"{item_code} has a drop batch where only some logs carry skip_recreate; "
                    f"re-creating as usual. Logs: {[log.name for log in logs]}"
        )
    return False


def _close_batch(item_code, status):
    """Land the finished batch on its final status.

    Closes every still-open (Issued) log for the product, not only the ones that came back
    deleted=1: when the timeout watchdog finalises a batch, the sites that never confirmed
    still carry deleted=0, and leaving them Issued would keep the batch open forever. In the
    all-responded path every Issued log is already deleted=1, so this closes the same rows.

    set_value, not save: it bypasses on_update, so the drop webhook does not see the flip.
    """
    open_logs = frappe.get_all(
        "Item Drop and Create Log",
        filters={"product": item_code, "status": "Issued"},
        pluck="name",
    )
    for name in open_logs:
        frappe.db.set_value("Item Drop and Create Log", name, "status", status)
    frappe.db.commit()


def _batch_is_open(item_code):
    """A batch stays open while any of its logs is still Issued; _close_batch flips them away.

    This is the idempotency guard shared by the all-responded path and the timeout watchdog:
    whichever runs first re-creates and closes the batch, and the other becomes a no-op.
    """
    return bool(
        frappe.db.exists("Item Drop and Create Log", {"product": item_code, "status": "Issued"})
    )


def _all_sites_responded(item_code):
    """True once no Issued log is still waiting on its site's deletion confirmation."""
    return not frappe.get_all(
        "Item Drop and Create Log",
        filters={"product": item_code, "status": "Issued", "deleted": 0},
        pluck="name",
    )

def _recreate_item(item_code, user):
    """Re-create the product on the websites and close its drop batch.

    Idempotent and lock-guarded: whichever of the all-responded path or the timeout watchdog
    reaches it first does the work and closes the batch; a later caller finds the batch closed
    and returns without touching anything. The caller must already hold the item_deletion lock.
    """
    if not _batch_is_open(item_code):
        return

    # The re-create is the item.save() loop below: each save re-fires the Item on_update
    # webhooks, which push the variants back to the sites. A merge that consolidated this
    # product away asks for the drop without that, by setting skip_recreate on every log in
    # the batch - there is nothing left to push back.
    if _batch_skips_recreate(item_code):
        frappe.publish_realtime(
            "msgprint",
            message=f"{item_code} was dropped from the websites without being re-created.",
            user=user,
        )
        _close_batch(item_code, "Dropped")
        return

    variants = frappe.get_all(
        "Item",
        filters={"variant_of": item_code},
        pluck="name"
    )

    for variant in variants:
        item = frappe.get_doc("Item", variant)
        # ignore_permissions because we're now acting as the log's owner, who
        # isn't necessarily allowed to write Items.
        item.save(ignore_permissions=True)

        # Webhooks queue on frappe.db.after_commit and aren't actually enqueued
        # until the next commit. Without this, the item's on_update webhook can
        # still be sitting unenqueued when the delayed inventory sync below runs,
        # so it gets no real head start.
        frappe.db.commit()

        is_product_bundle = frappe.db.exists('Product Bundle', item.item_code)
        if is_product_bundle:
            all_bins = get_all_bins_for_product_bundle(item.item_code)
            _delayed_update_item_inventory_output(
                item_code=item.item_code,
                net_available_bins=all_bins,
                bundle=True,
                voucher_type=item.doctype,
            )
        else:
            frappe.enqueue(
                _delayed_update_item_inventory_output,
                queue='default',
                item_code=item.item_code,
                voucher_type=item.doctype,
            )

    sync_s3_images(item_code, user=user)

    _close_batch(item_code, "Re-Created")


def schedule_recreate_watchdog(item_code, user):
    """Ensure a single timeout watchdog exists for this drop batch.

    Scheduled when the batch is created, so the item is re-created even if not one site ever
    confirms its drop - when the product was already gone on a site there is nothing to delete
    there and so nothing to report back, and with no confirmation receive_deletion_message never
    runs to start the clock. deduplicate + a per-item job_id means the copy the first
    confirmation would have enqueued collapses into this one, so the re-create - and the
    item.save() it does per variant - still happens exactly once, not once per site.
    """
    frappe.enqueue(
        _recreate_after_timeout,
        queue="long",
        timeout=RECREATE_TIMEOUT_SECONDS + 300,
        job_id=f"recreate_after_timeout::{item_code}",
        deduplicate=True,
        item_code=item_code,
        user=user,
    )


def _recreate_after_timeout(item_code, user):
    """Fallback for sites that never confirm their drop.

    Enqueued when the first site responds; sleeps out the grace period, then forces the
    re-create if the batch is still open. If every site confirmed in the meantime, the
    all-responded path has already closed the batch and this is a no-op. This runs in a
    worker (as the log's owner, captured at enqueue time) rather than off a scheduled task.
    """
    time.sleep(RECREATE_TIMEOUT_SECONDS)

    lock_key = f"item_deletion:{item_code}"
    with frappe.cache().lock(lock_key, timeout=60, blocking_timeout=60):
        # See the note in receive_deletion_message: commit so this transaction sees the log
        # flips other consumers committed while we were sleeping.
        frappe.db.commit()

        if not _batch_is_open(item_code):
            return

        pending = frappe.get_all(
            "Item Drop and Create Log",
            filters={"product": item_code, "status": "Issued", "deleted": 0},
            pluck="price_list",
        )
        frappe.publish_realtime(
            "msgprint",
            message=(
                f"Re-creating {item_code} after waiting {RECREATE_TIMEOUT_SECONDS // 60} "
                f"minutes; these price lists never confirmed the drop: {pending}."
            ),
            user=user,
        )
        _recreate_item(item_code, user)


@frappe.whitelist()
def receive_deletion_message(parsedContent):
    switched_user = False
    try:
        lead_source = parsedContent.get("publisher_site")
        # frappe.log_error(
        #     title="SB-Item Deletion Message Received",
        #     message=f"Received deletion message for lead source: {lead_source} \nContent: {parsedContent}"
        # )
        
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

        # This runs from the message consumer, i.e. as Administrator, so every save below
        # would otherwise be stamped "last updated by Administrator". Act as the user who
        # created the log instead, so the person who triggered the drop and create is the
        # one recorded on the documents it touches.
        if user and user != frappe.session.user:
            frappe.set_user(user)
            switched_user = True

        lock_key = f"item_deletion:{item_code}"

        with frappe.cache().lock(lock_key, timeout=60, blocking_timeout=60):
            frappe.db.commit()

            # Whether any site had already confirmed before this message. If none had, this
            # message is the first response and we start the grace-period clock for the rest
            # (below). Evaluated before the flip so "no deleted=1 yet" means "first".
            first_response = not frappe.db.exists(
                "Item Drop and Create Log",
                {"product": item_code, "status": "Issued", "deleted": 1},
            )

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

            if _all_sites_responded(item_code):
                completion_message = f"Item Deletion for {item_code} is completed in all price lists."
                frappe.publish_realtime("msgprint", message=completion_message, user=user)
                _recreate_item(item_code, user)
            elif first_response:
                # First site is in; give the rest RECREATE_TIMEOUT_SECONDS to catch up before
                # we re-create anyway. The batch already schedules a watchdog at drop time, so
                # this is normally a deduplicated no-op; it stays as a safety net for batches
                # created outside create_item_deletion_log (e.g. the merge paths).
                schedule_recreate_watchdog(item_code, user)

    except Exception as e:
        frappe.log_error(
            title="SB-Item Deletion Message Processing Error",
            message=f"Error processing deletion message: {str(e)} \nContent: {parsedContent}"
        )
        return False
    finally:
        if switched_user:
            frappe.set_user("Administrator")