// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Tag Assignment", {
	refresh(frm) {

	},
    setup: function(frm) {
		frm.get_field("conditions").$wrapper.html(
			`<p><b>${__("Total Items:")}  0</b></p>`
		);

		frappe.model.with_doctype("Item", () => {
			filter_group = new frappe.ui.FilterGroup({
				parent: frm.get_field("conditions").$wrapper,
				doctype: "Item",
				on_change: () => {
					if (!filter_group.get_filters().length) {
						frm.get_field("conditions").$wrapper.html(
							`<p><b>${__("Total Items:")}  0</b></p>`
						);
					}
					else{
						var total = frappe.db.count("Item", {
							filters: frm.events.get_filters(filter_group)
						})
						
						total.then((total) => {
							frm.get_field("conditions").$wrapper.html(
								`<p><b>${__("Total Items:")}  ${total}</b></p>`
							);
						});
					}
				},
			});
		});

	},

	get_filters(filter_group) {
		return filter_group.get_filters().map((filter) => {
			return filter.slice(0, 4);
		});
	}
});
