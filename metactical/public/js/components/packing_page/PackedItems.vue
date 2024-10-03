<template>
    <div class="packing-item" @click="selectItem">
        <img :src="item.image" :alt="item.item_name" />
        <div class="item-detail">
            <h5 class="item-title">{{ item.item_name }}</h5>
            <p class="item-description">{{ item.item_code }}</p>
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
            console.log('selecting item', this.item);
            this.$emit('select-item', this.item);
        }
    }
}
</script>