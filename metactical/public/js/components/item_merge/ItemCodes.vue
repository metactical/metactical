<template>
  <div class="space-y-4">
    <section class="im-card">
      <h3 class="im-card-title">Item codes, names and retail SKUs</h3>
      <p class="im-lede">Edit a template's variants at any time, including after a merge. Changes are saved as a job, one item at a time.</p>
      <form class="flex items-center flex-wrap gap-2" @submit.prevent="loadPicked">
        <div ref="pickerEl" class="im-link-control" style="flex: 1; min-width: 220px; max-width: 420px"></div>
        <button type="submit" class="btn btn-primary btn-sm" :disabled="loading">{{ loading ? 'Loading…' : 'Load variants →' }}</button>
      </form>
    </section>

    <div v-if="!tmpl && !loading" class="im-empty">Pick a template to edit its variants.</div>
    <div v-else-if="!tmpl" class="im-empty"><span class="animate-spin">⟳</span> Loading variants…</div>

    <template v-if="tmpl">
      <section class="im-card">
        <div class="im-locked mb-3">
          <span class="im-label" style="color: inherit">Template</span>
          <TemplateCode :template="tmpl.item_code" :item-name="tmpl.item_name || ''" :loading="loading || saving"
                        :locked-reason="changes.length ? 'Save or undo the variant edits first' : ''"
                        @renamed="(code) => load(code)" />
        </div>

        <div class="flex items-center flex-wrap gap-2 mb-3">
          <button class="btn btn-default btn-sm" :disabled="!variants.length" @click="codesToSku">
            Set every item code to its retail SKU
          </button>
          <button class="btn btn-default btn-sm" :disabled="!dashedCount" @click="collapseDashes"
                  title="create_variant emits doubled dashes while Variant Number is still on the template; once the old variants are gone the codes can be cleaned up">
            Collapse doubled dashes{{ dashedCount ? ' (' + dashedCount + ')' : '' }}
          </button>
          <button class="btn btn-default btn-sm" :disabled="!changes.length" @click="resetAll">↺ Undo all edits</button>
          <span class="ml-auto text-sm text-muted tabular-nums">{{ changes.length }} changed · {{ renameCount }} rename(s)</span>
          <button class="btn btn-danger btn-sm" :disabled="!changes.length || problems.length > 0 || saving" @click="save">
            {{ saving ? 'Saving…' : 'Save ' + changes.length + ' change(s)' }}
          </button>
        </div>

        <div v-if="!variants.length" class="im-empty">This template has no variants.</div>
        <div v-else class="im-table-wrap">
          <table class="im-table edit">
            <thead>
              <tr>
                <th>Item code now</th><th style="width: 22%">Item code</th><th style="width: 30%">Item name</th>
                <th style="width: 18%">Retail SKU</th><th class="r">Qty</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in variants" :key="v.item_code" :class="{ bad: rowProblems(v).length }">
                <td class="font-mono whitespace-nowrap">
                  <a class="im-link" :href="itemUrl(v.item_code)" target="_blank" rel="noopener">{{ v.item_code }}</a>
                  <div v-if="!v.is_new" class="text-xs text-faint">Variant Number</div>
                </td>
                <td>
                  <div class="im-edit font-mono"
                       :class="{ changed: changed(v, 'new_code'), invalid: rowProblems(v).some((p) => p.startsWith('item code') || p.includes('already another variant')) }">
                    <input :value="val(v, 'new_code')" @input="set(v, 'new_code', $event.target.value)" :aria-label="'New item code for ' + v.item_code" />
                    <button v-if="val(v, 'retail_sku').trim() && val(v, 'new_code') !== val(v, 'retail_sku').trim()" type="button"
                            title="Use the retail SKU" aria-label="Use the retail SKU as item code"
                            @click="set(v, 'new_code', val(v, 'retail_sku').trim())">⧉</button>
                    <button v-if="changed(v, 'new_code')" type="button" title="Undo" aria-label="Undo item code" @click="reset(v, 'new_code')">↺</button>
                  </div>
                </td>
                <td>
                  <div class="im-edit" :class="{ changed: changed(v, 'item_name'), invalid: !val(v, 'item_name').trim() }">
                    <input :value="val(v, 'item_name')" @input="set(v, 'item_name', $event.target.value)" :aria-label="'Item name for ' + v.item_code" />
                    <button v-if="changed(v, 'item_name')" type="button" title="Undo" aria-label="Undo item name" @click="reset(v, 'item_name')">↺</button>
                  </div>
                </td>
                <td>
                  <div class="im-edit font-mono" :class="{ changed: changed(v, 'retail_sku'), invalid: !val(v, 'retail_sku').trim() }">
                    <input :value="val(v, 'retail_sku')" @input="set(v, 'retail_sku', $event.target.value)" :aria-label="'Retail SKU for ' + v.item_code" />
                    <button v-if="changed(v, 'retail_sku')" type="button" title="Undo" aria-label="Undo retail SKU" @click="reset(v, 'retail_sku')">↺</button>
                  </div>
                </td>
                <td class="r tabular-nums">{{ num(v.qty) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="problems.length" class="im-note danger mt-3">
          <span v-for="p in problems" :key="p" class="issue">{{ p }}</span>
        </div>
      </section>

      <section class="im-card">
        <p class="text-xs text-muted mt-2 mb-0">Changing the template code changes what each site's External ID must be.</p>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import TemplateCode from './TemplateCode.vue'
import { itemMergeApi } from './api.js'
import { BAD_CODE, alertOk, confirmAction, itemUrl, makeLink, num } from './utils.js'

const props = defineProps({
  template: { type: String, default: '' },
})
const emit = defineEmits(['open', 'queued'])

const pickerEl = ref(null)
const loading = ref(false)
const saving = ref(false)
const tmpl = ref(null)
const variants = ref([])
const edits = ref({}) // item_code -> { new_code?, item_name?, retail_sku? } (only typed fields)
let picker = null

// ---------- loading ----------
let seq = 0
async function load(code) {
  const t = String(code || '').trim()
  if (!t) return
  const mine = ++seq
  loading.value = true
  try {
    const v = await itemMergeApi.getVariants(t)
    if (mine !== seq) return
    tmpl.value = v.template
    variants.value = v.variants || []
    edits.value = {}
    picker?.set(v.template.item_code)
    // the URL follows the template shown (the root re-renders with the same prop, so no second load)
    if (v.template.item_code !== props.template) emit('open', v.template.item_code)
  } catch (e) {
    // Frappe has shown the reason
    if (mine === seq) { tmpl.value = null; variants.value = []; edits.value = {} }
  } finally {
    if (mine === seq) loading.value = false
  }
}

async function dropEditsOk() {
  if (!changes.value.length) return true
  return confirmAction({
    title: 'Drop your edits?',
    message: `You have ${changes.value.length} unsaved change(s) under ${tmpl.value?.item_code}. They will be lost.`,
    label: 'Drop edits',
    danger: true,
  })
}

async function pick(code) {
  if (!code) return
  if (code !== tmpl.value?.item_code && !(await dropEditsOk())) {
    picker?.set(tmpl.value?.item_code || '')
    return
  }
  load(code)
}

function loadPicked() {
  const code = (picker?.control.get_value() || '').trim() || tmpl.value?.item_code || props.template
  if (code === tmpl.value?.item_code) return refresh()
  pick(code)
}

onMounted(() => {
  picker = makeLink(pickerEl.value, {
    options: 'Item',
    filters: { has_variants: 1 },
    placeholder: 'Select a template…',
    value: props.template,
    onPick: (v) => { if (v && v !== tmpl.value?.item_code) pick(v) },
  })
  if (props.template) load(props.template)
})
watch(() => props.template, (t) => { if (t && t !== tmpl.value?.item_code) load(t) })

async function refresh() {
  if (!tmpl.value) {
    const code = (picker?.control.get_value() || '').trim() || props.template
    if (code) load(code)
    return
  }
  if (!(await dropEditsOk())) return
  load(tmpl.value.item_code)
}

// ---------- edits ----------
const base = (v, field) => (field === 'new_code' ? v.item_code : (v[field] || ''))
const val = (v, field) => {
  const e = edits.value[v.item_code]
  return e && field in e ? e[field] : base(v, field)
}
function set(v, field, value) {
  edits.value = { ...edits.value, [v.item_code]: { ...(edits.value[v.item_code] || {}), [field]: value } }
}
function reset(v, field) {
  const e = { ...(edits.value[v.item_code] || {}) }
  delete e[field]
  edits.value = { ...edits.value, [v.item_code]: e }
}
const changed = (v, field) => field in (edits.value[v.item_code] || {}) && val(v, field).trim() !== base(v, field)

function codesToSku() {
  const next = { ...edits.value }
  variants.value.forEach((v) => {
    const sku = val(v, 'retail_sku').trim()
    if (sku) next[v.item_code] = { ...(next[v.item_code] || {}), new_code: sku }
  })
  edits.value = next
}

// RVX4183---001-0002 -> RVX4183-001-0002; same rule as pairing.clean_code on the server
const cleanCode = (code) => String(code || '').replace(/-{2,}/g, '-')
const dashedRows = computed(() => variants.value.filter((v) => {
  const code = val(v, 'new_code').trim()
  return code && cleanCode(code) !== code
}))
const dashedCount = computed(() => dashedRows.value.length)

function collapseDashes() {
  const next = { ...edits.value }
  const taken = new Set(variants.value.map((v) => val(v, 'new_code').trim()))
  dashedRows.value.forEach((v) => {
    const clean = cleanCode(val(v, 'new_code').trim())
    // a clean code already in use elsewhere in the family stays as it is, rather than colliding
    if (taken.has(clean)) return
    taken.add(clean)
    next[v.item_code] = { ...(next[v.item_code] || {}), new_code: clean }
  })
  edits.value = next
}
function resetAll() {
  edits.value = {}
}

// ---------- checks ----------
const rowProblems = (v) => {
  const out = []
  const code = val(v, 'new_code').trim()
  if (!code) out.push('item code is empty')
  else if (BAD_CODE.test(code)) out.push("item code can't contain spaces or / \\ % # ?")
  else if (code !== v.item_code && variants.value.some((o) => o.item_code === code && val(o, 'new_code').trim() === code)) {
    out.push(`${code} is already another variant`)
  }
  if (!val(v, 'item_name').trim()) out.push('item name is empty')
  if (!val(v, 'retail_sku').trim()) out.push('retail SKU is empty')
  return out
}

const problems = computed(() => {
  const out = []
  variants.value.forEach((v) => rowProblems(v).forEach((p) => out.push(`${v.item_code}: ${p}`)))
  const dupes = (field) => {
    const seen = {}
    variants.value.forEach((v) => {
      const x = val(v, field).trim()
      if (x) seen[x] = (seen[x] || 0) + 1
    })
    return Object.keys(seen).filter((k) => seen[k] > 1)
  }
  dupes('new_code').forEach((k) => out.push(`Item code ${k} is given to more than one variant`))
  dupes('retail_sku').forEach((k) => out.push(`Retail SKU ${k} is on more than one variant`))
  return out
})

const changes = computed(() => variants.value
  .filter((v) => ['new_code', 'item_name', 'retail_sku'].some((f) => changed(v, f)))
  .map((v) => ({
    item_code: v.item_code,
    ...(changed(v, 'new_code') ? { new_code: val(v, 'new_code').trim() } : {}),
    ...(changed(v, 'item_name') ? { item_name: val(v, 'item_name').trim() } : {}),
    ...(changed(v, 'retail_sku') ? { retail_sku: val(v, 'retail_sku').trim() } : {}),
  })))
const renameCount = computed(() => changes.value.filter((c) => c.new_code).length)

// ---------- save ----------
async function save() {
  if (!changes.value.length || problems.value.length) return
  const template = tmpl.value.item_code
  const lines = changes.value.map((c) => [
    c.new_code && `${c.item_code} → ${c.new_code}`,
    c.item_name && `${c.item_code} name → "${c.item_name}"`,
    c.retail_sku && `${c.item_code} SKU → ${c.retail_sku}`,
  ].filter(Boolean).join(', '))
  const ok = await confirmAction({
    title: 'Save item changes?',
    message: `Save ${changes.value.length} change(s) under ${template}:\n${lines.join('\n')}\n\n` +
      (renameCount.value ? 'ERPNext moves stock, prices and history with each renamed item, and records the rename in Item Merge History.\n' : '') +
      'This writes to ERPNext.',
    label: 'Save',
    danger: true,
  })
  if (!ok) return
  saving.value = true
  try {
    const res = await itemMergeApi.queueItemChanges(template, changes.value)
    alertOk(`Item changes queued as ${res.job}`)
    emit('queued', res.job)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    saving.value = false
  }
}

defineExpose({ refresh })
</script>
