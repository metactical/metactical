frappe.ui.form.on('Project', {
    refresh: function(frm) {
        setTimeout(() => {
            $(".form-dashboard-section.form-links").hide();
        }, 10);
    }
});