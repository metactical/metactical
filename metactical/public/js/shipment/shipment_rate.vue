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
			canadaPostRates: {},
			selectedService: '',
			creatingShipments: false,
			loadingMessage: '',
			loadingDetails: [],
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
			selectedServices: {},
			selectedRate: ""
		}
	},
	props: {
		doc: {
			type: Object,
			required: true
		}
	},
	mounted() {
		this.init();
	},
	methods: {
		init() {
			let me = this;
			me.loadingMessage = 'Fetching providers';
			me.loadingDetails = [];
			frappe.call({
				method: "metactical.utils.shipping.shipping.get_enabled_providers",
				freeze: true,
				callback: function(ret){
					me.enabledProviders = ret.message || [];
					if(me.enabledProviders.length > 0){
						me.get_rates();
					}
					else{
						me.loadingMessage = __("No shipping providers are enabled");
					}
				}
			});
		},

		get_rates() {
			let me = this;
			me.rates = {};
			me.tabsData = [];
			me.rateOptions = [];
			me.ratesLoaded = false;
			me.loadingDetails = [];  // reset

			let expectedProviders = me.enabledProviders.length;
			let completedProviders = 0;

			frappe.call({
				method: "metactical.metactical.doctype.shipment_settings.shipment_settings.get_default_services",
				callback: function(settings_response) {
					const settings = settings_response.message || {};
					const defaultProvider = settings.default_shipping_service;
					const defaultCarrierService = settings.default_carrier_service;

					me.loadingMessage = __('Loading rates from providers…');

					// Initialise detail entries for each provider
					me.enabledProviders.forEach(p => {
						me.loadingDetails.push({
							provider: p,
							status: __('Queued'),
							done: false,
							error: null
						});
					});

					for (let provider of me.enabledProviders) {
						let provider_key = provider.toLowerCase().replace(/\s+/g, '_');

						// helper to update one provider row in loadingDetails
						const setStatus = (prov, fields) => {
							const idx = me.loadingDetails.findIndex(d => d.provider === prov);
							if (idx !== -1) {
								me.loadingDetails[idx] = { ...me.loadingDetails[idx], ...fields };
							}
						};

						setStatus(provider, { status: __('Requesting rates…'), done: false, error: null });

						frappe.call({
							method: "metactical.utils.shipping.shipping.get_rate",
							args: {
								"name": me.doc.frm.docname,
								"provider": provider
							},
							callback: function(ret) {
								completedProviders += 1;

								// If backend returned something unexpected, treat as error but don't block others
								if (!ret.message) {
									setStatus(provider, {
										status: __('Failed to load rates'),
										done: true,
										error: true
									});
									if (completedProviders >= expectedProviders) {
										me.ratesLoaded = true;
									}
									return;
								}

								setStatus(provider, { status: __('Rates loaded'), done: true, error: false });

								me.rates[provider_key] = {
									"label": provider,
									"rates": ret.message,
									"supports_multiple": ret.message.supports_multiple,
									"no_of_parcels": ret.message.data.length
								};

								me.tabsData.push({
									"title": provider,
									"rates": ret.message,
									"supports_multiple": ret.message.supports_multiple,
									"no_of_parcels": ret.message.data.length
								});

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
								
								// Process rates and select default or minimum rates
								me.tabsData.forEach(provider_data => {
									provider_data.rates.data.forEach(row => {
										if (!me.minimumRate[row.idx]) {
											me.minimumRate[row.idx] = 0;
										}

										let foundDefault = false;

										if (defaultProvider && defaultCarrierService) {
											row.items.forEach((item) => {
												item["provider"] = provider_data.title;
												if (provider_data.title === defaultProvider &&
													item.carrier_service === defaultCarrierService) {
													me.minimumRate[row.idx] = flt(item.shipment_amount);
													me.minimumProvider[row.idx] = provider_data.title;
													me.minimumCarrier[row.idx] = item.carrier_service;
													me.minimumService[row.idx] = item.service_name;
													foundDefault = true;
												}
											});
										}

										if (!foundDefault) {
											row.items.forEach((item) => {
												item["provider"] = provider_data.title;
												if (flt(item.shipment_amount) < me.minimumRate[row.idx]
													|| me.minimumRate[row.idx] === 0) {
													me.minimumRate[row.idx] = flt(item.shipment_amount);
													me.minimumProvider[row.idx] = provider_data.title;
													me.minimumCarrier[row.idx] = item.carrier_service;
													me.minimumService[row.idx] = item.service_name;
												}
											});
										}

										me.selectedServices[row.idx] = {
											"piece_name": row.name,
											"selectedProvider": me.minimumProvider[row.idx],
											"selectedCarrier": me.minimumCarrier[row.idx],
											"selectedServiceName": me.minimumService[row.idx],
											"selectedRate": me.minimumRate[row.idx]
										};
									});
								});

								if (completedProviders >= expectedProviders) {
									me.ratesLoaded = true;
								}
							},
							error: function(err) {
								completedProviders += 1;

								// Try to extract a meaningful message (often backend already displayed it)
								let msg = (err && err.message) || '';

								// Frappe sometimes sends server messages as JSON string array
								const server_messages = err && err.responseJSON && err.responseJSON._server_messages;
								if (!msg && server_messages) {
									try {
										const parsed = JSON.parse(server_messages);
										if (Array.isArray(parsed) && parsed.length) {
											// entries can be JSON strings
											const first = parsed[0];
											msg = typeof first === 'string' ? first : JSON.stringify(first);
										}
									} catch (e) {
										// ignore parsing errors
										msg = '';
									}
								}

								setStatus(provider, {
									status: __('Error loading rates'),
									done: true,
									error: msg || true
								});

								// Only show a popup if we actually have a message.
								// If backend already handled display, this prevents duplicates/noise.
								if (msg) {
									frappe.msgprint({
										title: __('Rate Error: {0}', [provider]),
										message: msg,
										indicator: 'red'
									});
								}

								if (completedProviders >= expectedProviders) {
									me.ratesLoaded = true;
								}
							}
						});
					}
				}
			});
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
					shipment_amount = flt(shipment_amount) + flt(piece.selectedRate);
				}
				console.log("Carrier service: ", carrier_service, " Amount: ", shipment_amount, " Service: ", service_name);
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
						if(!ret.message.printing_disabled){
							let html = ''
							ret.message.labels.forEach(file => {
								html += `<embed src="${file}" type="application/pdf" frameBorder="0" scrolling="auto"
								height="100%"
								width="100%"
							></embed>`
							})
							let newWindow = window.open('', '_new')
							newWindow.document.write(html)
							newWindow.document.close()
						}
						else{
							frappe.msgprint("Labels created succesfully");
						}
					}
				});
			}
			else{
				frappe.throw("Please select a service");
				
			}
		},
		updateSelectedService({idx, piece_name, item}) {
			console.log("Called");
			this.selectedServices[idx] = {
				piece_name: piece_name,
				selectedProvider: item.provider,
				selectedCarrier: item.carrier_service,
				selectedServiceName: item.service_name,
				selectedRate: item.shipment_amount
			};
			console.log("idx: ", idx, " piece: ", piece_name, " item: ", item);
		}
	}
}
</script>