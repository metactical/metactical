# Time Clock (/trackerv2) - build log

Every update gets the next build number (`time_tracker/build.py`), an entry here, and an annotated git tag `tt-build-<N>`.
The build number is shown at the bottom of the Time Clock. Never edit or reuse an old build: add a new one.

## How to go back to a previous build

1. `git checkout tt-build-<N>` (or `git revert` the build's commit on the branch you deploy from).
2. Redeploy that code (`bench build --app metactical`), then `bench --site <site> migrate`.
3. Read **Data changes** for that build and every build after it: code can be rolled back, but a patch that already
   changed data stays changed unless you undo it with the SQL given. New columns/fields stay in the database after a
   rollback; they are unused and harmless.
4. Locally, each build's image is tagged `icl/erpnext-tracker:build-<N>` by `frappe-local/tracker/redeploy.sh`.

Patches run once per site (Patch Log). To run one again after undoing it, delete its row from Patch Log first.

---

## Build 7 - 2026-10-06 - tag `tt-build-7`
- Auto-close of a forgotten clock-out is now **2 hours** after the scheduled shift end (was 4). Setting
  `auto_close_hours_after_shift_end`; 0 switches it off.
- Every automatic close is also **posted to Rocket.Chat** (channel `Payroll-Time-Adjustments`): Name, ERP link, Scheduled time,
  Auto-closed time. Needs `rocketchat_webhook_url` in Time Tracker Settings (empty = nothing is posted). A failed post is logged
  and never blocks the close. The employee is still emailed (and texted when SMS is configured).
- Report renamed **Time Tracker V2 Report** (was Time Clock Hours). Same columns and filters.
- Build number + this changelog.
- **Schema:** Time Tracker Settings: `rocketchat_webhook_url` (Password), `rocketchat_channel`. Report folder renamed.
- **Patches:** `remove_old_time_clock_report` (deletes the old report record).
- **Data changes:** none besides removing the old Report record (re-created under the new name from files).
- **Rollback:** code-only. `rocketchat_*` columns remain, unused. The old report name comes back with build <= 6 on the next migrate.

## Build 6 - 2026-10-06 - commit `1a70cb45` - tag `tt-build-6`
- Phase 2: `Clockin Log.date` is the employee's work day (Canada by province from `ais_state`, everyone else Pacific).
- Forgot to clock out: follow-up time stored once per entry, 10-minute job (idle run = one indexed lookup), signed clock-out link
  `/trackerv2/clockout`, auto-close at scheduled end flagged for an approver, tab "Forgotten clock-outs".
- Approvals: one pay cycle at a time with all requests; Time Approval can go back one cycle, System Manager any number.
- Report "Time Clock Hours".
- **Schema:** Clockin Log `followup_due_on`, `reminder_sent_on`, `auto_close_reviewed`, `closed_via`, `closed_by`; Settings
  `reminder_minutes_after_shift_end`, `auto_close_hours_after_shift_end`.
- **Patches:** `schedule_followups_for_open_entries`.
- **Data changes:** none destructive. New entries store the work day; existing entries keep their date.
- **Rollback:** code-only; remove the cron line `*/10` in hooks.py (it goes with the code).

## Build 5 - 2026-10-06 - commit `d602e19c` - tag `tt-build-5`
- Time Approval only (HR Manager removed), approvals limited to current + previous cycle, "decline as expired", Expected Hours per
  Shift Type + 7 standard schedules, Employee State/Province as ISO drop-down, closing of old never-clocked-out entries.
- **Schema:** Shift Type `tt_expected_hours`; Clockin Log `auto_closed`; Settings `standard_day_hours`; `Employee-ais_state` becomes a
  Select; Employee Sign Up state becomes a Select.
- **Patches:** `time_tracker_shift_expected_hours`, `create_standard_shift_types`, `normalize_employee_regions`, `close_stale_open_entries`.
- **Data changes (one-way):**
  - `normalize_employee_regions`: free text converted to ISO codes; unmatched values were CLEARED and kept as a Comment on the Employee.
  - `close_stale_open_entries`: entries never clocked out and older than the previous pay cycle were closed at zero hours
    (`auto_closed = 1`). Undo: `update tabClockin Log set has_clocked_out = 0, to_time = null, auto_closed = 0 where auto_closed = 1 and total_hours = 0 and from_time = to_time`.
  - Seven Shift Types were added (delete them by name if unwanted).
  - "Decline as expired" is a button, so only what someone clicked: filter Checkin Request Modification by review comment starting `Expired:` to find/reset them.
- **Rollback:** code first; then the undo steps above if needed.

## Build 4 - 2026-10-06 - commit `ac70b510` - tag `tt-build-4`
- Display time zones: instants carry a UTC offset; per-user "Show times in" picker; PC clock skew warning.
- **Schema:** none. Preference stored in `tabDefaultValue` (key `time_clock_display_zone`).
- **Data changes:** none. **Rollback:** code-only.

## Build 3 - 2026-10-05 - commit `82e0564d` - tag `tt-build-3`
- Time Approval role + dedicated Approvals screen.
- **Patches:** `create_time_approval_role`. **Data changes:** the role. **Rollback:** code-only (the role stays, unused).

## Build 2 - 2026-10-05 - commit `acd714b6` - tag `tt-build-2`
- Missed-day ("Add time") requests, clock button hidden on small touch screens, short-day tolerance, defaults patch.
- **Schema:** Checkin Request Modification `request_type`; Settings `backdate_limit_days`. **Patches:** `time_tracker_settings_defaults`.
- **Data changes:** settings defaults only. **Rollback:** code-only.

## Build 1 - 2026-10-05 - commit `b11ef537` - tag `tt-build-1`
- First version of `/trackerv2`: server-time clock in/out, correction requests, approvals, fixes (hours precision, permissions).
- **Schema:** Clockin Log `total_hours` precision 4 and permission changes; Checkin Request Modification fields; Settings fields.
- **Data changes:** none destructive. **Rollback:** code + migrate; the old `/tracker` was never touched.
