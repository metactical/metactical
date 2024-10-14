<template>
  <div class="packing-item" @click="selectItem">
    <img :src="item.image" :alt="item.item_name" />
    <div class="item-detail">
      <p class="item-title">{{ item.item_name }}</p>
      <p class="item-description mt-2 text-bold">{{ item.ifw_retailskusufix }}</p>
    </div>
    <div class="item-quantity">
      <span>X {{ item.qty }}</span>
    </div>
  </div>
</template>
<script>
export default {
  props: ["item"],
  methods: {
    selectItem() {
      this.$emit("select-item", this.item);
    },
  },
};
</script>
