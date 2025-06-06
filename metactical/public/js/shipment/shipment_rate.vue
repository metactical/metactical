<template>
	<div v-if="ratesLoaded" id="shipment-dialog">
		<div class="col-xs-12">
			<!--<div class="form-group">
				<div class="clearfix"> <label class="control-label" style="padding-right: 0px;">{{ __("Select for All") }}</label> </div>
				<div class="control-input-wrapper">
					<div class="control-input flex align-center">
						<select type="text"
							v-on:change="select_service"
							class="input-with-feedback form-control ellipsis" 
							name="carrier_service"
							ref="selectService"
							:key="selectKey"
							:value="selectedService">
								<option v-for="(option, index) in rateOptions" 
									:key="index"
									:data-carrier="option.carrier_service" 
									:data-service="option.service_name"
									:data-provider="option.provider">
									{{ option.label }}
								</option>
						</select>
						<div class="select-icon ">
							<svg class="icon  icon-sm" style="">
								<use class="" href="#icon-select"></use>
							</svg>
						</div>
					</div>
					<div class="control-value like-disabled-input" style="display: none;">Company</div>
					<p class="help-box small text-muted"></p>
				</div>
			</div>-->
		</div>
		<Tabs :tabs="tabsData" 
			:selectedServices="selectedServices"  
			@update-selected-service="updateSelectedService" />
		<div class="col-xs-12">
			<button class="btn btn-primary btn-sm" @click="create_shipments()" :disabled="creatingShipments">
				Create Shipment(s)
			</button>
		</div>
	</div>
	<div v-else>
		<div class="loading-animation">
			<p><center>{{ loadingMessage }}...</center></p>
		</div>
	</div>
</template>

<script>
import Tabs from "./tabs.vue";

export default {
	components: {
		Tabs,
	},
	data() {
		return {
			ratesLoaded: false,
			//canadaPostRates: {},
			selectedService: '',
			creatingShipments: false,
			loadingMessage: '',
			enabledProviders: [],
			rates: {},
			minimumRate: {},
			minimumProvider: {},
			minimumService: {},
			minimumCarrier: {},
			noOfProviders: 0,
			tabsData: [],
			//rateOptions: [],
			selectedCarrier: "",
			selectedServiceName: "",
			selectedProvider: "",
			selectKey: 0,
			selectedServices: {},
			selectedRate: ""
		}
	},
	props: {
		doc: {
			type: Object,
			Required: true
		}
	},
	mounted() {
		this.init();
	},
	methods: {
		init() {
			let me = this;
			me.loadingMessage = 'Fetching providers'
			frappe.call({
				method: "metactical.utils.shipping.shipping.get_enabled_providers",
				freeze: true,
				callback: function(ret){
					me.enabledProviders = ret.message;
					if(me.enabledProviders.length > 0){
						me.get_rates();
					}
					else{
						frappe.throw(__("No shipping providers are enabled"));
					}
				}
			});
		},

		get_rates(){
			let me = this;
			me.rates = {};
			me.tabsData = [];
			for (let provider of me.enabledProviders) {
				me.loadingMessage = `Loading rates...`;
				let provider_key = provider.toLowerCase().replace(/\s+/g, '_');
				// Add any additional logic needed for each provider here
				frappe.call({
					method: "metactical.utils.shipping.shipping.get_rate",
					args: {
						"name": me.doc.frm.docname,
						"provider": provider
					},
					callback: function(ret){
						// me.rates[provider_key] = {
						// 	"label": provider,
						// 	"rates": ret.message,
						// 	"supports_multiple": ret.message.supports_multiple,
						// 	"no_of_parcels": ret.message.data.length
						// }

						// If the service provider allows multiple shipping services to be
						// selected for shipments with multiple parcels, then show mutiple tables
						// depending on the no of parcels. Otherwise the 
						
						// The format for tabs Data 
						// tabsData = [
						// 	{
						// 		no_of_parcels: Int16Array,
						// 		rates: [],
						// 		supports_multiple: Boolean,
						// 		title: "sample Title"
						// 	}
						// ]

						// rates = [
						// 	{
						// 		"count": 1,
						// 		"parcel_name": ['name'],
						// 		"services": []
						// 	}
						// ]

						// services = [
						// 	{
						// 		base: "37.76",
						// 		carrier_service: "DOM.EP",
						// 		expected_delivery_date: "2025-02-06",
						// 		expected_transit_time: "4",
						// 		guaranteed_delivery: "true",
						// 		provider: "Canada Post",
						// 		service_name: "Expedited Parcel",
						// 		shipment_amount: "53.77",
						//		
						// 	}
						// ]

						let rates = []
						if(ret.message.supports_multiple){
							ret.message.data.forEach(data => {
								let services = []
								data.items.forEach(option => {
									services.push({
										base: option.base,
										carrier_service: option.carrier_service,
										expected_delivery_date: option.expected_delivery_date,
										expected_transit_time: option.expected_transit_time,
										guaranteed_delivery: option.guaranteed_delivery,
										provider: provider,
										service_name: option.service_name,
										shipment_amount: option.shipment_amount,
									});
								});
								rates.push({
									"count": data.count,
									"parcel_name": [data.name],
									"services": services
								});
							});
						}
						else{
							let temp_services = {}
							let services = []
							let parcel_names = []
							ret.message.data.forEach(data => {
								data.items.forEach(option => {
									if (temp_services[option.service_name]) {
										temp_services[option.service_name].base = temp_services[option.service_name].base + option.base;
										temp_services[option.service_name].shipment_amount = temp_services[option.service_name].shipment_amount + option.shipment_amount;
									} else {
										temp_services[option.service_name] = { 
											base: option.base,
											carrier_service: option.carrier_service,
											expected_delivery_date: option.expected_delivery_date,
											expected_transit_time: option.expected_transit_time,
											guaranteed_delivery: option.guaranteed_delivery,
											provider: provider,
											service_name: option.service_name,
											shipment_amount: option.shipment_amount,

										};
									}
								});
								parcel_names.push(data.name);
							});
							
							for (let service in temp_services) {
								services.push({
									base: temp_services[service].base,
									carrier_service: temp_services[service].carrier_service,
									expected_delivery_date: temp_services[service].expected_delivery_date,
									expected_transit_time: temp_services[service].expected_transit_time,
									guaranteed_delivery: temp_services[service].guaranteed_delivery,
									provider: temp_services[service].provider,
									service_name: temp_services[service].service_name,
									shipment_amount: temp_services[service].shipment_amount
								});
							}
							// temp_services.forEach(service => {
							// 	services.push({
							// 		base: service.base,
							// 		carrier_service: service.carrier_service,
							// 		expected_delivery_date: service.expected_delivery_date,
							// 		expected_transit_time: service.expected_transit_time,
							// 		guaranteed_delivery: service.guaranteed_delivery,
							// 		provider: service.provider,
							// 		service_name: service.service_name,
							// 		shipment_amount: service.shipment_amount
							// 	})
							// });

							rates.push({
								count: 1,
								parcel_name: parcel_names,
								services: services
							});
						}

						console.log("Rates: ", rates);
						
						// me.tabsData.push({
						// 	"title": provider,
						// 	"rates": ret.message,
						// 	"supports_multiple": ret.message.supports_multiple,
						// 	"no_of_parcels": ret.message.data.length
						// })

						me.tabsData.push({
							"title": provider,
							"rates": rates,
							"supports_multiple": ret.message.supports_multiple,
							"no_of_parcels": ret.message.data.length
						});

						console.log("TabsData: ", me.tabsData);
						
						ret.message.options.forEach(option => {
							me.rateOptions.push({
								"carrier_service": option.key,
								"service_name": option.val,
								"provider": provider,
								"label": `${provider} - ${option.val}`
							});
						});
						me.canadaPostRates = ret.message;
						me.selectKey = me.rateOptions.length;
						
						//Select the least expensive service by default
						let min_value = 0;
						let last_id;
						me.tabsData.forEach(provider_data => {
							provider_data.rates.forEach(row => {
								//Initialize the minimum rate fot the piece
								if(!me.minimumRate[row.count]){
									me.minimumRate[row.count] = 0
								}

								row.forEach((item, idx) => {
									item["provider"] = provider_data.title;
									if (flt(item.shipment_amount) < me.minimumRate[row.count] 
										|| me.minimumRate[row.count] == 0) {

										me.minimumRate[row.count] = flt(item.shipment_amount)
										me.minimumProvider[row.count] = provider_data.title;
										me.minimumCarrier[row.count] = item.carrier_service;
										me.minimumService[row.count] = item.service_name
									}
								})

								// Add minimum rate as default selected service
								me.selectedServices[row.count] = {
									"piece_name": row.name,
									"selectedProvider": me.minimumProvider[row.count],
									"selectedCarrier": me.minimumCarrier[row.count],
									"selectedServicename": me.minimumService[row.count],
									"selectedRate": me.minimumRate[row.count]
								}
							});
						});
						me.ratesLoaded = true;
					}
				});
			}
		},

		select_service(){
			const selected = this.$refs.selectService.options[
				this.$refs.selectService.selectedIndex
			];
			this.selectedCarrier = selected.getAttribute("data-carrier");
			this.selectedServiceName = selected.getAttribute("data-service");
			this.selectedProvider = selected.getAttribute("data-provider");
		},

		create_shipments(){
			let me = this;
			this.creatingShipments = true;
			if(Object.keys(this.selectedServices).length > 0){
				let carrier_service = {}
				let service_name = {}
				let provider = '';
				let shipment_amount = 0;
				
				for (const row in this.selectedServices) {
					let piece = this.selectedServices[row];
					console.log("Piece: ", piece);
					provider = piece.selectedProvider;
					carrier_service[piece.piece_name] = piece.selectedCarrier;
					service_name[piece.piece_name] = piece.selectedServiceName;
					shipment_amount = shipment_amount + piece.selectedRate;
				}
				console.log("Carrier service: ", carrier_service, " Amount: ", shipment_amount);
				frappe.call({
					method: "metactical.utils.shipping.shipping.create_shipping",
					args: {
						name: me.doc.frm.docname,
						provider: provider,
						carrier_service: carrier_service,
						service_name: service_name,
						shipment_amount: shipment_amount
					},
					freeze: true,
					callback: function(ret){
						me.creatingShipments = false;
						me.doc.rateDialog.hide()
						me.doc.frm.reload_doc()
						let html = ''
						ret.message.forEach(file => {
							html += `<embed src="${file}" type="application/pdf" frameBorder="0" scrolling="auto"
							height="100%"
							width="100%"
						></embed>`
						})
						let newWindow = window.open('', '_new')
						newWindow.document.write(html)
						newWindow.document.close()
					}
				});
			}
			else{
				frappe.throw("Please select a service");
				
			}
		},
		updateSelectedService({count, piece_name, item}) {
			console.log("Item: ", item);
			this.$set(this.selectedServices, count, {
				piece_name: piece_name,
				selectedProvider: item.provider,
				selectedCarrier: item.carrier_service,
				selectedServiceName: item.service_name,
				selectedRate: item.shipment_amount
			});
		}
	}
}
</script>