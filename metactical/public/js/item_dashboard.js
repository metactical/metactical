frappe.require("item-dashboard.bundle.js", function () {
    const _BaseItemDashboard = erpnext.stock.ItemDashboard;

    erpnext.stock.ItemDashboard = class ItemDashboard extends _BaseItemDashboard {
        get_item_dashboard_data(data, max_count, show_item) {
            if (!max_count) max_count = 0;
            if (!data) data = [];

            data.forEach(function (d) {
                d.actual_or_pending =
                    d.projected_qty +
                    d.reserved_qty +
                    d.reserved_qty_for_production +
                    d.reserved_qty_for_sub_contract;
                d.pending_qty = d.ordered_qty;
                d.total_reserved =
                    d.reserved_qty + d.reserved_qty_for_production + d.reserved_qty_for_sub_contract;

                max_count = Math.max(d.actual_or_pending, d.actual_qty, d.total_reserved, max_count);
            });

            let can_write = 0;
            if (frappe.boot.user.can_write.indexOf("Stock Entry") >= 0) {
                can_write = 1;
            }

            return {
                data: data,
                max_count: max_count,
                can_write: can_write,
                show_item: show_item || false,
            };
        }
    };
});