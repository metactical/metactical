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
                current_sales_invoice: "",
                selected_customer: "",
                customer: {
                    first_name: "",
                    last_name: "",
                    email: "",
                    phone_number: "",
                    company: "",
                },
                si_items : [],
                taxes: [],
                item_area: "d-none",
                process_payment_button: "d-none"
            },
            el: "#store-credit-root",
            template: `
                <div>
                    <SearchForm @search="search" @clearCustomer="clearCustomer" :customer="customer" :item_area="item_area"/>
                    <hr>
                    <div class="row" :class="item_area">
                        <div class="col-md-4">
                            <input type="text"  class="form-control" placeholder="Sales Invoice" v-model="current_sales_invoice">
                        </div>
                        <div class="col-md-4">
                            <input type="text"  class="form-control" placeholder="Customer Name" readonly v-model="selected_customer">
                        </div>
                        <div class="col-md-4">
                            <button class="btn btn-primary" @click="loadSI">Load SI</button>
                            <button class="btn btn-primary" >Edit Price</button>
                            <button class="btn btn-primary" @click="clearSI">Clear SI</button>
                        </div>
                    </div>

                    <div class="row" :class="item_area">
                        <div class="col-md-7">
                            <div class="row">
                                <div class="col-12">
                                    <ItemsTable :items="si_items"/>
                                </div>
                            
                                <div class="col-12 mt-4">
                                    <Taxes :taxes="taxes"/>
                                </div>

                                <div class="col-12 mt-4">
                                    <button class="btn btn-primary btn-block btn-lg" :class="process_payment_button">Process Store Credit</button>
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
                    var me = this
                    frappe.call({
                        method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.search_customer',
                        args: {
                            phone_number: this.customer.phone_number,
                            email: this.customer.email
                        },
                        callback: function(r) {
                            if (r.message) {
                                me.customer.first_name = r.message[0].first_name
                                me.customer.last_name = r.message[0].last_name
                                me.customer.email = r.message[0].ifw_email
                                // this.customer.phone_number = r.message.phone_number
                                me.customer.company = r.message[0].company
                                me.item_area = ""
                            }

                        }
                    })
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
                },
                clearCustomer(){
                    this.customer = {
                        phone_number: '',
                        email: '',
                        company: '',
                        first_name: '',
                        last_name: ''
                    }

                    this.item_area = "d-none"
                    this.selected_customer = ""
                    this.current_sales_invoice = ""
                    this.si_items = []
                    this.taxes = []
                },
                clearSI(){
                    this.si_items = []
                    this.taxes = []
                    this.selected_customer = ""
                    this.process_payment_button = "d-none"
                },
                loadSI() {
                    var me = this
                    frappe.call({
                        method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.load_si',
                        args: {
                            sales_invoice: this.current_sales_invoice
                        },
                        callback: function(r) {
                            if (r.items.length){
                                me.selected_customer = r.customer
                                me.si_items = r.items
                                me.taxes = []
                                me.process_payment_button = ""

                                $.each(r.taxes, (key, value)=>{
                                    if (typeof(value) === "object")
                                    {
                                        $.each(value, (ind, tax)=> {
                                            me.taxes.push({
                                                "name": tax.name,
                                                "amount": tax.amount
                                            })
                                        })
                                    }else{
                                        me.taxes.push({
                                            "name": key,
                                            "amount": value
                                        })
                                    }
                                })
                            }
                            else{
                                me.si_items = []
                                me.taxes = []
                                me.process_payment_button = "d-none"
                                frappe.show_alert(`Sales Invoice <b>${me.current_sales_invoice}</b> not found!`)
                            }
                        }
                    })
                }
            }
        })

        return this.vue_instance
    }

}
