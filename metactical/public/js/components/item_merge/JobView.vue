<template>
  <div class="space-y-4">
    <div class="flex items-center gap-2">
      <button class="btn btn-default btn-sm" @click="go('jobs')">← All jobs</button>
      <span class="ml-auto text-xs text-muted tabular-nums" v-if="refreshedAt">updated {{ refreshedAt.toLocaleTimeString() }}</span>
      <button class="btn btn-default btn-sm" :disabled="busy" title="Refresh" aria-label="Refresh" @click="refresh">
        <span :class="{ 'animate-spin': busy }">⟳</span>
      </button>
    </div>

    <div v-if="!job" class="im-empty"><span class="animate-spin">⟳</span> Loading job…</div>

    <template v-else>
      <div class="im-locked">
        <span class="im-label" style="color: inherit">Template</span>
        <span class="im-code">{{ job.template }}</span>
        <span :class="pillClass(job.status)">{{ job.status }}</span>
        <span class="text-muted text-xs">{{ isChanges ? 'item changes' : 'merge' }}</span>
        <a class="ml-auto im-link font-mono text-xs" :href="'/app/item-merge-job/' + encodeURIComponent(job.name)"
           target="_blank" rel="noopener">{{ job.name }}</a>
      </div>

      <div v-if="job.error" class="im-note danger">{{ job.error }}</div>
      <div v-if="settled" class="im-note ok">
        <b>Settled.</b> Every old variant is merged, reposts have drained and stock matches what was expected.
      </div>

      <!-- item changes job -->
      <section v-if="isChanges" class="im-card">
        <div class="flex items-center flex-wrap gap-2 mb-3">
          <h3 class="im-card-title">Item changes</h3>
          <span class="ml-auto"></span>
          <button v-if="canResume" class="btn btn-primary btn-sm" :disabled="resuming" @click="resume">
            {{ resuming ? 'Resuming…' : '▶ Resume' }}
          </button>
          <button class="btn btn-default btn-sm" @click="go('codes', job.template)">✎ Edit again</button>
        </div>
        <div class="im-table-wrap">
          <table class="im-table">
            <thead>
              <tr><th>Item code</th><th>Changes</th><th>Status</th><th>In ERPNext now</th></tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in job.changes" :key="c.item_code">
                <td class="font-mono whitespace-nowrap">{{ c.item_code }}</td>
                <td>
                  <div v-if="c.new_code" class="font-mono">code → {{ c.new_code }}</div>
                  <div v-if="c.new_item_name">name → {{ c.new_item_name }}</div>
                  <div v-if="c.new_retail_sku" class="font-mono">SKU → {{ c.new_retail_sku }}</div>
                </td>
                <td>
                  <span :class="pillClass(c.status)" :title="c.message || null">{{ c.status }}</span>
                  <div v-if="c.message" class="text-xs text-danger mt-1">{{ c.message }}</div>
                </td>
                <td>
                  <template v-if="liveItem(i)">
                    <div class="font-mono">
                      <a v-if="liveItem(i).exists" class="im-link" :href="itemUrl(liveItem(i).item_code)" target="_blank" rel="noopener">{{ liveItem(i).item_code }}</a>
                      <template v-else>{{ liveItem(i).item_code }} <span class="indicator-pill red">not found</span></template>
                    </div>
                    <div class="text-xs text-muted">{{ liveItem(i).item_name }} · <span class="font-mono">{{ liveItem(i).retail_sku }}</span></div>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- merge job -->
      <template v-else>
        <section class="im-card">
          <div class="flex items-center flex-wrap gap-2">
            <h3 class="im-card-title">Progress</h3>
            <span class="ml-auto"></span>
            <button v-if="canResume" class="btn btn-primary btn-sm" :disabled="resuming" @click="resume">
              {{ resuming ? 'Resuming…' : '▶ Resume' }}
            </button>
          </div>
          <div class="im-progress mt-2 mb-3" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
            <div :style="{ width: progress + '%' }"></div>
          </div>
          <div class="im-kpis">
            <div class="im-kpi"><div class="v">{{ merged }}/{{ job.pairs.length }}</div><div class="k">merged</div></div>
            <div class="im-kpi"><div class="v" :class="{ 'text-danger': failedPairs }">{{ failedPairs }}</div><div class="k">failed</div></div>
            <div class="im-kpi">
              <div class="v">{{ live ? live.old_remaining : '-' }}</div><div class="k">old variants still in ERPNext</div>
            </div>
            <div class="im-kpi">
              <div class="v">{{ leftoversDeleted }}/{{ job.leftovers.length }}</div><div class="k">leftovers deleted</div>
            </div>
            <div v-if="reposts" class="im-kpi">
              <div class="v">{{ reposts.pending }}</div>
              <div class="k">
                reposts pending<span v-if="reposts.running"> · {{ reposts.running }} running</span><span
                  v-if="reposts.failed.length" class="text-danger" :title="reposts.failed.map((f) => f.item_code).join(', ')"> · {{ reposts.failed.length }} failed</span>
              </div>
            </div>
          </div>
          <div v-if="reposts && reposts.worker" class="text-xs text-muted mt-2">
            Repost worker runs {{ reposts.worker.frequency }}, last ran {{ prettyDate(reposts.worker.last_run) }}<span
              v-if="reposts.worker.stopped" class="text-danger"> - stopped</span>.
            Stock value on the new variants catches up as reposts drain; quantities move straight away.
          </div>
        </section>

        <div class="im-split">
          <section class="im-card">
            <h3 class="im-card-title mb-3">Pairs</h3>
            <div class="im-table-wrap">
              <table class="im-table">
                <thead>
                  <tr>
                    <th>Old</th><th></th><th>New</th><th>Merge</th><th class="r">Expected</th><th class="r">Actual</th><th>Stock</th><th>History</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in job.pairs" :key="p.old">
                    <td class="font-mono whitespace-nowrap">
                      <a v-if="auditBy[p.old] && !auditBy[p.old].old_gone" class="im-link" :href="itemUrl(p.old)" target="_blank" rel="noopener">{{ p.old }}</a>
                      <template v-else>{{ p.old }}</template>
                    </td>
                    <td class="text-faint">›</td>
                    <td class="whitespace-nowrap">
                      <a class="im-link font-mono" :href="itemUrl(currentCode(p))" target="_blank" rel="noopener">{{ currentCode(p) }}</a>
                      <div v-if="auditBy[p.old] && auditBy[p.old].code !== p.new" class="text-xs text-faint font-mono">was {{ p.new }}</div>
                      <div v-if="p.item_name || p.retail_sku" class="text-xs text-faint">
                        {{ p.item_name }}<span v-if="p.retail_sku" class="font-mono"> · {{ p.retail_sku }}</span>
                      </div>
                    </td>
                    <td>
                      <span :class="pillClass(p.status)" :title="p.message || null">{{ p.status }}</span>
                      <div v-if="p.status === 'failed' && p.message" class="text-xs text-danger mt-1">{{ p.message }}</div>
                    </td>
                    <td class="r tabular-nums">{{ num(auditBy[p.old] && auditBy[p.old].expected_qty) }}</td>
                    <td class="r tabular-nums">{{ num(auditBy[p.old] && auditBy[p.old].actual_qty) }}</td>
                    <td><span v-if="auditBy[p.old]" :class="pillClass(auditBy[p.old].state)">{{ auditBy[p.old].state }}</span></td>
                    <td>
                      <span v-if="auditBy[p.old] && auditBy[p.old].history" class="text-ok font-bold"
                            title="Item Merge History logged" aria-label="Item Merge History logged">✓</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <template v-if="job.leftovers.length">
              <h3 class="im-card-title mt-4 mb-3">Leftovers</h3>
              <div class="im-table-wrap">
                <table class="im-table">
                  <tbody>
                    <tr v-for="x in job.leftovers" :key="x.item_code">
                      <td class="font-mono whitespace-nowrap">{{ x.item_code }}</td>
                      <td><span :class="pillClass(x.status)">{{ x.status }}</span></td>
                      <td class="text-muted">{{ x.message }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </section>

          <aside class="im-card">
            <div class="im-label mb-2">Steps</div>
            <div class="im-steps">
              <div>
                <span class="indicator-pill green">done</span>
                <span class="min-w-0">
                  Queued {{ fmtDateTime(job.created) }}
                  <div class="text-xs text-faint font-mono break-all">{{ job.user }}</div>
                </span>
              </div>
              <div v-for="s in job.steps" :key="s.name">
                <span :class="pillClass(s.status)">{{ s.status }}</span>
                <span class="min-w-0" :title="s.at ? fmtDateTime(s.at) : null">
                  {{ s.name }}<span v-if="s.message" class="text-muted"> - {{ s.message }}</span>
                </span>
              </div>
              <div v-if="job.finished">
                <span :class="pillClass(job.status)">{{ job.status }}</span>
                <span>Finished {{ fmtDateTime(job.finished) }}</span>
              </div>
            </div>
          </aside>
        </div>
      </template>

      <!-- after a merge: item codes and websites -->
      <section v-if="!isChanges && merged > 0 && !active" class="im-card">
        <div class="flex items-center flex-wrap gap-3">
          <div class="min-w-0">
            <h3 class="im-card-title">Item codes, names and retail SKUs</h3>
            <p class="im-lede mb-0">Rename the merged variants' item codes (for example to their retail SKU), or fix a name or SKU.</p>
          </div>
          <button class="btn btn-default btn-sm ml-auto" @click="go('codes', job.template)">✎ Edit {{ job.template }}</button>
        </div>
      </section>

      <section v-if="!isChanges && merged > 0 && !active" class="im-card">
        <div class="flex items-center flex-wrap gap-2">
          <div class="min-w-0">
            <h3 class="im-card-title">Website slugs</h3>
            <p class="im-lede mb-0">Item Detail rows (price list + slug) for each website the product is on, then Load Data From SB.</p>
          </div>
          <span class="ml-auto"></span>
          <button class="btn btn-default btn-sm" :disabled="webBusy" @click="checkWebsites">
            {{ webBusy === 'check' ? 'Checking…' : 'Check' }}
          </button>
          <button class="btn btn-danger btn-sm" :disabled="webBusy" @click="fillWebsites">
            {{ webBusy === 'fill' ? 'Filling…' : 'Fill website slugs' }}
          </button>
        </div>
        <div v-if="webRows.length" class="mt-3">
          <div class="im-table-wrap">
            <table class="im-table">
              <thead>
                <tr><th>Price list</th><th>Website</th><th>Item Price</th><th>Slug</th><th>Result</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in webRows" :key="r.price_list">
                  <td class="whitespace-nowrap">{{ r.price_list }}</td>
                  <td class="text-muted">{{ r.site }}</td>
                  <td>{{ r.has_item_price ? 'yes' : 'no' }}</td>
                  <td class="font-mono">{{ r.slug || r.current_slug || '' }}</td>
                  <td>
                    <span :class="pillClass(r.action === 'skip' ? 'kept' : 'done')">{{ r.action }}</span>
                    <span class="text-xs text-muted ml-2">{{ r.note }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="web && web.load_data_from_sb" class="text-xs text-muted mt-2">Load Data From SB: {{ loadDataText }}</div>
          <div v-if="web && web.filled_gaps && web.filled_gaps.length" class="text-xs text-muted mt-1">
            Name and description filled for: {{ web.filled_gaps.join(', ') }}
          </div>
        </div>
        <div class="mt-4">
          <WebsiteCheck :template="job.template" :initial="(web && web.check) || job.website_check || null" />
        </div>
      </section>

      <section class="im-card">
        <h3 class="im-card-title mb-3">Log</h3>
        <div ref="logEl" class="im-log" @scroll="onLogScroll">
          <div v-for="(l, i) in job.log" :key="i" :class="logClass(l)">{{ l }}</div>
          <div v-if="!job.log.length" class="text-faint">Waiting for the worker…</div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import WebsiteCheck from './WebsiteCheck.vue'
import { itemMergeApi, PROGRESS_EVENT } from './api.js'
import { alertOk, confirmAction, fmtDateTime, go, itemUrl, num, pillClass, prettyDate } from './utils.js'

const props = defineProps({
  job: { type: String, required: true }, // Item Merge Job name
})

const CHEAP_MS = 5000 // while active: the job document only
const LIVE_MS = 20000 // what the items, reposts and stock say right now

const job = ref(null)
const refreshedAt = ref(null)
const busy = ref(false)
const resuming = ref(false)
const logEl = ref(null)

const isChanges = computed(() => job.value?.job_type === 'Item Changes')
const active = computed(() => ['queued', 'running'].includes(job.value?.status))
const canResume = computed(() => ['failed', 'interrupted'].includes(job.value?.status))
const live = computed(() => job.value?.live || null)
const reposts = computed(() => (!isChanges.value && live.value?.reposts) || null)
const audit = computed(() => (!isChanges.value && live.value?.audit) || [])
const auditBy = computed(() => Object.fromEntries(audit.value.map((a) => [a.old, a])))
const merged = computed(() => (job.value && !isChanges.value
  ? job.value.pairs.filter((p) => ['ok', 'skipped'].includes(p.status)).length : 0))
const failedPairs = computed(() => (job.value ? job.value.pairs.filter((p) => p.status === 'failed').length : 0))
const progress = computed(() => (job.value?.pairs.length ? Math.round((merged.value * 100) / job.value.pairs.length) : 0))
const leftoversDeleted = computed(() => (job.value ? job.value.leftovers.filter((x) => x.status === 'deleted').length : 0))
const settled = computed(() => job.value?.status === 'done' && !isChanges.value && !!reposts.value
  && !reposts.value.pending && audit.value.every((a) => a.state === 'ok'))
// after the job: keep checking while stock is still catching up
const stillSettling = computed(() => !isChanges.value && (!!reposts.value?.pending || audit.value.some((a) => a.state === 'syncing')))

const liveItem = (i) => (isChanges.value && live.value?.items ? live.value.items[i] : null)
const currentCode = (p) => auditBy.value[p.old]?.code || p.new

// ---------- loading ----------
let timer = null
let pending = null
let lastLive = 0
let seq = 0
let applied = 0
let failures = 0

async function load(wantLive = true) {
  const name = props.job
  const mine = ++seq
  if (wantLive) busy.value = true
  try {
    const next = await itemMergeApi.getJob(name, wantLive)
    if (name !== props.job) return
    if (mine < applied) {
      // a newer answer is already on screen; only its live view can still be useful
      if (wantLive && job.value) { job.value.live = next.live; lastLive = Date.now() }
      return
    }
    applied = mine
    const wasActive = active.value
    if (wantLive) lastLive = Date.now()
    else next.live = job.value?.live ?? null // keep the last live view between cheap polls
    const first = !job.value
    job.value = next
    refreshedAt.value = new Date()
    failures = 0
    scrollLog(first)
    // the job just finished: fetch what the items say now rather than waiting for the next live poll
    if (wasActive && !active.value && !wantLive) return load(true)
  } catch (e) {
    // Frappe has shown the reason
    failures++
  } finally {
    if (wantLive) busy.value = false
    if (mine === seq) schedule()
  }
}

function schedule() {
  clearTimeout(timer)
  timer = null
  if (failures >= 3) return // stop nagging with error dialogs; Refresh starts again
  if (!job.value) {
    timer = setTimeout(() => load(true), CHEAP_MS)
  } else if (active.value) {
    timer = setTimeout(() => load(Date.now() - lastLive >= LIVE_MS), CHEAP_MS)
  } else if (stillSettling.value) {
    timer = setTimeout(() => load(true), LIVE_MS)
  }
}

function refresh() {
  failures = 0
  return load(true)
}

// ---------- realtime ----------
const onProgress = (data) => {
  if (!data || data.job !== props.job || !job.value) return
  if (data.line) {
    job.value.log.push(data.line)
    scrollLog()
    return
  }
  clearTimeout(pending)
  pending = setTimeout(() => load(false), 400)
}

onMounted(() => {
  load(true)
  frappe.realtime.on(PROGRESS_EVENT, onProgress)
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  clearTimeout(pending)
  frappe.realtime.off(PROGRESS_EVENT, onProgress)
})
watch(() => props.job, () => {
  clearTimeout(timer)
  clearTimeout(pending)
  job.value = null
  web.value = null
  lastLive = 0
  applied = 0
  failures = 0
  load(true)
})

// ---------- log ----------
let stickToBottom = true
function onLogScroll() {
  const el = logEl.value
  if (el) stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
}
async function scrollLog(force = false) {
  if (!force && !stickToBottom) return
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}
const logClass = (line) => (/FAIL|ERROR|STOPPED/.test(line) ? 'fail' : /\bOK\b|=== job done/.test(line) ? 'ok' : '')

// ---------- resume ----------
async function resume() {
  resuming.value = true
  try {
    await itemMergeApi.resumeJob(props.job)
    alertOk(`Job ${props.job} queued again`)
    failures = 0
    await load(true)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    resuming.value = false
  }
}

// ---------- website Item Detail rows (price list + slug) ----------
const web = ref(null)
const webBusy = ref('') // '' | 'check' | 'fill'
const webRows = computed(() => web.value?.rows || job.value?.websites || [])
const loadDataText = computed(() => {
  const v = web.value?.load_data_from_sb
  if (!v) return ''
  return typeof v === 'string' ? v : v.map((m) => String(m?.message || '').replace(/<[^>]+>/g, '')).join(' · ')
})

async function checkWebsites() {
  webBusy.value = 'check'
  try {
    web.value = await itemMergeApi.getWebsitePlan(job.value.template)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    webBusy.value = ''
  }
}

async function fillWebsites() {
  const template = job.value.template
  const ok = await confirmAction({
    title: 'Fill website slugs?',
    message: `Look up ${template} on each website it has an Item Price for, add the slugs found to Item Detail, ` +
      'then run Load Data From SB (skipped if any row has a blank slug).\nThis writes to ERPNext.',
    label: 'Fill slugs',
    danger: true,
  })
  if (!ok) return
  webBusy.value = 'fill'
  try {
    web.value = await itemMergeApi.applyWebsites(template)
    alertOk(`${(web.value.applied || []).length} website row(s) added or filled`)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    webBusy.value = ''
  }
}

defineExpose({ refresh })
</script>
