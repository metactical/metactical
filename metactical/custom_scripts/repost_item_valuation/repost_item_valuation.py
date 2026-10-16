import frappe
from frappe.utils import getdate, add_days
from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import RepostItemValuation


def clamp_repost_to_open_period(doc, method=None):
    """Move a full-history repost forward to the first open day when a Period Closing
    Voucher would otherwise reject it.

    repost_actual_qty creates Repost Item Valuation entries with a hardcoded
    posting_date of 1900-01-01. Once any Period Closing Voucher exists,
    validate_period_closing_voucher throws because that date is inside a closed
    period. Entries inside a closed period are frozen by design, so reposting them
    is neither allowed nor meaningful -- reposting from the day after the closing
    date recomputes everything that may still change, and the current bin/value stay
    correct because the closed period's ending balance is a valid opening balance.

    Scoped to non-Transaction reposts (the full-history recalc type). Transaction-based
    reposts keep throwing on a closed period, so a genuine backdated posting into a
    closed period still surfaces instead of being silently shifted.
    """
    if doc.based_on == "Transaction":
        return

    # doc.company is pre-filled with the global default company on new_doc and only
    # corrected to the warehouse's company by set_company(), which runs inside validate()
    # -- i.e. AFTER this before_validate hook. Trusting doc.company here would read the
    # wrong company (and miss its closing date), so derive it from the warehouse ourselves,
    # the same rule set_company() uses for non-Transaction reposts.
    company = frappe.get_cached_value("Warehouse", doc.warehouse, "company") if doc.warehouse else doc.company
    if not company:
        return

    closing_date = RepostItemValuation.get_max_period_closing_date(company)
    if closing_date and getdate(doc.posting_date) <= getdate(closing_date):
        doc.posting_date = add_days(getdate(closing_date), 1)
        doc.posting_time = "00:00:00"
