import ItemMerge from "./components/item_merge/ItemMerge.vue";
import { createApp, h, getCurrentInstance } from "vue";

frappe.provide("metactical.item_merge");

metactical.item_merge.ItemMerge = class {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.init();
	}

	init() {
		const app = createApp({
			setup() {
				const instance = getCurrentInstance();
				const root = () => instance?.refs?.root;

				function refresh() {
					if (root() && typeof root().refresh === "function") {
						root().refresh();
					}
				}
				function syncRoute() {
					if (root() && typeof root().syncRoute === "function") {
						root().syncRoute();
					}
				}
				return { refresh, syncRoute };
			},
			render() {
				return h(ItemMerge, { ref: "root" });
			},
		});

		const vm = app.mount("#item_merge_ui");

		this.vue_instance = vm;
		return this.vue_instance;
	}
};
