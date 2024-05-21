frappe.provide('metactical.store_credit');
import SearchForm from './components/SearchForm.vue'
import ItemsTable from './components/ItemsTable.vue'
import Taxes from './components/Taxes.vue'

metactical.store_credit.StoreCredit = class {
    constructor({ parent }) {
        this.parent = parent;
        this.init()
    }

    init() {
        this.vue_instance = new Vue({
            components: {
                SearchForm,
                ItemsTable,
                Taxes
            },
            data: {
                si_items : [
                    {
                        "retail_sku": "SKU-001",
                        "item_name": "Item 1",
                        "returned_qty": 1,
                        "unit_price": "$ 10.00",
                        "discount": "",
                        "ttl_price": "$ 10.00"
                    },
                    {
                        "retail_sku": "SKU-002",
                        "item_name": "Item 2",
                        "returned_qty": 1,
                        "unit_price": "$ 20.00",
                        "discount": "",
                        "ttl_price": "$ 20.00"
                    },
                    {
                        "retail_sku": "SKU-003",
                        "item_name": "Item 3",
                        "returned_qty": 1,
                        "unit_price": "$ 30.00",
                        "discount": "",
                        "ttl_price": "$ 30.00"
                    },
                    {
                        "retail_sku": "SKU-004",
                        "item_name": "Item 4",
                        "returned_qty": 1,
                        "unit_price": "$ 40.00",
                        "discount": "",
                        "ttl_price": "$ 40.00"
                    },
                    {
                        "retail_sku": "SKU-005",
                        "item_name": "Item 5",
                        "returned_qty": 1,
                        "unit_price": "$ 50.00",
                        "discount": "",
                        "ttl_price": "$ 50.00"
                    }
                ],
                taxes: [
                    {
                        "name": "On Net Total",
                        "amount": "$ 2.00"
                    },
                    {
                        "name": "On Net Total",
                        "amount": "$ 1.00"
                    },
                    {
                        "name": "TTL Tax",
                        "amount": "$ 3.00"
                    },
                    {
                        "name": "Discount",
                        "amount": "$ 0.00"
                    },
                    {
                        "name": "TTL Store Credit",
                        "amount": "$ 153.00"
                    }, 
                    {
                        "name": "Total Qty Returned",
                        "amount": "5"
                    }
                ],
            },
            el: "#store-credit-root",
            template: `
                <div>
                    <SearchForm @search="search"/>
                    <hr>
                    <div class="row">
                        <div class="col-md-4">
                            <input type="text"  class="form-control" placeholder="Sales Invoice" readonly>
                        </div>
                        <div class="col-md-4">
                            <input type="text"  class="form-control" placeholder="Customer Name" readonly>
                        </div>
                        <div class="col-md-4">
                            <button class="btn btn-primary">Load SI</button>
                            <button class="btn btn-primary">Edit Price</button>
                            <button class="btn btn-primary">Clear SI</button>
                        </div>
                    </div>

                    <div class="row">
                        <div class="col-md-7">
                            <div class="row">
                                <div class="col-12">
                                    <ItemsTable :items="si_items"/>
                                </div>
                            
                                <div class="col-12 mt-4">
                                    <Taxes :taxes="taxes"/>
                                </div>

                                <div class="col-12 mt-4">
                                    <button class="btn btn-primary btn-block btn-lg">Process Store Credit</button>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-5 mt-4">
                            <div class="card">
                                <div class="card-body text-center">
                                    <p>Processed Items will show up here</p>
                                </div>
                            </div>
                        </div>
                    </div>
            `,
            methods: {
                search() {
                    console.log("test")
                },
                submit() {
                    frappe.call({
                        method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.create_store_credit',
                        args: {
                            user: this.store_credit.user,
                            amount: this.store_credit.amount,
                            action: this.store_credit.action
                        },
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint(r.message)
                            }
                        }
                    })
                }
            }
        })

        return this.vue_instance
    }

}
