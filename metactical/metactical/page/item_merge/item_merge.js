frappe.pages["item-merge"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Item Merge",
		single_column: true,
	});

	wrapper.item_merge_page = new ItemMergePage(wrapper);
};

// Routes inside the page (/app/item-merge/variants/RVX4184, /app/item-merge/jobs/IMJ-...) keep
// the same page loaded; tell the app when one is opened again from the address bar or history.
frappe.pages["item-merge"].on_page_show = function (wrapper) {
	wrapper.item_merge_page?.app.vue_instance?.syncRoute();
};

class ItemMergePage {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.main_section = this.page.main;
		this.main_section.append(`<div id="item_merge_ui"></div>`);
		this.app = new metactical.item_merge.ItemMerge(this.wrapper);

		var me = this;
		this.page.set_secondary_action("", () => {
			me.app.vue_instance.refresh();
		}, "refresh");
		this.page.add_menu_item(__("Item Merge Job list"), () => frappe.set_route("List", "Item Merge Job"));
		this.page.add_menu_item(__("Item Merge History"), () => frappe.set_route("List", "Item Merge History"));
	}
}
