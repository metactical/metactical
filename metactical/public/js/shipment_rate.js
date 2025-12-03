import ShipmentRate from "./shipment/shipment_rate.vue"
import { createApp, h } from "vue";

frappe.provide("metactical.shipment_rate");

metactical.shipment_rate.ShipmentPopUp = class {
	constructor(doc) {
		this.doc = doc;
		this.body = doc.rateDialog.$body[0];
		this.initVueInstance();
	}

	initVueInstance() {
		console.log("Body: ", this.body, " Doc: ", this.doc);

		// Create and mount Vue 3 app
		const app = createApp({
			render: () =>
				h(ShipmentRate, {
					doc: this.doc,          // props
				}),
		});

		app.mount(this.body);
	}
};
