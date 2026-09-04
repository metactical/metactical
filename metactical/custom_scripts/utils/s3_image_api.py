# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
import frappe
import requests
from frappe.utils import cint

from metactical.metactical.doctype.s3_settings.s3_settings import BASE_PREFIX as S3_BASE_PREFIX



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


def _plural(count, noun):
    """"1 image" / "3 images" — these messages are read by people, not parsed."""
    return "{0} {1}{2}".format(count, noun, "" if count == 1 else "s")


def _sb_site_name(price_list):
    """Readable website name for messages — price lists are named like "RET - Camo"."""
    if not price_list:
        return "(no price list)"
    return frappe.utils.escape_html(price_list.split("-")[-1].strip())


def _image_sync_key(item_code):
    return "sb_image_sync:{0}".format(item_code)


def set_image_sync_flag(item_code, user, reason="Loading images from Storebuilder"):
    frappe.cache().set_value(
        _image_sync_key(item_code),
        {"user": user, "started": frappe.utils.now(), "reason": reason},
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


def _flag_reason(flag):
    return (flag or {}).get("reason") or "Loading images from Storebuilder"


def _flag_started(flag):
    """When the job started, as 20-Aug-2026 12:47 rather than a raw timestamp."""
    started = (flag or {}).get("started")
    if not started:
        return "an unknown time"
    try:
        return frappe.utils.format_datetime(started, "dd-MMM-yyyy HH:mm")
    except Exception:
        return str(started)


def _flag_user(flag):
    """Who started it, by name — an email address means nothing to whoever is blocked."""
    user = (flag or {}).get("user")
    if not user:
        return "someone"
    try:
        return frappe.utils.get_fullname(user) or user
    except Exception:
        return user


def _flag_message(flag, item_code=None):
    """One short line: which item is held, what is running, who started it, and when."""
    line = "{0}. Started by {1} at {2}.".format(
        _flag_reason(flag), _flag_user(flag), _flag_started(flag)
    )
    return "{0}: {1}".format(item_code, line) if item_code else line


def _s3_lock_targets(item_code, variant_of=None):
    """Which items to hold while S3 work for this one is in flight.

    A variant's images live on its template's record, and the template is what anyone would
    drop and re-sync — so both have to be held, not just the item that changed.
    """
    return [code for code in dict.fromkeys([item_code, variant_of]) if code]


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
            "message": "<span class='text-warning'>{0} Please wait for it to finish.</span>".format(
                frappe.utils.escape_html(_flag_message(active_sync, item_code)))
        }]

    user = frappe.session.user
    set_image_sync_flag(item_code, user)

    # Queue before the detail pull, not after: the detail pull is a series of external calls
    # with no timeout, and if it hangs or raises here then an enqueue placed after it never
    # runs — leaving the flag raised for its full TTL with no job behind it to lower it.
    try:
        frappe.enqueue(
            "metactical.custom_scripts.utils.s3_image_api.sync_images_from_sb",
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

    # Imported here, not at module level: item.py is the Item controller and imports
    # this module back for its on_update hooks.
    from metactical.custom_scripts.item.item import get_item_details

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

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + (config.api_key or ""),
    }

    custom_header = frappe.get_doc("Item Import Validation", config.name).get_password("custom_header", raise_exception=False) if config.get("custom_header") else None
    if custom_header:
        headers.update({"X-Origin-Verify": custom_header})

    response = requests.post(
        config.api_url,
        json=body,
        headers=headers,
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
        stats["skipped"].add(s3_key)
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

    stats["uploaded"].add(s3_key)
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
    # uploaded/skipped hold S3 keys, not counts: websites share filenames, so the same file is
    # uploaded for the first site and found already present for the next. Counters would report
    # it twice and the totals would exceed the number of files that exist.
    stats = {"uploaded": set(), "skipped": set(), "errors": 0, "broken_links": 0}

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

            # site_found is one entry per size, so count the distinct images behind them —
            # "7 images" is what someone recognises, "28 files" is the machinery.
            distinct = len({(sku, order) for sku, order, _role in site_found})
            if distinct:
                messages.append(
                    "<span class='text-success'>{0}: found {1} ({2}).</span>".format(
                        site_name, _plural(distinct, "image"), _plural(len(site_found), "file"))
                )
            else:
                messages.append(
                    "<span class='text-warning'>{0}: no images found.</span>".format(site_name))

        if found:
            _save_imported_images(item_code, found, _doc_state, upsert_upload, resolve_item_codes)
            saved = len({(sku, order) for sku, order, _role in found})
            messages.append(
                "<span class='text-success'>{0} saved to this item.</span>".format(
                    _plural(saved, "image"))
            )
            uploaded = len(stats["uploaded"])
            already = len(stats["skipped"] - stats["uploaded"])
            if uploaded:
                messages.append(
                    "<span class='text-muted'>{0} newly copied into storage{1}.</span>".format(
                        _plural(uploaded, "file"),
                        "; {0} already there".format(already) if already else "")
                )
            elif already:
                messages.append(
                    "<span class='text-muted'>Every file was already in storage, so nothing "
                    "needed copying.</span>"
                )
        else:
            messages.append(
                "<span class='text-warning'>Nothing was saved to this item.</span>")

        if stats["broken_links"]:
            messages.append(
                "<span class='text-warning'>{0} listed by the website but not sent to us, so "
                "{1} skipped.</span>".format(
                    _plural(stats["broken_links"], "image"),
                    "it was" if stats["broken_links"] == 1 else "they were")
            )
        if stats["errors"]:
            messages.append(
                "<span class='text-danger'>{0} could not be copied. Please check the Error "
                "Log.</span>".format(_plural(stats["errors"], "file"))
            )
        if found:
            messages.append(
                "<span class='text-muted'>Use <b>Drop and Create In Websites</b> when you want "
                "the websites updated with these images.</span>"
            )

    except Exception:
        frappe.log_error(
            title="SB image import failed",
            message="{0}\n{1}".format(item_code, frappe.get_traceback()),
        )
        messages.append(
            "<span class='text-danger'>Loading the images failed. "
            "Please check the Error Log.</span>"
        )
    finally:
        clear_image_sync_flag(item_code)

    if user:
        frappe.publish_realtime(
            "msgprint",
            message="<b>Images loaded from Storebuilder for {0}</b><br><br>{1}".format(
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


def _rename_in_filename(path, old_sku, new_sku):
    """Swap the SKU at the front of a stored image path. None if it does not lead with it.

    Files are named `<sku>.<ext>` or `<sku>_<order>.<ext>`, so the SKU is a prefix of the stem.
    An image shared by several SKUs is stored under only the first one's name, so plenty of rows
    point at a file named for a different SKU — those are left alone rather than guessed at.
    """
    if not path:
        return None

    head, _, basename = path.rpartition("/")
    stem, dot, ext = basename.rpartition(".")
    if not dot:
        stem, ext = basename, ""

    if stem != old_sku and not stem.startswith(old_sku + "_"):
        return None

    new_stem = new_sku + stem[len(old_sku):]
    new_basename = "{0}.{1}".format(new_stem, ext) if ext else new_stem
    return "{0}/{1}".format(head, new_basename) if head else new_basename


def _s3_key_for(meta_path):
    """The bucket key for a stored path — the record drops the prefix the key carries."""
    if meta_path.startswith(META_PATH_PREFIX + "/"):
        return "{0}/{1}".format(S3_BASE_PREFIX, meta_path[len(META_PATH_PREFIX) + 1:])
    return meta_path


def _copy_s3_object(client, bucket, old_path, new_path, stats):
    """Copy one image to its new name, leaving the original in place.

    S3 has no rename, and the old key is deliberately kept: websites still hold URLs pointing at
    it, and deleting it would break every one of them until they are re-pushed.
    """
    old_key = _s3_key_for(old_path)
    new_key = _s3_key_for(new_path)

    try:
        client.head_object(Bucket=bucket, Key=new_key)
        stats["already_there"] += 1
        return True
    except Exception:
        pass

    try:
        client.head_object(Bucket=bucket, Key=old_key)
    except Exception:
        # The record can name a file that was never uploaded; the path still needs correcting.
        stats["source_missing"] += 1
        return False

    try:
        client.copy_object(
            Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key
        )
    except Exception:
        stats["errors"] += 1
        frappe.log_error(
            title="S3 SKU rename copy failed",
            message="{0} -> {1}\n{2}".format(old_key, new_key, frappe.get_traceback()),
        )
        return False

    stats["copied"] += 1
    return True


def apply_retail_sku_change_to_s3(old_sku, new_sku, item_code=None, lock_items=None, user=None):
    """Re-point this SKU's images and metadata after its retail SKU changed.

    Copies each image to its new name in S3 — the old object is left in place so websites
    holding the old URL keep working — then rewrites the SKU and the paths on every S3 record
    that referenced it.

    The websites are deliberately not told: this save does not fire the outbound webhook. They
    keep serving the old URLs, which still work, until someone does a drop and re-sync.
    """
    messages = []
    stats = {"copied": 0, "already_there": 0, "source_missing": 0, "errors": 0, "unmatched": 0}

    try:
        parents = frappe.get_all(
            "S3 Product Image SKU", filters={"nat_sku": old_sku}, pluck="parent"
        )
        records = sorted(set(parents))
        if not records:
            return ["<span class='text-warning'>This product has no images on file, so there "
                    "was nothing to rename.</span>"]

        settings = frappe.get_single("S3 Settings")
        client = settings.get_client()
        bucket = settings.nat_bucket_name

        for record in records:
            doc = frappe.get_doc("S3 Product Image Meta Data", record)

            for row in doc.nat_images:
                if row.nat_sku != old_sku:
                    continue
                for role in IMAGE_ROLES:
                    path = row.get("nat_" + role)
                    new_path = _rename_in_filename(path, old_sku, new_sku)
                    if not new_path:
                        if path:
                            stats["unmatched"] += 1
                        continue
                    if _copy_s3_object(client, bucket, path, new_path, stats):
                        row.set("nat_" + role, new_path)

            # The SKU is stamped on all three tables, so all three have to move together.
            for table in ("nat_skus", "nat_sites", "nat_images"):
                for row in doc.get(table) or []:
                    if row.nat_sku == old_sku:
                        row.nat_sku = new_sku

            if item_code and frappe.db.exists("Item", item_code):
                for row in doc.nat_skus:
                    if row.nat_sku == new_sku and not row.nat_item_code:
                        row.nat_item_code = item_code

            # Suppressed: the old objects were kept, so every URL a website holds still works.
            # A drop and re-sync is what tells them the new names, when someone chooses to.
            doc.nat_skip_website_push = 1
            doc.save(ignore_permissions=True)
            frappe.db.set_value(
                "S3 Product Image Meta Data", doc.name, "nat_skip_website_push", 0,
                update_modified=False,
            )
            doc.add_comment(
                "Comment",
                "Retail SKU changed from <b>{0}</b> to <b>{1}</b>. Images copied to the new "
                "name in S3; the originals were left in place. The websites were not notified, "
                "so drop and re-sync to update them.".format(old_sku, new_sku),
            )
            frappe.db.commit()

        renamed = stats["copied"] + stats["already_there"]
        if renamed:
            messages.append(
                "<span class='text-success'>{0} renamed to match the new code.</span>".format(
                    _plural(renamed, "image"))
            )
        if stats["source_missing"]:
            messages.append(
                "<span class='text-warning'>{0} listed here but missing from storage, so "
                "{1} kept the old name.</span>".format(
                    _plural(stats["source_missing"], "image"),
                    "it" if stats["source_missing"] == 1 else "they")
            )
        if stats["unmatched"]:
            messages.append(
                "<span class='text-warning'>{0} shared with another product code, so the old "
                "name was kept.</span>".format(_plural(stats["unmatched"], "image"))
            )
        if stats["errors"]:
            messages.append(
                "<span class='text-danger'>{0} could not be renamed. Please check the Error "
                "Log.</span>".format(_plural(stats["errors"], "image"))
            )
        if renamed:
            messages.append(
                "<span class='text-muted'>The old images were kept, so the websites carry on "
                "showing them. Use <b>Drop and Create In Websites</b> when you want the "
                "websites updated.</span>"
            )

    except Exception:
        frappe.log_error(
            title="S3 retail SKU change failed",
            message="{0} -> {1}\n{2}".format(old_sku, new_sku, frappe.get_traceback()),
        )
        messages.append(
            "<span class='text-danger'>Renaming the images failed. "
            "Please check the Error Log.</span>"
        )
    finally:
        for code in (lock_items or _s3_lock_targets(item_code)):
            clear_image_sync_flag(code)

    if user:
        frappe.publish_realtime(
            "msgprint",
            message="<b>Images renamed for {0}</b><br><span class='text-muted'>Product code "
                    "changed from {1} to {2}</span><br><br>{3}".format(
                        frappe.utils.escape_html(item_code or new_sku),
                        frappe.utils.escape_html(old_sku), frappe.utils.escape_html(new_sku),
                        "<br>".join(messages)),
            user=user,
        )

    return messages



def queue_retail_sku_change(doc):
    """Queue the S3 follow-up when an Item's retail SKU changed. Called from Item.on_update.

    Renaming or merging an Item does not by itself touch the images — the files are named from
    `ifw_retailskusuffix`, not the item code — so the SKU is what we watch. A rename, a merge
    and a plain edit all reach here through the same save.
    """
    # Bulk paths move thousands of rows and nobody is watching the result.
    if (frappe.flags.get("item_from_excel") or frappe.flags.in_import
            or frappe.flags.in_migrate or frappe.flags.in_install):
        return

    previous = doc.get_doc_before_save()
    if not previous:
        return

    old_sku = (previous.ifw_retailskusuffix or "").strip()
    new_sku = (doc.ifw_retailskusuffix or "").strip()
    if not old_sku or not new_sku or old_sku == new_sku:
        return

    user = frappe.session.user
    lock_items = _s3_lock_targets(doc.item_code, doc.variant_of)

    # Held for the same reason the import holds it: until the record and the files agree again,
    # a drop and re-sync would push a half-renamed image set to the websites.
    for code in lock_items:
        set_image_sync_flag(code, user, reason="Updating S3 for the new retail SKU")

    try:
        frappe.enqueue(
            "metactical.custom_scripts.utils.s3_image_api.apply_retail_sku_change_to_s3",
            queue="long",
            timeout=1500,
            job_name="s3-sku-rename-{0}".format(doc.item_code),
            # Only once the new SKU is actually committed — a rolled back save must not leave
            # S3 and the record renamed for a change that never happened.
            enqueue_after_commit=True,
            old_sku=old_sku,
            new_sku=new_sku,
            item_code=doc.item_code,
            lock_items=lock_items,
            user=user,
        )
    except Exception:
        for code in lock_items:
            clear_image_sync_flag(code)
        frappe.log_error(title="S3 SKU rename job not queued", message=frappe.get_traceback())
        raise


def block_if_image_job_running(item_code):
    """Stop a drop and re-sync while images for this item are still being written."""
    active = get_image_sync_flag(item_code)
    if active:
        frappe.throw("{0} Please wait for it to finish.".format(_flag_message(active, item_code)))
