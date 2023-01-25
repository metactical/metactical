$.extend(frappe.model, {
	get_new_doc: function(
		doctype,
		parent_doc,
		parentfield,
		with_mandatory_children
	) {
		frappe.provide("locals." + doctype);
		var doc = {
			docstatus: 0,
			doctype: doctype,
			name: frappe.model.get_new_name(doctype),
			__islocal: 1,
			__unsaved: 1,
			owner: frappe.session.user
		};
		frappe.model.set_default_values(doc, parent_doc);

		if (parent_doc) {
			$.extend(doc, {
				parent: parent_doc.name,
				parentfield: parentfield,
				parenttype: parent_doc.doctype
			});
			if (!parent_doc[parentfield]) parent_doc[parentfield] = [];
			doc.idx = parent_doc[parentfield].length + 1;
			parent_doc[parentfield].push(doc);
		} else {
			frappe.provide("frappe.model.docinfo." + doctype + "." + doc.name);
		}

		frappe.model.add_to_locals(doc);

		if (with_mandatory_children) {
			frappe.model.create_mandatory_children(doc);
		}

		if (!parent_doc) {
			doc.__run_link_triggers = 1;
		}

		// set the name if called from a link field
		if (frappe.route_options && frappe.route_options.name_field) {
			var meta = frappe.get_meta(doctype);
			// set title field / name as name
			if (meta.autoname && meta.autoname.indexOf("field:") !== -1) {
				doc[meta.autoname.substr(6)] = frappe.route_options.name_field;
			} else if (meta.title_field) {
				doc[meta.title_field] = frappe.route_options.name_field;
			}

			delete frappe.route_options.name_field;
		}

		// set route options
		//Comment this out to prevent creating new document with info from filters
		if (frappe.route_options && !doc.parent) {
			/*$.each(frappe.route_options, function(fieldname, value) {
				var df = frappe.meta.has_field(doctype, fieldname);
				if (
					df &&
					in_list(
						["Link", "Data", "Select", "Dynamic Link"],
						df.fieldtype
					) &&
					!df.no_copy
				) {
					doc[fieldname] = value;
				}
			});*/
			frappe.route_options = null;
		}

		return doc;
	}
});
