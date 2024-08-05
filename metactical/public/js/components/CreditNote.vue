<template>
    <div>
        <h4 class="text-center">Store Credits</h4>
        <div id="accordion" class="store-credits">
            <div v-for="(credit_note, sales_invoice) in credit_notes" :key="credit_note.id" v-if="Object.keys(credit_notes).length > 0">
                <div  class="cursor-pointer d-flex justify-content-between card-header" data-toggle="collapse" :data-target="'#collapse'+ sales_invoice" aria-expanded="false" :aria-controls="'collapse'+ sales_invoice">
                    <h5 class="card-title"> {{ sales_invoice }}</h5>
                    <p class="text-muted">{{ credit_note[0].posting_date }}</p>
                </div>

                <div class="collapse" :id="'collapse'+ sales_invoice" >
                    <div class="card-body">
                        <p>Customer: <b>{{ credit_note[0].neb_store_credit_beneficiary ? credit_note[0].neb_store_credit_beneficiary : "-" }}</b></p>
                        <div class="table-responsive">
                            <table class="table mt-0">
                                <thead>
                                        <th>Item</th>
                                        <th>Qty</th>
                                        <th>Rate</th>
                                        <th>Discount</th>
                                        <th>Amount</th>
                                </thead>
                                <tbody>
                                    <tr v-for="item in credit_note" :key="item.id">
                                        <td>{{ item.item_name }}</td>
                                        <td>{{ item.qty }}</td>
                                        <td>{{ item.rate }}</td>
                                        <td>{{ item.discount_amount }}</td>
                                        <td class="text-nowrap">{{ item.amount }}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <table style="width: 100%;margin: 0px 11px;">
                            <tbody>
                                <tr>
                                    <td colspan="4">TTL Taxes</td>
                                    <td>{{ credit_note[0].total_taxes_and_charges }}</td>
                                </tr>
                                <tr>
                                    <td colspan="4">Discount</td>
                                    <td>{{ credit_note[0].si_discount_amount }}</td>
                                </tr>
                                <tr>
                                    <td colspan="4">Grand Total</td>
                                    <td><b>{{ credit_note[0].grand_total }}</b></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            <div v-if="!Object.keys(credit_notes).length">
                <p class="text-center">No credit notes available</p>
            </div>
        </div>
    </div>
</template>
<script>
    export default {
        props: ['credit_notes'],
        methods: {}
    }
</script>