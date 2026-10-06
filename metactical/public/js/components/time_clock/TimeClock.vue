<template>
  <div class="tc-root">
    <!-- People with the Time Approval role get a second screen on the same login -->
    <div class="tc-topbar">
    <div v-if="canReview" class="tc-tabs tc-tabs-main" role="tablist">
      <button class="tc-tab" :class="{ active: tab === 'time' }" role="tab" @click="tab = 'time'">My time</button>
      <button class="tc-tab" :class="{ active: tab === 'approvals' }" role="tab" @click="tab = 'approvals'">
        Approvals <span v-if="pendingCount" class="tc-count">{{ pendingCount }}</span>
      </button>
    </div>
    <ZoneSelect />
    </div>

    <ApprovalsScreen v-if="tab === 'approvals'" @changed="pendingCount = $event" />

    <template v-else>
    <!-- Cannot clock: say exactly why -->
    <div v-if="state && state.status === 'blocked'" class="tc-card tc-blocked">
      <div class="tc-blocked-title">You can't clock in yet</div>
      <p v-for="b in state.blockers" :key="b.code">{{ b.message }}</p>
      <button class="btn btn-default btn-sm" @click="refresh">Check again</button>
    </div>

    <div v-else-if="loadError" class="tc-card tc-blocked">
      <div class="tc-blocked-title">Couldn't load your time</div>
      <p>{{ loadError }}</p>
      <button class="btn btn-default btn-sm" @click="refresh">Try again</button>
    </div>

    <div v-else-if="!state" class="tc-card tc-muted">Loading…</div>

    <template v-else>
      <div class="tc-grid">
      <div class="tc-col">
      <!-- Clock + the one action -->
      <div class="tc-card tc-hero" :class="'is-' + state.status">
        <div class="tc-who">
          {{ state.employee.employee_name }}
          <span class="tc-muted">· {{ state.shift.name }} {{ fmtTime(state.shift.start) }}–{{ fmtTime(state.shift.end) }}</span>
        </div>
        <div class="tc-clock">{{ clockText }}</div>
        <div class="tc-date">{{ weekdayText }} · {{ dateText }} · {{ zoneText }}</div>
        <div v-if="clockSkewMin" class="tc-skew">
          This computer's clock is {{ clockSkewMin }} min {{ clockSkewMs > 0 ? 'behind' : 'ahead' }}. The time shown and
          recorded comes from the server, so your punch is correct. Please tell IT to fix this PC.
        </div>

        <div class="tc-status">
          <template v-if="state.status === 'in'">
            <span class="tc-pill tc-pill-in">Clocked in</span>
            since {{ fmtTime(state.open_log.from_time) }} · <b>{{ fmtDuration(elapsedHours) }}</b>
          </template>
          <template v-else>
            <span class="tc-pill tc-pill-out">Clocked out</span>
            <span v-if="state.can_clock_in_reason" class="tc-muted">{{ state.can_clock_in_reason }}</span>
          </template>
        </div>

        <div v-if="smallTouch" class="tc-mobile-note">
          Clocking in and out isn't available on phones. Please use a workstation or kiosk.
          You can still check your hours below.
        </div>
        <button
          v-else
          class="tc-action"
          :class="state.status === 'in' ? 'tc-action-out' : 'tc-action-in'"
          :disabled="busy || (state.status === 'out' && !state.can_clock_in)"
          @click="state.status === 'in' ? clockOut() : clockIn()"
        >
          {{ busy ? 'One moment…' : state.status === 'in' ? 'Clock Out' : 'Clock In' }}
        </button>

        <div v-if="state.status === 'in' && elapsedHours > state.max_shift_hours" class="tc-warn">
          This entry has been open longer than {{ state.max_shift_hours }} hours. Clock out, then ask for a correction if the time is wrong.
        </div>
        <div v-if="notice" class="tc-notice" :class="'tc-notice-' + notice.kind">{{ notice.text }}</div>
        <div v-if="logoutIn !== null" class="tc-logout">
          Logging out in {{ logoutIn }}s
          <button class="btn btn-default btn-xs" @click="cancelLogout">Stay logged in</button>
        </div>
      </div>

      <!-- Today -->
      <div class="tc-card">
        <div class="tc-card-title">
          Today
          <span class="tc-total">{{ fmtDuration(state.today.total_hours) }}</span>
        </div>
        <div v-if="!state.today.logs.length" class="tc-muted">Nothing yet today.</div>
        <div v-for="l in state.today.logs" :key="l.name" class="tc-entry">
          <span>{{ fmtTime(l.from_time) }} → {{ l.open ? 'now' : fmtTime(l.to_time) }}</span>
          <span class="tc-muted">{{ fmtDuration(l.open ? elapsedHours : l.hours) }}</span>
          <button v-if="!l.open" class="tc-link" @click="openCorrection(l)">Request change</button>
        </div>
      </div>

      </div>
      <div class="tc-col">
      <!-- Pay cycle -->
      <div class="tc-card">
        <div class="tc-card-title">
          Pay cycle
          <span v-if="cycle && !cycle.error" class="tc-total">{{ fmtDuration(cycle.total_hours) }}</span>
        </div>
        <div v-if="!cycle" class="tc-muted">Loading…</div>
        <div v-else-if="cycle.error" class="tc-muted">{{ cycle.error }}</div>
        <template v-else>
          <div class="tc-cycle-nav">
            <button class="btn btn-default btn-xs" :disabled="!cycle.has_prev" @click="loadCycle(offset + 1)">‹ Earlier</button>
            <span>{{ fmtDate(cycle.from_date) }} – {{ fmtDate(cycle.to_date) }}</span>
            <button class="btn btn-default btn-xs" :disabled="!cycle.has_next" @click="loadCycle(offset - 1)">Later ›</button>
          </div>
          <div
            v-for="d in cycle.days"
            :key="d.date"
            class="tc-day"
            :class="{ 'is-today': d.is_today, 'is-open': openDay === d.date }"
          >
            <div class="tc-day-row">
            <button class="tc-day-main" :disabled="!d.log_count" @click="toggleDay(d)">
              <span class="tc-day-wd">{{ fmtWeekday(d.date) }}</span>
              <span class="tc-day-name">{{ fmtDate(d.date) }}</span>
              <span class="tc-bar" :title="d.short ? 'Shorter than the ' + fmtDuration(cycle.shift_hours) + ' shift' : ''"><span class="tc-bar-fill" :class="{ 'is-short': d.short }" :style="{ width: barWidth(d.hours) + '%' }"></span></span>
              <span class="tc-day-hours">{{ d.hours ? fmtDuration(d.hours) : '—' }}</span>
              <span v-if="d.short" class="tc-pill tc-pill-short">short day</span>
              <span v-if="d.pending_requests" class="tc-pill tc-pill-wait">request pending</span>
              <span
                v-if="d.add_request && d.add_request.status === 'Declined'"
                class="tc-pill tc-pill-declined"
                :title="d.add_request.review_comment || ''"
              >declined</span>
            </button>
            <button v-if="d.can_add && !d.pending_requests" class="tc-link tc-add" @click="openMissed(d)">Add time</button>
            </div>
            <div v-if="openDay === d.date && dayDetail" class="tc-day-detail">
              <div v-for="l in dayDetail.logs" :key="l.name" class="tc-entry">
                <span>{{ fmtTime(l.from_time) }} → {{ l.open ? 'now' : fmtTime(l.to_time) }}</span>
                <span class="tc-muted">{{ fmtDuration(l.hours) }}</span>
                <span v-if="l.request" class="tc-pill" :class="'tc-pill-' + l.request.status.toLowerCase()">{{ l.request.status }}</span>
                <button v-if="!l.open && !(l.request && l.request.status === 'Pending')" class="tc-link" @click="openCorrection(l)">Request change</button>
                <div v-if="l.request && l.request.review_comment" class="tc-muted tc-full">“{{ l.request.review_comment }}”</div>
              </div>
            </div>
          </div>
        </template>
      </div>
      </div>
      </div>
    </template>
    </template>

    <!-- Correction dialog -->
    <div v-if="correction" class="tc-modal-back" @click.self="correction = null">
      <div class="tc-modal" role="dialog" aria-modal="true">
        <div class="tc-card-title">{{ correction.mode === 'add' ? 'Add missed time' : 'Request a time change' }}</div>
        <p v-if="correction.mode === 'add'" class="tc-muted">{{ fmtDate(correction.date) }}: no time was recorded this day.</p>
        <p v-else class="tc-muted">{{ fmtDate(correction.log.date) }}: currently {{ fmtTime(correction.log.from_time) }} → {{ fmtTime(correction.log.to_time) }}</p>
        <p class="tc-muted tc-zone-note">Times below are in {{ zoneLabelFor(correction.tz) }}. They are saved as server time.</p>
        <label>Clock in
          <input type="datetime-local" v-model="correction.from" />
        </label>
        <label>Clock out
          <input type="datetime-local" v-model="correction.to" />
        </label>
        <label>{{ correction.mode === 'add' ? 'Why was it missed?' : 'Why does it need to change?' }}
          <textarea v-model="correction.reason" rows="3" :placeholder="correction.mode === 'add' ? 'e.g. Forgot to clock in, worked my normal shift' : 'e.g. Forgot to clock out, left at 5:00 PM'"></textarea>
        </label>
        <div v-if="correction.error" class="tc-warn">{{ correction.error }}</div>
        <div class="tc-modal-actions">
          <button class="btn btn-default btn-sm" @click="correction = null">Cancel</button>
          <button class="btn btn-primary btn-sm" :disabled="busy" @click="submitCorrection">Send for approval</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue"
import ApprovalsScreen from "./ApprovalsScreen.vue"
import { callBackend, errorText } from "./api"
import ZoneSelect from "./ZoneSelect.vue"
import { zoneState, activeTz } from "./zone"
import {
  parse, pad2, asDate, fmtDate, fmtWeekday, fmtTime, fmtDuration,
  fmtClock, fmtDateMs, fmtWeekdayLong, zoneLabelFor, wallInZone, wallStrToMs,
} from "./format"

const state = ref(null)
const loadError = ref("")
const busy = ref(false)
const notice = ref(null)
const cycle = ref(null)
const offset = ref(0)
const openDay = ref(null)
const dayDetail = ref(null)
const correction = ref(null)
const canReview = ref(false)
const pendingCount = ref(0)
const tab = ref("time") // "time" | "approvals"
const logoutIn = ref(null)
const smallTouch = ref(false) // phones and small tablets: clock in/out is not offered there

// The page shows the SERVER's time: remember how far the browser clock is from it.
const serverMs = ref(Date.now())
const fetchedAt = ref(Date.now())
const tick = ref(Date.now())
let timer = null
let logoutTimer = null

const nowMs = computed(() => serverMs.value + (tick.value - fetchedAt.value))
const nowDate = computed(() => new Date(nowMs.value))

// Shown in the zone the user chose (server time by default); what is stored is always server time.
const clockText = computed(() => fmtClock(nowMs.value))
const dateText = computed(() => fmtDateMs(nowMs.value))
const weekdayText = computed(() => fmtWeekdayLong(nowMs.value))
const zoneText = computed(() => zoneLabelFor(activeTz.value, nowMs.value))

// How far this PC's clock is from the server's (positive = PC behind). Only worth a warning past 2 minutes.
const clockSkewMs = ref(0)
const clockSkewMin = computed(() => (Math.abs(clockSkewMs.value) > 120000 ? Math.round(Math.abs(clockSkewMs.value) / 60000) : 0))
const elapsedHours = computed(() => {
  const from = state.value && state.value.open_log && parse(state.value.open_log.from_time)
  return from ? Math.max(0, (nowMs.value - from.getTime()) / 3600000) : 0
})

// A full bar is one scheduled shift. Longer days just stay full: overtime is deliberately not marked.
const barWidth = (hours) => {
  const shift = (cycle.value && cycle.value.shift_hours) || 8
  return Math.min(100, Math.max(0, (hours / shift) * 100))
}
const applyState = (s) => {
  serverMs.value = (parse(s.server_now) || new Date()).getTime()
  fetchedAt.value = Date.now()
  state.value = s
  loadError.value = ""
}

const setNotice = (text, kind = "ok") => {
  notice.value = { text, kind }
  setTimeout(() => { if (notice.value && notice.value.text === text) notice.value = null }, 6000)
}

async function refresh() {
  try {
    await loadReviewer() // also tells us the server zone and the user's saved display zone: needed before showing times
    const t0 = Date.now()
    const s = await callBackend("get_state")
    const t1 = Date.now()
    applyState(s)
    clockSkewMs.value = (parse(s.server_now) || new Date()).getTime() - (t0 + t1) / 2
    if (state.value.status === "blocked") {
      if (canReview.value) tab.value = "approvals" // e.g. an approver who is not an employee
    } else {
      await loadCycle(offset.value)
    }
  } catch (e) {
    loadError.value = errorText(e)
  }
}

async function act(method, okText) {
  busy.value = true
  try {
    const s = await callBackend(method)
    applyState(s)
    setNotice(s.notice || okText)
    await loadCycle(offset.value)
    startLogoutCountdown()
  } catch (e) {
    setNotice(errorText(e), "error")
    await refresh()
  } finally {
    busy.value = false
  }
}
const clockIn = () => act("clock_in", "Clocked in.")
const clockOut = () => act("clock_out", "Clocked out.")

async function loadCycle(n) {
  offset.value = n
  openDay.value = null
  cycle.value = await callBackend("get_cycle", { offset: n })
}

async function toggleDay(d) {
  if (openDay.value === d.date) { openDay.value = null; return }
  openDay.value = d.date
  dayDetail.value = null
  dayDetail.value = await callBackend("get_day", { date: d.date })
}

// Default a missed day to the employee's shift times (an overnight shift ends on the next day).
function openMissed(d) {
  // Shift hours are server time: put them on the missed (server) day, then show them in the chosen zone.
  const sh = state.value.shift
  const stz = zoneState.serverTz
  const startWall = wallInZone(parse(sh.start).getTime(), stz)
  const endWall = wallInZone(parse(sh.end).getTime(), stz)
  const overnight = endWall.slice(0, 10) !== startWall.slice(0, 10)
  const next = new Date(asDate(d.date).getTime() + 86400000)
  const nextIso = `${next.getFullYear()}-${pad2(next.getMonth() + 1)}-${pad2(next.getDate())}`
  const fromMs = wallStrToMs(`${d.date}T${startWall.slice(11)}`, stz)
  const toMs = wallStrToMs(`${overnight ? nextIso : d.date}T${endWall.slice(11)}`, stz)
  const tz = activeTz.value
  correction.value = {
    mode: "add",
    date: d.date,
    tz,
    from: wallInZone(fromMs, tz),
    to: wallInZone(toMs, tz),
    reason: "",
    error: "",
  }
}

function openCorrection(log) {
  const tz = activeTz.value
  const toInput = (s) => { const d = parse(s); return d ? wallInZone(d.getTime(), tz) : "" }
  correction.value = { mode: "change", log, tz, from: toInput(log.from_time), to: toInput(log.to_time), reason: "", error: "" }
}

async function submitCorrection() {
  const c = correction.value
  const toServer = (v) => v.replace("T", " ") + ":00"
  if (!c.from || !c.to) { c.error = "Enter both times."; return }
  busy.value = true
  try {
    if (c.mode === "add") {
      await callBackend("request_missed_punch", { date: c.date, from_time: toServer(c.from), to_time: toServer(c.to), reason: c.reason, timezone: c.tz })
    } else {
      await callBackend("request_correction", { log: c.log.name, from_time: toServer(c.from), to_time: toServer(c.to), reason: c.reason, timezone: c.tz })
    }
    correction.value = null
    setNotice("Sent for approval.")
    await loadCycle(offset.value)
    if (openDay.value) dayDetail.value = await callBackend("get_day", { date: openDay.value })
  } catch (e) {
    c.error = errorText(e)
  } finally {
    busy.value = false
  }
}

async function loadReviewer() {
  const p = await callBackend("get_my_permissions")
  zoneState.serverTz = p.server_tz || "UTC"
  zoneState.mode = p.display_zone || "server"
  canReview.value = !!p.can_review
  pendingCount.value = p.pending_count || 0
}

// Shared-device safety: after a clock action, return to the login screen unless told to stay.
function startLogoutCountdown() {
  cancelLogout()
  const secs = state.value && state.value.auto_logout_seconds
  if (!secs || secs < 2) return
  logoutIn.value = secs
  logoutTimer = setInterval(() => {
    logoutIn.value -= 1
    if (logoutIn.value <= 0) {
      cancelLogout()
      if (frappe.app && frappe.app.logout) frappe.app.logout()
      else fetch("/api/method/logout").finally(() => window.location.reload()) // website page: back to the login form
    }
  }, 1000)
}
function cancelLogout() {
  if (logoutTimer) clearInterval(logoutTimer)
  logoutTimer = null
  logoutIn.value = null
}

let touchQuery = null
const onTouchChange = (e) => { smallTouch.value = e.matches }

onMounted(() => {
  touchQuery = window.matchMedia("(pointer: coarse) and (max-width: 820px)")
  smallTouch.value = touchQuery.matches
  touchQuery.addEventListener("change", onTouchChange)
  timer = setInterval(() => { tick.value = Date.now() }, 1000)
  refresh()
})
onBeforeUnmount(() => {
  clearInterval(timer)
  cancelLogout()
  if (touchQuery) touchQuery.removeEventListener("change", onTouchChange)
})

defineExpose({ refresh })
</script>
