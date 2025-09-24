function edit_child_table(listview) {
    let selected_items = listview.get_checked_items();
    if (selected_items.length === 0) {
        frappe.msgprint(__("Please select at least one item to update."));
        return;
    }

    var all_fields = frappe.meta.get_docfields("Item", listview.doctype, true);

    let child_table_map = {};
    let child_table_options = [];
    let all_child_tables = [];

    all_fields.forEach((field) => {
        if ((field.fieldtype === "Table" || field.fieldtype === "Table MultiSelect") && field.options) {
            child_table_map[field.fieldname] = field.options;
            child_table_options.push(field.options);
            all_child_tables.push(field);
        }
    });


    if (Object.keys(child_table_map).length === 0) {
        frappe.msgprint(__("No child tables found in this doctype."));
        return;
    }

    let selected_items_name = selected_items.map(i => i.name)

    frappe.prompt([
        {
            label: __("Select Child Table"),
            fieldname: "child_table",
            fieldtype: "Select",
            options: child_table_options,
            reqd: 1,
        },
        {
            label: __("Update All Selected Items Based On"),
            fieldname: "update_based_on",
            fieldtype: "Select",
            options: selected_items_name.join("\n"),
        }
    ], function(values) {
        let child_fieldname = values.child_table;
        if (!child_fieldname) return;

        open_main_dialog(selected_items, values, all_child_tables);
    }, __("Select Child Table"), __("Load"));
}

function open_main_dialog(selected_items, values, all_child_tables) {
    let child_table = values.child_table;
    let selected_based_on = values.update_based_on;
    let fields = frappe.meta.get_docfields(child_table);
    let child_table_field = all_child_tables.find(f => f.options === child_table);

    console.log("Opening dialog for", child_table, "based on", selected_based_on);
    let item = null;
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Item",
            name: selected_based_on,
        },
        freeze: true,
        freeze_message: __("Loading item..."),
        async: false,
        callback: function(r) {
            if (r.message) {
                item = r.message;
            } else {
                frappe.msgprint(__("Could not load the selected item."));
                return;
            }
        }
    });

    if (child_table === "MT Item Website Specification") {
        fields = fields.map(f => {
            if (f.fieldname === "label") {
                f.onchange = function() {
                    console.log("Label changed to", this.value);
                    var grid_row = this.grid_row;
                    
                    frappe.call({
                        method: "metactical.custom_scripts.item.item.get_website_specification_description_options",
                        args: {
                            labels: [this.value],
                        },
                        callback: function (r) {
                            var descriptions = r.message.map(row => row.description)                            
                            let desc_field = grid_row.on_grid_fields_dict.description;

                            desc_field.df.options = descriptions;
                            desc_field.refresh();
                        },
                    })
                };
            }
            return f;
        });
    }


    let dialog = new frappe.ui.Dialog({
        title: __('Edit - {0}', [child_table_field.label]),
        size: 'extra-large ',
        fields: [
            {
                label: __(child_table_field.label),
                fieldname: "child_table",
                fieldtype: "Table",
                options: child_table,
                in_place_edit: true,
                fields: fields,
                get_data: function() {
                    return item[child_table_field.fieldname] || [];
                }
            }
        ],
        primary_action_label: __("Save"),
        primary_action(values) {
            let updates = dialog.fields_dict.child_table.get_value();
            console.log(selected_items, updates);
            frappe.call({
                method: "metactical.custom_scripts.item.item.update_child_table",
                args: {
                    item_names: selected_items.map(i => i.name),
                    child_table: child_table,
                    child_table_field: child_table_field.fieldname,
                    updates: updates,
                    updating: selected_based_on ? true : false,
                },
                freeze: true,
                freeze_message: __("Updating items..."),
                callback: function(r) {
                    frappe.msgprint(__("{0} items updated", [r.message]));
                    dialog.hide();
                    listview.refresh();
                }
            })
        },
    });

    dialog.show();
}


frappe.listview_settings['Item'] = {
    refresh: function(listview) {
        listview.page.add_action_item("Child Table Bulk Update", function() {
            edit_child_table(listview); 
        }); 
    }, 
};