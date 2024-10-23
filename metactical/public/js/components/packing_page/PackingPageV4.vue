<template>
  <div>
    <div class="packing-page-card">
      <filters @filtersUpdated="updateFilters" @itemScanned="itemScanned"></filters>
    </div>
    <template v-if="selected_delivery_note">
      <section class="packing-slip-wrapper py-2">
        <div class="row mx-0" v-if="no_feedback">
          <div class="col-md-3 packing-page-card">
            <section class="box pending-items">
              <h4 class="section-title pending-items-count">{{ getTotalPendingItems }} Item(s) left</h4>
              <div class="section-wrapper">
                <pending-item @select-item="selectItem" v-for="item in pending_items" :key="item.name" :item="item"></pending-item>
              </div>
            </section>
          </div>
          <div class="col-md-6 px-2">
            <section class="box current-item packing-page-card">
              <current-item :item="current_item" @itemScanned="itemScanned"></current-item>
            </section>
          </div>
          <div class="col-md-3 packing-page-card">
            <section class="box packed-items">
              <h4 class="section-title packed-items-count cursor-pointer" @click="showPackedItems">{{ getTotalPackedItems }} Item(s) Packed</h4>
              <div class="section-wrapper">
                <packed-item @revertItem="revertItem" v-for="item in packed_items" :key="item.name" :item="item"></packed-item>
                <div class="text-center pack-items-btn d-none">
                  <button class="btn btn-primary cursor-pointer" @click="packSelectedItems">Pack Selected Items</button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </section>
    </template>
    <template v-else>
      <div class="text-center mt-5 pt-2">
        <h4 class="text-muted">{{ no_feedback }}</h4>
      </div>
    </template>
  </div>
</template>

<script>
import PendingItem from "./PendingItems.vue";
import PackedItem from "./PackedItems.vue";
import CurrentItem from "./CurrentItem.vue";
import Filters from "./Filters.vue";

export default {
  data() {
    return {
      no_feedback: "Please select a Delivery Note",
      pending_items: [],
      packed_items: [],
      current_item: {},
      selected_delivery_note: "",
      item_clicked: false,
      cur_packing_slip: "",
      all_packed_items: {},
      filters: {},
      packed_packing_slips: {},
      ask_shipment_info: false,
    };
  },
  components: {
    "pending-item": PendingItem,
    "packed-item": PackedItem,
    "current-item": CurrentItem,
    filters: Filters,
  },
  computed: {
    getTotalPendingItems() {
      return this.pending_items.reduce((total, item) => total + item.qty, 0);
    },
    getTotalPackedItems() {
      return Object.values(this.all_packed_items).flat().reduce((total, item) => total + item.qty, 0);
    },
  },
  methods: {
    refresh() {
      $(".pack-items-btn").addClass("d-none");
      if (this.selected_delivery_note) {
        this.getItems();
      } else {
        frappe.msgprint("Please select a Delivery Note");
      }
    },
    revertItem(item) {
      // check if the item is in the pending items
      var exists = this.pending_items.find((i) => i.dn_detail === item.dn_detail);
      if (!exists) {
        new_item = { ...item, qty: 0, item_barcode: [item.item_barcode] };
        this.pending_items.push(new_item);
      }
       
      this.pending_items.forEach((pending_item) => {
        if (pending_item.dn_detail === item.dn_detail) {
          pending_item.qty += 1;
          item.qty -= 1;
          if (item.qty === 0) {
            this.packed_items = this.packed_items.filter((i) => i.item_code !== item.item_code);
            if (this.packed_items.length === 0) {
              $(".pack-items-btn").addClass("d-none");
            }
          }
          return false;
        }
      });
      this.reGenerateCurrentItem(item);
    },

    showPackedItems() {
      const dialog = new frappe.ui.Dialog({
        title: "Packed Items",
        size: "large",
        fields: [{ fieldtype: "HTML", fieldname: "packed_item_detail" }],
      });

      let packed_items = "";
      Object.entries(this.all_packed_items).forEach(([packing_slip, items]) => {
        packed_items += `<h5 class="cursor-pointer" onclick="openPackingSlip('${packing_slip}')">${packing_slip}</h5>`;
        const parcel_details = this.packed_packing_slips[packing_slip];
        if (parcel_details) {
          packed_items += `
            <table class='table table-bordered packing-slip-parcel my-0'>
              <thead>
                <tr>
                  <th>Box No.</th>
                  <th>Template</th>
                  <th class='text-center'>Gross Weight</th>
                  <th class='text-center'>Height</th>
                  <th class='text-center'>Width</th>
                  <th class='text-center'>Length</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>${parcel_details.from_case_no}</td>
                  <td>${parcel_details.custom_neb_parcel_template}</td>
                  <td class='text-center'>${parcel_details.gross_weight_pkg}</td>
                  <td class='text-center'>${parcel_details.custom_neb_box_height}</td>
                  <td class='text-center'>${parcel_details.custom_neb_box_width}</td>
                  <td class='text-center'>${parcel_details.custom_neb_box_length}</td>
                </tr>
              </tbody>
            </table>`;
        }
        packed_items += `
          <table class='table table-bordered packing-slip-detail mt-1'>
            <tbody class='packing-list-items-list'>
              ${items.map((props) => `
                <tr>
                  <td>${props.ifw_retailskusuffix}</td>
                  <td>${props.item_name}</td>
                  <td>${props.qty}</td>
                </tr>`).join('')}
            </tbody>
          </table>`;
      });

      dialog.fields_dict.packed_item_detail.$wrapper.html(packed_items);
      dialog.show();
    },

    updateFilters(filters) {
      this.filters = filters;
      this.getItems();
    },

    selectItem(item) {
      this.current_item = item;
    },

    itemScanned(barcode, amount = 1) {
      var me = this
      if (barcode === "SKIP") {
        this.reGenerateCurrentItem();
        return;
      }

      let barcode_found = false;
      this.pending_items.forEach((cur_item) => {
        if (cur_item.item_barcode.includes(barcode) && me.current_item.dn_detail == cur_item.dn_detail) {
          if (amount > cur_item.qty) {
            frappe.throw(`You can only add a maximum of ${cur_item.qty} items`);
          }
          frappe.utils.play_sound("alert");

          const fields = me.getMeasurementFields(cur_item);
          if (fields.length > 0 && me.ask_shipment_info) {
            me.showMeasurementDialog(fields, cur_item, barcode, amount);
          } else {
            me.packItem(cur_item, barcode, amount);
          }
          barcode_found = true;
          return
        }
      });

      if (!barcode_found) {
        frappe.utils.play_sound("error");
        frappe.msgprint("Wrong Barcode");
      }
    },

    getMeasurementFields(cur_item) {
      const fields = [];
      if (cur_item.net_weight === 0) fields.push({ fieldname: "item_weight", label: "Item weight", fieldtype: "Float", reqd: 1 });
      if (cur_item.shipping_length === 0) fields.push({ fieldname: "item_length", label: "Shipping length", fieldtype: "Float", reqd: 1 });
      if (cur_item.shipping_width === 0) fields.push({ fieldname: "item_width", label: "Shipping width", fieldtype: "Float", reqd: 1 });
      if (cur_item.shipping_height === 0) fields.push({ fieldname: "item_height", label: "Shipping height", fieldtype: "Float", reqd: 1 });
      return fields;
    },

    showMeasurementDialog(fields, cur_item, barcode, amount) {
      const dialog = new frappe.ui.Dialog({
        title: "Item Details",
        fields,
        primary_action_label: "Submit",
        primary_action(values) {
          frappe.call({
            method: "metactical.metactical.page.packing_page_v4.packing_page_v4.set_item_values",
            args: { item: cur_item.item_code, values },
            callback: (r) => {
              if (r.message) {
                if (values.item_weight && values.item_weight > 0) cur_item.net_weight = values.item_weight;
                this.packItem(cur_item, barcode, amount);
              } else {
                frappe.msgprint("Error updating values");
              }
            },
          });
          this.hide();
        },
      });
      dialog.show();
    },

    packItem(cur_item, barcode, amount = 1) {
      cur_item.qty -= amount;
      let cur_packed_item = this.packed_items.find((item) => item.dn_detail === cur_item.dn_detail);
      if (cur_packed_item) {
        cur_packed_item.qty += amount;
      } else {
        cur_packed_item = { ...cur_item, qty: amount, item_barcode: barcode };
        this.packed_items.push(cur_packed_item);
      }

      if (cur_item.qty === 0) {
        this.reGenerateCurrentItem();
      } else {
        this.reGenerateCurrentItem(cur_item);
      }
      $(".pack-items-btn").removeClass("d-none");
    },

    reGenerateCurrentItem(item = null) {
      if (!item) {
        const index = this.pending_items.findIndex((i) => i.dn_detail === this.current_item.dn_detail);
        this.pending_items.splice(index, 1);
      }

      if (this.pending_items.length > 0) {
        if (item) {
          this.current_item = this.pending_items.find((row) => row.dn_detail === item.dn_detail);
        } else {
          this.current_item = this.pending_items[0];
        }
      } else {
        this.current_item = {};
      }
    },

    packSelectedItems() {
      const dialog = new frappe.ui.Dialog({
        title: "Shipment Parcel",
        fields: [
          { fieldname: "parcel_template", fieldtype: "Link", options: "Shipment Parcel Template", label: "Parcel Template", onchange: () => this.updateParcelTemplate(dialog) },
          { fieldname: "gross_weight_pkg", label: "Box Gross Weight", fieldtype: "Float", reqd: 1 },
          { fieldname: "height", label: "Box Height", fieldtype: "Float", reqd: 1 },
          { fieldname: "width", label: "Width", fieldtype: "Float", reqd: 1 },
          { fieldname: "length", label: "Length", fieldtype: "Float", reqd: 1 },
        ],
        primary_action_label: "Pack",
        primary_action: (values) => this.saveForm(dialog),
      });
      dialog.show();
    },

    updateParcelTemplate(dialog) {
      frappe.db.get_value("Shipment Parcel Template", dialog.get_value("parcel_template"), ["weight", "height", "width", "length"]).then((r) => {
        dialog.set_values({
          gross_weight_pkg: r.message.weight,
          height: r.message.height,
          width: r.message.width,
          length: r.message.length,
        });
      });
    },

    saveForm(dialog) {
      values = dialog.get_values();
      this.cur_packing_slip = { ...this.cur_packing_slip, ...values };
      this.cur_packing_slip.items = this.packed_items;
      this.cur_packing_slip.custom_neb_box_height = values.height;
      this.cur_packing_slip.custom_neb_box_width = values.width;
      this.cur_packing_slip.custom_neb_box_length = values.length;
      this.cur_packing_slip.custom_neb_parcel_template = values.parcel_template;
      this.cur_packing_slip.gross_weight_pkg = values.gross_weight_pkg;
      this.cur_packing_slip.net_weight_pkg = this.calculateNetWeight();
      
      frappe.call({
        method: "frappe.desk.form.save.savedocs",
        args: { doc: this.cur_packing_slip, action: "Submit" },
        freeze: true,
        btn: $(".primary-action"),
        callback: () => {
          this.packed_items = [];
          $(".pack-items-btn").addClass("d-none");
          this.getAllPackedItems();
          this.refresh();

          dialog.hide();
        },
        error: (r) => {
          frappe.msgprint(r.message);
        },
      });
    },
    calculateNetWeight() {
      let net_weight_pkg = 0;
      const weight_uom = this.packed_items.length ? this.packed_items[0].weight_uom : "";
      this.packed_items.forEach((item) => {
        if (item.weight_uom !== weight_uom) {
          frappe.msgprint("The packed items have different weight UOM which leads to incorrect (Total) Net Weight value. Therefore the weight will not be calculated for this Packing Slip.");
        }
        net_weight_pkg += item.net_weight * item.qty;
      });
      return roundNumber(net_weight_pkg, 2);
    },

    getItems() {
      const delivery_note = this.filters.delivery_note;
      this.selected_delivery_note = delivery_note;
      if (!delivery_note) {
        this.pending_items = [];
        this.packed_items = [];
        this.current_item = {};
      } else {
        const new_packing_slip = frappe.model.get_new_doc("Packing Slip", null, null, 1);
        new_packing_slip.delivery_note = delivery_note;
        frappe.call({
          method: "runserverobj",
          args: { docs: new_packing_slip, method: "get_items" },
          callback: (r) => {
            const items = r.docs[0].items;
            if (items.length) this.cur_packing_slip = r.docs[0];
            frappe.call("metactical.api.packing_slip.get_item_master", { items }).then((r) => {
              this.pending_items = r.message;
              this.current_item = this.pending_items[0] || {};
              this.packed_items = [];
            });
          },
        });
        this.getAllPackedItems();
      }
    },

    getAllPackedItems() {
      frappe.call({
        method: "metactical.metactical.page.packing_page_v4.packing_page_v4.get_all_packed_items",
        freeze: true,
        args: { delivery_note: this.selected_delivery_note },
        callback: (ret) => {
          this.all_packed_items = ret.items;
          this.packed_packing_slips = ret.packed_packing_slips;
        },
      });
    },
  },
};
</script>