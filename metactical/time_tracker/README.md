# Time Clock (time_tracker)

Rebuild of the `/tracker` clock-in page. Lives in the `metactical` app as a desk Page
(`/app/time-clock`) with a Vue component, per the S3 Uploader pattern. The old `/tracker`
www page is untouched and still works; switch staff over once this is accepted.

## What changed vs `/tracker`

| Before | Now |
|---|---|
| Browser sent the timestamp | Server time only (`core.context()` -> `now_datetime()`) |
| Buttons flipped before the API answered; a failed clock-in left Clock Out red ("Clockin Log None not found") | Every action returns the full new state; blockers are shown as a reason |
| `total_hours` precision 1 (6-minute rounding) | precision 4 |
| Employees could write/delete their own Clockin Logs via REST | Employee is read-only (own rows); HR Manager / System Manager edit |
| Anyone logged in could approve any request | Only the approver, HR Manager or System Manager; never your own request; overlap-checked |
| Overnight shifts rejected | `core.shift_window` handles shifts crossing midnight |
| Two open logs possible | validated + per-employee row lock |
| Pay Cycle roll-up matched on `owner`, unbounded loop | `sync_pay_cycle_day`, bounded, keyed on user+date |

## Files

- `time_tracker/core.py` - rules (employee, shift, window, cycle, hours). `Blocked` carries a UI-safe code.
- `time_tracker/api.py` - whitelisted endpoints. `get_state`, `clock_in`, `clock_out`, `get_cycle`, `get_day`,
  `request_correction`, `get_pending_requests`, `review_request`, `get_my_permissions`.
- `metactical/doctype/clockin_log/clockin_log.py` - validation, Employee Checkin sync, Pay Cycle sync.
- `public/js/components/time_clock/TimeClock.vue`, `public/js/time_clock.js`, `metactical/page/time_clock/*`.
- Settings added to Time Tracker Settings: `early_clockin_minutes`, `enforce_shift_window`, `max_shift_hours`.
- Checkin Request Modification added: `reason`, `requested_from/to` (exact datetimes), `reviewed_by/on`, `review_comment`.
  Legacy 12h/military string fields are still filled so the old approve/decline pages keep working.

## Gotchas found

- ERPNext's `validate_employee_role` **removes the Employee role from any user not linked to an Employee record**.
  So the page cannot be restricted to the Employee role: unlinked users would see a bare "Not permitted"
  instead of the explanation. Access control is in the API.
- Frappe re-imports a Page/DocType JSON only when its `modified` stamp changes.
- The desk caches pages in `localStorage` (`_page:<name>`); clear it when testing CSS/JS changes.
- `frappe.call`'s `error` callback receives no response object here; `callBackend` uses `fetch` instead.
- HRMS refuses two Employee Checkins with the same timestamp.

## Tests

`bench --site <site> run-tests --skip-test-records --module metactical.time_tracker.tests.test_time_tracker`
(`--skip-test-records` because the global fixtures fail on metactical's mandatory `neb_company` on Lead Source.)

## Not built yet

Manager "who's in now" board, payroll/exceptions report + CSV export, missed-punch requests (a log with no
existing row), break tracking, PIN/badge login for shared tablets, switching `/tracker` over.
