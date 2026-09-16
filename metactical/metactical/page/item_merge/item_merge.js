// Who may use the page. The same pair is on the Page's own roles (which guard the desk route) and
// in ROLES in item_merge.py (which guards the API). This check is only so someone who does land
// here is told why it is empty, rather than watching an app fail every call.
const ITEM_MERGE_ROLES = ["System Manager", "Item Manager"];
const ROLE_NEEDED = "Item Manager";

frappe.pages["item-merge"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Item Merge",
		single_column: true,
	});

	if (!ITEM_MERGE_ROLES.some((role) => frappe.user.has_role(role))) {
		$(wrapper.page.main).html(`
			<div class="text-muted" style="padding: 3rem 1rem; text-align: center">
				<p style="font-size: var(--text-lg); margin-bottom: 0.5rem">
					${__("You need the {0} role to use Item Merge.", [frappe.utils.escape_html(ROLE_NEEDED)])}
				</p>
				<p class="mb-0">${__("Ask a System Manager to add it to your user.")}</p>
			</div>`);
		return;
	}

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
		// Single doctypes: the Form route needs the docname too, which for a Single is its own name.
		// frappe.set_route("Form", "X") alone lands on a blank form (show_doc reads route.slice(2)).
		const open_single = (doctype) => frappe.set_route("Form", doctype, doctype);
		// what the merge carries between items, and the Metabase credentials the website steps use
		this.page.add_menu_item(__("Item Merge Settings"), () => open_single("Item Merge Settings"));
	}
}
