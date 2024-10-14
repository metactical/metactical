<template>
    <!-- Current Item -->
    <div>
        <div class="d-flex justify-content-between section-title align-items-center">
            <h4 class="cur-item-barcode mb-0" v-if="item">{{ item.item_barcode ? item.item_barcode.join(", ") : '' }}</h4>
            <span class="fa fa-gear fa-lg cur-item-close cursor-pointer" @click="showSettings"></span>
        </div>
        <div class="current-items-wrap">
            <div class="current-packing-item">
                <div class="item-detail">
                    <h5 class="item-title cur-item-name">{{ item.item_name }}</h5>
                    <p class="item-description cur-item-code">{{ item.item_code }}</p>
                </div>
                <div class="item-quantity" v-if="item && item.qty">
                    <span class="cur-item-quantity-remaining">{{ item.qty }} more to scan</span>
                </div>

                <h3 class="current-section-title cur-item-scan-feedback" v-if="has_add_permission">
                <button class='btn btn-default btn-sm' @click='addOneItem()'>Click to Add</button>
                <button class='btn btn-default btn-sm' @click='add_multiple()'>Add Multiple</button>
            </h3>
            <h3 class="current-section-title cur-item-scan-feedback" v-else-if="item.qty > max_qty_to_pack">
                <button class='btn btn-default btn-sm' @click='add_multiple()'>Add Multiple</button>
            </h3>
                <template v-if="item.image">
                    <img :src="item.image" alt="" class="cur-item-image my-4" />
                </template>
                <template v-else>
                    <h5 class="my-5 py-5 text-muted text-center">No Image Available</h5>
                </template>
            </div>
        </div>
    </div>
    <!--/ Current Item -->
</template>
<script>
export default {
    props: ['item'],
    data() {
        return {
            max_qty_to_pack: 0,
            has_add_permission: false,
            ask_shipment_info: false
        }
    },
    mounted() {
        this.get_max_qty_to_pack();
        this.check_has_add_permission();
    },
    methods: {
        get_max_qty_to_pack() {
            var me = this;
            frappe.db.get_single_value("Packing Settings", "multi_pack_if_qty").then((res) => {
                me.max_qty_to_pack = res;
            })
        },
        check_has_add_permission() {
            var me = this;
            frappe.call({
                method: "metactical.metactical.page.packing_page_v4.packing_page_v4.check_to_add_permission",
                freeze: true,
                callback: function (ret) {
                    if (ret.message) {
                        me.has_add_permission = true;
                    }
                }
            });
        },
        add_multiple(){
            var me = this;
            frappe.prompt(
                [{"fieldtype": "Int", "fieldname": "amount", "label": "Number of Items to Add", "reqd": 1}],
                function(values){
                    if(values.amount > me.item.qty){
                        frappe.throw("You can only add a maximum of " + me.item.qty + " items");
                    }
                    else{
                        me.$emit('itemScanned', me.item.item_barcode[0], values.amount);
                    }
                });
        },
        showSettings() {
            var me = this;
            var d = new frappe.ui.Dialog({
                title: __("Settings"),
                fields: [
                    {
                        fieldname: "ask_shipment_info",
                        fieldtype: "Check",
                        default: me.ask_shipment_info,
                        label: __("Ask Shipment Information for each item"),
                    }
                ],
                primary_action_label: __("Save"),
                primary_action: (values) => {
                    me.ask_shipment_info = values.ask_shipment_info;
                    d.hide();
                }
            });

            d.show();
        },
    }
}
</script>