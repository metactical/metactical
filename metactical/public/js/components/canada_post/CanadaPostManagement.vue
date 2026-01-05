<template>
	<div class="canada-post-management">
		<!-- Filters Section -->
		<div class="card mb-3">
			<div class="card-body">
				<div class="row">
					<div class="col-md-3">
						<div class="form-group">
							<label>Load</label>
							<select 
								v-model="filters.load_type" 
								class="form-control"
							>
								<option value="shipments_without_manifests">Shipments Without Manifests</option>
							</select>
						</div>
					</div>
					<div class="col-md-3">
						<div class="form-group">
							<label>Warehouse</label>
							<select 
								v-model="filters.warehouse" 
								class="form-control"
							>
								<option value="">All Warehouses</option>
								<option 
									v-for="warehouse in warehouses" 
									:key="warehouse" 
									:value="warehouse"
								>
									{{ warehouse }}
								</option>
							</select>
						</div>
					</div>
					<div class="col-md-2" v-if="showDateFilters">
						<div class="form-group">
							<label>From Date</label>
							<input 
								type="date" 
								v-model="filters.from_date" 
								class="form-control"
							>
						</div>
					</div>
					<div class="col-md-2" v-if="showDateFilters">
						<div class="form-group">
							<label>To Date</label>
							<input 
								type="date" 
								v-model="filters.to_date" 
								class="form-control"
							>
						</div>
					</div>
					<div :class="showDateFilters ? 'col-md-2' : 'col-md-6'">
						<div class="form-group">
							<label>&nbsp;</label>
							<button 
								class="btn btn-primary btn-block" 
								@click="fetchShipments"
								:disabled="loading"
							>
								<span v-if="loading">
									<i class="fa fa-spinner fa-spin"></i> Loading...
								</span>
								<span v-else>
									<i class="fa fa-download"></i> Load
								</span>
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Summary Cards -->
		<div class="row mb-3" v-if="hasLoadedData">
			<div class="col-md-4">
				<div class="card text-white bg-info">
					<div class="card-body">
						<h5 class="card-title">Canada Post Shipments</h5>
						<h2>{{ canadaPostShipments.length }}</h2>
					</div>
				</div>
			</div>
			<div class="col-md-4">
				<div class="card text-white bg-warning">
					<div class="card-body">
						<h5 class="card-title">ERPNext Only Shipments</h5>
						<h2>{{ erpnextShipments.length }}</h2>
					</div>
				</div>
			</div>
			<div class="col-md-4">
				<div class="card text-white bg-success">
					<div class="card-body">
						<h5 class="card-title">Available Groups</h5>
						<h2>{{ availableGroups.length }}</h2>
					</div>
				</div>
			</div>
		</div>

		<!-- Pickup Date Filter -->
		<div class="card mb-3" v-if="hasLoadedData && shipments.length > 0">
			<div class="card-body">
				<div class="row align-items-center">
					<div class="col-md-3">
						<div class="form-group mb-0">
							<label>Filter by Pickup Date</label>
							<input 
								type="date" 
								v-model="pickupDateFilter" 
								class="form-control"
								placeholder="Select date to filter"
							>
						</div>
					</div>
					<div class="col-md-2" v-if="pickupDateFilter">
						<button 
							class="btn btn-sm btn-secondary" 
							@click="pickupDateFilter = ''"
							style="margin-top: 28px;"
						>
							<i class="fa fa-times"></i> Clear Filter
						</button>
					</div>
					<div class="col-md-7" v-if="pickupDateFilter">
						<p class="text-muted mb-0" style="margin-top: 28px;">
							Showing {{ filteredShipments.length }} of {{ shipments.length }} shipment(s)
						</p>
					</div>
				</div>
			</div>
		</div>

		<!-- Loading State -->
		<div v-if="loading" class="text-center py-5">
			<i class="fa fa-spinner fa-spin fa-3x text-muted"></i>
			<p class="text-muted mt-3">Loading shipments...</p>
		</div>

		<!-- No Data State -->
		<div v-else-if="!loading && hasLoaded && !hasLoadedData" class="text-center py-5">
			<i class="fa fa-inbox fa-3x text-muted"></i>
			<p class="text-muted mt-3">No untransmitted shipments found</p>
			<p class="text-muted">All shipments have been transmitted or no shipments match the criteria</p>
		</div>

		<!-- Shipments Table -->
		<div v-else-if="hasLoadedData" class="card">
			<!-- Tabs -->
			<ul class="nav nav-tabs" style="margin: 0; border-bottom: 1px solid #d1d8dd;">
				<li class="nav-item">
					<a 
						class="nav-link" 
						:class="{ active: activeTab === 'canadapost' }"
						@click="switchTab('canadapost')"
						style="cursor: pointer;"
					>
						Canada Post ({{ canadaPostShipments.length }})
					</a>
				</li>
				<li class="nav-item">
					<a 
						class="nav-link" 
						:class="{ active: activeTab === 'erpnext' }"
						@click="switchTab('erpnext')"
						style="cursor: pointer;"
					>
						ERPNext Only ({{ erpnextShipments.length }})
					</a>
				</li>
			</ul>
			
			<div class="card-header">
				<h5 class="mb-0">{{ activeTab === 'canadapost' ? 'Canada Post Shipments' : 'ERPNext Only Shipments' }} ({{ filteredShipments.length }})</h5>
			</div>
			<div v-if="filteredShipments.length > 0" class="card-body p-0">
				<div class="table-responsive">
					<table class="table table-hover mb-0">
						<thead>
							<tr>
								<th>Shipment ID</th>
								<th>Tracking Number</th>
								<th>Pickup Date</th>
								<th>Warehouse</th>
								<th>Service</th>
								<th>Delivery Customer</th>
								<th>Group ID</th>
								<th>Action</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="shipment in filteredShipments" :key="shipment.name">
								<td>
									<a :href="`/app/shipment/${shipment.name}`" target="_blank">
										{{ shipment.name }}
									</a>
								</td>
								<td>
									<span v-if="shipment.tracking_number">
										{{ shipment.tracking_number }}
									</span>
									<span v-else class="text-muted">-</span>
								</td>
								<td>{{ formatDate(shipment.pickup_date) }}</td>
								<td>{{ shipment.warehouse }}</td>
								<td>
									<span class="badge badge-info">
										{{ shipment.service_provider }}
									</span>
								</td>
								<td>{{ shipment.delivery_customer || '-' }}</td>
								<td>
									<span class="badge badge-secondary">
										{{ shipment.group_id }}
									</span>
								</td>
								<td>
									<button 
										class="btn btn-sm btn-outline-primary"
										@click="viewShipment(shipment.name)"
									>
										<i class="fa fa-eye"></i> View
									</button>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
			<div v-else class="card-body text-center py-5">
				<i class="fa fa-inbox fa-3x text-muted"></i>
				<p class="text-muted mt-3">{{ pickupDateFilter ? 'No shipments match the selected date' : (activeTab === 'canadapost' ? 'No Canada Post shipments found' : 'No ERPNext only shipments found') }}</p>
				<button v-if="pickupDateFilter" class="btn btn-sm btn-secondary" @click="pickupDateFilter = ''">Clear Filter</button>
			</div>
		</div>
	</div>
</template>

<script>
export default {
	name: "CanadaPostManagement",
	data() {
		return {
			loading: false,
			hasLoaded: false,
			activeTab: 'canadapost',
			canadaPostShipments: [],
			erpnextShipments: [],
			warehouses: [],
			availableGroups: [],
			pickupDateFilter: '',
			filters: {
				load_type: "shipments_without_manifests",
				warehouse: "",
				from_date: this.getDefaultFromDate(),
				to_date: this.getDefaultToDate(),
			},
		};
	},
	computed: {
		showDateFilters() {
			return this.filters.load_type !== "shipments_without_manifests";
		},
		shipments() {
			return this.activeTab === 'canadapost' ? this.canadaPostShipments : this.erpnextShipments;
		},
		hasLoadedData() {
			return this.hasLoaded && (this.canadaPostShipments.length > 0 || this.erpnextShipments.length > 0);
		},
		filteredShipments() {
			if (!this.pickupDateFilter) {
				return this.shipments;
			}
			
			return this.shipments.filter(shipment => {
				if (!shipment.pickup_date) return false;
				const pickupDate = new Date(shipment.pickup_date).toISOString().split('T')[0];
				return pickupDate === this.pickupDateFilter;
			});
		},
	},
	mounted() {
		this.loadWarehouses();
	},
	methods: {
		refresh() {
			this.fetchShipments();
		},

		switchTab(tab) {
			this.activeTab = tab;
			this.pickupDateFilter = '';
		},

		getDefaultFromDate() {
			const date = new Date();
			date.setDate(date.getDate() - 30);
			return date.toISOString().split('T')[0];
		},

		getDefaultToDate() {
			return new Date().toISOString().split('T')[0];
		},

		async loadWarehouses() {
			try {
				const response = await frappe.call({
					method: "frappe.client.get_list",
					args: {
						doctype: "Warehouse",
						fields: ["name"],
						filters: {
							disabled: 0,
							is_group: 0
						},
						order_by: "name asc",
					},
				});

				if (response.message) {
					this.warehouses = response.message.map(w => w.name);
				}
			} catch (error) {
				console.error("Error loading warehouses:", error);
				frappe.msgprint({
					title: "Error",
					message: "Failed to load warehouses",
					indicator: "red",
				});
			}
		},

		async fetchShipments() {
			this.loading = true;
			this.canadaPostShipments = [];
			this.erpnextShipments = [];
			this.availableGroups = [];

			try {
				// Fetch Canada Post shipments
				const cpResponse = await frappe.call({
					method: "metactical.metactical.page.canada_post_manageme.canada_post_manageme.get_untransmitted_shipments",
					args: {
						warehouse: this.filters.warehouse,
					},
				});

				if (cpResponse.message) {
					console.log("Canada Post Shipments: ", cpResponse.message);
					this.canadaPostShipments = cpResponse.message.shipments || [];
					this.availableGroups = cpResponse.message.available_groups || [];
				}

				// Fetch ERPNext shipments (those not on Canada Post)
				const erpResponse = await frappe.call({
					method: "metactical.metactical.page.canada_post_manageme.canada_post_manageme.get_erpnext_untransmitted_shipments",
					args: {
						warehouse: this.filters.warehouse,
					},
				});

				if (erpResponse.message) {
					console.log("ERPNext Shipments: ", erpResponse.message);
					this.erpnextShipments = erpResponse.message.shipments || [];
				}

				this.hasLoaded = true;
			} catch (error) {
				console.error("Error fetching shipments:", error);
				frappe.msgprint({
					title: "Error",
					message: error.message || "Failed to fetch untransmitted shipments",
					indicator: "red",
				});
				this.hasLoaded = true;
			} finally {
				this.loading = false;
			}
		},

		viewShipment(shipmentName) {
			window.open(`/app/shipment/${shipmentName}`, "_blank");
		},

		formatDate(dateStr) {
			if (!dateStr) return "-";
			const date = new Date(dateStr);
			return date.toLocaleDateString('en-US', {
				year: 'numeric',
				month: 'short',
				day: 'numeric'
			});
		},
	},
};
</script>

<style scoped>
.canada-post-management {
	padding: 15px;
}

.card {
	border: 1px solid #d1d8dd;
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.card-header {
	background-color: #f8f9fa;
	border-bottom: 1px solid #d1d8dd;
	padding: 12px 15px;
}

.table th {
	background-color: #f8f9fa;
	font-weight: 600;
	font-size: 13px;
	text-transform: uppercase;
	color: #6c757d;
	border-bottom: 2px solid #d1d8dd;
}

.table td {
	vertical-align: middle;
	font-size: 14px;
}

.table-hover tbody tr:hover {
	background-color: #f8f9fa;
}

.badge {
	padding: 4px 8px;
	font-size: 12px;
}

.bg-info .card-title {
	font-size: 14px;
	font-weight: 500;
	margin-bottom: 5px;
}

.bg-info h2,
.bg-warning h2,
.bg-success h2 {
	margin: 0;
	font-size: 32px;
	font-weight: 700;
}
</style>
