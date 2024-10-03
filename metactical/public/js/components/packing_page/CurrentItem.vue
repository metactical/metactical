<template>
    <!-- Current Item -->
    <div>
        <h4 class="section-title cur-item-barcode" v-if="item">Packing Now {{ item.item_barcode }}</h4>
        <div class="current-items-wrap">
            <h3 class="current-section-title cur-item-scan-feedback" v-if="has_add_permission">
                <button class='btn btn-default btn-sm' onClick='addOneItem()'>Click to Add</button>
                <button class='btn btn-default btn-sm' onClick='addMultiple()'>Add Multiple</button>
            </h3>
            <h3 class="current-section-title cur-item-scan-feedback" v-else-if="item.qty > max_qty_to_pack">
                <button class='btn btn-default btn-sm' onClick='addMultiple()'>Add Multiple</button>
            </h3>
            <div class="current-packing-item">
                <div class="item-detail">
                    <h5 class="item-title cur-item-name">{{ item.item_name }}</h5>
                    <p class="item-description cur-item-code">{{ item.item_code }}</p>
                </div>

                <div class="item-quantity">
                    <span class="cur-item-quantity-remaining">{{ item.qty }} more to scan</span>
                </div>
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
            has_add_permission: false
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
                console.log('max_qty_to_pack', me.max_qty_to_pack);
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
        ShowPackedItems() {
            // Show packed items
        },
        packSelectedItems() {
            // Pack selected items
        }
    }
}
</script>