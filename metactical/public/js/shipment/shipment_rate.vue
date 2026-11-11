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
			:selection="selection"
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
import { summarizeRates, parcelRate } from "./rate_utils";

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
			// The one (provider, service) choice for the whole shipment.
			selection: null,
			// Every parcel still needing a label, as [{idx, name}].
			allParcels: [],
			defaultServices: {},
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
					me.defaultServices = settings_response.message || {};

					me.loadingMessage = __('Loading rates from providers…');

					// Seeding waits until every provider has answered: the default has to
					// be chosen across all of them at once, so it lands on a single
					// carrier for the whole shipment.
					const finish = () => {
						if (completedProviders < expectedProviders) return;
						me.build_parcel_list();
						me.seed_default_selection();
						me.ratesLoaded = true;
					};

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
									finish();
									return;
								}

								setStatus(provider, { status: __('Rates loaded'), done: true, error: false });

								me.rates[provider_key] = {
									"label": provider,
									"rates": ret.message,
									"supports_multiple": ret.message.supports_multiple,
									"no_of_parcels": ret.message.data.length
								};

								// Stamp the provider on each rate so the raw rows stay
								// self-describing wherever they are read.
								ret.message.data.forEach(row => {
									(row.items || []).forEach(item => { item.provider = provider; });
								});

								me.tabsData.push({
									"title": provider,
									"rates": ret.message,
									"supports_multiple": ret.message.supports_multiple,
									// Missing means per-parcel pricing, which is what Canada
									// Post has always returned.
									"rates_per_parcel": ret.message.rates_per_parcel !== false,
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
								
								finish();
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

								finish();
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

		// Every parcel still awaiting a label, taken from the rates themselves:
		// Canada Post already leaves out parcels that are fully shipped, so this
		// must not come from frm.doc.shipment_parcel.
		build_parcel_list(){
			const byIdx = new Map();
			this.tabsData.forEach(tab => {
				(tab.rates.data || []).forEach(row => {
					if (!byIdx.has(row.idx)) {
						byIdx.set(row.idx, { idx: row.idx, name: row.name });
					}
				});
			});
			this.allParcels = Array.from(byIdx.values()).sort((a, b) => a.idx - b.idx);
		},

		// One summary row per service, across every provider, keeping only services
		// that can actually label the whole shipment.
		selectable_services(){
			let candidates = [];
			this.tabsData.forEach(tab => {
				summarizeRates(tab.rates.data, tab.title).forEach(summary => {
					// A per-parcel carrier can only be used when it quoted this service
					// for every parcel - otherwise some parcel would have no service code.
					if (tab.rates_per_parcel && summary.parcels.length < this.allParcels.length) {
						return;
					}
					candidates.push(summary);
				});
			});
			return candidates;
		},

		seed_default_selection(){
			const candidates = this.selectable_services();
			if (!candidates.length) return;

			const defaultProvider = this.defaultServices.default_shipping_service;
			const defaultCarrierService = this.defaultServices.default_carrier_service;

			let chosen = null;
			if (defaultProvider && defaultCarrierService) {
				chosen = candidates.find(
					c => c.provider === defaultProvider
						&& c.carrier_service === defaultCarrierService
				);
			}
			if (!chosen) {
				chosen = candidates.reduce(
					(best, c) => (!best || flt(c.total_amount) < flt(best.total_amount)) ? c : best,
					null
				);
			}
			this.applySelection(chosen);
		},

		// The single writer of selection state: one service for the whole shipment,
		// written to every parcel at once so the maps sent to the backend can never
		// straddle two carriers.
		applySelection(summary){
			if (!summary) return;

			this.selection = {
				provider: summary.provider,
				carrier_service: summary.carrier_service,
				service_name: summary.service_name,
				amount: flt(summary.total_amount)
			};

			const tab = this.tabsData.find(t => t.title === summary.provider);
			const rows = tab ? tab.rates.data : [];
			const next = {};
			this.allParcels.forEach(parcel => {
				next[parcel.idx] = {
					piece_name: parcel.name,
					selectedProvider: summary.provider,
					selectedCarrier: summary.carrier_service,
					selectedServiceName: summary.service_name,
					// Display only. 0 where the carrier priced the shipment as a whole
					// rather than this parcel; the total lives on this.selection.amount.
					selectedRate: parcelRate(
						rows, parcel.idx, summary.carrier_service, summary.service_name
					)
				};
			});
			this.selectedServices = next;
		},

		create_shipments(){
			let me = this;

			if (!this.selection || !Object.keys(this.selectedServices).length) {
				frappe.throw(__("Please select a service"));
				return;
			}

			let carrier_service = {}
			let service_name = {}
			let mismatched = [];

			for (const row in this.selectedServices) {
				let piece = this.selectedServices[row];
				// Tripwire: one carrier per shipment. Sending a mixed map means one
				// carrier receives another's service code, which comes back as an
				// opaque carrier error rather than anything actionable.
				if (piece.selectedProvider !== this.selection.provider) {
					mismatched.push(row);
				}
				carrier_service[piece.piece_name] = piece.selectedCarrier;
				service_name[piece.piece_name] = piece.selectedServiceName;
			}

			if (mismatched.length) {
				frappe.throw(__(
					"Parcel(s) {0} are not set to {1}. Please reopen Get Rate and choose one carrier for the whole shipment.",
					[mismatched.join(", "), this.selection.provider]
				));
				return;
			}

			this.creatingShipments = true;
			frappe.call({
				method: "metactical.utils.shipping.shipping.create_shipping",
				args: {
					name: me.doc.frm.docname,
					provider: this.selection.provider,
					carrier_service: carrier_service,
					service_name: service_name,
					shipment_amount: this.selection.amount
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
				},
				// Without this the button stays disabled after a failed label request
				// and the dialog has to be reopened.
				error: function(){
					me.creatingShipments = false;
				}
			});
		},
		updateSelectedService(summary) {
			this.applySelection(summary);
		}
	}
}
</script>