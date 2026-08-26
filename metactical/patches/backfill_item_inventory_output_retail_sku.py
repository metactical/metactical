import frappe

BATCH_SIZE = 1000


def execute():
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
