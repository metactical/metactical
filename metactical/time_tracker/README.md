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

## Approvals

Role **Time Approval** (created by `patches/create_time_approval_role.py`): sees and decides every request.
`api.can_review` also allows HR Manager, System Manager and the Time Tracker Settings approver address.
`api.get_requests(tab)` feeds `ApprovalsScreen.vue`; shared helpers live in `components/time_clock/api.js` and `format.js`.

## Work zone, reminders, approvals by cycle

- `core.work_day(moment, tz)` / `core.employee_for_user().work_tz`: `Clockin Log.date` is the WORK day; shifts stay in server time
  (`core.shift_times_for_workday`). Report: `metactical/report/time_tracker_v2_report` ("Time Tracker V2 Report").
- `reminders.py`: `schedule_followup` (once, on creation) + `run` (every 10 min, idle = one indexed lookup) + signed link token.
  Guest endpoints `get_clockout_link` / `confirm_clockout`; page `www/trackerv2/clockout.html`.
- `api.get_requests(cycle_offset)`: one cycle, all statuses; offset > 1 needs System Manager. `get_attention`, `close_entry`.

## Pay cycles, expected hours, regions

- `core.scope_cycles()` = current and previous cycle; approvals, change requests and approval are limited to them.
- `core.expected_hours(shift)` = Shift Type `tt_expected_hours`, else the shift length (<= 14h), else Standard Day Hours.
- `locations.py` = ISO 3166-2 codes for `Employee.ais_state` and the work time zone rule (Phase 2 will use it).
- Patches added: `time_tracker_shift_expected_hours`, `create_standard_shift_types`, `normalize_employee_regions`,
  `close_stale_open_entries`, `create_time_approval_role`, `time_tracker_settings_defaults`.

## Time zones

Storage and rules are in site (server) time. API instants carry a UTC offset (`core.with_offset`); times typed by a
user in another zone are converted with `core.to_server_naive(value, tz)`. The display zone is a per-user preference
(`set_display_zone`). Front end: `zone.js` (state), `format.js` (zone-aware formatting), `ZoneSelect.vue`.
The Work Time Zone per employee (work day / shift window in the employee's zone) is Phase 2.

## Gotchas found

- ERPNext's `validate_employee_role` **removes the Employee role from any user not linked to an Employee record**.
  So the page cannot be restricted to the Employee role: unlinked users would see a bare "Not permitted"
  instead of the explanation. Access control is in the API.
- Frappe re-imports a Page/DocType JSON only when its `modified` stamp changes.
- The desk caches pages in `localStorage` (`_page:<name>`); clear it when testing CSS/JS changes.
- `frappe.call`'s `error` callback receives no response object here; `callBackend` uses `fetch` instead.
- HRMS refuses two Employee Checkins with the same timestamp.

- Frappe does not apply a new field's default to an existing Single doc; saving the form then stores 0.
  `patches/time_tracker_settings_defaults.py` sets the defaults once on migrate.
- Frappe's `between` filter on the text `date` field of Checkin Request Modification builds invalid SQL; filter in Python.
- Time Tracker Settings validate auto-generates pay cycles from `start_date` (saving it creates ~26 cycles).

## Tests

`bench --site <site> run-tests --skip-test-records --module metactical.time_tracker.tests.test_time_tracker`
(`--skip-test-records` because the global fixtures fail on metactical's mandatory `neb_company` on Lead Source.)

## Not built yet

Manager "who's in now" board, payroll/exceptions report + CSV export, break tracking, PIN/badge login for shared tablets, switching `/tracker` over.

## Builds

`build.py` holds the build number; every update adds a `CHANGELOG.md` entry and a `tt-build-<N>` tag. See the changelog for rollback.
