import { createApp, reactive } from "vue";
import PriceGrid from "./price_grid/PriceGrid.vue";

frappe.provide("metactical_pricing");

metactical_pricing.PriceGrid = class {
	constructor(page, el) {
		this.state = reactive({ name: null, nonce: 0 });
		this.app = createApp(PriceGrid, { page, state: this.state });
		this.app.mount(el);
	}

	load(name) {
		this.state.name = name ? decodeURIComponent(name) : null;
		this.state.nonce += 1;
	}
};
