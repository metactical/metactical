import CanadaPostManagement from "./components/canada_post/CanadaPostManagement.vue";
import Vue from "vue";

frappe.provide("metactical.canada_post");

metactical.canada_post.CanadaPostManagement = class {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.init();
	}

	init() {
		const vm = new Vue({
			el: "#canada_post_ui",
			render: h => h(CanadaPostManagement, { ref: "canadaPostPage" }),
		});

		this.vue_instance = vm.$refs.canadaPostPage;
		
		return this.vue_instance;
	}
};
