frappe.ui.form.on("Warehouse", {
  refresh: function (frm) {
    frm.add_custom_button(__("Export Inventory to Excel"), function () {
      frappe.call({
        method: "metactical.custom_scripts.warehouse.warehouse.export_to_excel",
        args: {
          warehouse: frm.doc.name,
        },
        callback: function (r) {
          var file_url = r.message;
          if (file_url) {
            frappe.msgprint(
              __(
                "Warehouse data exported successfully. Please click on the link to download."
              )
            );
            window.open(file_url, "_blank");
          }
        },
      });
    });
  },
});
