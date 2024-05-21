<template>
    <ul class="list-group">
        <li v-for="tax in taxes" :key="tax.id" class="d-flex justify-content-between list-group-item">
            <span>{{ tax.name }}</span>
            <span>{{ tax.amount }}</span>
        </li>
    </ul>
</template>
<script>
    export default {
        props: ['taxes']
    }
</script>
