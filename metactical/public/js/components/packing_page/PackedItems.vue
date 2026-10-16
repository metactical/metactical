<template>
    <div class="packing-item" @click="selectItem">
        <img :src="item.image" :alt="item.item_name" />
        <div class="item-detail">
            <p class="item-title">
                {{ item.item_name }}
                <span v-if="item.is_bundle" class="badge badge-warning ml-1" style="font-size:10px">Bundle</span>
            </p>
            <p class="item-description text-bold mt-2">{{ item.ifw_retailskusufix }}</p>
            <template v-if="item.is_bundle">
                <p v-for="bi in item.bundle_items" :key="bi.item_code" class="mb-0" style="font-size:11px;color:#6c757d;">
                    {{ bi.item_name }} &times; {{ bi.scanned_qty }}
                </p>
            </template>
        </div>
        <div class="item-quantity">
            <span>X {{ item.qty }}</span>
        </div>
    </div>
</template>
<script>
export default {
    props: ['item'],
    methods: {
        selectItem() {
            this.$emit('revertItem', this.item);
        }
    }
}
</script>