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
  }
})

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
    var row = locals[cdt][cdn]
    frappe.db.get_list(
      "Sub Operation",
      {
        fields:["operation", "time_in_mins", "description", "time_in_secs"],
        filters:{
            parent: row.operation,
            parenttype: "Operation",
            parentfield: "sub_operations",
        },
        order_by:"idx asc"
    }).then(res => {
        if (res.length){

            $.each(res, (key, so)=> {
                frm.add_child("sub_operations",{
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
    })

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
