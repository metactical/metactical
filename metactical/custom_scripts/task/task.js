frappe.ui.form.on('Task', {
    onload: function(frm) {
        setTimeout(() => {
            $(".form-dashboard-section.form-links").hide();
        }, 10);
    }
});