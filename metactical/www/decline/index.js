let params = new URLSearchParams(document.location.search);
let notification = document.getElementById("notification"
)
req = params.get("req")

frappe.ready(function() {
    if (frappe.session.user != "Guest") {
        frappe.call({
<<<<<<< HEAD
            method: "metactical.api.clockin.decline_details_change_request",
=======
            method: "metactical.api.decline_details_change_request",
>>>>>>> parent of 1e30092 (Revert "Test clockin request details modification")
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

<<<<<<< HEAD
console.log(req)
=======
console.log(req)
>>>>>>> parent of 1e30092 (Revert "Test clockin request details modification")
