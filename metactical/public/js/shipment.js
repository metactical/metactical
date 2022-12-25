const ShipmentController = frappe.ui.form.Controller.extend({
    refresh: function() {
        console.log(this.frm.doc.shipment_id)
        if (!this.frm.doc.shipment_id) {
            this.make_rate_btn()
        }
    },
    make_rate_btn: function() {
        this.frm.add_custom_button(__("Get Rate"), () => {
            if (this.frm.is_dirty()) {
                frappe.throw(__("Please Save before fetch rate"))
            }
            this.fetch_rate()
        })
    },
    fetch_rate: function() {
        frappe.xcall("metactical.utils.shipping.shipping.get_rate", {
            name: this.frm.docname,
            provider: this.frm.doc.service_provider
        }).then(r => {
            if (r) {
                this.show_rate(r)
            }
        })
    },
    show_rate: function(rates) {
        this.rateDialog = frappe.msgprint({
            title: __("Choose best one."),
            msg:`
        <div class="list-group radio-list-group">
            <div class="list-group-item disabled">
                <span class="list-group-item-text">
                    <span></span>
                    <span>${__("Service")}</span>
                    <span>${__("Base Price")}</span>
                    <span>${__("Total")}</span>
                    <span>${__("Guaranteed Delivery")}</span>
                    <span>${__("Expected Transit Time")}</span>
                    <span>${__("Expected Delivery Date")}</span>
                </span>
            </div>
            ${this.get_html(rates)}
        </div>
        `}).set_primary_action(__("Create Shipmnet"), ()=>{
            let service_code = $(this.rateDialog.body).find('[name="service_code"]:checked').val()
            frappe.xcall("metactical.utils.shipping.create_shipping", {
                name: this.frm.doc,
                provider: this.frm.doc.service_provider,
                service_code: service_code
            }).then(r=>{
                this.rateDialog.hide()
                this.frm.reload()
            })
        })
    },
    get_html: function(rates) {
        let html = ''
        rates.forEach(row=>{
            html += `<div class="list-group-item">&nbsp;
                <label>
                    <input type="radio" name="service_code" value="${row.service_code}">
                    <span class="list-group-item-text">
                        <span>${row.service_name}</span>
                        <span>${row.base}</span>
                        <span>${row.total}</span>
                        <span>${row.guaranteed_delivery?"Yes": "No"}</span>
                        <span>${row.expected_transit_time}</span>
                        <span>${row.expected_delivery_date}</span>
                    </span>
                </label>
            </div>`
        })
        return html
    }
})

$.extend(cur_frm.cscript, new ShipmentController({ frm: cur_frm }));
