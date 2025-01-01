<template>
	<div v-if="ratesLoaded" id="shipment-dialog">
		<div class="col-xs-12">
			<div class="form-group">
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
			</div>
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
			canadaPostRates: {},
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
			rateOptions: [],
			selectedCarrier: "",
			selectedServiceName: "",
			selectedProvider: "",
			selectKey: 0,
			selectedServices: {}
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
					console.log("Enabled Providers: ", me.enabledProviders);
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
				me.loadingMessage = `Loading rates for ${provider}`;
				let provider_key = provider.toLowerCase().replace(/\s+/g, '_');
				// Add any additional logic needed for each provider here
				frappe.call({
					method: "metactical.utils.shipping.shipping.get_rate",
					args: {
						"name": me.doc.frm.docname,
						"provider": provider
					},
					callback: function(ret){
						me.rates[provider_key] = {
							"label": provider,
							"rates": ret.message
						}

						me.tabsData.push({
							"title": provider,
							"rates": ret.message
						})
						
						ret.message.options.forEach(option => {
							me.rateOptions.push({
								"carrier_service": option.key,
								"service_name": option.val,
								"provider": provider,
								"label": `${provider} - ${option.val}`
							});
						});
						console.log(ret);
						me.canadaPostRates = ret.message;
						me.selectKey = me.rateOptions.length;
						
						// Select the least expensive service by default
						let min_value = 0;
						let last_id;
						me.tabsData.forEach(provider_data => {
							provider_data.rates.data.forEach(row => {
								//Initialize the minimum rate fot the piece
								if(!me.minimumRate[row.count]){
									me.minimumRate[row.count] = 0
								}

								row.items.forEach((item, idx) => {
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
									"selectedServicename": me.minimumService[row.count]
								}
							});
						});
						me.ratesLoaded = true;
					}
				});
			}
			console.log("Rates: ", me.rates);
			console.log("Default Selected: ", me.selectedServices);
		},

		select_service(){
			const selected = this.$refs.selectService.options[
				this.$refs.selectService.selectedIndex
			];
			this.selectedCarrier = selected.getAttribute("data-carrier");
			this.selectedServiceName = selected.getAttribute("data-service");
			this.selectedProvider = selected.getAttribute("data-provider");
			//this.selectedService = id;
			console.log("Selected Carrier: ", this.selectedCarrier, " Selected Service: ", this.selectedServiceName,
				" Seelcted Provider: ", this.selectedProvider
			);
		},

		create_shipments(){
			let me = this;
			this.creatingShipments = true;
			console.log("Selected: ", this.selectedServices);
			if(Object.keys(this.selectedServices).length > 0){
				let carrier_service = {}
				let service_name = {}
				let provider = '';
				// this.canadaPostRates.data.forEach(row => {
				// 	row.items.forEach(item => {
				// 		if (this.selectedService === 'carrier_service_' + item.carrier_service) {
				// 			carrier_service[row.name] = item.carrier_service;
				// 			service_name[row.name] = item.service_name;
				// 		}
				// 	});
				// });
				for (const row in this.selectedServices) {
					let piece = this.selectedServices[row];
					console.log("Piece: ", piece);
					provider = piece.selectedProvider;
					carrier_service[piece.piece_name] = piece.selectedCarrier;
					service_name[piece.piece_name] = piece.selectedServiceName
				}
				console.log("Provider: ", provider, " Carrier: ", carrier_service, " Service: ", service_name);
				frappe.call({
					method: "metactical.utils.shipping.shipping.create_shipping",
					args: {
						name: me.doc.frm.docname,
						provider: provider,
						carrier_service: carrier_service,
						service_name: service_name
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
			this.$set(this.selectedServices, count, {
				piece_name: piece_name,
				selectedProvider: item.provider,
				selectedCarrier: item.carrier_service,
				selectedServiceName: item.service_name
			});
		}
	}
}
</script>