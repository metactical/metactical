const ShipmentController = frappe.ui.form.Controller.extend({
    refresh: function () {
        if (!this.frm.doc.shipment_id) {
            this.make_rate_btn()
        }
    },
    make_rate_btn: function () {
        this.frm.add_custom_button(__("Get Rate"), () => {
            if (this.frm.is_dirty()) {
                frappe.throw(__("Please Save before fetch rate"))
            }
            this.fetch_rate()
        })
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
                    $(this.rateDialog.body).find('[name^="carrier_service_"]:checked').each(function(){
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
                    })
                },
                primary_action_label: __(`Create Shipmnet<small>(s)</small>`)
            })
        }
        this.rateDialog.enable_primary_action()
        this.rateDialog.$body.html(frappe.render_template('shipment_rate', this.rates))
        this.rateDialog.$body.find(`select[name="carrier_service"]`).on('click', ()=>{
            let val = this.rateDialog.$body.find(`select[name="carrier_service"]`).val()
            if (!val) {
                return
            }
            this.rateDialog.$body.find(`input[value="${val}"]`).prop('checked', true)
        })
        this.rateDialog.show()
    }
})

$.extend(cur_frm.cscript, new ShipmentController({ frm: cur_frm }));
