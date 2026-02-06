frappe.pages['canada-post-management'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Canada Post Management',
		single_column: true
	});

	new CanadaPostManagementPage(wrapper);
};

class CanadaPostManagementPage {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.main_section = this.page.main;
		
		// Append the Vue app container
		this.main_section.append(`<div id="canada_post_ui"></div>`);
		
		// Initialize Vue app
		this.canada_post_app = new metactical.canada_post.CanadaPostManagement(this.wrapper);

		// Add refresh button
		var me = this;
		this.page.set_secondary_action("Refresh", () => {
			if (me.canada_post_app.vue_instance && me.canada_post_app.vue_instance.refresh) {
				me.canada_post_app.vue_instance.refresh();
			}
		}, "octicon octicon-sync");
	}
}