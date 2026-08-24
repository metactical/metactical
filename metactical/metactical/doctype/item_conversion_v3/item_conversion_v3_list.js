// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Item Conversion V3 List Bulk Delete" (List view).
// Adds a "Delete Drafts" bulk action that skips submitted rows.

frappe.listview_settings['Item Conversion V3'] = frappe.listview_settings['Item Conversion V3'] || {};
(function() {
    var prev = frappe.listview_settings['Item Conversion V3'].onload;
    frappe.listview_settings['Item Conversion V3'].onload = function(listview) {
        if (prev) prev(listview);
        listview.page.add_actions_menu_item(__('Delete Drafts'), function() {
            var picked = listview.get_checked_items() || [];
            if (!picked.length) {
                frappe.msgprint(__('Tick the rows you want to remove first.'));
                return;
            }
            var drafts = picked.filter(function(d) { return cint(d.docstatus) === 0; });
            var locked = picked.length - drafts.length;
            if (!drafts.length) {
                frappe.msgprint(__('Nothing selected is a draft. Submitted conversions must be cancelled first.'));
                return;
            }
            var names = drafts.map(function(d) { return d.name; });
            var msg = __('Permanently delete {0} draft {1}?', [names.length, 'conversion']);
            if (locked) {
                msg += '<br><br>' + __('{0} selected row(s) are not drafts and will be left alone.', [locked]);
            }
            msg += '<br><br><b>' + names.slice(0, 12).join('<br>') + '</b>'
                 + (names.length > 12 ? '<br>…' : '');
            frappe.confirm(msg, function() {
                frappe.call({
                    method: 'frappe.desk.reportview.delete_items',
                    args: { doctype: 'Item Conversion V3', items: names },
                    freeze: true,
                    freeze_message: __('Deleting {0}…', [names.length]),
                    callback: function() {
                        frappe.show_alert({ message: __('Deleted {0}', [names.length]), indicator: 'green' });
                        listview.refresh();
                    }
                });
            });
        });
    };
})();