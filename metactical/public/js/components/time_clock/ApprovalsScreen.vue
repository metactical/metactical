<template>
  <div class="ap-root">
    <div class="ap-bar">
      <div class="tc-tabs" role="tablist">
        <button class="tc-tab" :class="{ active: tab === 'Pending' }" role="tab" @click="setTab('Pending')">
          Pending <span v-if="counts.pending" class="tc-count">{{ counts.pending }}</span>
        </button>
        <button class="tc-tab" :class="{ active: tab === 'Decided' }" role="tab" @click="setTab('Decided')">
          Decided <span class="ap-n">{{ counts.decided }}</span>
        </button>
      </div>
      <div class="ap-filters">
        <select v-model="f.employee" aria-label="Employee">
          <option value="">All employees</option>
          <option v-for="e in employees" :key="e.user" :value="e.user">{{ e.name }}</option>
        </select>
        <select v-model="f.cycle" aria-label="Pay cycle">
          <option value="">Both pay cycles</option>
          <option value="current">Current pay cycle</option>
          <option value="previous">Previous pay cycle</option>
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

    <div v-if="cycles" class="ap-scope">
      Showing the current and previous pay cycle:
      {{ fmtDate(cycles.previous ? cycles.previous.from : cycles.current.from) }} – {{ fmtDate(cycles.current.to) }}.
      Older periods are already paid out.
    </div>
    <div v-if="hiddenOlder" class="tc-card ap-old">
      <div>
        <b>{{ hiddenOlder }}</b> older request{{ hiddenOlder === 1 ? ' is' : 's are' }} hidden because that pay period is already paid out.
        They can no longer be approved.
      </div>
      <button class="btn btn-default btn-sm" :disabled="busy" @click="expireOld">Decline them as expired</button>
    </div>

    <div v-if="loading" class="tc-card tc-muted">Loading…</div>
    <div v-else-if="error" class="tc-card tc-blocked">
      <div class="tc-blocked-title">Couldn't load requests</div>
      <p>{{ error }}</p>
      <button class="btn btn-default btn-sm" @click="load(tab)">Try again</button>
    </div>
    <div v-else-if="!shown.length" class="tc-card ap-empty">
      <template v-if="rows.length">No requests match these filters.</template>
      <template v-else-if="tab === 'Pending'">Nothing waiting for approval.</template>
      <template v-else>No decided requests yet.</template>
    </div>

    <div v-else class="ap-grid">
      <!-- The queue -->
      <div class="tc-card ap-list">
        <button
          v-for="r in shown"
          :key="r.name"
          class="ap-item"
          :class="{ active: sel && sel.name === r.name }"
          @click="selectedName = r.name"
        >
          <span class="ap-item-top">
            <span class="ap-item-name">{{ r.employee_name }}</span>
            <span v-if="tab === 'Decided'" class="tc-pill" :class="'tc-pill-' + r.status.toLowerCase()">{{ r.status }}</span>
            <span v-else class="ap-delta">{{ fmtDelta(r.delta_hours) }}</span>
          </span>
          <span class="ap-item-sub">
            {{ fmtDate(r.date) }} · <span class="ap-cycle">{{ r.cycle }}</span> ·
            <span class="tc-pill" :class="r.request_type === 'Add' ? 'tc-pill-wait' : 'tc-pill-out'">{{ r.request_type === 'Add' ? 'missed time' : 'time change' }}</span>
          </span>
        </button>
      </div>

      <!-- The one being decided -->
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

    <div v-if="notice" class="tc-notice" :class="'tc-notice-' + notice.kind">{{ notice.text }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { callBackend, errorText } from "./api"
import { fmtDate, fmtWeekday, fmtTime, fmtDateTime, fmtDuration, fmtDelta } from "./format"

const emit = defineEmits(["changed"])

const tab = ref("Pending")
const rows = ref([])
const counts = ref({ pending: 0, decided: 0 })
const loading = ref(true)
const error = ref("")
const busy = ref(false)
const actionError = ref("")
const comment = ref("")
const notice = ref(null)
const selectedName = ref("")
const f = ref({ employee: "", type: "", shift: "", cycle: "" })
const cycles = ref(null)
const hiddenOlder = ref(0)

// Everyone with the Time Approval role sees every request, so the filters are built from what came back.
const employees = computed(() => {
  const seen = new Map()
  rows.value.forEach((r) => seen.set(r.user, r.employee_name))
  return [...seen.entries()].map(([user, name]) => ({ user, name })).sort((a, b) => a.name.localeCompare(b.name))
})
const shifts = computed(() => [...new Set(rows.value.map((r) => r.shift).filter(Boolean))].sort())

const shown = computed(() =>
  rows.value.filter(
    (r) =>
      (!f.value.employee || r.user === f.value.employee) &&
      (!f.value.cycle || r.cycle === f.value.cycle) &&
      (!f.value.type || r.request_type === f.value.type) &&
      (!f.value.shift || r.shift === f.value.shift)
  )
)
const sel = computed(() => shown.value.find((r) => r.name === selectedName.value) || shown.value[0] || null)

async function load(which) {
  loading.value = true
  error.value = ""
  try {
    const data = await callBackend("get_requests", { tab: which })
    rows.value = data.rows
    counts.value = { pending: data.pending_count, decided: data.decided_count }
    cycles.value = data.cycles
    hiddenOlder.value = data.hidden_older_pending || 0
    selectedName.value = data.rows.length ? data.rows[0].name : ""
    comment.value = ""
    actionError.value = ""
    emit("changed", data.pending_count)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}

function setTab(which) {
  if (tab.value === which) return
  tab.value = which
  load(which)
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
    // Move straight on to the next request in the queue.
    const list = shown.value
    const idx = list.findIndex((x) => x.name === r.name)
    const next = list[idx + 1] || list[idx - 1]
    rows.value = rows.value.filter((x) => x.name !== r.name)
    counts.value = { pending: counts.value.pending - 1, decided: counts.value.decided + 1 }
    selectedName.value = next ? next.name : ""
    comment.value = ""
    emit("changed", counts.value.pending)
    setNotice(`${decision}: ${r.employee_name}, ${fmtDate(r.date)}.`)
  } catch (e) {
    actionError.value = errorText(e)
  } finally {
    busy.value = false
  }
}

// Pending requests about a period that is already paid out cannot be approved any more: close them with a note.
async function expireOld() {
  if (!window.confirm(`Decline ${hiddenOlder.value} older request(s) as expired? The employees will be told to send a new request if it still needs changing.`)) return
  busy.value = true
  try {
    const r = await callBackend("expire_old_requests")
    setNotice(`Declined ${r.expired} old request(s) as expired.`)
    await load(tab.value)
  } catch (e) {
    setNotice(errorText(e), "error")
  } finally {
    busy.value = false
  }
}

onMounted(() => load(tab.value))
defineExpose({ reload: () => load(tab.value) })
</script>
