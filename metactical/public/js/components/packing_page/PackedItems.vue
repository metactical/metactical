<template>
    <div class="packing-item" @click="selectItem">
        <img :src="item.image" :alt="item.item_name" />
        <div class="item-detail">
            <p class="item-title">{{ item.item_name }}</p>
            <p class="item-description text-bold mt-2">{{ item.ifw_retailskusufix }}</p>
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