frappe.provide('metactical.store_credit');
import SearchForm from './components/SearchForm.vue'
import ItemsTable from './components/ItemsTable.vue'
import Taxes from './components/Taxes.vue'
import CreditNote from './components/CreditNote.vue'

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
                Taxes,
                CreditNote
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
                    territory: "",
                    name: ""
                },
                si_items : [],
                taxes: [],
                credit_notes: [],
                item_area: "d-none",
                tax_types: [],
                process_payment_button: "d-none",
                freeze_fields: false,
                items_in_queue: []
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
                        <div class="col-md-4 mb-3">
                            <input type="text"  
                                    class="form-control" 
                                    placeholder="Sales Invoice" 
                                    v-model="current_sales_invoice"
                                    v-on:keyup.enter="loadSI">
                        </div>
                        <div class="col-md-4 mb-3">
                            <input type="text" class="form-control" placeholder="Customer Name" readonly v-model="selected_customer">
                        </div>
                        <div class="col-md-4 mb-3">
                            <button class="btn btn-primary" @click="loadSI">Load SI</button>
                            <button class="btn btn-primary" @click="editPrice">Edit</button>
                            <button class="btn btn-primary" @click="clearSI">Clear SI</button>
                            <button class="btn btn-primary" v-if="Object.keys(credit_notes).length" @click="createPDF">PDF</button>
                            <button class="btn btn-primary" v-if="Object.keys(credit_notes).length" @click="printPDF">Print</button>
                        </div>
                    </div>

                    <div class="row" :class="item_area">
                        <div class="col-lg-7">
                            <div class="row">
                                <div class="col-12">
                                    <ItemsTable :items="si_items" @updateTotals="updateTotals"/>
                                </div>
                            
                                <div class="col-12 mt-4">
                                    <Taxes :taxes="taxes" v-if="si_items.length > 0"/>
                                </div>

                                <div class="col-12 mt-4">
                                    <button class="btn btn-primary btn-block btn-lg" 
                                            :class="process_payment_button" 
                                            id="process_payment_button"
                                            @click="processStoreCredit">Process Store Credit</button>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-5 mt-4">
                            <div class="table-bg">
                                <div class="card-body">
                                    <CreditNote :credit_notes="credit_notes"/>
                                </div>
                            </div>
                        </div>
                    </div>
            `,
            mounted() {
                var me = this
                frappe.realtime.on("transfer_store_credit", (data) => {
                    if (data.error){
                        frappe.show_alert("Error: "+ data.error)
                        me.loadSI()
                    }
                    else if (data.sales_invoice == me.current_sales_invoice){
                        me.loadSI()
                    }

                    if (!data.error){
                        frappe.msgprint("Store Credit Processed Successfully For Sales Invoice " + data.sales_invoice)
                    }
                })
            },
            methods: {
                customerCleared(){
                    this.item_area = "d-none"
                    this.selected_customer = ""
                    this.current_sales_invoice = ""
                    this.si_items = []
                    this.taxes = []
                    this.credit_notes = []
                    this.freeze_fields = false
                },
                customerFound(){
                    this.item_area = ""
                    this.freeze_fields = true
                },
                clearSI(){
                    this.si_items = []
                    this.taxes = []
                    this.credit_notes = []
                    this.current_sales_invoice = ""
                    this.selected_customer = ""
                    this.process_payment_button = "d-none"
                },
                updateTotals() {
                    var total_amount = 0
                    var total_tax = 0
                    var discount = 0
                    var total_qty_returned = 0
                    var tax_types = []

                    $.each(this.si_items, (index, item) => {
                        total_amount += item.amount_with_out_format
                        discount +=  item.discount > 0 ? item.discount: 0
                        total_qty_returned += item.qty
                    })

                    $.each(this.taxes, (index, tax) => {
                        if (!["TTL Tax", "Discount", "TTL Store Credit", "Total Qty Returned"].includes(tax.name)){
                            total_tax += total_amount * (tax.rate / 100)
                            tax.amount = "$ " + Math.round(total_amount * (tax.rate / 100) * 100) / 100
                            tax_types.push(tax)
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
                            tax.amount = "$ " + Math.round((total_amount + total_tax) * 100) / 100
                        }
                        else if (tax.name === "Total Qty Returned"){
                            tax.amount = Math.round(total_qty_returned * 100) / 100
                        }
                    })

                    this.tax_types = tax_types
                    if (this.si_items.length)
                        this.process_payment_button = ""
                    else
                        this.process_payment_button = "d-none"
                },
                processStoreCredit(){
                    var me = this
                    if (!this.customer.name)
                    {
                        frappe.msgprint("Please Create/Search a Customer")
                        return
                    }

                    // change 'process store credit' button to 'processing'
                    $("#process_payment_button").html("Processing...").attr("disabled", true)
                    
                    frappe.call({
                        method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.transfer_store_credit',
                        args: {
                            sales_invoice: this.current_sales_invoice,
                            customer: this.customer.name,
                            items: this.si_items,
                            tax_types: this.tax_types
                        },
                        callback: function(r) {
                            if (r.success) {
                                var items = r.items
                                for (var i = 0; i < items.length; i++){
                                    me.items_in_queue.push(items[i])
                                }

                                me.loadSI()
                            }
                            else{
                                frappe.show_alert(r.error)
                            }
                            
                            $("#process_payment_button").html("Process Store Credit").attr("disabled", false)

                        }
                    })

                    me.clearSI()
                },
                loadSI() {
                    if (!this.current_sales_invoice)
                    {
                        frappe.show_alert("Please enter a Sales Invoice")
                        return
                    }

                    var me = this
                    frappe.call({
                        method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.load_si',
                        args: {
                            sales_invoice: this.current_sales_invoice
                        },
                        callback: function(r) {
                            if (r.items.length || Object.keys(r.credit_notes).length){
                                var existing_store_credit = false
                                var fully_returned_items = []

                                // remove item form items list if store credit is already processed or it is in the queue
                                $.each(r.items, (index, item) => {
                                    $.each(r.credit_notes, (sales_invoice, credit_notes) => {
                                        $.each(credit_notes, (key, credit_note) => {
                                            if (credit_note.retail_sku === item.retail_sku){
                                                if (-1 * credit_note.qty === item.qty){
                                                    fully_returned_items.push(item.name)
                                                }
                                                else{
                                                    item.qty = item.qty - (credit_note.qty)
                                                }
                                                existing_store_credit = true
                                            }
                                        })
                                    })

                                    if(me.items_in_queue.includes(item.name)){
                                        if (!fully_returned_items.includes(item.name))
                                            fully_returned_items.push(item.name)
                                    }
                                })

                                // remove fully returned items
                                me.si_items = r.items.filter(item => !fully_returned_items.includes(item.name))
                                me.selected_customer = r.customer
                                me.taxes = []
                                me.credit_notes = r.credit_notes

                                $.each(r.taxes, (key, value)=>{
                                    if (typeof(value) === "object")
                                    {
                                        $.each(value, (ind, tax)=> {
                                            me.taxes.push({
                                                "name": tax.name,
                                                "amount": tax.amount,
                                                "rate": tax.rate,
                                                "account_head": tax.account_head,
                                                "description": tax.description,
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

                                if (existing_store_credit){
                                    me.updateTotals()
                                }

                                if (!me.si_items.length)
                                    me.process_payment_button = "d-none"
                                else
                                    me.process_payment_button = ""
                            }
                            else{
                                me.si_items = []
                                me.taxes = []
                                me.credit_notes = []
                                me.process_payment_button = "d-none"
                                frappe.show_alert(`Sales Invoice <b>${me.current_sales_invoice}</b> not found!`)
                            }
                        }
                    })
                },
                editPrice(){
                    var me = this
                    var items = []
                    $.each(this.si_items, (index, item) => {
                        items.push({
                            "retail_sku": item.retail_sku,
                            "rate": item.rate,
                            "item_name": item.item_name,
                            "iname": item.name,
                            "qty": item.qty
                        })
                    })

                    var d = new frappe.ui.Dialog({
                        title: __("Edit Price & Quantity"),
                        fields: [
                            {
                                "label": "Items",
                                "fieldname": "edit_price",
                                "fieldtype": "Table",
                                "fields": [
                                    {
                                        "label": "",
                                        "fieldname": "iname",
                                        "fieldtype": "Data",
                                        "read_only": 1,
                                        "hidden": 1
                                    },
                                    {
                                        "label": "Item Name",
                                        "fieldname": "item_name",
                                        "fieldtype": "Data",
                                        "read_only": 1,
                                        "in_list_view": 1
                                    },
                                    {
                                        "label": "Retail SKU",
                                        "fieldname": "retail_sku",
                                        "fieldtype": "Data",
                                        "read_only": 1,
                                        "in_list_view": 1
                                    },
                                    {
                                        "label": "Price",
                                        "fieldname": "rate",
                                        "fieldtype": "Currency",
                                        "in_list_view": 1
                                    },
                                    {
                                        "label": "Quantity",
                                        "fieldname": "qty",
                                        "fieldtype": "Float",
                                        "in_list_view": 1
                                    }
                                ],
                                "data": items
                            }
                        ],
                        primary_action: function(){
                            var values = d.get_values()
                            var valid = true

                            $.each(values.edit_price, (index, item) => {
                                $.each(me.si_items, (ind, si_item) => {
                                    if (si_item.name === item.iname){
                                        if (item.rate > si_item.original_price){
                                            frappe.show_alert("Price cannot be greater than the original price")
                                            valid = false
                                            return
                                        }
                                        else if (item.qty > si_item.original_qty){
                                            frappe.show_alert("Quantity cannot be greater than the original quantity")
                                            valid = false
                                            return
                                        }
                                        else{
                                            si_item.rate = item.rate
                                            si_item.qty = item.qty
                                            si_item.amount_with_out_format = item.rate * si_item.qty
                                            si_item.amount = "$ " + si_item.amount_with_out_format
                                        }


                                    }
                                })

                                me.updateTotals()
                            })

                            if (valid)
                                d.hide()
                        },
                        primary_action_label: __("Update")
                    })

                    d.show()

                    setTimeout(() => {
                        $(`[data-route="manage-store-credit"] [data-fieldname="edit_price"] .row-index`).remove()
                    }, 200);
                },
                printPDF(){
                    var sales_invoice_to_print = ""
                    if (Object.keys(this.credit_notes).length > 1){
                        var prompt_fields = get_prompt_fields(Object.keys(this.credit_notes))
                        frappe.prompt(prompt_fields, (data) => {
                                if (data.value){
                                    sales_invoice_to_print = data.value
                                    print_pdf(sales_invoice_to_print, "/printview?", data.print_format)
                                }
                            }, __("Print Store Credit"), __("Print"))
                    }else{
                        var prompt_fields = get_prompt_fields(Object.keys(this.credit_notes), true)
                        frappe.prompt(prompt_fields, (data) => {
                            if (data.value){
                                sales_invoice_to_print = Object.keys(this.credit_notes)[0]
                                print_pdf(sales_invoice_to_print, "/printview?", data.print_format)
                            }
                        }, __("Print Store Credit"), __("Print"))
                    }
                },
                createPDF(){
                    var sales_invoice_to_print = ""
                    if (Object.keys(this.credit_notes).length > 1){
                        var prompt_fields = get_prompt_fields(Object.keys(this.credit_notes))
                        frappe.prompt(prompt_fields, (data) => {
                                if (data.value){
                                    sales_invoice_to_print = data.value
                                    create_pdf(sales_invoice_to_print, data.print_format)
                                }
                            }, __("Download Store Credit"), __("Download"))
                    }else{
                        var prompt_fields = get_prompt_fields(Object.keys(this.credit_notes), true)
                        frappe.prompt(prompt_fields, (data) => {
                            if (data.value){
                                sales_invoice_to_print = Object.keys(this.credit_notes)[0]
                                create_pdf(sales_invoice_to_print, data.print_format)
                            }
                        }, __("Download Store Credit"), __("Download"))
                    }
                }
            }
        })
        
        return this.vue_instance
    }
}

let create_pdf = function(sales_invoice, print_format="Standard"){
    open_url_post("/api/method/metactical.metactical.page.manage_store_credit.manage_store_credit.create_pdf",{
        sales_invoice: sales_invoice,
        print_format: print_format
    
    })
}


let print_pdf = function(sales_invoice, method, print_format="Standard"){

    let w = window.open(
        frappe.urllib.get_full_url(
            method +
                'doctype=' +
                encodeURIComponent("Sales Invoice") +
                '&name=' +
                encodeURIComponent(sales_invoice) +
                '&trigger_print=1' +
                '&format=' +
                encodeURIComponent(print_format) +
                '&letterhead=' +
                encodeURIComponent("")
        )
    );
    if (!w) {
        frappe.msgprint(__('Please enable pop-ups'));
        return;
    }
}



let get_prompt_fields = function(sales_invoices, single_store_credit = false){
    var fields = [
        {
            "label": __("Sales Invoice"),
            "fieldtype": "Select",
            "fieldname": "value",
            "options": sales_invoices,
            "default": single_store_credit ? sales_invoices[0] : "",
            "reqd": 1,
            "read_only": single_store_credit
        },
        {
            "label": __("Print Format"),
            "fieldtype": "Link",
            "fieldname": "print_format",
            "options": "Print Format",
            "default": "Credit Note POS - V1",
            "get_query": function(){
                return {
                    "filters": {
                        "name": ["in", ["Credit Note POS - V1", "Custom Store Credit - V1"]],
                    }
                }
            }
        }
    ]

    return fields
}
