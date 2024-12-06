frappe.ui.form.on("Item", {
      refresh: function (frm) {
            cur_frm.fields_dict['neb_website_specifications'].grid.get_field('description_link').get_query = function(doc, cdt, cdn) {
                  var row = locals[cdt][cdn];
                  var options = ["", row.label]
                  return {
                        filters:[
                              ['Website Specifications Description', 'label', 'in', options.join(",")]
                        ]
                  }
            }
      },
      neb_copy_from_item_group: function (frm) {
            if (!frm.doc.item_group) {
                  frappe.msgprint(__("Please set Item Group first"));
                  return;
            }

            return frm.call({
                  method: "metactical.custom_scripts.item.item.copy_specification_from_item_group",
                  args: { item_group: frm.doc.item_group },
                  callback: function (r) {
                        if (r.message.length) {
                              frm.clear_table("neb_website_specifications");
                              r.message.forEach((spec) => {
                                    frm.add_child(
                                          "neb_website_specifications",
                                          {
                                                label: spec.label,
                                                mandatory: spec.mandatory,
                                          }
                                    );
                              });
                              frm.refresh_field("neb_website_specifications");
                        } else {
                              frappe.msgprint(
                                    __(
                                          "No specifications found in the Item Group"
                                    )
                              );
                        }
                  },
            });
      },
});
