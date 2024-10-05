(() => {
  // frappe-html:/media/n/Files/projects/metactical_v14/apps/metactical/metactical/public/js/template/shipment_rate.html
  frappe.templates["shipment_rate"] = `<div id="shipment-dialog">
    <div class="col-xs-12">
        <div class="form-group">
            <div class="clearfix"> <label class="control-label" style="padding-right: 0px;">{{ __("Select for All") }}</label> </div>
            <div class="control-input-wrapper">
                <div class="control-input flex align-center"><select type="text"
                        class="input-with-feedback form-control ellipsis" name="carrier_service">
                        <option>&nbsp;</option>
                        {% for opt in options %}
                        <option value="{{opt.key}}">{{ opt.val }}</option>
                        {% endfor %}
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
    {% for row in data %}
    <table class="table table-bordered" data-row-name="{{ row.name }}">
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
        {% for item in row.items %}
        <tr>&nbsp;
            <td><input type="radio" name="carrier_service_{{row.idx}}" value="{{ item.carrier_service }}" data-service-name="{{item.service_name}}"></td>
            <td>{{ item.service_name }}</td>
            <td>{{ item.base }}</td>
            <td>{{ item.shipment_amount }}</td>
            <td>{{ item.guaranteed_delivery ? "Yes" : "No" }}</td>
            <td>{{ item.expected_transit_time }}</td>
            <td>{{ item.expected_delivery_date }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endfor %}
</div>`;
})();
//# sourceMappingURL=metactical.bundle.NBWVN5B2.js.map
