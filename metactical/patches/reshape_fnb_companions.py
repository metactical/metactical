"""The F&B companions lost their pizza-specific columns (slices per pie, hot-case slice counts, menu item
group) when the concept moved to FnB Menu / FnB Prepared Resource. Frappe keeps dropped fields' columns;
remove them so the tables match the doctypes."""
import frappe

DROPPED = {
	"FnB POS Profile": ("slices_per_pie", "slice_cost_account", "menu_item_group"),
	"FnB Opening": ("opening_slices",),
	"FnB Closing": ("opening_slices", "pies_baked", "slices_sold", "slices_counted", "slice_variance", "slice_variance_reason"),
}


def execute():
	for doctype, columns in DROPPED.items():
		if not frappe.db.table_exists(doctype):
			continue
		existing = frappe.db.get_table_columns(doctype)
		for column in columns:
			if column in existing:
				frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `{column}`")
