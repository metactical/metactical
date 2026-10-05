<template>
  <div class="tc-root">
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
        <div class="tc-date">{{ weekdayText }} · {{ dateText }}</div>

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

        <button
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

      <!-- Approvals (only for the approver) -->
      <div v-if="canReview && pending.length" class="tc-card">
        <div class="tc-card-title">Waiting for your approval <span class="tc-count">{{ pending.length }}</span></div>
        <div v-for="r in pending" :key="r.name" class="tc-req">
          <div class="tc-req-main">
            <b>{{ r.user }}</b> · {{ fmtDate(r.date) }}
            <div class="tc-muted">{{ r.current_checkin }} – {{ r.current_checkout }} → <b>{{ fmtTime(r.requested_from) || r.requested_checkin }} – {{ fmtTime(r.requested_to) || r.requested_checkout }}</b> ({{ r.requested_total_hours }} h)</div>
            <div v-if="r.reason" class="tc-reason">“{{ r.reason }}”</div>
          </div>
          <div class="tc-req-actions">
            <button class="btn btn-primary btn-xs" :disabled="busy" @click="review(r, 'Approved')">Approve</button>
            <button class="btn btn-default btn-xs" :disabled="busy" @click="review(r, 'Declined')">Decline</button>
          </div>
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
            <button class="tc-day-row" :disabled="!d.log_count" @click="toggleDay(d)">
              <span class="tc-day-wd">{{ fmtWeekday(d.date) }}</span>
              <span class="tc-day-name">{{ fmtDate(d.date) }}</span>
              <span class="tc-bar" :title="d.short ? 'Shorter than the ' + fmtDuration(cycle.shift_hours) + ' shift' : ''"><span class="tc-bar-fill" :class="{ 'is-short': d.short }" :style="{ width: barWidth(d.hours) + '%' }"></span></span>
              <span class="tc-day-hours">{{ d.hours ? fmtDuration(d.hours) : '—' }}</span>
              <span v-if="d.short" class="tc-pill tc-pill-short">short day</span>
              <span v-if="d.pending_requests" class="tc-pill tc-pill-wait">change pending</span>
            </button>
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

    <!-- Correction dialog -->
    <div v-if="correction" class="tc-modal-back" @click.self="correction = null">
      <div class="tc-modal" role="dialog" aria-modal="true">
        <div class="tc-card-title">Request a time change</div>
        <p class="tc-muted">{{ fmtDate(correction.log.date) }}: currently {{ fmtTime(correction.log.from_time) }} → {{ fmtTime(correction.log.to_time) }}</p>
        <label>Clock in
          <input type="datetime-local" v-model="correction.from" />
        </label>
        <label>Clock out
          <input type="datetime-local" v-model="correction.to" />
        </label>
        <label>Why does it need to change?
          <textarea v-model="correction.reason" rows="3" placeholder="e.g. Forgot to clock out, left at 5:00 PM"></textarea>
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

const API = "metactical.time_tracker.api"

// Server rejections carry a human message in _server_messages; surface it instead of a stack trace.
// (frappe.call's error callback gets no response object here, so this talks to the endpoint directly.)
const serverMessage = (body, status) => {
  try {
    const msgs = JSON.parse(body._server_messages).map((m) => JSON.parse(m).message)
    const text = msgs.join(" ").replace(/<[^>]+>/g, "").trim()
    if (text) return text
  } catch (_) { /* fall through */ }
  if (status === 403) return "You don't have permission to do that."
  if (status === 401 || status === 410) return "Your session expired. Please log in again."
  return "Something went wrong. Please try again."
}

const callBackend = async (method, args = {}) => {
  const res = await fetch(`/api/method/${API}.${method}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Frappe-CSRF-Token": frappe.csrf_token || window.csrf_token,
    },
    body: JSON.stringify(args),
  })
  let body = {}
  try { body = await res.json() } catch (_) { /* non-JSON error page */ }
  if (!res.ok) throw new Error(serverMessage(body, res.status))
  return body.message
}

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
const pending = ref([])
const logoutIn = ref(null)

// The page shows the SERVER's time: remember how far the browser clock is from it.
const serverMs = ref(Date.now())
const fetchedAt = ref(Date.now())
const tick = ref(Date.now())
let timer = null
let logoutTimer = null

// "2026-10-05 12:30:12.123456" is server-local wall time. Parse it as-is, never through UTC.
const parse = (s) => {
  if (!s) return null
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : null
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const pad2 = (n) => String(n).padStart(2, "0")
// 01 - Jan - 2026
const dateParts = (d) => `${pad2(d.getDate())} - ${MONTHS[d.getMonth()]} - ${d.getFullYear()}`
const nowMs = computed(() => serverMs.value + (tick.value - fetchedAt.value))
const nowDate = computed(() => new Date(nowMs.value))

const clockText = computed(() =>
  nowDate.value.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })
)
const dateText = computed(() => dateParts(nowDate.value))
const weekdayText = computed(() => nowDate.value.toLocaleDateString("en", { weekday: "long" }))
const elapsedHours = computed(() => {
  const from = state.value && state.value.open_log && parse(state.value.open_log.from_time)
  return from ? Math.max(0, (nowMs.value - from.getTime()) / 3600000) : 0
})

const fmtTime = (s) => {
  const d = parse(s)
  return d ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : ""
}
const asDate = (s) => parse(String(s).length === 10 ? s + " 00:00" : s)
const fmtDate = (s) => { const d = asDate(s); return d ? dateParts(d) : "" }
const fmtWeekday = (s) => { const d = asDate(s); return d ? d.toLocaleDateString("en", { weekday: "short" }) : "" }
// A full bar is one scheduled shift. Longer days just stay full: overtime is deliberately not marked.
const barWidth = (hours) => {
  const shift = (cycle.value && cycle.value.shift_hours) || 8
  return Math.min(100, Math.max(0, (hours / shift) * 100))
}
const fmtDuration = (h) => {
  const mins = Math.round((h || 0) * 60)
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`
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

const errorText = (e) => (e && e.message) || "Something went wrong. Please try again."

async function refresh() {
  try {
    applyState(await callBackend("get_state"))
    if (state.value.status !== "blocked") {
      await Promise.all([loadCycle(offset.value), loadReviewer()])
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

function openCorrection(log) {
  const toInput = (s) => { const d = parse(s); return d ? new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "" }
  correction.value = { log, from: toInput(log.from_time), to: toInput(log.to_time), reason: "", error: "" }
}

async function submitCorrection() {
  const c = correction.value
  const toServer = (v) => v.replace("T", " ") + ":00"
  if (!c.from || !c.to) { c.error = "Enter both times."; return }
  busy.value = true
  try {
    await callBackend("request_correction", { log: c.log.name, from_time: toServer(c.from), to_time: toServer(c.to), reason: c.reason })
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
  canReview.value = !!p.can_review
  pending.value = canReview.value ? await callBackend("get_pending_requests") : []
}

async function review(r, decision) {
  const comment = decision === "Declined" ? window.prompt("Reason for declining (optional)") : null
  if (decision === "Declined" && comment === null) return
  busy.value = true
  try {
    await callBackend("review_request", { name: r.name, decision, comment })
    pending.value = pending.value.filter((x) => x.name !== r.name)
    setNotice(`Request ${decision.toLowerCase()}.`)
  } catch (e) {
    setNotice(errorText(e), "error")
  } finally {
    busy.value = false
  }
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

onMounted(() => {
  timer = setInterval(() => { tick.value = Date.now() }, 1000)
  refresh()
})
onBeforeUnmount(() => { clearInterval(timer); cancelLogout() })

defineExpose({ refresh })
</script>
