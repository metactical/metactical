cur_frm.fields_dict['neb_website_specifications'].grid.get_field('description_link').get_query = function(doc, cdt, cdn) {
        var row = locals[cdt][cdn];
        var options = ["", row.label]
        return {
            filters:[
                    ['Website Specifications Description', 'label', 'in', options.join(",")]
            ]
        }
}
