// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Item Group", {
    refresh: function (frm) {
        frm.add_custom_button(__("Copy spec to items"), function () {
            
            frappe.prompt([{
                label: 'Overwrite existing spec?',
                fieldname: 'overwrite',
                fieldtype: 'Check'
            },{
                label: 'Add missing labels to existing items?',
                fieldname: 'add_missing_labels',
                fieldtype: 'Check'
            }], 
            (values) => {
                if (values.overwrite){
                    frappe.confirm('This will clear all existing specs on items in this group and copy the specs from this group. Are you sure you want to proceed?',
                        () => {
                            copy_specs(frm.doc.name, values.overwrite, values.add_missing_labels);
                        },)
                } else {
                    copy_specs(frm.doc.name, values.overwrite, values.add_missing_labels);
                }
                
                
            });

            
		});
	},
});

function copy_specs(item_group, overwrite, add_missing_labels) {
    frappe.call({
        method: "metactical.custom_scripts.item_group.item_group.copy_specification_from_item_group",
        args: {
            item_group: item_group,
            overwrite: overwrite,
            add_missing_labels: add_missing_labels
        }
    });
}