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
					<th>Service</th>
					<th>Base Price</th>
					<th>Total</th>
					<th>Guaranteed Delivery</th>
					<th>Expected Transit Time</th>
					<th>Expected Delivery Date</th>
				</tr>
				<tr v-for="(item, idx) in getSummarizedRates(tabs[activeTab].rates.data)" :key="idx">
					<td>
						<!-- One radio group for the whole dialog: picking a rate here replaces
						     the selection for every parcel, across providers. -->
						<input
							type="radio"
							name="shipment_rate"
							:id="'shipment_rate_' + serviceKey(item).replace(/\s+/g, '')"
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

			<!-- Multiple tables for carriers that support multiple parcels.
			     Unreachable today: no provider returns supports_multiple: true. If one
			     ever does, note that selectService below still emits a shipment-level
			     selection - a per-parcel selection would let two carriers share one
			     shipment, which is the bug this dialog now prevents. -->
			<table
				v-else
				v-for="row in tabs[activeTab].rates.data"
				:key="row.name"
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
				<tr v-for="(item, idx) in row.items" :key="idx">
					<td>
						<input
							type="radio"
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
import { summarizeRates, serviceKey } from "./rate_utils";

export default {
name: "Tabs",
props: {
	tabs: {
		type: Array,
		required: true,
	},
	selectedServices: {
		type: Object,
		required: false,
		default: () => ({}),
	},
	// The single (provider, service) choice for the whole shipment.
	selection: {
		type: Object,
		required: false,
		default: null,
	},
},
data() {
	return {
		activeTab: 0,
	};
},
watch: {
	selection: {
		handler() {
			this.setTabWithSelectedService();
		},
		deep: true,
	},
	tabs: {
		handler() {
			this.setTabWithSelectedService();
		},
		deep: true,
	},
},
mounted() {
	this.$nextTick(() => {
		this.setTabWithSelectedService();
	});
},
methods: {
	setActiveTab(index) {
		this.activeTab = index;
	},

	setTabWithSelectedService() {
		if (!this.tabs || this.tabs.length === 0 || !this.selection) {
			return;
		}
		const tabIndex = this.tabs.findIndex(
			(tab) => tab.title === this.selection.provider
		);
		if (tabIndex !== -1) {
			this.activeTab = tabIndex;
		}
		},

	serviceKey,

	isSelectedService(idx, item) {
		if (!this.selectedServices || !this.selectedServices[idx]) return false;

		const selected = this.selectedServices[idx];
		return (
			selected.selectedProvider === item.provider &&
			selected.selectedCarrier === item.carrier_service &&
			selected.selectedServiceName === item.service_name
		);
	},

	selectService(idx, piece_name, item) {
		// Emits the shipment-level summary for this service, not just this parcel.
		const summary = this.getSummarizedRates(
			this.tabs[this.activeTab].rates.data
		).find(
			(row) =>
				row.carrier_service === item.carrier_service &&
				row.service_name === item.service_name
		);
		if (summary) {
			this.$emit("update-selected-service", summary);
		}
	},

	getSummarizedRates(data) {
		const tab = this.tabs[this.activeTab];
		return summarizeRates(data, tab && tab.title);
	},

	isSelectedSummaryService(item) {
		const selected = this.selection;
		return !!(
			selected &&
			selected.provider === item.provider &&
			selected.carrier_service === item.carrier_service &&
			selected.service_name === item.service_name
		);
	},

	selectSummaryService(item) {
		this.$emit("update-selected-service", item);
	},

	formatCurrency(value) {
		if (typeof value !== "number") {
			value = parseFloat(value) || 0;
		}
		return value.toFixed(2);
	},
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