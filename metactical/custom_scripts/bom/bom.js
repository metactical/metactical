var raw_material_item_groups = []
frappe.ui.form.on("BOM", {
  setup: function () {
    // frappe.call({
    //   method: "erpnext_paki.custom_scripts.bom.bom.get_item_group_with_children",
    //   callback: function (r) {
    //     raw_material_item_groups = r.message
    //   },
    // });
  },
  refresh: function(frm){
  //   frm.set_query('item_code', "items", () => {
  //     return {
  //         filters: {
  //             item_group: ["in", raw_material_item_groups]
  //         }
  //     }
  // })
    default_currency_for_pkr_company(frm);
    apply_usd_pkr_override(frm, "refresh");
  },
  currency: function(frm){
    apply_usd_pkr_override(frm, "currency");
  },
  conversion_rate: function(frm){
    apply_usd_pkr_override(frm, "conversion_rate");
  },
  company: function(frm){
    default_currency_for_pkr_company(frm);
    apply_usd_pkr_override(frm, "company");
  }
})

var get_company_currency = function(company) {
  return frappe.db.get_value("Company", company, "default_currency").then(r => {
    return r && r.message ? r.message.default_currency : null;
  });
};

// On new BOMs for a PKR company, default the BOM currency to USD.
// Skip on saved docs so we never overwrite a user's choice.
var default_currency_for_pkr_company = function(frm) {
  get_company_currency(frm.doc.company).then(company_currency => {
    if (company_currency === "PKR" && frm.doc.currency !== "USD") {
      frm.set_value("currency", "USD");
    }
  });
};

var apply_usd_pkr_override = function(frm, source) {
  get_company_currency(frm.doc.company).then(company_currency => {
    if (frm.doc.currency === "USD" && company_currency === "PKR") {
      if (flt(frm.doc.conversion_rate) !== 280) {
        frm.set_value("conversion_rate", 280);
      }
      return;
    }
  });
};

frappe.ui.form.on("BOM Operation", {
  time_in_mins: function (frm, cdt, cdn) {
    calculate_total_time(frm);
  },
  time_in_secs: function (frm, cdt, cdn) {
    calculate_total_time(frm);
  },
  operations_remove(frm, cdt, cdn) {
    calculate_total_time(frm);
  },
  before_operations_remove(frm, cdt, cdn) {
    var row = locals[cdt][cdn]
    var updated_sub_operations = []
    
    $.each(frm.doc.sub_operations, (key, so)=>{
        if (so.parent_operation != row.operation){
            updated_sub_operations.push(so)
        }
    })

    frm.clear_table("sub_operations")
    updated_sub_operations.forEach(so => {
        frm.add_child("sub_operations",{
            parent_operation: so.parent_operation,
            operation: so.operation,
            time_in_mins: so.time_in_mins,
            description: so.description,
            time_in_secs: so.time_in_secs,
            workstation: so.workstation,
        })
    })
    frm.refresh_field("sub_operations")
  },
  operation: function (frm, cdt, cdn) {
    var is_focused = $(`[data-fieldname="operations"] [data-fieldname='operation']`).is(":focus")
    if(is_focused){
      $(`[data-fieldname="operations"] [data-fieldname='operation']`).blur();
    }

    var row = locals[cdt][cdn]
    frappe.call({
      method: "frappe.client.get",
      args: {
        doctype: "Operation",
        // fields: ["operation", "time_in_mins", "description", "time_in_secs"],
        filters: {
          name: row.operation
        },
      },
      callback: function (res) {
          $.each(res.message.sub_operations, (key, so) => {
            frm.add_child("sub_operations", {
              parent_operation: row.operation,
              operation: so.operation,
              time_in_mins: so.time_in_mins,
              description: so.description,
              time_in_secs: so.time_in_secs,
              workstation: row.workstation,
            })
          })

          frm.refresh_field("sub_operations")
      }
    });
  },
});

var calculate_total_time = function (frm) {
  frm.doc.total_operation_time = 0;
  $.each(frm.doc.operations, (row, op) => {
    frm.doc.total_operation_time += op.time_in_mins ? op.time_in_mins : 0;

    if (op.time_in_secs) {
      var time_in_mins = op.time_in_secs / 60;
      frm.doc.total_operation_time += time_in_mins;
    }
  });

  // frm.doc.total_operation_time_secs = frm.doc.total_operation_time * 60
  frm.refresh_field("total_operation_time");
  // frm.refresh_field("total_operation_time_secs")
};
