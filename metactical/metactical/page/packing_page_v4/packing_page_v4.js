frappe.pages['packing-page-v4'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Packing Page - V4',
		single_column: true
	});

	var packing_page = new PackingPageV4(wrapper);
	$(wrapper).on('show', function() {
		packing_page.show();
	});

	$(wrapper).on('hide', function() {
		packing_page.hide();
	});
}

class PackingPageV4 {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.main_section = this.page.main;

		console.log(this.page.page_actions)

	}

	show() {
		metactical.packing_page = new metactical.packing_page.PackingPageV4({parent: this});
		this.page.add_menu_item('Refresh', () => {
			
		}, true);

		// change type of a button in a group
		this.page.change_inner_button_type('Delete Posts', 'Actions', 'danger');
		this.page.set_primary_action('New', () => {});

		this.page.add_menu_item('Settings', () => {
			console.log("Print button clicked");
		});

	}

	hide() {
		this.page.clear_primary_action();
	}

	load_page() {
		this.main_section.empty();
		this.main_section.append(frappe.render_template('packing_page_v4', {"no_data_feedback": "No data to display"}));
	}
}