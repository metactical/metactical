import CanadaPostManagement from "./components/canada_post/CanadaPostManagement.vue";
import { createApp, h } from "vue";

frappe.provide("metactical.canada_post");

metactical.canada_post.CanadaPostManagement = class {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.init();
	}

	init() {
		const app = createApp({
			setup() {
				return {};
			},
			render() {
				return h(CanadaPostManagement, { ref: "canadaPostPage" });
			},
		});

		const vm = app.mount("#canada_post_ui");
		this.vue_instance = vm.$refs.canadaPostPage;
		
		return this.vue_instance;
	}
};
