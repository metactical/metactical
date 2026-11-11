"""Rolling back and retrying one item in the GearStock jobs.

Each job commits after every item, so a full rollback only undoes the current item. It has to be a
full rollback: a deadlock makes the database undo the whole transaction and drop its savepoints, so
"rollback to savepoint" then fails and takes the job down with it.
"""

import time

import frappe

ATTEMPTS = 3
RETRY_DELAY = 5  # seconds


def rollback_item():
	"""Roll back the current item, and drop the webhooks it queued.

	A full rollback removes Frappe's flush callback but leaves frappe.local._webhook_queue as it
	is. run_webhooks only adds the callback when that queue is empty, so a queue left behind would
	stop every later webhook in the job from being sent.
	"""
	frappe.db.rollback()
	frappe.local._webhook_queue = []


def run(func):
	"""Call func, retrying when it loses a deadlock or a lock wait. func has to do the whole item
	again from the database, because its work has been rolled back by then."""
	for attempt in range(1, ATTEMPTS + 1):
		try:
			return func()
		except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
			rollback_item()
			if attempt == ATTEMPTS:
				raise
			time.sleep(RETRY_DELAY)
