<template>
    <div>
        <form @submit.prevent="search">
            <div class="row">
                <div class="col-md-9">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="customer.phone_number" placeholder="Phone Number">
                            </div>
                        </div>
                        <div class="col-md-6">
                            <!-- Email -->
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="customer.email" placeholder="Email">
                            </div>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-4">
                            <div class="form-group">
                                <!-- Company Name -->
                                <input type="text" class="form-control" v-model="customer.company" placeholder="Company Name">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- First Name -->
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="customer.first_name" placeholder="First Name">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- Last Name -->
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="customer.last_name" placeholder="Last Name">
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="d-flex ">
                        <div class="mr-3">
                            <button type="submit" class="btn btn-primary">Search</button>
                        </div>
                        <div class="d-flex flex-column">
                            <button type="button" class="btn btn-secondary mb-2" @click="clearCustomer">Clear Customer</button>
                            <button type="button" class="btn btn-secondary">Create Customer</button>
                        </div>
                    </div>                    
                </div>
            </div>

            
        </form>
    </div>
</template>
<script>
    export default {
        props: ["customer", "item_area"],
        methods: {
            search() {
                this.$emit('search', this.customer)
            },
            clearCustomer() {
                this.$emit('clearCustomer')
            }
        }
    }
</script>