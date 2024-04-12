frappe.ui.form.on('Task', {
    onload: function(frm) {
        console.log("test")
        setTimeout(() => {
            $(".form-dashboard-section.form-links").hide();
        }, 10);
    }
});