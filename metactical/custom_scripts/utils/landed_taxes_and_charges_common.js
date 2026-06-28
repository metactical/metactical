// Extend erpnext.landed_cost_taxes_and_charges to allow accounts with
// account_type = "Cost of Goods Sold" in the expense_account dropdown of
// Stock Entry → Additional Costs and Landed Cost Voucher → Taxes, without
// duplicating the core filter list.
const _core_setup_triggers = erpnext.landed_cost_taxes_and_charges.setup_triggers;

erpnext.landed_cost_taxes_and_charges.setup_triggers = function (doctype) {
	_core_setup_triggers.call(this, doctype);

	frappe.ui.form.on(doctype, {
		refresh: function (frm) {
			const tax_field = frm.doc.doctype == "Landed Cost Voucher" ? "taxes" : "additional_costs";
			const field = frm.fields_dict[tax_field].grid.get_field("expense_account");
			if (field._cogs_patched) return;

			const original_get_query = field.get_query;
			field.get_query = function () {
				const q = original_get_query.apply(this, arguments) || {};
				const acct = q.filters && q.filters.account_type;
				if (Array.isArray(acct) && acct[0] === "in" && Array.isArray(acct[1]) && !acct[1].includes("Cost of Goods Sold")) {
					q.filters.account_type = ["in", [...acct[1], "Cost of Goods Sold"]];
				}
				return q;
			};
			field._cogs_patched = true;
		},
	});
};
