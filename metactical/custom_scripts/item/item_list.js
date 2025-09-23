function edit_child_table(listview) {
    var all_fields = frappe.meta.get_docfields("Item", listview.doctype, true);

    let child_table_map = {};
    let child_table_options = [];

    all_fields.forEach((field) => {
        if (field.fieldtype === "Table" && field.options) {
            child_table_map[field.fieldname] = field.options;
            child_table_options.push({
                label: `${field.label}`,
                value: field.fieldname,
            });
        }
    });

    if (Object.keys(child_table_map).length === 0) {
        frappe.msgprint(__("No child tables found in this doctype."));
        return;
    }

    let dialog = new frappe.ui.Dialog({
        title: __('Bulk Edit Child Table'),
        fields: [
            {
                label: __("Child Table"),
                fieldname: "child_table",
                fieldtype: "Select",
                options: child_table_options,
                reqd: 1,
            },
            { fieldtype: "Section Break" },
            {
                label: __("Child Table Data"),
                fieldname: "child_table_data",
                fieldtype: "HTML",
            },
        ],
        primary_action_label: __("Save"),
        primary_action(values) {
            let child_fieldname = values.child_table;
            if (!dialog.fields_dict._table_control) {
                frappe.msgprint(__("Please select a child table and load data first."));
                return;
            }
            let updates = dialog.fields_dict._table_control.get_value();

            let selected_items = listview.get_checked_items();
            if (selected_items.length === 0) {
                frappe.msgprint(__("Please select at least one item to update."));
                return;
            }

            let promises = selected_items.map((item) => {
                return frappe.call({
                    method: "frappe.client.set_value",
                    args: {
                        doctype: "Item",
                        name: item.name,
                        fieldname: child_fieldname,
                        value: updates,
                    },
                });
            });

            Promise.all(promises).then(() => {
                frappe.msgprint(__("Child table updated successfully for selected items."));
                dialog.hide();
                listview.refresh();
            });
        },
    });

    dialog.fields_dict["child_table"].df.onchange = () => {
        let child_fieldname = dialog.get_value("child_table");
        if (!child_fieldname) return;

        let child_doctype = child_table_map[child_fieldname];
        if (!child_doctype) {
            frappe.msgprint(__("Could not resolve child doctype for " + child_fieldname));
            return;
        }

        let first_item = listview.get_checked_items()[0];
        if (!first_item) {
            frappe.msgprint(__("Please select at least one item."));
            return;
        }

        frappe.call({
            method: "frappe.client.get",
            args: { doctype: "Item", name: first_item.name, with_childnames: 1 },
        }).then(({ message }) => {
            let data = [];
            if (message && message[child_fieldname]) {
                data = message[child_fieldname];
            }

            dialog.fields_dict.child_table_data.$wrapper.empty();
            let table_control = frappe.ui.form.make_control({
                parent: dialog.fields_dict.child_table_data.$wrapper,
                df: {
                    fieldtype: "Table",
                    fieldname: "child_table_data",
                    label: __(child_doctype),
                    options: child_doctype,
                    in_place_edit: true,
                    get_data: () => data, 
                },
                render_input: true,
            });

            table_control.make();
            table_control.refresh();
            dialog.fields_dict._table_control = table_control;
        });
    };

    dialog.show();
}


frappe.listview_settings['Item'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Edit Child Table", function() {
            edit_child_table(listview); 
        }); 
    }, 
};
