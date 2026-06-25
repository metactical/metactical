# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import StockLedgerEntry

from metactical.custom_scripts.utils import restock_notification


class CustomStockLedgerEntry(StockLedgerEntry):
	def on_submit(self):
		super(CustomStockLedgerEntry, self).on_submit()
		# Metactical Customization: create Restock Email Logs for subscriptions on
		# this item. All logic lives in restock_notification.py.
		restock_notification.on_sle_submit(self)
