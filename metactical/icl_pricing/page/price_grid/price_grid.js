// /app/price-grid/<Price Revision>. The grid itself is a Vue app in
// public/js/metactical_price_grid.bundle.js, bundled natively into the desk via
// app_include_js / app_include_css (hooks.py), so it is already loaded here.

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
	if (!wrapper.grid) {
		wrapper.grid = new metactical_pricing.PriceGrid(wrapper.page, wrapper.grid_host[0]);
	}
	wrapper.grid.load(name);
	check_for_newer_screen();
};

// A tab keeps the code it first loaded. After an update, say so once. The
// version comes from Frappe's own bundle map (assets.json): what this tab
// loaded lives in frappe.boot.assets_json; the current one is fetched natively.
function check_for_newer_screen() {
	const loaded = (frappe.boot.assets_json || {})["metactical_price_grid.bundle.js"];
	if (!loaded || frappe.pages["price-grid"].update_offered) return;
	frappe.call("frappe.sessions.get_boot_assets_json").then((r) => {
		const current = (r.message || {})["metactical_price_grid.bundle.js"];
		if (!current || current === loaded) return;
		frappe.pages["price-grid"].update_offered = true;
		frappe.confirm(
			__("This screen has been updated since you opened it. Reload now to get the new version? Save any unsaved prices first."),
			() => window.location.reload()
		);
	});
}
