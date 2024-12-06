<template>
	<div v-if="ratesLoaded" id="shipment-dialog">
		<div class="col-xs-12">
			<div class="form-group">
				<div class="clearfix"> <label class="control-label" style="padding-right: 0px;">{{ __("Select for All") }}</label> </div>
				<div class="control-input-wrapper">
					<div class="control-input flex align-center">
						<select type="text"
							v-on:change="select_service($event.target.value, 'select')"
							class="input-with-feedback form-control ellipsis" 
							name="carrier_service"
							:value="selectedService">
								<option>&nbsp;</option>
								<option v-for="option in canadaPostRates.options" :value="'carrier_service_' + option.key">{{ option.val }}</option>
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
		<div v-for="(carrier_rates, carrier_service) in rates">
			<table v-for="row in carrier_rates.rates.data" class="table table-bordered" :data-row-name="row.name">
				<tr>
					<th>
						{{ __("Row") }} # {{ row.idx }}
						{{ __("Count") }} # {{ row.count }}
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
						<input type="radio" :name="carrier_service + '_' + item.carrier_service" 
							:checked="selectedService === carrier_service + '_' + item.carrier_service"
							v-on:change="select_service(carrier_service + '_' + item.carrier_service, 'check')"
							:value="item.carrier_service" 
							:data-service-name="item.service_name">
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
export default {
	data() {
		return {
			ratesLoaded: false,
			canadaPostRates: {},
			selectedService: '',
			creatingShipments: false,
			loadingMessage: '',
			enabledProviders: [],
			rates: {},
			minimumRate: 0,
			minimumProvider: '',
			minimumService: ''
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

						me.ratesLoaded = true;
						console.log(ret);
						me.canadaPostRates = ret.message;

						// Select the least expensive service by default
						let min_value = 0;
						let last_id;
						me.rates[provider_key].rates.data.forEach(row => {
							row.items.forEach((item, idx) => {
								if (flt(item.shipment_amount) < me.minimumRate || me.minimumRate == 0) {
									me.minimumRate = flt(item.shipment_amount)
									me.minimumProvider = provider_key;
									me.minimumService = item.carrier_service;
								}
							})
						})
						me.selectedService = me.minimumProvider + '_' + me.minimumService;
						console.log("Selected Service: ", me.selectedService);
					}
				});
			}
			console.log("Rates: ", me.rates);
		},

		select_service(id, method){
			this.selectedService = id;
			console.log("Selected: ", this.selectedService);
		},

		create_shipments(){
			let me = this;
			this.creatingShipments = true;
			if(this.selectedService){
				let carrier_service = {}
				let service_name = {}
				this.canadaPostRates.data.forEach(row => {
					row.items.forEach(item => {
						if (this.selectedService === 'carrier_service_' + item.carrier_service) {
							carrier_service[row.name] = item.carrier_service;
							service_name[row.name] = item.service_name;
						}
					});
				});
				frappe.call({
					method: "metactical.utils.shipping.shipping.create_shipping",
					args: {
						name: me.doc.frm.docname,
						provider: me.doc.frm.doc.service_provider,
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
		}
	}
}
</script>