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
            el: "#store-credit-root",
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
                item_area: "",
                process_payment_button: "d-none",
                freeze_fields: false
            },
            template: `
                <div>
                    <SearchForm @customerCleared="customerCleared"
                                @customerFound="customerFound"
                                :customer="customer" 
                                :freeze_fields="freeze_fields"
                                :item_area="item_area"/>
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
                                    <ItemsTable :items="si_items" @updateTotals="updateTotals"/>
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
                customerCleared(){
                    this.item_area = "d-none"
                    this.selected_customer = ""
                    this.current_sales_invoice = ""
                    this.si_items = []
                    this.taxes = []
                    this.freeze_fields = false
                },
                customerFound(){
                    this.item_area = ""
                    this.freeze_fields = true
                },
                clearSI(){
                    this.si_items = []
                    this.taxes = []
                    this.selected_customer = ""
                    this.process_payment_button = "d-none"
                },
                updateTotals() {
                    console.log(this.taxes)
                    var total_amount = 0
                    var total_tax = 0
                    var discount = 0
                    var total_qty_returned = 0

                    $.each(this.si_items, (index, item) => {
                        console.log(item.amount_with_out_format, typeof(item.amount_with_out_format), total_amount, typeof(total_amount))
                        total_amount += item.amount_with_out_format
                        discount +=  item.discount > 0 ? item.discount: 0
                        total_qty_returned += item.qty
                    })

                    $.each(this.taxes, (index, tax) => {
                        if (!["TTL Tax", "Discount", "TTL Store Credit", "Total Qty Returned"].includes(tax.name)){
                            console.log(total_amount, typeof(total_amount), tax.rate, typeof(tax.rate))
                            total_tax += total_amount * (tax.rate / 100)
                            tax.amount = "$ " + Math.round(total_amount * (tax.rate / 100) * 100) / 100
                        }
                    })

                    $.each(this.taxes, (index, tax) => {
                        if (tax.name === "TTL Tax"){
                            tax.amount = "$ " + Math.round(total_tax * 100) / 100
                        }
                        else if (tax.name === "Discount"){
                            tax.amount = "$ " + Math.round(discount * 100) / 100
                        }
                        else if (tax.name === "TTL Store Credit"){
                            tax.amount = "$ " + Math.round((total_amount - discount + total_tax) * 100) / 100
                        }
                        else if (tax.name === "Total Qty Returned"){
                            tax.amount = Math.round(total_qty_returned * 100) / 100
                        }
                    })
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
                                                "amount": tax.amount,
                                                "rate": tax.rate
                                            })
                                        })
                                    }
                                    else{
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
