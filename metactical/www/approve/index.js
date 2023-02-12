let params = new URLSearchParams(document.location.search);
let notification = document.getElementById("notification"
)
req = params.get("req")

frappe.ready(function() {
    if (frappe.session.user != "Guest") {
        frappe.call({
            method: "metactical.api.checkin.approve_details_change_request",
            args: {
                "request_name": req
            },
            callback: r => {
                console.log(r.message)
                notification.classList.toggle("d-none")
            }
        })
    }

    else {
        frappe.throw("You must be logged in")
    }
})

console.log(req)
