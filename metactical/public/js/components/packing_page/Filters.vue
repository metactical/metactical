<template>
  <div class="row">
    <div class="col-md-3">
      <div class="warehouse-wrapper pt-2"></div>
    </div>
    <div class="col-md-3">
      <div class="picklist-tote-wrapper pt-2"></div>
    </div>
    <div class="col-md-3">
      <div class="delivery-note-wrapper pt-2"></div>
    </div>
    <div class="col-md-3">
      <div class="item-barcode-wrapper pt-2"></div>
    </div>
  </div>
</template>
<script>
export default {
  data() {
    return {
      filters: {
        delivery_note: "",
        item_barcode: "",
        tote_barcode: "",
        selected_warehouse: "",
        selected_warehouse_field: ""
      }
    };
  },
  mounted() {
    this.makeFilters();
  },
  methods: {
    get_warehouse() {
      var me = this;

    },
    ShowPendingItems() {
      // Show pending items
    },
    packSelectedItems() {
      // Pack selected items
    },

    makeFilters() {
      // delivery note control
      var me = this
      $('.picklist-tote-wrapper').hide();

      let delivery_note_field = frappe.ui.form.make_control({
        parent: $(".delivery-note-wrapper"),
        df: {
          label: "Delivery Note",
          fieldname: "delivery_note",
          fieldtype: "Link",
          options: "Delivery Note",
          get_query: () => {
            return {
              filters: {
                docstatus: 0
              },
            };
          },
          change() {
            var is_focused = $(`#page-packing-page-v4  [data-fieldname='delivery_note']`).is(":focus")
            if (is_focused)
              $(`#page-packing-page-v4 [data-fieldname='delivery_note']`).blur();
            else {
              me.filters.delivery_note = delivery_note_field.get_value();
              me.$emit("filtersUpdated", me.filters);
            }
          },
        },
        render_input: true,
      });

      let tote_barcode_field = frappe.ui.form.make_control({
        parent: $('.picklist-tote-wrapper'),
        df: {
          label: "Tote Barcode",
          fieldname: "tote_barcode",
          fieldtype: "Data",
          get_query: function () {
            return {
              filters: [
                ["warehouse", "=", me.filters.selected_warehouse],
                ["current_delivery_note", "is", "set"]
              ]
            }
          }
        },
        render_input: true
      });

      tote_barcode_field.$input.on('keypress', function (e) {
        //Only when enter is pressed
          if (event.keyCode == 13) {
            me.filters.tote_barcode = tote_barcode_field.get_value();
            frappe.call({
              method: "metactical.metactical.page.packing_page_v4.packing_page_v4.get_delivery_from_tote",
              args: {
                tote: me.filters.tote_barcode,
                warehouse: me.filters.selected_warehouse
              },
              freeze: true,
              callback: function (ret) {
                let is_tote = ret.message.is_tote;
                if (is_tote) {
                  delivery_note_field.set_value(ret.message.delivery_note);
                }
                else {
                  frappe.throw("Error: No tote registered at warehouse with that name. Please check and try again.");
                }
              }
            });
          }
      });


      // item barcode control
      let item_barcode_field = frappe.ui.form.make_control({
        parent: $(".item-barcode-wrapper"),
        df: {
          label: "Item Barcode",
          fieldname: "item_barcode",
          fieldtype: "Data",
          change() {
            let value = item_barcode_field.get_value();
            if (value != "" || value != 0) {
              item_barcode_field.set_value("");
              me.$emit("itemScanned", value);
            }
          },
        },
        render_input: true,
      });

      let selected_warehouse_field = frappe.ui.form.make_control({
        parent: $('.warehouse-wrapper'),
        df: {
          label: 'Warehouse',
          fieldtype: 'Link',
          fieldname: 'selected_warehouse',
          options: 'Warehouse',
          change() {
            var value = selected_warehouse_field.get_value()
            if (value)
              $('.picklist-tote-wrapper').show();
            else
              $('.picklist-tote-wrapper').hide();
            me.filters.selected_warehouse = selected_warehouse_field.get_value()
          }
        },
        render_input: true
      });

      frappe.call({
        method: "metactical.metactical.page.packing_page_v4.packing_page_v4.get_default_warehouse",
        freeze: true,
        callback: function (ret) {
          // me.selected_warehouse = ret.message
          selected_warehouse_field.value = ret.message
          selected_warehouse_field.refresh()
        }
      });


      // Load default warehouse
      if (metactical.packing_page.default_warehouse != "") {
        $('[data-fieldname=selected_warehouse]').val(metactical.packing_page.default_warehouse);
        $('.picklist-tote-wrapper').show();
      }

    }
  },
};
</script>
