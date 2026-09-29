// Relearn every markup from the Item Prices ICL already has. Rows marked
// Locked are left alone.
frappe.listview_settings["Pricing Matrix"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Rebuild from History"), () => {
			frappe.confirm(
				__("Recalculate every markup from current Item Prices? Locked rows are kept as they are."),
				() =>
					frappe
						.call({
							method: "metactical.pricing.matrix.rebuild_from_history",
							freeze: true,
							freeze_message: __("Learning markups…"),
						})
						.then((r) => {
							frappe.show_alert({ message: __("{0} markups updated", [r.message.pairs_written]), indicator: "green" }, 5);
							listview.refresh();
						})
			);
		});
	},
};
