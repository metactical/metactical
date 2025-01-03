frappe.ui.form.on("Item", {
      onload_post_render: function (frm) {
            $('body input[data-fieldname="description"]').on("focus", function(e){
                  console.log(e.target)
                  console.log($(this).val())
            })
      },
      onload: function (frm) {
            $('body input[data-fieldname="description"]').on("focus", function(e){
                  console.log(e.target)
                  console.log($(this).val())
            })
      },
      refresh: function (frm) {
            // cur_frm.fields_dict["neb_website_specifications"].grid.get_field(
            //       "description"
            // ).get_query = function (doc, cdt, cdn) {
            //       var d = locals[cdt][cdn];
            //       return {
            //             query: "metactical.custom_scripts.website_item.website_item.get_website_label_descriptions",
            //             filters: {
            //                   parent: d.label,
            //             },
            //       };
            // };
            
            // Trigger this function when the form is refreshed or reloaded
            
            // console.log(
            // var input = $(
            //       cur_frm.fields_dict["neb_website_specifications"].grid.wrapper
            // ).find("");
            // $('input[data-fieldname="description"]').on(input, function () {
            //       console.log("focus");
            // });
            
            // $.each(cur_frm.fields_dict, (field, obj) =>{
            //       if (field.includes("neb_website_specifications")){
            //             console.log(obj);
            //       }
            // })
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
