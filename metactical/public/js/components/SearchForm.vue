<template>
    <div>
        <form @submit.prevent="search">
            <div class="row">
                <div class="col-md-9">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="phone_number" placeholder="Phone Number">
                            </div>
                        </div>
                        <div class="col-md-6">
                            <!-- Email -->
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="email" placeholder="Email">
                            </div>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-4">
                            <div class="form-group">
                                <!-- Company Name -->
                                <input type="text" class="form-control" v-model="company_name" placeholder="Company Name">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- First Name -->
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="first_name" placeholder="First Name">
                            </div>
                        </div>
                        <div class="col-md-4">
                            <!-- Last Name -->
                            <div class="form-group">
                                <input type="text" class="form-control" v-model="last_name" placeholder="Last Name">
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
                            <button type="button" class="btn btn-secondary mb-2">Clear Customer</button>
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
        data() {
            return {
                searchTerm: ''
            }
        },
        methods: {
            search() {
                this.$emit('search', this.searchTerm)
            }
        }
    }
</script>