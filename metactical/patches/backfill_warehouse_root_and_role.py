import frappe

# Checked in order; the first keyword found anywhere in the warehouse name wins.
NAME_KEYWORD_ROLES = [
	("active stock", "Active Stock"),
	("defective", "Defective"),
	("in transit", "In Transit"),
	("intransit", "In Transit"),
	("packing", "Packing"),
	("returntosupplier", "Return"),
	("return", "Return"),
	("received stock", "Receiving"),
	("receivedstock", "Receiving"),
	("receiving", "Receiving"),
	("work in progress", "Work In Process"),
	("workinprocess", "Work In Process"),
	("work in process", "Work In Process"),
]

def execute():
	# Process parents before children so leaf classification can look at the
	# already-computed role of its parent.
	warehouses = frappe.get_all(
		"Warehouse",
		fields=["name", "parent_warehouse", "is_group"],
		order_by="lft asc",
	)
	parent_map = {w.name: w.parent_warehouse for w in warehouses}
	role_map = {}
	root_cache = {}

	for warehouse in warehouses:
		root = get_root_warehouse(warehouse.name, parent_map, root_cache)
		role = classify_warehouse_role(
			warehouse.name, warehouse.is_group, warehouse.parent_warehouse, parent_map, role_map
		)
		role_map[warehouse.name] = role

		frappe.db.set_value(
			"Warehouse",
			warehouse.name,
			{"root_warehouse": root, "warehouse_role": role or ""},
			update_modified=False,
		)

	frappe.db.commit()

def get_root_warehouse(warehouse_name, parent_map, root_cache):
	# Walk up parent_warehouse to the top-level physical location -- the
	# ancestor whose own parent is the synthetic per-company root ("All
	# Warehouses - X") -- NOT that synthetic root itself, which isn't a real
	# location. Memoized since many leaves share the same root.
	path = []
	current = warehouse_name

	while current not in root_cache:
		parent = parent_map.get(current)
		if not parent:
			# No parent at all -> current is the synthetic root itself;
			# there's no physical location above it.
			root_cache[current] = current
			break

		grandparent = parent_map.get(parent)
		if not grandparent:
			# Parent is the synthetic root -> current is the top-level
			# physical location.
			root_cache[current] = current
			break

		path.append(current)
		current = parent

	root = root_cache[current]
	for name in path:
		root_cache[name] = root

	return root

def classify_warehouse_role(warehouse_name, is_group, parent_warehouse, parent_map, role_map):
	name_lower = warehouse_name.lower()

	for keyword, role in NAME_KEYWORD_ROLES:
		if keyword in name_lower:
			return role

	if is_group:
		if not parent_warehouse:
			# The synthetic per-company root ("All Warehouses - X") isn't a
			# real physical location, so it gets no role.
			return None

		grandparent = parent_map.get(parent_warehouse)
		if not grandparent:
			# Direct child of the synthetic root -> a top-level physical location.
			return "Location"

		return "Group Bin"

	# Leaf with no keyword match: only call it a plain "Bin" when it lives
	# inside the numbered bin hierarchy (its parent was classified as a
	# Group Bin). Other leaves (ManualOrders, ShipOut, DropShip, Stores, ...)
	# don't map cleanly onto any role from their name alone, so leave unset
	# rather than guessing.
	if role_map.get(parent_warehouse) == "Group Bin":
		return "Bin"

	return None
