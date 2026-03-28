frappe.listview_settings['USAePay Refund'] = {
    hide_name_column: true,
    hide_name_filter: true, 
    add_fields: ['status'], //Your custom status fieldname
    has_indicator_for_draft: true,
    has_indicator_for_cancelled: true,

    get_indicator: function (doc) {
        const status = doc.status || 'Unknown';

        // Status color map
        const status_map = {
            "Refunded": "green",
            "Pending": "yellow"
        };

        const label = `${status}`;
        const color = status_map[status] || "gray";

        return [label, color, `status,=,${status}`];
    }
}
  

