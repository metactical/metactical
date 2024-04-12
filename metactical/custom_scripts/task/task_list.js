frappe.listview_settings['Task'].refresh = function(listview) {
    var route = frappe.get_route()

    // If the the route is Task List, then redirect to the kanban view
    if (route[2] === "List" && route[1] === "Task") {
        frappe.set_route("task/view/kanban/Buying Board");
    }
}; 