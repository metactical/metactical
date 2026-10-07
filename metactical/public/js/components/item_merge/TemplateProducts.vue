<template>
  <section class="im-card mt-3">
    <div class="flex items-center gap-2">
      <h3 class="im-card-title mb-0">Storebuilder products</h3>
      <span v-if="rows.length" class="text-xs text-muted">
        {{ verifiedCount }} read from Storebuilder<span v-if="skippedCount">, {{ skippedCount }} with nothing to check</span><span v-if="attentionCount">, {{ attentionCount }} needing attention</span>
      </span>
      <button class="btn btn-default btn-sm ml-auto" :disabled="busy || !templates.length" @click="check">
        {{ busy ? 'Checking…' : 'Check Storebuilder' }}
      </button>
    </div>
    <p class="im-lede">
      The External ID and slug each website holds for these templates, read from
      <span class="font-mono">papi_product_details</span>. The merge deletes the templates it
      consolidates away, so this is the only chance to take the handle on their Storebuilder
      products - without it they stay live on the sites as duplicates.
    </p>

    <div v-if="loading" class="im-empty"><span class="animate-spin">⟳</span> Loading…</div>
    <div v-else-if="!templates.length" class="im-empty">Tick a template to see what the websites hold for it.</div>
    <div v-else-if="!rows.length" class="im-empty">Nothing to check for this selection.</div>
    <template v-else>
      <div class="im-table-wrap">
        <table class="im-table">
          <thead>
            <tr>
              <th>Template</th>
              <th>Retail SKU</th>
              <th>External ID</th>
              <th>Slug</th>
              <th>Price list</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.template + '|' + (r.price_list || '-')" :class="{ bad: r.status === 'missing' || r.status === 'error' }">
              <td class="font-mono whitespace-nowrap">{{ r.template }}</td>
              <td class="font-mono text-muted whitespace-nowrap">{{ r.retail_sku || '—' }}</td>
              <td class="font-mono whitespace-nowrap">{{ r.external_id || '—' }}</td>
              <td class="font-mono">{{ r.slug || r.erp_slug || '—' }}</td>
              <td class="whitespace-nowrap">
                <template v-if="r.price_list">
                  <span class="flex items-center gap-1">
                    {{ r.price_list }}
                    <button class="im-row-remove ml-auto" :disabled="busy"
                            :title="'Remove ' + r.price_list + ' from ' + r.template"
                            :aria-label="'Remove ' + r.price_list + ' from ' + r.template"
                            @click="removePriceList(r)">✕</button>
                  </span>
                </template>
                <span v-else class="text-faint">—</span>
              </td>
              <td>
                <span :class="pillClass(r.status)">{{ label(r.status) }}</span>
                <div class="text-xs text-muted">{{ r.message }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="problems.length" class="im-note danger mt-2">
        <div v-for="p in problems" :key="p" class="issue">{{ p }}</div>
      </div>

      <!-- Empty Storebuilder Websites means nothing is read and nothing is ever dropped. That is
           a quiet way to lose every legacy product, so it is said first and plainly. -->
      <div v-if="!websitesConfigured" class="im-note danger mt-2">
        <b>No Storebuilder website is set up.</b>
        Add the price lists Item Merge may read under <b>Storebuilder Websites</b> on
        Item Merge Settings. Until then nothing is read from Storebuilder, and no legacy
        product is dropped after a merge.
      </div>

      <div v-else-if="!anyConfig" class="im-note warn mt-2">
        No <b>Product Detail APIs</b> are configured. Add one row per website under
        Storebuilder Sync Settings before this screen can ask anything.
      </div>
      <div v-else-if="attentionCount" class="im-note warn mt-2">
        <b>{{ attentionCount }} row(s) still need attention.</b>
        Fix them in Storebuilder and check again, or remove the price list with ✕ if the template
        isn't sold on that website after all.
      </div>
      <!-- Nothing needing attention is not the same as everything verified. A selection that is
           only "nothing to check" has no External ID and no slug behind it, and saying it was all
           fine is how a stranded product gets past this screen. -->
      <div v-else-if="!verifiedCount" class="im-note warn mt-2">
        <b>Nothing was read from Storebuilder.</b>
        None of these templates has a product on Storebuilder - either it is not priced above zero on
        a website, or no product carries its External ID or slug - so there is nothing to drop after
        the merge. If that is wrong, add the Item Price or fix the product in Storebuilder first.
      </div>
      <div v-else class="im-note ok mt-2">
        {{ verifiedCount }} website product(s) recorded<span v-if="skippedCount">; {{ skippedCount }} row(s) had nothing to check</span>.
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { itemMergeApi } from './api.js'
import { alertOk, confirmAction, pillClass } from './utils.js'

const props = defineProps({ templates: { type: Array, default: () => [] } })
const emit = defineEmits(['update:ok', 'update:live'])

const rows = ref([])
const problems = ref([])
const anyConfig = ref(true)
const websitesConfigured = ref(true)
const loading = ref(false)
const busy = ref(false)

const LABELS = {
  full: 'Item has full information',
  stale: 'Checked a while ago',
  zeroprice: 'Priced at 0',
  noexternalid: 'No External ID',
  wrongexternalid: 'Wrong External ID',
  noslug: 'The slug is not found',
  notconfigured: 'No API for this website',
  missing: "Can't find the item",
  nowebsite: 'Not on any website',
  notonsb: 'Not on Storebuilder',
  error: 'The website could not answer',
  unchecked: 'Not checked',
}
const label = (status) => LABELS[status] || 'Not checked'

// Three states, not two. `full` is an answer from Storebuilder; `nowebsite` and `zeroprice` are
// the absence of a question; everything else needs attention. Counting the middle group as
// verified is what made an unpriced selection report green.
// `notonsb` was asked about and has nothing on Storebuilder - no product to drop, so not a problem.
const NOTHING_TO_CHECK = ['nowebsite', 'zeroprice', 'notonsb']
const verifiedCount = computed(() => rows.value.filter((r) => r.status === 'full').length)
const skippedCount = computed(() => rows.value.filter((r) => NOTHING_TO_CHECK.includes(r.status)).length)
const attentionCount = computed(() => rows.value.length - verifiedCount.value - skippedCount.value)
const ok = computed(() => rows.value.length > 0 && attentionCount.value === 0)
watch(ok, (v) => emit('update:ok', v), { immediate: true })
// The templates Storebuilder has a product for (External ID and slug). Only one of these may
// survive a merge - the others' products are dropped afterwards.
const live = computed(() => [...new Set(rows.value
  .filter((r) => r.status === 'full' && r.external_id && (r.slug || '').trim())
  .map((r) => r.template))])
watch(live, (v) => emit('update:live', v), { immediate: true })

// What a live check answered, kept by row so a reload - after a ✕, say - does not throw the
// check away and make the operator run it again.
const checked = ref({})
const rowKey = (r) => r.template + '|' + (r.price_list || '-')
const merge = (list) => list.map((r) => ({ ...r, ...(checked.value[rowKey(r)] || {}) }))

// The plan is a read - it never calls the websites - so it can follow the tick boxes. The live
// check is a button, because it is N templates x M sites of real HTTP.
let seq = 0
async function load() {
  if (!props.templates.length) { rows.value = []; return }
  const mine = ++seq
  loading.value = true
  try {
    const res = await itemMergeApi.templateWebsitePlan(props.templates)
    if (mine !== seq) return
    rows.value = merge(res.rows || [])
    anyConfig.value = !!res.any_config
    websitesConfigured.value = !!res.websites_configured
  } catch (e) {
    // Frappe has shown the reason
    if (mine === seq) rows.value = []
  } finally {
    if (mine === seq) loading.value = false
  }
}
watch(() => props.templates, load, { deep: true, immediate: true })

async function check() {
  const mine = ++seq
  busy.value = true
  try {
    const res = await itemMergeApi.lookupTemplateProducts(props.templates)
    if (mine !== seq) return
    websitesConfigured.value = !!res.websites_configured
    const fresh = res.rows || []
    const keep = {}
    fresh.forEach((r) => { keep[rowKey(r)] = r })
    checked.value = keep
    rows.value = fresh
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    if (mine === seq) busy.value = false
  }
}

async function removePriceList(row) {
  const n = row.price_rows || 0
  const confirmed = await confirmAction({
    title: 'Remove price list',
    message: `Remove ${row.price_list} from ${row.template}?\n\n` +
      `This deletes ${n} Item Price record(s) - the template and its variants - and the websites ` +
      `are told about it. It cannot be undone.`,
    label: 'Delete price list',
    danger: true,
  })
  if (!confirmed) return
  busy.value = true
  try {
    const res = await itemMergeApi.removeTemplatePriceList(row.template, row.price_list)
    alertOk(`${res.deleted} Item Price row(s) removed from ${row.price_list}`)
    delete checked.value[rowKey(row)]
    await load()
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

// Called by StepTemplates before it leaves the step - and, when templates are being combined,
// before consolidate_templates deletes the sources this has just read.
async function save(survivor) {
  const res = await itemMergeApi.saveTemplateProducts(survivor, rows.value)
  if (res.problems && res.problems.length) {
    problems.value = res.problems
    throw new Error(res.problems[0])
  }
  problems.value = []
  return res
}

defineExpose({ refresh: load, save, rows })
</script>
