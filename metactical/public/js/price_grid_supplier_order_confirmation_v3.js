// Loaded onto the Procurement V3 confirmation by metactical's ICL Pricing module.
// When the supplier confirmed any line at a different cost, the confirmation
// offers the price revision grid for it.

frappe.ui.form.on("Supplier Order Confirmation V3", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2) return;

		const changed = (frm.doc.items || []).filter(
			(r) => flt(r.confirmed_rate) && Math.abs(flt(r.rate_variance_pct)) > 0.001
		);
		if (!changed.length) return;

		frappe
			.call({
				method: "metactical.pricing.api.revisions_for_confirmation",
				args: { confirmation: frm.doc.name },
			})
			.then((r) => {
				const live = (r.message || []).find((x) => x.status !== "Reverted");
				const open = () =>
					frappe
						.call({
							method: "metactical.pricing.api.open_for_confirmation",
							args: { confirmation: frm.doc.name },
							freeze: true,
							freeze_message: __("Working out new prices…"),
						})
						.then((res) => frappe.set_route("price-grid", res.message));

				const btn = frm.add_custom_button(live ? __("Price Revision") : __("Revise Prices"), open);
				if (!live) btn.addClass("btn-primary");

				if (!live) {
					frm.dashboard.set_headline_alert(
						__("{0} line(s) confirmed at a different cost. Retail prices haven't been revised yet.", [changed.length]),
						"orange"
					);
				} else {
					const colour = { Draft: "blue", "Pending Review": "orange", Applied: "green" }[live.status] || "gray";
					let msg = __("Price revision {0}: {1}", [
						`<a href="/app/price-grid/${encodeURIComponent(live.name)}">${live.name}</a>`,
						__(live.status),
					]);
					if (live.status !== "Applied" && live.lines_needing_review)
						msg += " · " + __("{0} need a decision", [live.lines_needing_review]);
					frm.dashboard.set_headline_alert(msg, colour);
				}
			});
	},
});
