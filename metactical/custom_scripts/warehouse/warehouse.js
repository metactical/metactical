frappe.ui.form.on("Warehouse", {
  refresh: function (frm) {
    frm.add_custom_button(__("Export Inventory to Excel"), function () {
      frappe.call({
        method: "metactical.custom_scripts.warehouse.warehouse.export_to_excel",
        args: {
          warehouse: frm.doc.name,
        },
        callback: function (r) {
          
        },
      });
    }, __("Export"));

    frm.add_custom_button(__("Export Stock Items With Rate"), function () {
      frappe.call({
        method: "metactical.custom_scripts.warehouse.warehouse.export_items_with_price_list",
        args: {
          warehouse: frm.doc.name,
        },
        callback: function (r) {
          
        },
      });
    }, __("Export"));
  },
  
});
