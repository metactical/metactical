import frappe

BATCH_SIZE = 1000


def execute():
    """Bring every Item Inventory Output's Retail SKU into line with its Item.

    Item Inventory Output.ifw_retailskusuffix is declared with
    fetch_from="item_code.ifw_retailskusuffix", but a fetch_from only fires when
    the dependent document is itself saved, and this one also carries
    fetch_if_empty=1 so it will not overwrite a value that is already there.
    Editing an Item's Retail SKU therefore left the inventory output showing the
    old one, with nothing to ever correct it.

    CustomItem.sync_retail_sku_to_inventory_output now keeps the two in step on
    every save. This patch cleans up the rows that drifted before that existed.

    Runs in batches of BATCH_SIZE, committing as it goes, so a large site does
    not build one enormous transaction. Corrected rows stop matching the query,
    so each pass simply picks up the next batch.

    Safe to re-run: it only touches rows that actually disagree.
    """
    total = 0

    while True:
        rows = frappe.db.sql(
            """
            select iio.name, iio.ifw_retailskusuffix as had,
                   item.ifw_retailskusuffix as should_be
            from `tabItem Inventory Output` iio
            join `tabItem` item on item.name = iio.item_code
            where ifnull(iio.ifw_retailskusuffix, '') != ifnull(item.ifw_retailskusuffix, '')
            limit %s
            """,
            BATCH_SIZE,
            as_dict=True,
        )
        if not rows:
            break

        for row in rows:
            frappe.db.set_value(
                "Item Inventory Output", row.name, "ifw_retailskusuffix",
                row.should_be, update_modified=False,
            )

        frappe.db.commit()
        total += len(rows)
        print("Item Inventory Output retail SKU: %d corrected so far" % total)

        # A corrected row no longer matches the query, so a short batch means
        # there is nothing left. Guarding on this also stops the loop dead if a
        # row ever refuses to update, rather than spinning forever.
        if len(rows) < BATCH_SIZE:
            break

    # rows whose item no longer exists cannot be synced from anything - report
    # them rather than leaving them silently wrong
    orphans = frappe.db.sql(
        """
        select count(*) from `tabItem Inventory Output` iio
        left join `tabItem` item on item.name = iio.item_code
        where ifnull(iio.item_code, '') != '' and item.name is null
        """
    )[0][0]

    if total or orphans:
        print(
            "Item Inventory Output retail SKU: %d corrected, %d orphan(s) skipped"
            % (total, orphans)
        )
