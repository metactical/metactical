frappe.provide("metactical.packing_page");
import PendingItem from "./components/packing_page/PendingItems.vue";
import PackedItem from "./components/packing_page/PackedItems.vue";
import CurrentItem from "./components/packing_page/CurrentItem.vue";
import Filters from "./components/packing_page/Filters.vue";
import PendingItems from "./components/packing_page/PendingItems.vue";

metactical.packing_page.PackingPageV4 = class {
    constructor({ parent }) {
        this.wrapper = $(parent);
        this.page = parent.page;
        this.main_section = this.page.main;
        this.show();
    }

    show() {
        // this.page.clear_primary_action();
        this.load_page();
    }

    hide() {
        // this.page.clear_primary_action();
    }

    load_page() {
        var no_data_feedback = "Please select a Delivery Note";
        var vue = new Vue({
            el: this.main_section[0],
            data() {
                return {
                    no_feedback: no_data_feedback,
                    pending_items: [],
                    packed_items: [],
                    current_item: {},
                    selected_delivery_note: "",
                    item_clicked: false,
                    cur_packing_slip: "",
                    all_packed_items: {},
                    filters: {},
                    packed_packing_slips: {},
                };
            },
            components: {
                "pending-item": PendingItem,
                "packed-item": PackedItem,
                "current-item": CurrentItem,
                filters: Filters,
            },
            template: `
            <div class="">
                <div class="packing-page-card">
                    <filters @filtersUpdated="updateFilters" @itemScanned="itemScanned"></filters>
                </div>
                <template v-if="selected_delivery_note">
                <section class="packing-slip-wrapper py-2">
                    <div class="row mx-0" v-if="no_feedback">
                        <div class="col-md-3  packing-page-card">
                        <section class="box pending-items">
                            <h4 class="section-title pending-items-count">{{get_total_pending_items}} Item(s) left</h4>
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
                              <h4 class="section-title packed-items-count cursor-pointer" @click="ShowPackedItems()">{{get_total_packed_items}} Item(s) Packed</h4>
                              <div class="section-wrapper">
                                  <packed-item v-for="item in packed_items" :key="item.name" :item="item"></packed-item>
                                  <div class="text-center pack-items-btn d-none">
                                  <button class="btn btn-primary cursor-pointer" @click="pack_selected_items()">Pack Seleted Items</button>
                                  </div>
                              </div>
                          </section>
                        </div>
                    </div>
                </section>
                </template>
                <template v-else>
                    <div class="text-center mt-5 pt-2">
                        <h4 class="text-muted">{{no_feedback}}</h4>
                    </div>
                </template>
            </div>
            `,
            computed: {
                refresh() {
                    if (this.selected_delivery_note) {
                        this.get_items();
                    }
                    else{
                        frappe.msgprint("Please select a Delivery Note");
                    }
                },
                get_total_pending_items() {
                    var total_pending_items = 0;
                    this.pending_items.forEach((item) => {
                        total_pending_items += item.qty;
                    });

                    return total_pending_items;
                },
                get_total_packed_items() {
                    var total_packed_items = 0;
                    var all_packed_items = JSON.parse(
                        JSON.stringify(this.all_packed_items)
                    );

                    $.each(all_packed_items, (packing_slip, items) => {
                        items.forEach((item) => {
                            total_packed_items += item.qty;
                        });
                    });

                    return total_packed_items;
                },
            },
            methods: {
                ShowPackedItems(){
                    var dialog = new frappe.ui.Dialog({
                        title: "Packed Items",
                        size: "large",
                        fields: [{
                            fieldtype: "HTML",
                            fieldname: "packed_item_detail",
                        }]
                    })
                    
                    let all_packed_items = JSON.parse(JSON.stringify(this.all_packed_items));
                    let packed_items = "";
                    $.each(all_packed_items, (packing_slip, item) => {
                        packed_items += '<h5 class="cursor-pointer" onclick="openPackingSlip(\''+packing_slip+'\')">' + packing_slip + "</h5>";

                        // add parcel details
                        let parcel_details = this.packed_packing_slips[packing_slip];

                        if (parcel_details) {
                            packed_items += "<table class='table table-bordered packing-slip-parcel my-0'>";
                            packed_items += "<thead><tr><th>Box No.</th><th>Template</th><th>Gross Weight</th><th>Height</th><th>Width</th><th>Length</th></tr></thead>";
                            packed_items += "<tbody>";
                            packed_items += "<tr>";
                            packed_items += "<td>" + parcel_details.from_case_no + "</td>";
                            packed_items += "<td>" + parcel_details.custom_neb_parcel_template + "</td>";
                            packed_items += "<td>" + parcel_details.gross_weight_pkg + "</td>";
                            packed_items += "<td>" + parcel_details.custom_neb_box_height + "</td>";
                            packed_items += "<td>" + parcel_details.custom_neb_box_width + "</td>";
                            packed_items += "<td>" + parcel_details.custom_neb_box_length + "</td>";
                            packed_items += "</tr>";
                            packed_items += "</tbody>";
                            packed_items += "</table>";
                        }


                        packed_items += "<table class='table table-bordered packing-slip-detail mt-1'>";
                        // packed_items += "<thead><tr><th>Retail SKU</th><th>Item Name</th><th>Qty</th></tr></thead>";
                        packed_items += "<tbody class='packing-list-items-list'>";
                        $.each(item, (i, props) => {
                            packed_items += "<tr>";
                            packed_items += "<td>" + props.ifw_retailskusuffix + "</td>";
                            packed_items += "<td>" + props.item_name + "</td>";
                            packed_items += "<td>" + props.qty + "</td>";
                            packed_items += "</tr>";
                        });
                        packed_items += "</tbody>";
                        packed_items += "</table>";
                    }); 
                
                    dialog.fields_dict.packed_item_detail.$wrapper.html(packed_items);
                    dialog.show()
                },
                updateFilters(filters) {
                    this.filters = filters;
                    this.get_items();
                },
                selectItem(item) {
                    this.current_item = item;
                },
                itemScanned(barcode, amount = 1) {
                    var me = this;
                    if (barcode == "SKIP") {
                        me.re_generate_current_item();
                        return;
                    }

                    var mee = this;
                    me.pending_items.forEach(function (cur_item) {
                        if (cur_item.item_barcode.indexOf(barcode) != -1) {
                            if (amount > cur_item.qty) {
                                frappe.throw(
                                    "You can only add a maximum of " +
                                        cur_item.qty +
                                        " items"
                                );
                            }
                            frappe.utils.play_sound("alert");

                            // var fields = me.get_measurement_fields(cur_item)
                            var fields = mee.get_measurement_fields(cur_item);
                            if (fields.length > 0) {
                                me.show_measurement_dialog(
                                    fields,
                                    cur_item,
                                    barcode,
                                    amount
                                );
                            } else {
                                me.pack_item(cur_item, barcode, amount);
                            }

                            //return;
                            throw "Break";
                        }
                    });

                    frappe.utils.play_sound("error");
                    frappe.msgprint("Wrong Barcode");
                },
                get_measurement_fields(cur_item) {
                    let fields = [];

                    if (cur_item.net_weight === 0) {
                        fields.push({
                            fieldname: "item_weight",
                            label: "Item weight",
                            fieldtype: "Float",
                            reqd: 1,
                        });
                    }

                    if (cur_item.shipping_length === 0) {
                        fields.push({
                            fieldname: "item_length",
                            label: "Shipping length",
                            fieldtype: "Float",
                            reqd: 1,
                        });
                    }

                    if (cur_item.shipping_width === 0) {
                        fields.push({
                            fieldname: "item_width",
                            label: "Shipping width",
                            fieldtype: "Float",
                            reqd: 1,
                        });
                    }

                    if (cur_item.shipping_height === 0) {
                        fields.push({
                            fieldname: "item_height",
                            label: "Shipping height",
                            fieldtype: "Float",
                            reqd: 1,
                        });
                    }

                    return fields;
                },
                show_measurement_dialog(fields, cur_item, barcode, amount) {
                    var me = this;
                    let dialog = new frappe.ui.Dialog({
                        title: "Item Details",
                        fields: fields,
                        primary_action_label: "Submit",
                        primary_action(values) {
                            frappe.call({
                                method: "metactical.metactical.page.packing_page_v4.packing_page_v4.set_item_values",
                                args: {
                                    item: cur_item.item_code,
                                    values: values,
                                },
                                callback: function (r) {
                                    if (r.message) {
                                        if (
                                            values.item_weight &&
                                            values.item_weight > 0
                                        ) {
                                            cur_item.net_weight =
                                                values.item_weight;
                                        }
                                        me.pack_item(cur_item, barcode, amount);
                                    } else {
                                        frappe.msgprint(
                                            "Error updating values"
                                        );
                                    }
                                },
                            });

                            this.hide();
                        },
                    });

                    dialog.show();
                },
                pack_item(cur_item, barcode, amount = 1) {
                    var me = this;
                    cur_item.qty -= amount;
                    let cur_packed_item = this.packed_items.filter(
                        (item) => item.item_code == cur_item.item_code
                    );

                    if (cur_packed_item.length > 0) {
                        cur_packed_item[0].qty += amount;
                    } else {
                        cur_packed_item = $.extend(true, {}, cur_item);
                        cur_packed_item.qty = amount;
                        cur_packed_item.item_barcode = barcode;
                        this.packed_items.push(cur_packed_item);
                    }

                    if (cur_item.qty == 0) {
                        me.re_generate_current_item();
                    } else {
                        me.re_generate_current_item(cur_item);
                    }

                    $(".pack-items-btn").removeClass("d-none");
                },
                re_generate_current_item(item = null) {
                    var me = this;
                    if (!item) {
                        for (var i = 0; i < me.pending_items.length; i++) {
                            if (
                                me.pending_items[i].item_code ==
                                me.current_item.item_code
                            ) {
                                break;
                            }
                        }
                        me.pending_items.splice(i, 1);
                    }

                    if (me.pending_items.length > 0) {
                        if (item) {
                            me.pending_items.forEach(function (row) {
                                if (row.item_code == item) {
                                    me.item_clicked = true;
                                    me.current_item = row;
                                }
                            });
                        } else {
                            me.current_item = me.pending_items[0];
                        }
                    } else {
                        me.current_item = {};
                    }
                    return;
                },
                pack_selected_items() {
                    var me = this;
                    var d = new frappe.ui.Dialog({
                        title: "Shipment Parcel",
                        fields: [
                            {
                                fieldname: "parcel_template",
                                fieldtype: "Link",
                                options: "Shipment Parcel Template",
                                label: "Parcel Template",
                                onchange: function() {
                                    frappe.db
                                        .get_value(
                                            "Shipment Parcel Template",
                                            d.get_value("parcel_template"),
                                            ["weight", "height", "width", "length"]
                                        )
                                        .then((r) => {
                                            d.set_values({
                                                gross_weight_pkg: r.message.weight,
                                                height: r.message.height,
                                                width: r.message.width,
                                                length: r.message.length,
                                            });
                                        });
                                }
                            },
                            {
                                fieldname: "gross_weight_pkg",
                                label: "Box Gross Weight",
                                fieldtype: "Float",
                                fetch_from: "parcel_template.weight",
                                reqd: 1,
                            },
                            {
                                fieldname: "height",
                                label: "Box Height",
                                fieldtype: "Float",
                                fetch_from: "parcel_template.height",
                                reqd: 1,
                            },
                            {
                                fieldname: "width",
                                label: "Width",
                                fieldtype: "Float",
                                fetch_from: "parcel_template.width",
                                reqd: 1,
                            },
                            {
                                fieldname: "length",
                                label: "Length",
                                fieldtype: "Float",
                                fetch_from: "parcel_template.length",
                                reqd: 1,
                            }
                        ],
                        primary_action_label: "Pack",
                        primary_action(values) {
                            me.cur_packing_slip.parcel_template = values.parcel_template;
                            me.cur_packing_slip.gross_weight_pkg = values.gross_weight_pkg;
                            me.cur_packing_slip.custom_neb_box_height = values.height;
                            me.cur_packing_slip.custom_neb_box_width = values.width;
                            me.cur_packing_slip.custom_neb_box_length = values.length;
                            me.cur_packing_slip.custom_neb_parcel_template = values.parcel_template;
                            me.save_form();
                            d.hide();
                        },
                    });
                    d.show();
                },
                save_form() {
                    var me = this;
                    let cur_doc = me.cur_packing_slip;
                    cur_doc.items = me.packed_items;

                    // Calculate weight
                    var net_weight_pkg = 0;
                    cur_doc.net_weight_uom =
                        me.packed_items && me.packed_items.length
                            ? me.packed_items[0].weight_uom
                            : "";
                    cur_doc.gross_weight_uom = cur_doc.net_weight_uom;

                    for (var i = 0; i < me.packed_items.length; i++) {
                        var item = me.packed_items[i];
                        if (item.weight_uom != cur_doc.net_weight_uom) {
                            frappe.msgprint(
                                __(
                                    "The packed items have different weight UOM fwhich leads to incorrect (Total) Net Weight value.\
                       Therefore the weight will not be calculated for this Packing Slip."
                                )
                            );
                        }
                        net_weight_pkg += flt(item.net_weight) * flt(item.qty);
                    }

                    cur_doc.net_weight_pkg = roundNumber(net_weight_pkg, 2);
                    if (!flt(cur_doc.gross_weight_pkg)) {
                        cur_doc.gross_weight_pkg = cur_doc.net_weight_pkg;
                    }

                    frappe.call({
                        method: "frappe.desk.form.save.savedocs",
                        args: {
                            doc: cur_doc,
                            action: "Submit",
                        },
                        freeze: true,
                        btn: $(".primary-action"),
                        callback: (r) => {
                            // refresh();
                            me.packed_items = [];
                            $(".pack-items-btn").addClass("d-none");
                            me.get_items();
                            me.get_all_packed_items();
                        },
                        error: (r) => {
                            console.error(r);
                        },
                    });
                },

                get_items() {
                    var me = this;
                    let delivery_note = me.filters.delivery_note;
                    this.selected_delivery_note = delivery_note;

                    if (!delivery_note) {
                        me.pending_items = [];
                        me.packed_items = [];
                        me.current_item = {};
                    } else {
                        let new_packing_slip = frappe.model.get_new_doc(
                            "Packing Slip",
                            null,
                            null,
                            1
                        );
                        new_packing_slip.delivery_note = delivery_note;
                        frappe.call({
                            method: "runserverobj",
                            args: {
                                docs: new_packing_slip,
                                method: "get_items",
                            },
                            callback: function (r) {
                                let items = r.docs[0].items;
                                me.cur_packing_slip = r.docs[0];

                                frappe
                                    .call(
                                        "metactical.api.packing_slip.get_item_master",
                                        {
                                            items: items,
                                        }
                                    )
                                    .then((r) => {
                                        items = r.message;
                                        me.current_item = [];
                                        if (me.item_clicked && !from_refresh) {
                                            //A hack to fix a bug(?) when the delivery note loaded. First click anywhere
                                            //on the page calls refresh()
                                            me.item_clicked = false;
                                        } else {
                                            me.pending_items = items;
                                            me.current_item = items[0];
                                            me.packed_items = [];
                                        }
                                    });
                            },
                        });
                        this.get_all_packed_items();
                    }
                },

                get_all_packed_items() {
                    // get packed items
                    var me = this;
                    this.all_packed_items = [];
                    // console.log("getting");
                    frappe.call({
                        method: "metactical.metactical.page.packing_page_v4.packing_page_v4.get_all_packed_items",
                        freeze: true,
                        args: {
                            delivery_note: this.selected_delivery_note,
                        },
                        callback: function (ret) {
                            me.all_packed_items = ret.items;
                            me.packed_packing_slips = ret.packed_packing_slips;
                        },
                    });
                },
            },
        });
    }
};
