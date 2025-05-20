// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Item Group", {
    refresh: function (frm) {
        frm.add_custom_button(__("Copy spec to items"), function () {
            frappe.confirm('This will add the missing website specification labels to the items. Do you want to continue?',
                () => {
                    copy_specs(frm.doc.name);
                })

		});
	},
});

function copy_specs(item_group) {
    frappe.call({
        method: "metactical.custom_scripts.item_group.item_group.copy_specifications_to_items",
        args: {
            item_group: item_group,
            add_missing_labels: 1
        },
        callback: function (r) {
            frappe.msgprint("The task has been enqueued as a background job")
        }
    });
}