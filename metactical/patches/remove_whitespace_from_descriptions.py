import frappe

def execute():
    web_spec_descriptions = frappe.get_all("Website Spec Label Descriptions", fields=["name", "description"])
    for spec in web_spec_descriptions:
        # Remove leading and trailing whitespace from description
        cleaned_description = spec.description.strip()
        
        # Update the record with the cleaned description
        frappe.db.set_value("Website Spec Label Descriptions", spec.name, "description", cleaned_description)
        
    frappe.db.commit()