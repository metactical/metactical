<template>
  <div class="ap-root">
    <!-- Requests | Forgotten clock-outs -->
    <div class="tc-tabs" role="tablist">
      <button class="tc-tab" :class="{ active: view === 'requests' }" role="tab" @click="view = 'requests'">
        Requests <span v-if="pendingCount" class="tc-count">{{ pendingCount }}</span>
      </button>
      <button class="tc-tab" :class="{ active: view === 'attention' }" role="tab" @click="openAttention">
        Forgotten clock-outs <span v-if="attentionCount" class="tc-count tc-count-warn">{{ attentionCount }}</span>
      </button>
    </div>

    <!-- ============ Requests, one pay cycle at a time ============ -->
    <template v-if="view === 'requests'">
      <div class="ap-cyclebar">
        <button class="btn btn-default btn-sm" :disabled="!data || !data.has_older || loading" @click="go(offset + 1)">‹ Earlier cycle</button>
        <div class="ap-cycle-title">
          <b>{{ cycleName }}</b>
          <span v-if="data" class="tc-muted">{{ fmtDate(data.cycle.from) }} – {{ fmtDate(data.cycle.to) }}</span>
          <span v-if="data && data.can_browse_history" class="tc-muted ap-admin">Administrator: full history</span>
        </div>
        <button class="btn btn-default btn-sm" :disabled="!data || !data.has_newer || loading" @click="go(offset - 1)">Later cycle ›</button>
      </div>

      <div v-if="data && offset === 0 && data.hidden_older_pending" class="tc-card ap-old">
        <div>
          <b>{{ data.hidden_older_pending }}</b> older request{{ data.hidden_older_pending === 1 ? ' is' : 's are' }} still pending from pay periods that are already paid out.
          They can no longer be approved.
        </div>
        <button class="btn btn-default btn-sm" :disabled="busy" @click="expireOld">Decline them as expired</button>
      </div>

      <div class="ap-bar">
        <div class="ap-chips" role="group" aria-label="Status">
          <button v-for="c in chips" :key="c.key" class="ap-chip" :class="{ active: status === c.key }" @click="status = c.key">
            {{ c.label }} <span class="ap-chip-n">{{ data ? data.counts[c.key] : 0 }}</span>
          </button>
        </div>
        <div class="ap-filters">
          <select v-model="f.employee" aria-label="Employee">
            <option value="">All employees</option>
            <option v-for="e in employees" :key="e.user" :value="e.user">{{ e.name }}</option>
          </select>
          <select v-model="f.type" aria-label="Request type">
            <option value="">All types</option>
            <option value="Change">Time changes</option>
            <option value="Add">Missed time</option>
          </select>
          <select v-model="f.shift" aria-label="Shift">
            <option value="">All shifts</option>
            <option v-for="s in shifts" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
      </div>

      <div v-if="loading" class="tc-card tc-muted">Loading…</div>
      <div v-else-if="error" class="tc-card tc-blocked">
        <div class="tc-blocked-title">Couldn't load requests</div>
        <p>{{ error }}</p>
        <button class="btn btn-default btn-sm" @click="go(offset)">Try again</button>
      </div>
      <div v-else-if="!shown.length" class="tc-card ap-empty">
        <template v-if="data && data.counts.All">No requests match these filters.</template>
        <template v-else>No requests in this pay cycle.</template>
      </div>

      <div v-else class="ap-grid">
        <div class="tc-card ap-list">
          <button v-for="r in shown" :key="r.name" class="ap-item" :class="{ active: sel && sel.name === r.name }" @click="selectedName = r.name">
            <span class="ap-item-top">
              <span class="ap-item-name">{{ r.employee_name }}</span>
              <span class="tc-pill" :class="'tc-pill-' + r.status.toLowerCase()">{{ r.status }}</span>
            </span>
            <span class="ap-item-sub">
              {{ fmtDate(r.date) }} ·
              <span class="tc-pill" :class="r.request_type === 'Add' ? 'tc-pill-wait' : 'tc-pill-out'">{{ r.request_type === 'Add' ? 'missed time' : 'time change' }}</span>
              · <span class="ap-delta">{{ fmtDelta(r.delta_hours) }}</span>
            </span>
          </button>
        </div>

        <div v-if="sel" class="tc-card ap-detail">
          <div class="ap-detail-head">
            <div>
              <div class="ap-title">{{ sel.employee_name }}</div>
              <div class="tc-muted">{{ sel.shift || 'No active shift' }} · {{ fmtWeekday(sel.date) }} {{ fmtDate(sel.date) }}</div>
            </div>
            <span class="tc-pill" :class="sel.request_type === 'Add' ? 'tc-pill-wait' : 'tc-pill-out'">{{ sel.request_type === 'Add' ? 'missed time' : 'time change' }}</span>
          </div>

          <div class="ap-compare">
            <div class="ap-side">
              <div class="ap-label">Recorded</div>
              <template v-if="sel.current_from">
                <div class="ap-times">{{ fmtTime(sel.current_from) }} – {{ fmtTime(sel.current_to) }}</div>
                <div class="tc-muted">{{ fmtDuration(sel.current_hours) }}</div>
              </template>
              <div v-else class="tc-muted">Nothing recorded</div>
            </div>
            <div class="ap-arrow" aria-hidden="true">→</div>
            <div class="ap-side ap-side-new">
              <div class="ap-label">Requested</div>
              <div class="ap-times">{{ fmtTime(sel.requested_from) }} – {{ fmtTime(sel.requested_to) }}</div>
              <div class="tc-muted">{{ fmtDuration(sel.requested_hours) }} <b class="ap-delta">{{ fmtDelta(sel.delta_hours) }}</b></div>
            </div>
          </div>

          <div class="ap-block">
            <div class="ap-label">Reason</div>
            <div class="ap-reason">{{ sel.reason || 'No reason given.' }}</div>
          </div>

          <div class="ap-block">
            <div class="ap-label">That day</div>
            <div v-if="!sel.same_day.length" class="tc-muted">No other entries.</div>
            <div v-for="(l, i) in sel.same_day" :key="i" class="tc-entry">
              <span>{{ fmtTime(l.from_time) }} → {{ l.to_time ? fmtTime(l.to_time) : 'still open' }}</span>
              <span class="tc-muted">{{ fmtDuration(l.hours) }}</span>
              <span v-if="l.is_this_entry" class="tc-pill tc-pill-wait">this entry</span>
            </div>
          </div>

          <div class="tc-muted ap-when">Requested {{ fmtDateTime(sel.requested_at) }}</div>

          <template v-if="sel.status === 'Pending'">
            <label class="ap-note">Note to the employee (optional)
              <textarea v-model="comment" rows="2" placeholder="Shown to them on the day. Helpful when declining."></textarea>
            </label>
            <div v-if="actionError" class="tc-warn">{{ actionError }}</div>
            <div class="ap-actions">
              <button class="btn btn-default" :disabled="busy" @click="decide('Declined')">Decline</button>
              <button class="btn btn-primary ap-approve" :disabled="busy" @click="decide('Approved')">Approve</button>
            </div>
          </template>
          <div v-else class="ap-decided">
            <span class="tc-pill" :class="'tc-pill-' + sel.status.toLowerCase()">{{ sel.status }}</span>
            by {{ sel.reviewed_by_name || 'unknown' }} · {{ fmtDateTime(sel.reviewed_on) }}
            <div v-if="sel.review_comment" class="ap-reason">“{{ sel.review_comment }}”</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ============ Forgotten clock-outs ============ -->
    <template v-else>
      <div v-if="attLoading" class="tc-card tc-muted">Loading…</div>
      <div v-else-if="attError" class="tc-card tc-blocked"><p>{{ attError }}</p></div>
      <template v-else>
        <div class="tc-card">
          <div class="tc-card-title">Still clocked in after their shift <span class="tc-count">{{ att.open.length }}</span></div>
          <p v-if="!att.open.length" class="tc-muted">Nobody is clocked in past their scheduled end.</p>
          <div v-for="r in att.open" :key="r.name" class="ap-att">
            <div class="ap-att-main">
              <b>{{ r.employee_name }}</b> · in since {{ fmtDate(r.from_time) }} {{ fmtTime(r.from_time) }}
              <div class="tc-muted">
                Shift ended {{ r.expected_end ? fmtTime(r.expected_end) : 'unknown' }} · open {{ fmtDuration(r.open_hours) }}
                <template v-if="r.reminder_sent_on"> · reminder sent {{ fmtTime(r.reminder_sent_on) }}</template>
              </div>
            </div>
            <div class="ap-att-act">
              <label class="ap-att-label">They left at
                <input type="datetime-local" v-model="closeAt[r.name]" />
              </label>
              <button class="btn btn-primary btn-sm" :disabled="busy" @click="closeEntry(r, closeAt[r.name])">Close entry</button>
            </div>
          </div>
        </div>

        <div class="tc-card">
          <div class="tc-card-title">Closed by the system, please confirm <span class="tc-count">{{ att.auto_closed.length }}</span></div>
          <p v-if="!att.auto_closed.length" class="tc-muted">Nothing to confirm.</p>
          <div v-for="r in att.auto_closed" :key="r.name" class="ap-att">
            <div class="ap-att-main">
              <b>{{ r.employee_name }}</b> · {{ fmtDate(r.date) }}
              <div class="tc-muted">{{ fmtTime(r.from_time) }} → {{ fmtTime(r.to_time) }} · {{ fmtDuration(r.hours) }}: closed at the end of their shift</div>
            </div>
            <div class="ap-att-act">
              <label class="ap-att-label">Actually left at
                <input type="datetime-local" v-model="closeAt[r.name]" />
              </label>
              <button class="btn btn-default btn-sm" :disabled="busy" @click="closeEntry(r, closeAt[r.name])">Change time</button>
              <button class="btn btn-primary btn-sm" :disabled="busy" @click="closeEntry(r, null)">Looks right</button>
            </div>
          </div>
        </div>
      </template>
    </template>

    <div v-if="notice" class="tc-notice" :class="'tc-notice-' + notice.kind">{{ notice.text }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { callBackend, errorText } from "./api"
import { activeTz } from "./zone"
import { fmtDate, fmtWeekday, fmtTime, fmtDateTime, fmtDuration, fmtDelta, parse, wallInZone } from "./format"

const emit = defineEmits(["changed"])

const view = ref("requests") // "requests" | "attention"

// ---- requests: one pay cycle at a time
const data = ref(null)
const offset = ref(0)
const loading = ref(true)
const error = ref("")
const busy = ref(false)
const actionError = ref("")
const comment = ref("")
const notice = ref(null)
const selectedName = ref("")
const status = ref("All")
const f = ref({ employee: "", type: "", shift: "" })
const pendingCount = ref(0)

const chips = [
  { key: "All", label: "All" },
  { key: "Pending", label: "Pending" },
  { key: "Approved", label: "Approved" },
  { key: "Declined", label: "Declined" },
]

const rows = computed(() => (data.value ? data.value.rows : []))
const employees = computed(() => {
  const seen = new Map()
  rows.value.forEach((r) => seen.set(r.user, r.employee_name))
  return [...seen.entries()].map(([user, name]) => ({ user, name })).sort((a, b) => a.name.localeCompare(b.name))
})
const shifts = computed(() => [...new Set(rows.value.map((r) => r.shift).filter(Boolean))].sort())
const shown = computed(() =>
  rows.value.filter(
    (r) =>
      (status.value === "All" || r.status === status.value) &&
      (!f.value.employee || r.user === f.value.employee) &&
      (!f.value.type || r.request_type === f.value.type) &&
      (!f.value.shift || r.shift === f.value.shift)
  )
)
const sel = computed(() => shown.value.find((r) => r.name === selectedName.value) || shown.value[0] || null)
const cycleName = computed(() => {
  const l = data.value && data.value.cycle.label
  return l === "current" ? "Current pay cycle" : l === "previous" ? "Previous pay cycle" : "Earlier pay cycle"
})

async function go(n, keep = "") {
  offset.value = n
  loading.value = true
  error.value = ""
  try {
    const d = await callBackend("get_requests", { cycle_offset: n })
    data.value = d
    pendingCount.value = d.pending_count
    emit("changed", d.pending_count)
    const firstPending = d.rows.find((r) => r.status === "Pending")
    selectedName.value = keep && d.rows.some((r) => r.name === keep) ? keep : firstPending ? firstPending.name : d.rows[0] ? d.rows[0].name : ""
    if (!firstPending && status.value === "Pending") status.value = "All"
    comment.value = ""
    actionError.value = ""
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}

const setNotice = (text, kind = "ok") => {
  notice.value = { text, kind }
  setTimeout(() => { if (notice.value && notice.value.text === text) notice.value = null }, 5000)
}

async function decide(decision) {
  const r = sel.value
  if (!r || busy.value) return
  busy.value = true
  actionError.value = ""
  try {
    await callBackend("review_request", { name: r.name, decision, comment: comment.value })
    // move on to the next request that is still waiting, then refresh the cycle
    const waiting = rows.value.filter((x) => x.status === "Pending" && x.name !== r.name)
    await go(offset.value, waiting[0] ? waiting[0].name : r.name)
    setNotice(`${decision}: ${r.employee_name}, ${fmtDate(r.date)}.`)
  } catch (e) {
    actionError.value = errorText(e)
  } finally {
    busy.value = false
  }
}

// Pending requests about a period that is already paid out cannot be approved any more: close them with a note.
async function expireOld() {
  const n = data.value.hidden_older_pending
  if (!window.confirm(`Decline ${n} older request(s) as expired? The employees will be told to send a new request if it still needs changing.`)) return
  busy.value = true
  try {
    const r = await callBackend("expire_old_requests")
    setNotice(`Declined ${r.expired} old request(s) as expired.`)
    await go(offset.value)
  } catch (e) {
    setNotice(errorText(e), "error")
  } finally {
    busy.value = false
  }
}

// ---- forgotten clock-outs
const att = ref({ open: [], auto_closed: [] })
const attLoading = ref(false)
const attError = ref("")
const attentionCount = ref(0)
const closeAt = ref({})

async function loadAttention() {
  attLoading.value = true
  attError.value = ""
  try {
    const d = await callBackend("get_attention")
    att.value = d
    attentionCount.value = d.open.length + d.auto_closed.length
    const tz = activeTz.value
    const inputs = {}
    d.open.forEach((r) => { const t = parse(r.expected_end || r.from_time); inputs[r.name] = t ? wallInZone(t.getTime(), tz) : "" })
    d.auto_closed.forEach((r) => { const t = parse(r.to_time); inputs[r.name] = t ? wallInZone(t.getTime(), tz) : "" })
    closeAt.value = inputs
  } catch (e) {
    attError.value = errorText(e)
  } finally {
    attLoading.value = false
  }
}

function openAttention() {
  view.value = "attention"
  loadAttention()
}

async function closeEntry(r, when) {
  if (busy.value) return
  busy.value = true
  try {
    await callBackend("close_entry", { log: r.name, to_time: when ? when.replace("T", " ") + ":00" : null, timezone: activeTz.value })
    setNotice(when ? `Saved the time for ${r.employee_name}.` : `Confirmed ${r.employee_name}.`)
    await loadAttention()
  } catch (e) {
    setNotice(errorText(e), "error")
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await go(0)
  // the badge on the second tab should be right without visiting it
  try {
    const d = await callBackend("get_attention")
    attentionCount.value = d.open.length + d.auto_closed.length
  } catch (_) { /* shown when the tab is opened */ }
})
defineExpose({ reload: () => go(offset.value) })
</script>
