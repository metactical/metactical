<template>
    <div class="table-responsive">
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Retail SKU</th>
                    <th>Item Name</th>
                    <th>Returned Qty</th>
                    <th>Unit Price</th>
                    <th>Discount</th>
                    <th>TTL Price</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in items" :key="item.id">
                    <td> <a href="#" class="text-danger">Delete</a></td>
                    <td>{{ item.retail_sku }}</td>
                    <td>{{ item.item_name }}</td>
                    <td>{{ item.returned_qty }}</td>
                    <td>{{ item.unit_price }}</td>
                    <td>{{ item.discount }}</td>
                    <td>{{ item.ttl_price }}</td>
                </tr>
            </tbody>
        </table>
    </div>
</template>
<script>
    export default {
        props: ['items']
    }
</script>
