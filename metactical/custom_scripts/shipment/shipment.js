const ShipmentController = frappe.ui.form.Controller.extend({
    refresh: function () {
        if (this.has_shipments() && this.frm.doc.docstatus===1) {
            this.make_rate_btn()
        }
        if (this.has_shipments(false)) {
            this.avoid_shipment_btn()
        }
    },
    has_shipments: function (fully = true) {
        let exists = {}
        this.frm.doc.shipments?.forEach(row => {
            if (row.row_id in exists) {
                exists[row.row_id] += 1
            } else {
                exists[row.row_id] = 1
            }
        })
        if (!fully) {
            return !$.isEmptyObject(exists)
        }
        let has = this.frm.doc.shipment_parcel.filter(row => row.count !== exists[row.name])
        return has.length
    },
    make_rate_btn: function () {
        this.frm.add_custom_button(__("Get Rate"), () => {
            if (this.frm.is_dirty()) {
                frappe.throw(__("Please Save before fetch rate"))
                return
            }
            this.fetch_rate()
        })
    },
    avoid_shipment_btn: function () {
        this.frm.add_custom_button(__("Void Shipment<small>(s)</small>"), () => {
            if (this.frm.is_dirty()) {
                frappe.throw(__("Please Save before fetch rate"))
                return
            }
            this.avoid_shipment()
        })
    },
    avoid_shipment: function () {
        let d = new frappe.ui.Dialog({
            title: __("Select Shipment to Void"),
            fields: this.frm.doc.shipments.map(r => {
                return {
                    fieldname: r.name,
                    fieldtype: 'Check',
                    label: r.shipment_id
                }
            }),
            primary_action_label: __('Void'),
            primary_action: values => {
                frappe.xcall('metactical.utils.shipping.shipping.avoid_shpment', {
                    name: this.frm.docname,
                    shipments_name: Object.keys(values).filter(r => values[r])
                })
                d.hide()
                this.frm.reload_doc()
            }
        })
        d.show()
    },
    fetch_rate: function () {
        frappe.xcall("metactical.utils.shipping.shipping.get_rate", {
            name: this.frm.docname,
            provider: this.frm.doc.service_provider
        }).then(r => {
            if (r) {
                this.show_rate(r)
            }
        })
    },
    show_rate: function (rates) {
        this.rates = rates
        if (!this.rateDialog) {
            this.rateDialog = new frappe.ui.Dialog({
                title: __("Choose best one."),
                size: 'large',
                minimizable: true,
                primary_action: () => {
                    this.rateDialog.disable_primary_action()
                    let carrier_service = {}
                    $(this.rateDialog.body).find('[name^="carrier_service_"]:checked').each(function () {
                        carrier_service[$(this).closest('table').attr('data-row-name')] = $(this).val()
                    })
                    if ($.isEmptyObject(carrier_service)) {
                        frappe.msgprint(__("Please select min one."))
                        return
                    }
                    frappe.xcall("metactical.utils.shipping.shipping.create_shipping", {
                        name: this.frm.docname,
                        provider: this.frm.doc.service_provider,
                        carrier_service: carrier_service
                    }).then(r => {
                        this.rateDialog.enable_primary_action()
                        this.rateDialog.hide()
                        this.frm.reload_doc()
                        let html = ''
                        r.forEach(file => {
                            html += `<embed src="${file}" type="application/pdf" frameBorder="0" scrolling="auto"
                            height="100%"
                            width="100%"
                        ></embed>`
                        })
                        let newWindow = window.open('', '_new')
                        newWindow.document.write(html)
                        newWindow.document.close()
                    })
                },
                primary_action_label: __(`Create Shipment<small>(s)</small>`)
            })
        }
        this.rateDialog.enable_primary_action()
        this.rateDialog.$body.html(frappe.render_template('shipment_rate', this.rates))
        this.rateDialog.$body.find(`select[name="carrier_service"]`).on('change', () => {
            let val = this.rateDialog.$body.find(`select[name="carrier_service"]`).val()
            if (!val) {
                return
            }
            this.rateDialog.$body.find(`input[value="${val}"]`).prop('checked', true)
        })
        // Select Defalut.
        let min_value = 0;
        let last_id;
        this.rates.data.forEach(row => {
            row.items.forEach(item => {
                if (flt(item.shipment_amount) < min_value || min_value == 0) {
                    min_value = flt(item.shipment_amount)
                    last_id = item.carrier_service
                }
            })
        })
        if (last_id) {
            this.rateDialog.$body.find(`select[name="carrier_service"]`).val(last_id).trigger('change')
        }
        // end select default
        this.rateDialog.show()
    },
    
    get_manifest: function(){
		let shipment_id = this.frm.doc.shipments[0].shipment_id;
		this.frm.call({
			method: "metactical.custom_scripts.shipment.shipment.get_manifest",
			args: {
				start_date: moment(this.frm.doc.creation).format("YYYYMMDD"),
				shipment_id: shipment_id,
				doctype: this.frm.doctype,
				docname: this.frm.docname
			},
			freeze: true,
			callback: function(ret){
				console.log({"ret": ret});
			}
		});
		
	}
})

$.extend(cur_frm.cscript, new ShipmentController({ frm: cur_frm }));
