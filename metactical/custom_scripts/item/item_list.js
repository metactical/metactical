function edit_child_table(listview) {
    var all_fields = frappe.meta.get_docfields("Item", listview.doctype, true);
    var child_fields = all_fields.filter((field) => field.fieldtype === "Table");
    if (child_fields.length === 0) {
        frappe.msgprint(__("No child tables found in this doctype."));
        return;
    }

    // create a dialog to select the child table
    var d = new frappe.ui.Dialog({
        title: __("Select Child Table to Edit"),
        fields: [
            {
                label: __("Child Table"),
                fieldname: "child_table",
                fieldtype: "Select",
                options: child_fields.map((field) => field.options),
                reqd: 1,
            },
        ],
        primary_action_label: __("Edit"),
        primary_action(values) {
            d.hide();
            var child_table = values.child_table;
            if (!child_table) {
                frappe.msgprint(__("Please select a child table."));
                return;
            }



            // Fetch existing data for the child table from the first selected item
            var first_item = listview.get_checked_items()[0];
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Item",
                    name: first_item.name,
                },
                callback: function (r) {
                    // if (r.message && r.message[child_table]) {
                    //     child_table_dialog.set_value("child_table_data", r.message[child_table]);
                    // }
                },
            });

            child_table_dialog.show();
        },
    });

    d.show();
}


function update_child_table_dialog(listview, child_table) {
    // Open the child table in a new dialog
    var child_table_dialog = new frappe.ui.Dialog({
        title: __("Edit {0}", [child_table]),
        fields: [
            {
                label: __(child_table),
                fieldname: "child_table_data",
                fieldtype: "Table",
                options: child_table,
                reqd: 1,
                in_place_edit: true,
                data: [],
            },
        ],
        primary_action_label: __("Save"),
        primary_action(child_values) {
            // Save the changes to all selected items
            var selected_items = listview.get_checked_items();
            if (selected_items.length === 0) {
                frappe.msgprint(__("Please select at least one item to update."));
                return;
            }

            var updates = child_values.child_table_data;

            // Prepare the updates for each selected item
            var promises = selected_items.map((item) => {
                return frappe.call({
                    method: "frappe.client.set_value",
                    args: {
                        doctype: "Item",
                        name: item.name,
                        fieldname: child_table,
                        value: updates,
                    },
                });
            });

            // Wait for all updates to complete
            Promise.all(promises)
                .then(() => {
                    frappe.msgprint(__("Child table updated successfully for selected items."));
                    child_table_dialog.hide();
                    listview.refresh();
                })
                .catch((error) => {
                    frappe.msgprint(__("Error updating child table: {0}", [error.message]));
                });
        },
    });

}

frappe.listview_settings['Item'] = {
   refresh: function(listview) {
       listview.page.add_inner_button("Edit Child Table", function() {
           edit_child_table(listview);
       });
   },
};