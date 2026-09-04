import frappe
import erpnext.stock.doctype.repost_item_valuation.repost_item_valuation as _riv

_LOCK_KEY = "repost_item_valuation_running"
_LOCK_TTL_SEC = 7200  # 2 hours; covers the longest expected single repost run


def repost_entries():
	"""
	Serialized wrapper around ERPNext's repost_entries.

	Item valuation reposting must be strictly sequential: each SLE's valuation
	depends on the running balance of all earlier entries.  If two repost runs
	overlap they will read each other's in-flight state and corrupt stock values.

	We use an atomic Redis NX lock so that a scheduler tick that fires while a
	previous run is still executing exits immediately rather than starting a
	concurrent repost.  The TTL is a safety valve in case the worker dies
	without releasing the lock.
	"""
	cache = frappe.cache()
	acquired = cache.set(_LOCK_KEY, 1, nx=True, ex=_LOCK_TTL_SEC)
	if not acquired:
		return  # another repost_entries call is in progress; skip this tick

	try:
		_riv._original_repost_entries()
	finally:
		cache.delete(_LOCK_KEY)
