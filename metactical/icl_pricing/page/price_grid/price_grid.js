// /app/price-grid/<Price Revision>. The grid itself is a Vue app in
// public/js/metactical_price_grid.bundle.js, loaded on first visit only.

frappe.pages["price-grid"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Price Revision"),
		single_column: true,
	});
	wrapper.grid_host = $('<div class="price-grid-host"></div>').appendTo(wrapper.page.main);
};

frappe.pages["price-grid"].on_page_show = function (wrapper) {
	const name = frappe.get_route()[1];
	frappe.require(["metactical_price_grid.bundle.js", "metactical_price_grid.bundle.css"]).then(() => {
		if (!wrapper.grid) {
			wrapper.grid = new metactical_pricing.PriceGrid(wrapper.page, wrapper.grid_host[0]);
		}
		wrapper.grid.load(name);
	});
	check_for_newer_screen();
};

// A tab keeps the code it first loaded. After an update, say so once.
function check_for_newer_screen() {
	const loaded = (frappe.boot.assets_json || {})["metactical_price_grid.bundle.js"];
	if (!loaded || frappe.pages["price-grid"].update_offered) return;
	frappe.call("metactical.pricing.api.screen_version").then((r) => {
		if (!r.message || r.message === loaded) return;
		frappe.pages["price-grid"].update_offered = true;
		frappe.confirm(
			__("This screen has been updated since you opened it. Reload now to get the new version? Save any unsaved prices first."),
			() => window.location.reload()
		);
	});
}
