frappe.listview_settings['Project'].refresh = function(listview) {
    var route = frappe.get_route()

    // If the the route is Project List, then redirect to the kanban view
    if (route[2] === "List" && route[1] === "Project") {
        frappe.set_route("project/view/kanban/Projects Status");
    }
}; 