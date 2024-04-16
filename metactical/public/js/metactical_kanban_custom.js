$(function(){
    update_default_route()

    frappe.router.on('change', () => {
            update_default_route()
    })

    // change default link address from project form to kanban view
    function update_default_route(){
        var project_kanban_view = false
        var route = frappe.get_route()

        if (route.length == 4){
            if (route[2] === "Kanban" && route[1] === "Project") {
                project_kanban_view = true

                $(body).on("click", ".kanban-title-area a", function(e){
                    if (project_kanban_view){
                        e.preventDefault()
                        e.stopPropagation()
                    
                        var project = $(this).find(".kanban-card-title").attr("title")
                        frappe.route_options = {}
                        frappe.set_route("task/view/Kanban/"+project)
                        project_kanban_view = false
                    }

                })
            }
            else{
                project_kanban_view = false
            }
        }
    }

})