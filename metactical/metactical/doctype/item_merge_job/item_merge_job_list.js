frappe.listview_settings["Item Merge Job"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { Queued: "gray", Running: "blue", Done: "green", Failed: "red", Interrupted: "orange" }[doc.status];
		return [__(doc.status), colour || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Item Merge"), () => frappe.set_route("item-merge"));
	},
};
