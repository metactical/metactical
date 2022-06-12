frappe.pages['picklist-page'].on_page_load = function(wrapper) {
	new PicklistPage(wrapper)
}

class PicklistPage{
	constructor(wrapper) {
		//this.page = wrapper.page;
		this.make_page(wrapper);
		/*frappe.run_serially(
			() => this.make_page(wrapper)
		);*/
	}
	
	make_page(wrapper){
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'Electronic Picklist',
			single_column: true
		});
		this.wrapper = $(wrapper).find(".page-content");
		this.load_home();		
	}
	
	load_home(){
		const me = this;
		this.wrapper.html(frappe.render_template("picklist_page"));
		this.$single_order_button = this.wrapper.find("#single_order_button")
		this.$list_orders_btn = this.wrapper.find('#list_orders_button')
		this.$single_order_button.on('click', function(){
			frappe.run_serially([
				() => me.wrapper.html(frappe.render_template('items_list')),
				() => me.list_items()
			]);
		});
		this.$list_orders_btn.on('click', function(){
			frappe.run_serially([
				() => me.wrapper.html(frappe.render_template('orders_list')),
				() => me.list_orders()
			]);
		});
	}
	
	list_items(){
		const me = this;
		//this.wrapper.find('#picked-items-div').hide();
		this.$back_to_home = this.wrapper.find('#back-to-home');
		this.$load_picked = this.wrapper.find('#picked-items-btn');
		this.$back_to_pick = this.wrapper.find('#back-to-pick');
		this.$back_to_home.on('click', function(){
			me.load_home();
		});
		this.$load_picked.on('click', function(){
			$('#pick-list-items-div').hide();
			$('#picked-items-div').show();
		});
		this.$back_to_pick.on('click', function(){
			$('#pick-list-items-div').show();
			$('#picked-items-div').hide();
		});
	}
	
	list_orders(){
		const me = this;
	}
	
	load_picked(){
		const me = this;
		this.$wrapper.html(frappe.render_template('picked_items_list'));
		this.$back_to_list = this.$wrapper.find("#back-to-list");
	}
}
