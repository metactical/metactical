frappe.ui.form.on("Bulk Update Rule", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Preview"),
                () => frm.trigger("show_preview"),
                __("Actions")
            );
            frm.add_custom_button(
                __("Execute"),
                () => frm.trigger("execute_rule"),
                __("Actions")
            );
        }

        frappe.realtime.on("bulk_update_progress", (data) => {
            if (data.rule_name !== frm.doc.name) return;
            if (data.status === "Completed") {
                frappe.hide_progress();
                frappe.show_alert({
                    message: __("{0} items updated, {1} errors.", [data.updated, data.errors]),
                    indicator: data.errors ? "orange" : "green",
                });
                frm.reload_doc();
            } else if (data.status === "Failed") {
                frappe.hide_progress();
                frappe.show_alert({ message: __("Failed: {0}", [data.error]), indicator: "red" });
                frm.reload_doc();
            } else {
                frappe.show_progress(__("Executing"), data.current, data.total);
            }
        });
    },

    show_preview(frm) {
        if (frm.is_dirty()) {
            frappe.msgprint(__("Please save the rule before previewing."));
            return;
        }
        frappe.call({
            method: "metactical.bulk_item_update.doctype.bulk_update_rule.bulk_update_rule.preview_rule",
            args: { rule_name: frm.doc.name, limit: 20, start: 0 },
            callback(r) {
                if (!r.message) return;
                const d = r.message;
                let html = `<p>${d.total} items matched.</p><table class="table table-sm table-bordered"><thead><tr><th>Item</th>`;
                (d.action_columns || []).forEach(c => { html += `<th>${c} (Before)</th><th>${c} (After)</th>`; });
                html += "</tr></thead><tbody>";
                (d.preview || []).forEach(row => {
                    html += `<tr><td>${row.name}</td>`;
                    (d.action_columns || []).forEach(c => {
                        html += `<td>${row[c+"_before"] ?? ""}</td><td><strong>${row[c+"_after"] ?? ""}</strong></td>`;
                    });
                    html += "</tr>";
                });
                html += "</tbody></table>";
                frappe.msgprint({ title: __("Preview"), message: html, wide: true });
            },
        });
    },

    execute_rule(frm) {
        if (frm.is_dirty()) {
            frappe.msgprint(__("Please save the rule first."));
            return;
        }
        frappe.confirm(__("This will update all matching items in the background. Proceed?"), () => {
            frappe.call({
                method: "metactical.bulk_item_update.doctype.bulk_update_rule.bulk_update_rule.execute_rule",
                args: { rule_name: frm.doc.name },
                callback(r) {
                    if (r.message && r.message.status === "queued") {
                        frappe.show_alert({ message: __("Queued. You'll be notified on completion."), indicator: "blue" });
                        frm.reload_doc();
                    }
                },
            });
        });
    },
});