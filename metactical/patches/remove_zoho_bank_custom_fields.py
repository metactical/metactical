import frappe


ZOHO_FIELDS = [
	"Bank Account-zoho_account_code",
	"Bank Account-zoho_account_id",
	"Bank Account-zoho_account_sub_type",
	"Bank Account-zoho_balance_difference",
	"Bank Account-zoho_bank_balance",
	"Bank Account-zoho_book_balance",
	"Bank Account-zoho_col_break_1",
	"Bank Account-zoho_col_break_2",
	"Bank Account-zoho_currency",
	"Bank Account-zoho_feed_status",
	"Bank Account-zoho_feeds_last_refresh_date",
	"Bank Account-zoho_last_synced_on",
	"Bank Account-zoho_section",
	"Bank Account-zoho_section_feed",
	"Bank Account-zoho_uncategorized_transactions",
]


def execute():
	for name in ZOHO_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
