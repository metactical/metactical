<template>
    <div>
        <form @submit.prevent="searchCustomer">
            <div class="row">
                <div class="col-md-9">
                    <div class="row">
                        <div class="col-md-4">
                            <div class="form-group">
                                <input type="text" class="form-control" id="search-phone_number" :readonly="freeze_fields" v-input="onPhoneChange" >
                                <input type="hidden" id="search-country_code" v-model="customer.phone_number">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- Email -->
                            <div class="form-group">
                                <input type="text" class="form-control" id="search-email" :readonly="freeze_fields" v-model="customer.email" placeholder="Email">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="form-group">
                                <!-- Company Name -->
                                <input type="text" class="form-control" id="search-company" :readonly="freeze_fields" v-model="customer.company" placeholder="Company Name">
                            </div>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-4">
                            <!-- First Name -->
                            <div class="form-group">
                                <input type="text" class="form-control" id="search-first_name" :readonly="freeze_fields" v-model="customer.first_name" placeholder="First Name">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- Last Name -->
                            <div class="form-group">
                                <input type="text" class="form-control" id="search-last_name" :readonly="freeze_fields" v-model="customer.last_name" placeholder="Last Name">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- Territory -->
                            <div class="form-group">
                                <select class="form-control" id="search-territory" :readonly="freeze_fields" v-model="customer.territory">
                                </select>
                            </div>
                        </div>
                            
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="d-flex justify-content-end">
                        <div class="mr-3">
                            <button type="submit" class="btn btn-primary" id="search_customer">Search</button>
                        </div>
                        <div class="d-flex flex-column">
                            <button type="button" class="btn btn-secondary mb-2" @click="clearCustomer">Clear Customer</button>
                            <button type="button" class="btn btn-success" @click="createCustomer">Create Customer</button>
                        </div>
                    </div>                    
                </div>
            </div>

            
        </form>
    </div>
</template>
<script>

    export default {
        props: ["customer", "item_area", "freeze_fields"],
        data() {
            return {
                phone_no: ''
            }
        },
        mounted: function () {
            var me = this
            $(document).ready(() => {
                frappe.require(['assets/metactical/node_modules/intl-tel-input/build/js/intlTelInput.js',
                                "/assets/metactical/node_modules/intl-tel-input/build/css/intlTelInput.css"], () => {
                    const input = document.querySelector('#search-phone_number');
                    this.phone_no = window.intlTelInput(input, {
                        geoIpLookup: function(callback) {
                            $.get("http://ipinfo.io", function() {}, "jsonp").always(function(resp) {
                                var countryCode = (resp && resp.country) ? resp.country : "";
                                callback(countryCode);
                            });
                        },
                        utilsScript: "/assets/metactical/node_modules/intl-tel-input/build/js/utils.js"
                    }); 

                    this.addPhoneMasking()
                    input.addEventListener("countrychange", function() {
                        me.addPhoneMasking()
                    });
                });
            })

            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Territory',
                    filters: {
                        "is_group": 0,
                    },
                    limit_page_length: 1000,
                    order_by: "name asc"
                },
                callback: (r) => {
                    $.each(r.message, (key, value) => {
                        $('#search-territory').append(`<option value="${value.name}" >${value.name}</option>`)
                    })

                    $('#search-territory').val("British Columbia")
                }
            })

        },
        methods: {
            searchCustomer() {
                var valid = true       

                // remove country code from phone number
                this.customer.phone_number = this.phone_no.getNumber().replace("+"+this.phone_no.getSelectedCountryData().dialCode, '')
                if (!this.customer.phone_number && !this.customer.email){
                    frappe.msgprint('Please fill the phone number or email to search')
                    return
                }

                var phone_regex = /^\d{7,}$/
                if (this.customer.phone_number && phone_regex.test(this.customer.phone_number) === false){
                    $(`#search-phone_number`).addClass('is-invalid')
                    frappe.throw('Please enter a valid phone number')
                    valid = false
                }
                else{
                    $(`#search-phone_number`).removeClass('is-invalid')
                }
                
                var email_regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
                if(this.customer.email && email_regex.test(this.customer.email) === false){
                    $(`#search-email`).addClass('is-invalid')
                    frappe.throw('Please enter a valid email')
                    valid = false
                }
                else{
                    $(`#search-email`).removeClass('is-invalid')
                }

                // change search button to loading
                $("#search_customer").html('<i class="fa fa-spinner fa-spin"></i>').attr('disabled', true)
                $("#create_customer").attr('disabled', true)

                var me = this
                frappe.call({
                    method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.search_customer',
                    args: {
                        phone_number: this.customer.phone_number,
                        email: this.customer.email
                    },
                    callback: function(r) {
                        // change back to search
                        $("#search_customer").html('Search').attr('disabled', false)
                        $("#create_customer").attr('disabled', false)
                        
                        if (r.success){
                            if (r.customers.length == 1) {
                                me.updateCustomer(r.customers[0])
                            }
                            else if (r.customers.length > 1){
                                // let the user select customer if more than one customer found by the search
                                frappe.prompt([
                                    {
                                        fieldname: 'customer',
                                        fieldtype: 'Link',
                                        options: 'Customer',
                                        label: 'Select Customer',
                                        reqd: 1,
                                        get_query: function(){
                                            return {
                                                filters: {
                                                    name: ['in', r.customers.map(c => c.name)]
                                                }
                                            }
                                        }
                                    }
                                ], (values) => {
                                    me.updateCustomer(r.customers.find(c => c.name == values.customer))
                                }, 'Search Results', 'Select')
                            }
                            else{
                                me.customer.territory = "British Columbia"
                                frappe.msgprint("There is no customer with the provided details!")
                            }
                        }
                        else{
                            frappe.msgprint("Unable to search customer. Please try again later") 
                        }
                    }
                })

                this.$emit('search', this.customer)
            },
            updateCustomer(customer){
                this.customer.first_name = customer.first_name
                this.customer.last_name = customer.last_name
                this.customer.email = customer.email
                this.phone_no.setNumber(customer.phone_number)
                this.customer.company = customer.company
                this.customer.territory = customer.territory
                this.customer.name = customer.name

                this.$emit('customerFound', customer)
            },
            clearCustomer() {
                this.customer.first_name = ""
                this.customer.last_name = ""
                this.customer.email = ""
                this.customer.phone_number = ""
                this.customer.company = ""
                this.customer.territory = "British Columbia"
                this.freeze_fields = false
                this.phone_no.setNumber('')
                
                // remove disabled from all options
                $('#search-territory option').each(function(){
                    $(this).attr('disabled', false)
                })

                this.$emit("customerCleared")
            },
            addPhoneMasking(){
                frappe.require(['assets/metactical/node_modules/jquery-mask-plugin/dist/jquery.mask.min.js'], () => {                
                    var correct_format_sample = $("#search-phone_number").attr('placeholder');
                    // create the mask
                    var mask = '(000) 000-0000';
                    if (correct_format_sample)
                        mask = correct_format_sample.replace(/\d/g, '0')
                    $('#search-phone_number').mask(mask);
                });
            },
            createCustomer() {
                var me = this
                me.customer.phone_number = me.phone_no.getNumber()
                if (me.customer.phone_number.length < 10){
                    frappe.msgprint('Please enter a valid phone number')
                    return
                }

                var valid = this.validateForm()
                
                if (!valid){
                    frappe.msgprint('Please fill all the required fields')
                    return
                }

                frappe.call({
                    method: 'metactical.metactical.page.manage_store_credit.manage_store_credit.create_customer',
                    args: {
                        customer: this.customer
                    },
                    callback: (r) => {
                        if (r.success){
                            me.freeze_fields = true
                            me.customer.name = r.customer
                            me.$emit('customerFound')
                            frappe.show_alert('Customer created successfully')
                        }
                        else
                            frappe.msgprint(r.error)
                    }
                })
            },
            validateForm(){
                var valid = true
                $.each(this.customer, (key, value) => {
                    if (key === 'name')
                        return
                    
                    // regex to check phone number that starts with + and must more than 8 digits
                    var phone_regex = /^\+\d{7,}$/

                    if (!value && key !== 'company'){
                        $(`#search-${key}`).addClass('is-invalid')
                        valid = false
                    }
                    else if (key === 'phone_number' && phone_regex.test(value) === false){
                        $(`#search-${key}`).addClass('is-invalid')
                        frappe.throw('Please enter a valid phone number')
                        valid = false
                    }
                    else if (key === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)){
                        $(`#search-${key}`).addClass('is-invalid')
                        frappe.throw('Please enter a valid email')
                        valid = false
                    }
                    else{
                        $(`#search-${key}`).removeClass('is-invalid')
                    }
                })

                return valid
            },
        }
    }
</script>