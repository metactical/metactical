<template>
  <section class="im-card">
    <h3 class="im-card-title">Merge jobs</h3>
    <p class="im-lede">Every merge and item-change job run from this page. Search by template to check on a family.</p>
    <form class="flex items-center gap-2" @submit.prevent="load">
      <div ref="pickerEl" class="im-link-control" style="flex: 1; max-width: 420px"></div>
      <button type="submit" class="btn btn-default btn-sm" :disabled="loading">{{ loading ? 'Loading…' : 'Search' }}</button>
      <button v-if="q" type="button" class="btn btn-default btn-sm" @click="clearFilter">Clear</button>
      <a class="btn btn-default btn-sm ml-auto" href="/app/item-merge-job">Open the job list</a>
    </form>
    <div v-if="!loading && !jobs.length" class="im-empty">{{ q ? 'No jobs for ' + q : 'No merge jobs yet.' }}</div>
    <div v-else class="im-table-wrap mt-3">
      <table class="im-table">
        <thead>
          <tr><th>Template</th><th>Job</th><th>Type</th><th>Status</th><th class="r">Done</th><th class="r">Failed</th><th>Created</th><th>Finished</th><th>User</th></tr>
        </thead>
        <tbody>
          <tr v-for="j in jobs" :key="j.name" class="clickable" tabindex="0" @click="emit('open', j.name)" @keydown.enter="emit('open', j.name)">
            <td class="font-mono whitespace-nowrap">{{ j.template }}</td>
            <td class="font-mono text-muted whitespace-nowrap">{{ j.name }}</td>
            <td class="text-muted">{{ j.job_type === 'Item Changes' ? 'item changes' : 'merge' }}</td>
            <td><span :class="pillClass(j.status)">{{ j.status }}</span></td>
            <td class="r tabular-nums">{{ j.processed }}/{{ j.total }}</td>
            <td class="r tabular-nums" :class="{ 'text-danger': j.failed }">{{ j.failed || '' }}</td>
            <td class="whitespace-nowrap tabular-nums">{{ fmtDateTime(j.created) }}</td>
            <td class="whitespace-nowrap tabular-nums">{{ fmtDateTime(j.finished) }}</td>
            <td class="text-muted">{{ j.user }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { itemMergeApi, PROGRESS_EVENT } from './api.js'
import { fmtDateTime, makeLink, pillClass } from './utils.js'

const emit = defineEmits(['open'])

const q = ref('')
const jobs = ref([])
const loading = ref(false)
const pickerEl = ref(null)
let picker = null
let timer = null

async function load() {
  loading.value = true
  try {
    jobs.value = (await itemMergeApi.listJobs((q.value || '').trim())).jobs
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    loading.value = false
  }
  clearTimeout(timer)
  // realtime updates cover a job this user started; a slow poll covers everyone else's
  if (jobs.value.some((j) => ['queued', 'running'].includes(j.status))) timer = setTimeout(load, 15000)
}

let pending = null
const onProgress = (data) => {
  if (!jobs.value.some((j) => j.name === data.job) || data.line) return
  clearTimeout(pending)
  pending = setTimeout(load, 500)
}

function clearFilter() {
  q.value = ''
  picker?.set('')
  load()
}

onMounted(() => {
  nextTick(() => {
    // the template filter is a real Link on Item, so it only ever offers templates that exist
    picker = makeLink(pickerEl.value, {
      options: 'Item',
      filters: { has_variants: 1 },
      placeholder: 'Any template',
      onPick: (v) => { q.value = v || ''; load() },
    })
  })
  load()
  frappe.realtime.on(PROGRESS_EVENT, onProgress)
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  clearTimeout(pending)
  frappe.realtime.off(PROGRESS_EVENT, onProgress)
})

defineExpose({ refresh: load })
</script>
