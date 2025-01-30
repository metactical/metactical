import ShipmentRate from "./shipment/shipment_rate.vue"
frappe.provide("metactical.shipment_rate");

metactical.shipment_rate.ShipmentPopUp = class {
	constructor(doc) {
		this.doc = doc;
		this.body = doc.rateDialog.$body[0];
		this.initVueInstance();
	}

	initVueInstance() {
		console.log("Body: ", this.body, " Doc: ", this.doc);
		new Vue({
			el: this.body,
			render: (h) => h(ShipmentRate, {
				props: {
					doc: this.doc
				}
			})
		});
	}
};
