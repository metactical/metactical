<template>
	<div class="tabs">
	  <div class="tab-buttons">
		<button
		  v-for="(tab, index) in tabs"
		  :key="index"
		  :class="{ active: activeTab === index }"
		  @click="setActiveTab(index)"
		>
		  {{ tab.title }}
		</button>
	  </div>
	  <div class="tab-content">
		<div v-if="tabs[activeTab]">
			<!-- Single table for carriers that don't support multiple parcels -->
			<table v-if="!tabs[activeTab].supports_multiple" class="table table-bordered">
			<tr>
				<th>All Parcels</th>
				<th>{{ __("Service") }}</th>
				<th>{{ __("Base Price") }}</th>
				<th>{{ __("Total") }}</th>
				<th>{{ __("Guaranteed Delivery") }}</th>
				<th>{{ __("Expected Transit Time") }}</th>
				<th>{{ __("Expected Delivery Date") }}</th>
			</tr>
			<tr v-for="(item, idx) in getSummarizedRates(tabs[activeTab].rates.data)">
				<td>
				<input type="radio"
					:name="item.provider.replace(/\s+/g, '')"
					:id="item.provider.replace(/\s+/g, '') + '_combined'"
					:checked="isSelectedSummaryService(item)"
					:data-piece="item.idx"
					:data-service-name="item.service_name"
					:data-provider="item.provider"
					:data-carrier="item.carrier_service"
					@change="selectSummaryService(item)"
				>
				</td>
				<td>{{ item.service_name }}</td>
				<td>{{ formatCurrency(item.total_base) }}</td>
				<td>{{ formatCurrency(item.total_amount) }}</td>
				<td>{{ item.guaranteed_delivery ? "Yes" : "No" }}</td>
				<td>{{ item.expected_transit_time }}</td>
				<td>{{ item.expected_delivery_date }}</td>
			</tr>
			</table>

			<!-- Original multiple tables for carriers that support multiple parcels -->
			<table v-else 
			v-for="row in tabs[activeTab].rates.data" 
			class="table table-bordered" 
			:data-row-name="row.name"
			>
			<tr>
				<th>
				Parcel No. 
				<span>{{ row.idx }}</span>
				</th>
				<th>{{ __("Service") }}</th>
				<th>{{ __("Base Price") }}</th>
				<th>{{ __("Total") }}</th>
				<th>{{ __("Guaranteed Delivery") }}</th>
				<th>{{ __("Expected Transit Time") }}</th>
				<th>{{ __("Expected Delivery Date") }}</th>
			</tr>
			<tr v-for="(item, idx) in row.items">
				<td>
				<input type="radio"
					:name="item.provider.replace(/\s+/g, '') + '_' + row.idx"
					:id="item.provider.replace(/\s+/g, '') + '_' + row.idx"
					:checked="isSelectedService(row.idx, item)"
					:data-piece="row.idx"
					:data-service-name="item.service_name"
					:data-provider="item.provider"
					:data-carrier="item.carrier_service"
					@change="selectService(row.idx, row.name, item)"
				>
				</td>
				<td>{{ item.service_name }}</td>
				<td>{{ item.base }}</td>
				<td>{{ item.shipment_amount }}</td>
				<td>{{ item.guaranteed_delivery ? "Yes" : "No" }}</td>
				<td>{{ item.expected_transit_time }}</td>
				<td>{{ item.expected_delivery_date }}</td>
			</tr>
			</table>
		</div>
	  </div>
	</div>
</template>
  
<script>
  export default {
	  name: "Tabs",
	  props: {
		  tabs: {
			  type: Array,
			  required: true,
		  },
		  selectedServices: {
			  type: Object, 
			  required: false
		  }
	  },
	  data() {
		  return {
			  activeTab: 0, // Index of the active tab
		  };
	  },
	  watch: {
		  selectedServices(newVal) {
			  console.log("Prop updated:", newVal);
		  },
	  },
	  methods: {
		setActiveTab(index) {
			console.log("Tabs: ", this.tabs);
			this.activeTab = index;
		},

		isSelectedService(idx, item) {
			let selectedProvider = this.selectedServices[idx]["selectedProvider"]
			let selectedCarrier = this.selectedServices[idx]["selectedCarrier"]
			let selectedServiceName = this.selectedServices[idx]["selectedServicename"]
			if(selectedProvider == item.provider && selectedCarrier == item.carrier_service 
				&& selectedServiceName == item.service_name) {
				return true;
			}
			else{
				return false;
			}
		},

		selectService(idx, piece_name, item){
			this.$emit('update-selected-service', { idx, piece_name, item });
		},

		getSummarizedRates(data) {
			if (!data || !data.length) return [];
			
			// Create a map to aggregate services across parcels
			const serviceMap = new Map();
			
			data.forEach(row => {
			row.items.forEach(item => {
				const key = `${item.provider}_${item.carrier_service}_${item.service_name}`;
				
				if (!serviceMap.has(key)) {
				// Initialize with first occurrence
				serviceMap.set(key, {
					...item,
					total_base: parseFloat(item.base) || 0,
					total_amount: parseFloat(item.shipment_amount) || 0,
					parcels: [row.idx],
					idx: "All"  // Indicating this is for all parcels
				});
				} else {
				// Update existing entry
				const existing = serviceMap.get(key);
				existing.total_base += parseFloat(item.base) || 0;
				existing.total_amount += parseFloat(item.shipment_amount) || 0;
				existing.parcels.push(row.idx);
				
				// Keep the latest delivery date
				if (item.expected_delivery_date) {
					const currentDate = new Date(existing.expected_delivery_date);
					const newDate = new Date(item.expected_delivery_date);
					if (newDate > currentDate) {
					existing.expected_delivery_date = item.expected_delivery_date;
					existing.expected_transit_time = item.expected_transit_time;
					}
				}
				}
			});
			});
			
			// Convert map back to array
			return Array.from(serviceMap.values());
		},
		
		isSelectedSummaryService(item) {
			// Check if all parcels have selected this service
			if (!item.parcels || !item.parcels.length) return false;
			
			return item.parcels.every(parcelCount => {
			const selected = this.selectedServices[parcelCount];
			return selected && 
					selected.selectedProvider === item.provider && 
					selected.selectedCarrier === item.carrier_service && 
					selected.selectedServicename === item.service_name;
			});
		},
		
		selectSummaryService(item) {
			// Update all parcels with this service
			if (!item.parcels || !item.parcels.length) return;
			
			// For each parcel, find the corresponding service and select it
			item.parcels.forEach(idx => {
				const data = this.tabs[this.activeTab].rates.data;
				const row = data.find(r => r.idx === idx);
				
				if (row) {
					const matchingItem = row.items.find(i => 
						i.provider === item.provider && 
						i.carrier_service === item.carrier_service &&
						i.service_name === item.service_name
					);
					
					if (matchingItem) {
						this.$emit('update-selected-service', { 
							idx, 
							piece_name: row.name, 
							item: matchingItem 
						});
					}
				}
			});
		},
		
		formatCurrency(value) {
			// Format number with 2 decimal places
			if (typeof value !== 'number') {
			value = parseFloat(value) || 0;
			}
			return value.toFixed(2);
		}
	  },
  };
  </script>
  
  <style scoped>
  .tabs {
	border: 1px solid #ddd;
	border-radius: 5px;
	width: 100%;
	margin: 20px auto;
	font-family: Arial, sans-serif;
  }
  .tab-buttons {
	display: flex;
	justify-content: space-around;
	background: #f5f5f5;
	border-bottom: 1px solid #ddd;
  }
  .tab-buttons button {
	padding: 10px 20px;
	border: none;
	background: none;
	cursor: pointer;
	font-size: 16px;
	transition: background 0.3s;
  }
  .tab-buttons button.active {
	background: #ddd;
	font-weight: bold;
  }
  .tab-content {
	padding: 20px;
  }
  </style>