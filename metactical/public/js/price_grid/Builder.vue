<template>
	<div class="pg-builder">
		<div class="pg-builder__title">{{ t("New price revision") }}</div>
		<div class="pg-muted pg-builder__hint">
			{{ t("No PO needed. Fill in any of these; they combine. Code, retail SKU and template fields take one term (matched anywhere) or a pasted list, one per line (matched exactly).") }}
		</div>
		<div ref="fields"></div>
		<div class="pg-builder__actions">
			<button class="btn btn-default btn-sm" :disabled="busy" @click="find">{{ t("Find Items") }}</button>
			<template v-if="result">
				<span v-if="!result.suppliers.length" class="pg-muted">{{ t("Nothing with a supplier cost matches.") }}</span>
				<template v-else-if="result.suppliers.length === 1 || picked">
					<button class="btn btn-primary btn-sm" :disabled="busy || tooMany" @click="build">
						{{ t("Build Revision") }} · {{ chosen.items }} {{ t("items") }} · {{ chosen.supplier }}
					</button>
					<span v-if="tooMany" class="pg-bad">{{ t("Over the {0}-item limit. Narrow it down.", [result.limit]) }}</span>
					<span v-else-if="chosen.items > result.background_threshold" class="pg-muted">
						{{ t("Large selection: it builds in the background, in batches, and the grid shows its progress.") }}
					</span>
				</template>
			</template>
		</div>
		<div v-if="result && result.suppliers.length > 1 && !picked" class="pg-builder__choices">
			<div class="pg-muted">{{ t("These items come from more than one supplier. A revision takes its costs from one supplier; pick it:") }}</div>
			<button v-for="s in result.suppliers" :key="s.price_list" class="btn btn-default btn-xs" @click="picked = s">
				{{ s.supplier }} · {{ s.items }}
			</button>
		</div>
	</div>
</template>

<script>
const BUILD = "metactical.pricing.build.";
const FIELDS = ["supplier", "brand", "item_group", "item_codes", "retail_skus", "template_skus"];

export default {
	name: "Builder",
	data() {
		return { result: null, picked: null, busy: false };
	},
	computed: {
		chosen() {
			return this.picked || (this.result && this.result.suppliers[0]) || {};
		},
		tooMany() {
			return this.chosen.items > this.result.limit;
		},
	},
	mounted() {
		const reset = () => this.reset();
		const list = (fieldname, label, placeholder) => ({
			fieldname, fieldtype: "Small Text", label, change: reset,
			description: placeholder,
		});
		this.form = new frappe.ui.FieldGroup({
			body: this.$refs.fields,
			fields: [
				{ fieldname: "supplier", fieldtype: "Link", options: "Supplier", label: __("Supplier"), change: reset },
				{ fieldname: "brand", fieldtype: "Link", options: "Brand", label: __("Brand"), change: reset },
				{ fieldname: "item_group", fieldtype: "Link", options: "Item Group", label: __("Item Group"), change: reset,
					description: __("Includes its sub-groups") },
				{ fieldtype: "Column Break" },
				list("item_codes", __("Item Code"), __("Code or barcode")),
				{ fieldtype: "Column Break" },
				list("retail_skus", __("Retail SKU"), __("ifw retail SKU")),
				{ fieldtype: "Column Break" },
				list("template_skus", __("Template SKU"), __("Template code or its retail SKU: every variant under it")),
			],
		});
		this.form.make();
	},
	methods: {
		t(text, args) {
			return __(text, args);
		},
		values() {
			const v = {};
			for (const f of FIELDS) {
				const x = this.form.get_value(f);
				if (x && String(x).trim()) v[f] = x;
			}
			return v;
		},
		reset() {
			this.result = null;
			this.picked = null;
		},
		find() {
			const v = this.values();
			if (!Object.keys(v).length) {
				frappe.msgprint(__("Fill in at least one field."));
				return;
			}
			this.busy = true;
			// frappe.call returns a jQuery promise, which has no .finally
			Promise.resolve(frappe.call({ method: BUILD + "preview_selection", args: v }))
				.then((r) => {
					this.result = r.message;
					this.picked = null;
				})
				.finally(() => (this.busy = false));
		},
		build() {
			const v = this.values();
			v.supplier = this.chosen.supplier;
			this.busy = true;
			Promise.resolve(frappe.call({ method: BUILD + "from_selection", args: v, freeze: true, freeze_message: __("Setting up the revision…") }))
				.then((r) => frappe.set_route("price-grid", r.message))
				.finally(() => (this.busy = false));
		},
	},
};
</script>
