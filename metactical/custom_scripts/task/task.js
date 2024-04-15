frappe.ui.form.on('Task', {
    onload: function(frm) {
        setTimeout(() => {
            $(".form-dashboard-section.form-links").hide();
        }, 10);
    }, 
    refresh: function(frm) {
        
        show_checklists(frm);
    }
});

let show_checklists = function(frm) {
    $(".form-dashboard-section.form-links").hide();
    var check_list_html = frm.fields_dict.checklists_html.$wrapper;
    check_list_html.closest(".form-section").hide();

    var checklist_items = frm.doc.checklist;
    var grouped_checklist_items = get_grouped_checklist_items(checklist_items);
    var parent_checklists = get_parent_name_title_combinations(checklist_items);
    
    if (checklist_items) {
        check_list_html.empty();
        check_list_html.closest(".form-section").show();
        check_list_html.append(`
            <div class="row">
                <div class="col-md-8  border-right">
                    <div class="checklist">
                        <div class="checklist-header">
                            <div class="checklist-header-section d-flex justify-content-between">
                                <div>                       
                                    <h4 class="checklist-status-text">${__("Checklists")}</h4>
                                </div>
                                <div>
                                    <button class="btn btn-default btn-xs checklist-group-add-action" data-action="add">${__("Add Checklist Group")}</button>
                                </div>
                            </div>
                        </div>
                        <hr>
                        <div class="checklist-body mt-2 my-4">
                            <ul class="checklist-items px-0"></ul>
                        </div>
                    </div>  
                </div>
            </div>
        `);

        if (Object.keys(grouped_checklist_items).length == 0) {
            check_list_html.find(".checklist-items").append(`
                <div class="text-muted text-center my-4">${__("No checklists found")}</div>
            `);
        }

        // add event listener to the add checklist group button
        add_checklist_group_action(check_list_html, frm);

        var checklist_items_html = check_list_html.find(".checklist-items");
        $.each(grouped_checklist_items, function(parent, item) {
            var checklist_html = $(`
                <li class="checklist-item-main mb-4" data-parent="${parent}">
                    <div class="checklist-item-header d-flex justify-content-between" style="padding-top: 8px;">
                        <div>
                        <h5 data-target="${parent}"> <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16"><path d="M2.75 1h10.5c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 13.25 15H2.75A1.75 1.75 0 0 1 1 13.25V2.75C1 1.784 1.784 1 2.75 1ZM2.5 2.75v10.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25V2.75a.25.25 0 0 0-.25-.25H2.75a.25.25 0 0 0-.25.25Zm9.28 3.53-4.5 4.5a.75.75 0 0 1-1.06 0l-2-2a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018l1.47 1.47 3.97-3.97a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042Z"></path></svg>
                            <span class="checklist-item-name">${parent_checklists[parent].title}</span>
                        </h5>
                        </div>
                        <div>
                            <button class="btn btn-default btn-xs checklist-delete-action" data-action="add">${__("Delete")}</button>
                        </div>
                    </div>
                    <div class="checklist-item-body mt-2">
                        <ul class="checklist-subitems px-0"></ul>
                    </div>
                </li>
            `);

            // show edit dialog on double click of checklist-item
            show_edit_modal(checklist_html.find(".checklist-item-header"), frm, {"title": parent_checklists[parent].title, "name": parent})

            // add event listener to the delete button
            checklist_delete_action(checklist_html, parent, parent_checklists, frm)

            // progress bar to the checklist item
            var progress = get_progress(item);
            var checklist_progress = $(`
                <div class="progress mt-2">
                    <div class="progress-bar" id="progress-${parent}" role="progressbar" style="width: ${progress}%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
            `);
            checklist_html.find(".checklist-item-body").prepend(checklist_progress);

            var checklist_subitems = checklist_html.find(".checklist-subitems");
            $.each(item, function(i, subitem) {
                console.log(subitem.assign_to, subitem.first_name)
                var checked = subitem.is_completed ? "checked" : "";
                var user_name =  subitem.first_name ? subitem.first_name[0].toUpperCase(): ""
                var randomColor = get_random_color();
                
                var subitem_html = $(`
                    <li class="checklist-item my-2 pt-2 px-2">
                        <label>
                            <input type="checkbox" ${checked} class="checklist-item-status" data-target="${subitem.name}">
                            <span  class="checklist-item-name">${subitem.title}</span>
                        </label>
                        <span class="checklist-item-actions float-right d-none">
                            <span class="checklist-item-delete-action text-danger">
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16"><path d="M11 1.75V3h2.25a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1 0-1.5H5V1.75C5 .784 5.784 0 6.75 0h2.5C10.216 0 11 .784 11 1.75ZM4.496 6.675l.66 6.6a.25.25 0 0 0 .249.225h5.19a.25.25 0 0 0 .249-.225l.66-6.6a.75.75 0 0 1 1.492.149l-.66 6.6A1.748 1.748 0 0 1 10.595 15h-5.19a1.75 1.75 0 0 1-1.741-1.575l-.66-6.6a.75.75 0 1 1 1.492-.15ZM6.5 1.75V3h3V1.75a.25.25 0 0 0-.25-.25h-2.5a.25.25 0 0 0-.25.25Z"></path></svg>                                
                            </span>
                        </span>
                        <span class="float-right rounded mx-3 checklist-item-assignee" title="${subitem.first_name}" style="background: ${randomColor}">${user_name}</span>
                    </li>
                `);

                // <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16"><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm7-3.25v2.992l2.028.812a.75.75 0 0 1-.557 1.392l-2.5-1A.751.751 0 0 1 7 8.25v-3.5a.75.75 0 0 1 1.5 0Z"></path></svg>
                // <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16"><path d="M7.9 8.548h-.001a5.528 5.528 0 0 1 3.1 4.659.75.75 0 1 1-1.498.086A4.01 4.01 0 0 0 5.5 9.5a4.01 4.01 0 0 0-4.001 3.793.75.75 0 1 1-1.498-.085 5.527 5.527 0 0 1 3.1-4.66 3.5 3.5 0 1 1 4.799 0ZM13.25 0a.75.75 0 0 1 .75.75V2h1.25a.75.75 0 0 1 0 1.5H14v1.25a.75.75 0 0 1-1.5 0V3.5h-1.25a.75.75 0 0 1 0-1.5h1.25V.75a.75.75 0 0 1 .75-.75ZM5.5 4a2 2 0 1 0-.001 3.999A2 2 0 0 0 5.5 4Z"></path></svg>
                
                // delete checklist-item
                delete_checklist_item(subitem_html, subitem, checklist_subitems, parent, frm)
                
                // add event listener to the checkbox
                updadate_status_on_change(subitem_html, checklist_subitems, parent, frm)
                
                // edit modal on double click of checklist-item
                show_edit_modal(subitem_html, frm, subitem) 

                // show checklist-item-actions on hover of checklist-item
                hover_blur_event(subitem_html);

                checklist_subitems.append(subitem_html);
            })

            checklist_subitems.append(`
                <li class="checklist-new mt-2">
                    <div class="">
                        <button class="btn btn-default btn-xs checklist-add-item-action" data-action="add">${__("Add Item")}</button>
                    </div>
                </li>
            `);

            // add event listener to the add item button
            add_new_item_action(checklist_subitems, parent, frm);

            checklist_items_html.append(checklist_html);
        })
    }
}

let get_random_color = function() {
    // "#3700B3", "#00b200", "#9000a6", 
    var colors = ["#00746f"]
    var randomColor = colors[Math.floor(Math.random() * colors.length)];
    return randomColor
}

let delete_checklist_item = function(subitem_html, subitem, checklist_subitems, parent, frm) {
    subitem_html.find(".checklist-item-delete-action").on("click", function() {
        var me = $(this);
        frappe.confirm(__(`Are you sure you want to delete <b>${subitem.title}</b>?`), function() {
            me.parents(".checklist-item").remove();
            
            // update the child table
            $.each(frm.doc.checklist, function(i, item) {
                if (item.name == subitem.name) {
                    frappe.model.clear_doc("Task Checklist", item.name);
                    return false;
                }
            })
            frm.refresh_field("checklist");

            // update the progress bar
            var progress = get_progress(checklist_subitems.find(".checklist-item-status"))
            $("#progress-"+parent).css("width", `${progress}%`);

            frappe.call({
                method: "metactical.custom_scripts.task.task.delete_checklist_item",
                args: {
                    docname: subitem.name
                },
                callback: function(r) {
                    if (!r.success){
                        frappe.show_alert(r.error)
                        frm.reload_doc()
                    }
                }
            })
        })
    })
}


let show_edit_modal = function(subitem_html, frm, subitem) {
    subitem_html.on("dblclick", function() {
        var dialog = new frappe.ui.Dialog({
            title: __("Edit Checklist Item"),
            fields: [
                {
                    fieldname: "title",
                    label: __("Title"),
                    fieldtype: "Data",
                    reqd: 1,
                    default: subitem.title
                },
                {
                    fieldname: "due_date",
                    label: __("Due Date"),
                    fieldtype: "Date",
                    default: subitem.due_date
                },
                {
                    fieldname: "assign_to",
                    label: __("Assign To"),
                    fieldtype: "Link",
                    options: "User",
                    reqd: 1,
                    default: subitem.assign_to
                }
            ],
            primary_action: function() {
                var values = dialog.get_values();
                if (values) {
                    frappe.call({
                        method: "metactical.custom_scripts.task.task.update_checklist_item",
                        args: {
                            name: subitem.name,
                            title: values.title,
                            due_date: values.due_date,
                            assign_to: values.assign_to
                        },
                        callback: function(r) {
                            if (r.success) {
                                subitem.title = values.title;
                                subitem.due_date = values.due_date;
                                subitem.assign_to = values.assign_to
                                
                                // update child table
                                $(frm.doc.checklist).each(function(i, item) {
                                    if (item.name == subitem.name) {
                                        item.title = values.title;
                                        item.due_date = values.due_date;
                                        item.assign_to = values.assign_to;
                                        return false;
                                    }
                                })

                                // update the UI
                                subitem_html.find(".checklist-item-name").text(values.title);
                                if (r.first_name){
                                    subitem_html.find(".checklist-item-assignee").text(r.first_name[0].toUpperCase());
                                    subitem_html.find(".checklist-item-assignee").css("title", r.first_name);
                                    subitem_html.find(".checklist-item-assignee").css("background", get_random_color());
                                }
                                frm.refresh_field("checklist");
                                frm.save()
                                dialog.hide();
                            }
                        }
                    })
                }
            },
            primary_action_label: __("Update")
        }).show()
    })
}

let updadate_status_on_change = function(subitem_html, checklist_subitems, parent, frm) {
    subitem_html.find(".checklist-item-status").on("change", function() {
        var me = $(this);
        var status = me.prop("checked");
        var progress = get_progress(checklist_subitems.find(".checklist-item-status"))
        
        frappe.call({
            method: "metactical.custom_scripts.task.task.update_checklist_item_status",
            args: {
                name: me.attr("data-target"),
                value: status ? 1 : 0
            },
            callback: function(r) {
                if (r.success) {
                    $(frm.doc.checklist).each(function(i, item) {
                        if (item.name == me.attr("data-target")) {
                            item.is_completed = status ? 1 : 0;
                            return false;
                        }
                    })
                    frm.refresh_field("checklist")
                }
                else{
                    frappe.show_alert(r.error)
                    me.attr("checked", false)  
                    var progress = get_progress(checklist_subitems.find(".checklist-item-status"))
                    $("#progress-"+parent).css("width", `${progress}%`);
                }
            }
        })

        $("#progress-"+parent).css("width", `${progress}%`);
    })
}

let get_progress = function (items){
    var total_completed = 0
    $.each(items, function(i, item) {
        if ($(item).prop("checked") || item.is_completed) {
            total_completed += 1
        }
    })
    
    var progress = 0
    if (total_completed){
        progress = (total_completed / items.length) * 100;
    }

    return progress
}

let add_checklist_group_action = function(check_list_html, frm) {
    check_list_html.find(".checklist-group-add-action").on("click", function() {
        var dialog = new frappe.ui.Dialog({
            title: __("Add Checklist Group"),
            fields: [
                {
                    fieldname: "title",
                    label: __("Title"),
                    fieldtype: "Data",
                    reqd: 1
                }
            ],
            primary_action: function() {
                var values = dialog.get_values();
                if (values) {
                    var checklist_item = frappe.model.add_child(frm.doc, "Task Checklist", "checklist");
                    checklist_item.title = values.title;
                    checklist_item.is_parent = 1;
                    frm.refresh_field("checklist");
                    frm.save()
                    dialog.hide();
                }
            },
            primary_action_label: __("Add")
        }).show()
    })
}

let hover_blur_event = function(subitem_html) {
    subitem_html.on("mouseenter", function() {
        // subitem_html.css({"background-color": "#f5f5f5", "cursor": "pointer"});
        subitem_html.find(".checklist-item-actions").removeClass("d-none");
    })

    subitem_html.on("mouseleave", function() {
        subitem_html.removeAttr("style");
        subitem_html.find(".checklist-item-actions").addClass("d-none");
    })
}

let add_new_item_action = function(checklist_html, parent, frm) {
    checklist_html.find(".checklist-add-item-action").on("click", function() {
        var dialog = new frappe.ui.Dialog({
            title: __("Add Checklist Item"),
            fields: [
                {
                    "fieldname": "parent",
                    "fieldtype": "Data",
                    "hidden": 1,
                    "default": parent
                },
                {
                    fieldname: "title",
                    label: __("Title"),
                    fieldtype: "Data",
                    reqd: 1
                },
                {
                    fieldname: "due_date",
                    label: __("Due Date"),
                    fieldtype: "Date"
                },
                {
                    fieldname: "assign_to",
                    label: __("Assign To"),
                    reqd: 1,
                    fieldtype: "Link",
                    options: "User"
                }
            ],
            primary_action: function() {
                var values = dialog.get_values();
                if (values) {
                    var checklist_item = frappe.model.add_child(frm.doc, "Task Checklist", "checklist");
                    checklist_item.title = values.title;
                    checklist_item.assign_to = values.assign_to;
                    checklist_item.due_date = values.due_date;
                    checklist_item.is_parent = 0;
                    checklist_item.parent_checklist = parent;
                    frm.refresh_field("checklist");
                    frm.save()
                    dialog.hide();
                }
            },
            primary_action_label: __("Add")
        }).show()
    })
}

let checklist_delete_action = function(checklist_html, parent, parent_checklists, frm) {
    checklist_html.find(".checklist-delete-action").on("click", function() {
        var me = $(this); 

        frappe.confirm(__(`Are you sure you want to delete <b>${parent_checklists[parent].title}</b>?`), function() {
            frappe.call({
                method: "metactical.custom_scripts.task.task.delete_checklist_group",
                freeze: true,
                args: {
                    docname: parent
                },
                callback: function(r) {
                    if (r.success){
                        me.parents(".checklist-item-main").remove();
                        
                        $.each(frm.doc.checklist, function(i, item) {
                            if (item.name == parent) {
                                frappe.model.clear_doc("Task Checklist", item.name);
                            }
                            else if (item.parent_checklist == parent) {
                                frappe.model.clear_doc("Task Checklist", item.name);
                            }
                        })

                        frm.refresh_field("checklist");
                    }
                }
            })
        })
    })
}

let get_parent_name_title_combinations = function(checklist_items) {
    var parent_name_title = {};
    $.each(checklist_items, function(i, item) {
        if (item.is_parent) {
            parent_name_title[item.name] = item;
        }
    })
    
    return parent_name_title;
}

let get_grouped_checklist_items = function(checklist_items) {
    var grouped_checklist_items = {};
    
    // create a list of checklist items grouped by the is_parent field
    // if item is a parent, add it to the grouped_checklist_items object

    $.each(checklist_items, function(i, item) {
        if (item.is_parent) {
            if (Object.keys(grouped_checklist_items).indexOf(item.name) == -1){
                grouped_checklist_items[item.name] = [];
            }
        }
        else{
            if (Object.keys(grouped_checklist_items).indexOf(item.parent_checklist) == -1){
                grouped_checklist_items[item.parent_checklist] = [];
            }
            
            grouped_checklist_items[item.parent_checklist].push(item);
            
        }
    })

    return grouped_checklist_items;
}