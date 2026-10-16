// Copyright (c) 2026, International Camouflage Ltd
// For license information, please see license.txt

frappe.ui.form.on("Price Revision", {
	refresh(frm) {
		frm.trigger("show_state");

		// The grid is where prices are worked; this form is the record.
		if (!frm.is_new()) {
			frm.add_custom_button(__("Open in Grid"), () =>
				frappe.set_route("price-grid", frm.doc.name)
			).addClass(frm.doc.docstatus === 0 ? "btn-primary" : "");
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Pending Review") {
			frm.add_custom_button(__("Apply Prices"), () => {
				frappe.confirm(
					removalNote(frm, __("Write {0} price change(s) to Item Price?", [frm.doc.total_price_changes || 0])),
					() => {
						frappe.call({
							method: "metactical.icl_pricing.doctype.price_revision.price_revision.apply_revision",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Writing prices…"),
							callback(r) {
								if (!r.message) return;
								frappe.show_alert(
									{ message: __("{0} prices written", [r.message.written]), indicator: "green" },
									7
								);
								frm.reload_doc();
							},
						});
					}
				);
			}).addClass("btn-primary");
		}

		if (frm.doc.status === "Applied") {
			frm.add_custom_button(__("Revert"), () => {
				frappe.confirm(
					__("Put every price this revision changed back to what it was?"),
					() => {
						frappe.call({
							method: "metactical.icl_pricing.doctype.price_revision.price_revision.revert_revision",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Reverting…"),
							callback(r) {
								if (!r.message) return;
								frappe.show_alert(
									{
										message: __("{0} prices put back, {1} left in place", [
											r.message.reverted,
											r.message.left_in_place,
										]),
										indicator: "orange",
									},
									7
								);
								frm.reload_doc();
							},
						});
					}
				);
			});

			frm.add_custom_button(__("What This Changed"), () => {
				frappe.set_route("List", "Price Revision Log", { price_revision: frm.doc.name });
			});
		}

	},

	// The headline is the point of the document: what it costs, what it earns,
	// and whether anything needs a person to look at it.
	show_state(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;

		const colour = { Draft: "blue", "Pending Review": "orange", Applied: "green", Reverted: "red", Cancelled: "grey" };
		const bits = [];

		if (frm.doc.avg_cost_change_pct) {
			bits.push(
				__("Cost {0}{1}%", [
					frm.doc.avg_cost_change_pct > 0 ? "+" : "",
					flt(frm.doc.avg_cost_change_pct, 1),
				])
			);
		}
		if (frm.doc.avg_margin_before || frm.doc.avg_margin_after) {
			bits.push(
				__("margin {0}% → {1}%", [
					flt(frm.doc.avg_margin_before, 1),
					flt(frm.doc.avg_margin_after, 1),
				])
			);
		}
		bits.push(__("{0} price change(s)", [frm.doc.total_price_changes || 0]));
		if (removals(frm)) bits.push(__("{0} price(s) to be removed", [removals(frm)]));

		let msg = bits.join(" · ");
		if (frm.doc.lines_needing_review) {
			msg += "<br>" + __("<b>{0} line(s) need a decision</b> — margin floor, missing price, or a rate that would sit at or under landed cost.", [frm.doc.lines_needing_review]);
		}

		frm.dashboard.set_headline(msg, frm.doc.lines_needing_review ? "orange" : colour[frm.doc.status] || "blue");
	},
});

// A removal deletes the item's price on that list; it never sets it to zero.
function removals(frm) {
	return (frm.doc.prices || []).filter((p) => p.action === "Delete").length;
}

function removalNote(frm, message) {
	const n = removals(frm);
	return n
		? message + "<br><br>" + __("<b>{0} price(s) will be removed</b> from their list, not set to zero. Revert puts them back.", [n])
		: message;
}
