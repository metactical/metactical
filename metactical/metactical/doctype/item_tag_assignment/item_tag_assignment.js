// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt
var filter_group = null;

frappe.ui.form.on("Item Tag Assignment", {
	refresh(frm) {   
        var filters = JSON.parse(frm.doc.filters || "[]");
    
        filters && frappe.model.with_doctype("Item", () => {
            // Clear existing filters before adding new ones
            filter_group.clear_filters();
            filter_group.add_filters_to_filter_group(filters);
        });
    
        frappe.db.count("Item", {
            filters: filters
        }).then((total) => {
            frm.get_field("filters_detail").$wrapper.html(
                `<p><b>${__("Total Items:")}  ${total}</b></p>`
            );
        });
    },
    
	setup: function(frm) {
		frm.get_field("filters_detail").$wrapper.html(
			`<p><b>${__("Total Items:")}  0</b></p>`
		);

		frappe.model.with_doctype("Item", () => {
			filter_group = new frappe.ui.FilterGroup({
				parent: frm.get_field("conditions").$wrapper,
				doctype: "Item",
                default_filters: '[["Item","name","=","2"],["Item","ifw_discontinued","=",1]]',
				on_change: () => {
					if (!filter_group.get_filters().length) {
						frm.get_field("filters_detail").$wrapper.html(
							`<p><b>${__("Total Items:")}  0</b></p>`
						);
					}
					else{
						var total = frappe.db.count("Item", {
							filters: frm.events.get_filters(filter_group)
						})
						
						total.then((total) => {
							frm.get_field("filters_detail").$wrapper.html(
								`<p><b>${__("Total Items:")}  ${total}</b></p>`
							);
						});
					}

                    frm.set_value("filters", JSON.stringify(frm.events.get_filters(filter_group)));
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
