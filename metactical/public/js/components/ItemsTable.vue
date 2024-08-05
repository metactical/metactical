<template>
        <div class="table-responsive">
            <table class="table table-bg">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Retail SKU</th>
                        <th>Item Name</th>
                        <th>Returning Qty</th>
                        <th>Unit Price</th>
                        <th>Discount</th>
                        <th>TTL Price</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="item in items" :key="item.id" v-if="items.length > 0 ">
                        <td> <span @click="deleteItem(item.name)" class="text-danger cursor-pointer">Delete</span></td>
                        <td>{{ item.retail_sku }}</td>
                        <td>{{ item.item_name }}</td>
                        <td>{{ item.qty }}</td>
                        <td>{{ item.rate }}</td>
                        <td>{{ item.discount_amount }}</td>
                        <td class="text-nowrap">{{ item.amount }}</td>
                    </tr>
                    <tr v-if="!items.length">
                        <td colspan="7" class="text-center">No items added / All Items are issued to store credit</td>
                    </tr>
                </tbody>
            </table>
        </div>

</template>
<script>
    export default {
        props: ['items'],
        methods: {
            deleteItem(item_name){
                var me = this
                $.each(me.items, (key, value)=> {
                    if(value){
                        if (item_name === value.name){
                            me.items.splice(key, 1);
                        }
                    }
                })

                this.$emit('updateTotals', me.items)
            }
        }
    }
</script>
