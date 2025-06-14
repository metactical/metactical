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
			  <table v-for="row in tabs[activeTab].rates.data" class="table table-bordered" :data-row-name="row.name">
				  <tr>
					  <!-- <th>
						  {{ __("Row") }} # {{ row.idx }}
						  {{ __("Count") }} # {{ row.count }}
					  </th> -->
					  <th>
						  Parcel No. 
						  <span v-if="!tabs[activeTab].supports_multiple">
							  {{ Array.from({ length: tabs[activeTab].no_of_parcels }, (_, i) => i + 1).join(', ') }}
						  </span>
						  <span v-else>
							  {{ row.count }}
						  </span>
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
							  :name="item.provider.replace(/\s+/g, '') + '_' + row.count"
							  :id="item.provider.replace(/\s+/g, '') + '_' + row.count"
							  :checked="isSelectedService(row.count, item)"
							  :data-piece="row.count"
							  :data-service-name="item.service_name"
							  :data-provider="item.provider"
							  :data-carrier="item.carrier_service"
							  @change="selectService(row.count, row.name, item)"
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
			  this.activeTab = index;
		  },
  
		  isSelectedService(count, item) {
			  let selectedProvider = this.selectedServices[count]["selectedProvider"]
			  let selectedCarrier = this.selectedServices[count]["selectedCarrier"]
			  let selectedServiceName = this.selectedServices[count]["selectedServicename"]
			  if(selectedProvider == item.provider && selectedCarrier == item.carrier_service 
				  && selectedServiceName == item.service_name) {
				  return true;
			  }
			  else{
				  return false;
			  }
		  },
  
		  selectService(count, piece_name, item){
			  this.$emit('update-selected-service', { count, piece_name, item });
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