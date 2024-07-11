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
                item_area: "",
                tax_types: [],
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
                        discount +=  item.discount > 0 ? item.discount * item.qty: 0
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
                                // 
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
                                var total_discount = 0

                                // remove item form items list if store credit is already processed or it is in the queue
                                $.each(r.items, (index, item) => {
                                    $.each(r.credit_notes, (sales_invoice, credit_notes) => {
                                        $.each(credit_notes, (key, credit_note) => {
                                            if (credit_note.retail_sku === item.retail_sku){
                                                if (-1 * credit_note.qty === item.qty){
                                                    fully_returned_items.push(item.name)
                                                }
                                                else{
                                                    item.qty = item.qty + (credit_note.qty)
                                                    item.amount = "$ " + (item.qty * item.rate)
                                                    item.amount_with_out_format = item.qty * item.rate
                                                }
                                                existing_store_credit = true
                                            }
                                        })
                                    })
                                    
                                    item.discount_amount = item.discount * item.qty
                                    total_discount += item.discount_amount
                                })

                                // update discount amount of credit notes
                                $.each(r.credit_notes, (sales_invoice, credit_notes) => {
                                    var total_discount = 0
                                    $.each(credit_notes, (key, credit_note) => {
                                        total_discount += credit_note.discount_amount * credit_note.qty
                                        credit_note.discount_amount = credit_note.discount_amount * credit_note.qty
                                    })

                                    credit_notes[0].si_discount_amount = total_discount + credit_notes[0].si_discount_amount
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
                                        if (key == "Discount"){
                                            me.taxes.push({
                                                "name": key,
                                                "amount": total_discount
                                            })
                                        }else{
                                            me.taxes.push({
                                                "name": key,
                                                "amount": value
                                            })
                                        }
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
                            "qty": item.qty,
                            "original_qty": item.original_qty
                        })
                    })

                    var d = new frappe.ui.Dialog({
                        title: __("Edit Price & Quantity"),
                        fields: [
                            {
                                "label": "Items",
                                "fieldname": "edit_price",
                                "fieldtype": "HTML",
                            }
                        ],
                        primary_action: function(){
                            var valid = true

                            if (valid)
                                d.hide()
                        },
                        primary_action_label: __("Close")
                    })

                    var html = me.get_modal_content(items)
                    me.set_modal_events()
                    d.fields_dict.edit_price.$wrapper.html($(html).html())
                    d.show()
                },
                get_modal_content(items){
                    var html = $(`<div id="editPriceDialog"></div>`)
                    var headers = $(`<div class="table-header">
                                        <div class="table-cell">Item Name</div>
                                        <div class="table-cell">
                                            Retail SKU
                                        </div>
                                        <div class="table-cell">
                                            Price
                                        </div>
                                        <div class="table-cell">
                                            Quantity
                                        </div>
                                    </div>`)
                                    
                    var table_body = $(`<div class="table-body"></div>`)
        
                    $.each(items, function(index, item) {
                        var row = $('<div class="table-row" data-target="'+item.retail_sku+'"></div>');
                        row.append('<div class="table-cell">' + item.item_name + '</div>');
                        row.append('<div class="table-cell">' + item.retail_sku + '</div>');
                        row.append('<div class="table-cell"><input type="number" steps=1 class="price-input form-control" value="' + item.rate + '"></div>');
                        row.append('<div class="table-cell"><input type="number" min=1 max="'+item.original_qty+'" onfocus="this.blur()" onkeydown="return false" class="quantity-input form-control" value="' + item.qty + '"></div>');
                        
                        table_body.append(row);
                    });

                    html.append(headers)
                    html.append(table_body)

                    return html
                },
                set_modal_events(){
                    var me = this
                    $(document).on("change", ".price-input", function(){
                        var price = $(this).val()
                        var retail_sku = $(this).closest(".table-row").data("target")
                        $.each(me.si_items, (index, item) => {
                            if (item.retail_sku === retail_sku){
                                if (parseFloat(price) <= item.original_price){
                                    item.rate = parseFloat(price)
                                    item.amount_with_out_format = item.rate * item.qty
                                    item.discount = item.price_list_rate - item.rate
                                    item.discount_amount = item.discount * item.qty
                                    item.amount = "$ " + item.amount_with_out_format
                                    me.updateTotals()
                                }
                                else{
                                    frappe.show_alert("Price cannot be greater than the original price")
                                    $(this).val(item.rate)
                                }
                            }
                        })

                    })

                    $(document).on("change", ".quantity-input", function(){
                        var qty = $(this).val()
                        var retail_sku = $(this).closest(".table-row").data("target")
                        $.each(me.si_items, (index, item) => {
                            if (item.retail_sku === retail_sku){
                                if (parseFloat(qty) <= item.original_qty){
                                    item.qty = parseFloat(qty)
                                    item.discount = item.price_list_rate - item.rate
                                    item.discount_amount = item.discount * item.qty
                                    item.amount_with_out_format = item.rate * item.qty
                                    item.amount = "$ " + item.amount_with_out_format
                                    me.updateTotals()
                                }
                                else{
                                    frappe.show_alert("Quantity cannot be greater than the original quantity")
                                    $(this).val(item.qty)
                                }
                            }
                        })
                    });
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
