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
                    let carrier_service = $(this.rateDialog.body).find('[name="carrier_service"]:checked').val()
                    frappe.xcall("metactical.utils.shipping.shipping.create_shipping", {
                        name: this.frm.docname,
                        provider: this.frm.doc.service_provider,
                        carrier_service: this.rate_dict[carrier_service]
                    }).then(r => {
                        this.rateDialog.hide()
                        this.frm.reload()
                    })
                },
                primary_action_label: __("Create Shipmnet")
            })
        }
        let [rows, last_id] = this.get_html()
        this.rateDialog.$body.html(`
        <table class="table table-bordered">
            <tr>
                <th></th>
                <th>${__("Service")}</th>
                <th>${__("Base Price")}</th>
                <th>${__("Total")}</th>
                <th>${__("Guaranteed Delivery")}</th>
                <th>${__("Expected Transit Time")}</th>
                <th>${__("Expected Delivery Date")}</th>
            </tr>
            ${rows}
        </table>`)
        this.rateDialog.$body.find(`[value="${last_id}"]`).prop('checked', true)
        this.rateDialog.show()
    },
    get_html: function () {
        let html = ''
        let last_rate=0;
        let last_id;
        this.rate_dict = {}
        this.rates.forEach(row => {
            if (last_rate > flt(row.shipment_amount) || last_rate===0) {
                last_id=row.carrier_service
                last_rate=flt(row.shipment_amount)
            }
            this.rate_dict[row.carrier_service] = row
            html += `<tr>&nbsp;
                        <td><input type="radio" name="carrier_service" value="${row.carrier_service}"></td>
                        <td>${row.service_name}</td>
                        <td>${row.base}</td>
                        <td>${row.shipment_amount}</td>
                        <td>${row.guaranteed_delivery ? "Yes" : "No"}</td>
                        <td>${row.expected_transit_time}</td>
                        <td>${row.expected_delivery_date}</td>
            </tr>`
        })
        return [html, last_id]
    }
})

$.extend(cur_frm.cscript, new ShipmentController({ frm: cur_frm }));
