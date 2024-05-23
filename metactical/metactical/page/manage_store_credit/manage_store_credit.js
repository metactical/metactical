frappe.pages['manage-store-credit'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Transfer/Create Store Credit',
		single_column: true
	});

	var store_credit = new StoreCredit(wrapper)
	store_credit.setup()
}

class StoreCredit {
	constructor(wrapper){
		this.page = wrapper.page
		this.wrapper = wrapper
	}

	setup(){
		this.main_section = this.page.main;

		// create a link field for the sales invoice
		var sales_invoice_field = 

		this.main_section.append("<div id='store-credit-root'></div>")
		var vue_instance = new metactical.store_credit.StoreCredit({
			parent: this.wrapper
		})
	}
	
	

}