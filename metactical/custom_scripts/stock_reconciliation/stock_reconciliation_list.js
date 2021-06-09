frappe.listview_settings['Stock Reconciliation'] = {
	onload: function (listview) {

        var df = {

            fieldname:'warehouse',

            label:"Warehouse",

            fieldtype: "Link",

            options:"Warehouse",

            onchange: function(){

         	  listview.start = 0;

               listview.refresh();

               listview.on_filter_change();

           },

        }

     listview.page.add_field(df);

    }
};