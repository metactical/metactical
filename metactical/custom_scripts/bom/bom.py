import frappe

@frappe.whitelist()
def fetch_item_groups(parent):
    # Use parameterized query to avoid SQL injection
    query = """
        SELECT ig.name, ig.is_group
        FROM `tabItem Group` ig
        WHERE ig.parent_item_group = %s OR ig.name = %s
    """
    
    # Execute the query with the parent as a parameter
    item_groups = frappe.db.sql(query, (parent, parent), as_dict=True)
    
    return item_groups

def get_item_group_with_children(kwargs, processed_groups=None):
    if processed_groups is None:
        processed_groups = set()

    parent = kwargs.get("parent", "Raw Material To Stock")
    
    # Fetch the item groups for the given parent
    item_groups = fetch_item_groups(parent)

    all_item_groups = []

    # Recursively process each group
    for item_group in item_groups:
        if item_group["name"] not in processed_groups:
            processed_groups.add(item_group["name"])
            
            if item_group["is_group"]:
                # Recursively fetch the children of the group
                children = get_item_group_with_children({"parent": item_group["name"]}, processed_groups)
                children.append(item_group["name"])
                all_item_groups.extend(children)
            else:
                all_item_groups.append(item_group["name"])

    return all_item_groups
