<template>
  <div class="space-y-4">
    <!-- locked template header -->
    <div class="im-locked">
      <span class="im-label">Template</span>
      <TemplateCode :template="template" :item-name="tmpl ? tmpl.item_name : ''" :loading="loading"
                    :code-locked-reason="newCount ? 'New variants already exist under this template - change its code on the Item codes screen' : ''"
                    @renamed="(code) => code === template ? load() : emit('renamed', code)" />
      <button class="btn btn-default btn-xs ml-auto" @click="emit('back')">Change template</button>
    </div>

    <div class="im-split">
      <!-- the family as it is now -->
      <section class="im-card">
        <div class="flex items-center flex-wrap gap-2">
          <h3 class="im-card-title">Variants under this template</h3>
          <span class="ml-auto" :class="pillClass('old')">{{ oldCount }} old</span>
          <span :class="pillClass('ready')">{{ newCount }} with attributes</span>
        </div>
        <div v-if="loading" class="im-empty"><span class="animate-spin">⟳</span> Loading variants…</div>
        <div v-else-if="!variants.length" class="im-empty">This template has no variants.</div>
        <div v-else class="im-table-wrap mt-3" style="max-height: 420px; overflow-y: auto">
          <table class="im-table">
            <thead>
              <tr>
                <th><button class="im-sort" :class="{ active: sortKey === 'item_code' }" @click="sortBy('item_code')">Item code <span class="arrow">{{ arrow('item_code') }}</span></button></th>
                <th><button class="im-sort" :class="{ active: sortKey === 'item_name' }" @click="sortBy('item_name')">Item name <span class="arrow">{{ arrow('item_name') }}</span></button></th>
                <th><button class="im-sort" :class="{ active: sortKey === 'retail_sku' }" @click="sortBy('retail_sku')">Retail SKU <span class="arrow">{{ arrow('retail_sku') }}</span></button></th>
                <th class="r">Qty</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in sortedVariants" :key="v.item_code">
                <td class="font-mono whitespace-nowrap">
                  <a class="im-link" :href="itemUrl(v.item_code)" target="_blank" rel="noopener">{{ v.item_code }}</a>
                </td>
                <td>{{ v.item_name }}</td>
                <td class="font-mono whitespace-nowrap text-muted">{{ v.retail_sku }}</td>
                <td class="r tabular-nums">{{ num(v.qty) }}</td>
                <td class="whitespace-nowrap">
                  <span :class="pillClass(v.is_new ? 'ready' : 'old')">{{ v.is_new ? 'new' : 'old' }}</span>
                  <span v-if="unreadableCodes.has(v.item_code)" class="ml-2" :class="pillClass('fix')"
                        title="Its name has no value of the chosen attributes - add its combination with Add in bulk">not read</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- attributes -->
      <aside class="im-card space-y-3">
        <div class="im-label">Item attributes for the new variants</div>
        <div>
          <label class="control-label-sm block">Attribute 1 <span class="text-faint" style="font-weight: 400">(required)</span></label>
          <div ref="attr1El" class="im-link-control"></div>
        </div>
        <div>
          <label class="control-label-sm block">Attribute 2 <span class="text-faint" style="font-weight: 400">(optional)</span></label>
          <div ref="attr2El" class="im-link-control"></div>
        </div>
        <div class="im-note info text-xs">
          <b>Two attributes</b> make combined variants only - e.g. <i>Black - XSmall</i>.<br>
          <b>One attribute</b> makes single-value variants - e.g. <i>Black</i>.
        </div>
        <button class="btn btn-default btn-sm w-full" :disabled="!attr1 || suggesting" @click="suggest">
          {{ suggesting ? 'Suggesting…' : 'Suggest combinations' }}
        </button>
        <button v-if="newCount" class="btn btn-primary btn-sm w-full" @click="emit('next')">Continue to alignment →</button>
      </aside>
    </div>

    <!-- combinations grid -->
    <section v-if="suggestion" class="im-card">
      <div class="flex items-center flex-wrap gap-2">
        <h3 class="im-card-title">New variants to create</h3>
        <span class="ml-auto text-sm text-muted">
          {{ toCreate.length }} to create · {{ existingCount }} already exist · {{ rows.length }} in the grid
        </span>
      </div>
      <p class="im-lede">
        Read from the old variants' names; combinations with stock history start ticked. Add more with <b>Add in bulk</b>,
        edit any code or name, and remove rows you don't want.
      </p>

      <div class="flex items-center flex-wrap gap-2 mb-3">
        <label class="im-label" for="im-style-name">Product name</label>
        <input id="im-style-name" v-model="styleName" class="form-control input-sm" style="flex: 1; min-width: 260px" />
      </div>

      <div v-if="suggestion.unreadable.length" class="im-note warn mb-3">
        {{ suggestion.unreadable.length }} old variant(s) don't name a {{ attributes.join(' / ') }} value
        (marked <b>not read</b> above):
        <span class="font-mono">{{ suggestion.unreadable.slice(0, 4).map((u) => u.item_code).join(', ') }}{{ suggestion.unreadable.length > 4 ? '…' : '' }}</span>.
        Add their combinations with <b>Add in bulk</b>.
      </div>

      <div class="flex items-center flex-wrap gap-2 mb-2">
        <button class="btn btn-default btn-sm" @click="openBulk">+ Add in bulk</button>
        <button class="btn btn-default btn-xs" @click="tickAll(true)">Tick all</button>
        <button class="btn btn-default btn-xs" @click="tickAll(false)">Untick all</button>
        <button class="btn btn-default btn-xs text-danger" :disabled="!rows.some((r) => !r.tick && !r.existing)" @click="removeUnticked">
          ✕ Remove unticked rows
        </button>
      </div>

      <div class="im-table-wrap">
        <table class="im-table edit">
          <thead>
            <tr>
              <th style="width: 36px"></th>
              <th style="width: 24%">New item code</th>
              <th>New item name</th>
              <th>From old variant(s)</th>
              <th class="r">Qty</th>
              <th>Status</th>
              <th style="width: 36px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!rows.length"><td colspan="7" class="im-empty">No combinations - use Add in bulk.</td></tr>
            <tr v-for="r in rows" :key="r.key">
              <td>
                <input type="checkbox" v-model="r.tick" :disabled="!!r.existing" :aria-label="'Create ' + r.item_name" />
              </td>
              <td>
                <div v-if="r.existing" class="font-mono">
                  <a class="im-link" :href="itemUrl(r.existing)" target="_blank" rel="noopener">{{ r.existing }}</a>
                </div>
                <div v-else class="im-edit font-mono" :class="{ changed: r.code_edited, invalid: codeInvalid(r) }">
                  <input :value="r.item_code" @input="editCode(r, $event.target.value)" :aria-label="'Item code for ' + r.item_name" />
                  <button v-if="r.code_edited" title="Back to the generated code" aria-label="Reset item code" @click="resetCode(r)">↺</button>
                </div>
              </td>
              <td>
                <div v-if="r.existing">{{ r.item_name }}</div>
                <div v-else class="im-edit" :class="{ changed: r.name_edited, invalid: problemOf(r) === 'Item name is empty' }">
                  <input :value="r.item_name" @input="editName(r, $event.target.value)" :aria-label="'Item name for ' + r.key" />
                  <button v-if="r.name_edited" title="Back to product name + values" aria-label="Reset item name" @click="resetName(r)">↺</button>
                </div>
              </td>
              <td class="font-mono text-muted text-xs">{{ r.from_old.join(', ') || '-' }}</td>
              <td class="r tabular-nums">{{ num(r.qty) }}</td>
              <td class="whitespace-nowrap">
                <span v-if="createdStatus(r.item_code) && createdStatus(r.item_code).status === 'failed'" :class="pillClass('failed')"
                      :title="createdStatus(r.item_code).error">failed</span>
                <span v-else-if="r.existing" :class="pillClass('exists')">exists</span>
                <span v-else-if="problemOf(r)" :class="pillClass('blocked')" :title="problemOf(r)">{{ problemOf(r) }}</span>
                <span v-else-if="r.abbr_issue.length && !r.code_edited" :class="pillClass('fix')" :title="r.abbr_issue.join(' · ')">check code</span>
                <span v-else-if="r.manual" :class="pillClass('added')">added</span>
                <span v-else-if="!r.suggested" :class="pillClass('empty')">no stock history</span>
                <span v-else :class="pillClass('queued')">to create</span>
              </td>
              <td>
                <button v-if="!r.existing" class="im-row-remove" title="Remove from the grid" :aria-label="'Remove ' + r.item_name" @click="removeRow(r)">✕</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center flex-wrap gap-2 mt-3">
        <span v-if="problems.length" class="text-sm text-danger">{{ problems.length }} ticked row(s) need fixing before creating</span>
        <button class="btn btn-primary btn-sm ml-auto" :disabled="!toCreate.length || problems.length > 0 || creating" @click="create">
          {{ creating ? 'Creating…' : 'Create ' + toCreate.length + ' variant(s)' }}
        </button>
      </div>
    </section>

    <!-- add combinations in bulk -->
    <div v-if="bulkOpen" class="im-modal-backdrop" @click.self="bulkOpen = false">
      <div class="im-modal" role="dialog" aria-modal="true" aria-labelledby="im-bulk-title">
        <div class="im-modal-header">
          <h4 id="im-bulk-title">Add combinations in bulk</h4>
          <button class="im-row-remove" aria-label="Close" @click="bulkOpen = false">✕</button>
        </div>
        <div class="im-modal-body">
          <p class="text-muted mt-0">
            Tick every {{ attributes.join(' and every ') }} you want. Each combination not already in the grid is added;
            remove any you don't need afterwards.
          </p>
          <div class="im-bulk-grid" :class="{ one: !attributes[1] }">
            <div v-for="(a, i) in attributes" :key="a" class="space-y-2 min-w-0">
              <div class="flex items-center flex-wrap gap-2">
                <span class="im-label">{{ a }}</span>
                <span class="ml-auto text-xs text-muted">{{ bulkSel[i].length }} selected</span>
                <button class="btn btn-default btn-xs" :disabled="!shownOptions(i).length" @click="selectShown(i)">Select shown</button>
                <button class="btn btn-default btn-xs" :disabled="!bulkSel[i].length" @click="bulkSel[i] = []">Clear</button>
              </div>
              <input :ref="(el) => { if (i === 0) bulkSearchEl = el }" v-model="bulkQ[i]" class="form-control input-sm"
                     :placeholder="'Search ' + a" :aria-label="'Search ' + a" />
              <div class="im-pick-list">
                <div v-if="!shownOptions(i).length" class="im-empty text-xs">No values match.</div>
                <label v-for="o in shownOptions(i)" :key="o.value" :class="{ on: bulkSets[i].has(o.value) }">
                  <input type="checkbox" :checked="bulkSets[i].has(o.value)" @change="toggleBulk(i, o.value)" />
                  <span class="flex-1">{{ o.value }}</span>
                  <span v-if="o.bad" :class="pillClass('fix')"
                        :title="'Abbreviation ' + (o.abbr || '(blank)') + ' has characters that can\'t go in a code - check the generated code'">abbr</span>
                </label>
              </div>
            </div>
          </div>
        </div>
        <div class="im-modal-footer flex-wrap">
          <span class="text-muted">{{ bulkCombos.length }} combination(s) · <b>{{ bulkNew.length }}</b> new to the grid</span>
          <label class="flex items-center gap-2 ml-2 cursor-pointer">
            <input type="checkbox" v-model="bulkTick" /> tick them for creation
          </label>
          <button class="btn btn-default btn-sm ml-auto" @click="bulkOpen = false">Cancel</button>
          <button class="btn btn-primary btn-sm" :disabled="!bulkNew.length" @click="addBulk">
            + Add {{ bulkNew.length }} to the grid
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { itemMergeApi } from './api.js'
import TemplateCode from './TemplateCode.vue'
import { BAD_CODE, pillClass, alertOk, alertWarn, confirmAction, makeLink, itemUrl, num } from './utils.js'

const props = defineProps({
  template: { type: String, required: true },
})
const emit = defineEmits(['next', 'back', 'renamed'])

const VARIANT_NUMBER = 'Variant Number'
// letters and digits only - 'Coyo Brn' -> 'CoyoBrn', '-001' -> '001' (same rule as the server)
const codePart = (abbr, value) => (abbr || '').replace(/[^A-Za-z0-9]/g, '') || (value || '').replace(/[^A-Za-z0-9]/g, '')
const abbrUsable = (abbr) => /^[A-Za-z0-9]+$/.test((abbr || '').replace(/^-+|-+$/g, ''))

const loading = ref(true)
const tmpl = ref(null)
const variants = ref([])
const attr1 = ref(null)
const attr2 = ref(null)
const suggestion = ref(null)
const rows = ref([])
const styleName = ref('')
const suggesting = ref(false)
const creating = ref(false)
const created = ref(null)

const oldCount = computed(() => variants.value.filter((v) => !v.is_new).length)
const newCount = computed(() => variants.value.filter((v) => v.is_new).length)
const attributes = computed(() => [attr1.value, attr2.value].filter(Boolean))
const existingCount = computed(() => rows.value.filter((r) => r.existing).length)
const unreadableCodes = computed(() => new Set((suggestion.value?.unreadable || []).map((u) => u.item_code)))

// ---- variants table ----
const sortKey = ref('item_code')
const sortDir = ref(1)
const sortedVariants = computed(() => [...variants.value].sort((a, b) =>
  String(a[sortKey.value] ?? '').localeCompare(String(b[sortKey.value] ?? ''), undefined, { numeric: true }) * sortDir.value))
const sortBy = (k) => { sortDir.value = sortKey.value === k ? -sortDir.value : 1; sortKey.value = k }
const arrow = (k) => (sortKey.value === k ? (sortDir.value > 0 ? '▲' : '▼') : '⇅')

async function load() {
  loading.value = true
  try {
    const v = await itemMergeApi.getVariants(props.template)
    tmpl.value = v.template
    variants.value = v.variants
    // preselect the attributes the template already has (never Variant Number)
    const existing = (v.template.attributes || []).filter((x) => x !== VARIANT_NUMBER)
    if (!attr1.value && existing[0]) { attr1.value = existing[0]; link1?.set(existing[0]) }
    if (!attr2.value && existing[1]) { attr2.value = existing[1]; link2?.set(existing[1]) }
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    loading.value = false
  }
}

// ---- attribute pickers (native Frappe Link controls) ----
const attr1El = ref(null)
const attr2El = ref(null)
let link1 = null
let link2 = null
// get_query reads these objects on every search, so attribute 2 can exclude the current attribute 1
const filters1 = { numeric_values: 0, name: ['!=', VARIANT_NUMBER] }
const filters2 = { numeric_values: 0, name: ['not in', [VARIANT_NUMBER]] }

function pick(which, value) {
  const v = value || null
  const link = which === 1 ? link1 : link2
  const target = which === 1 ? attr1 : attr2
  if (v === VARIANT_NUMBER) {
    alertWarn('Variant Number is what this replaces - pick a real attribute')
    link.set('')
    target.value = null
    return
  }
  if (v && which === 2 && v === attr1.value) {
    alertWarn('Attribute 2 must differ from attribute 1')
    link.set('')
    target.value = null
    return
  }
  target.value = v
  if (which === 1 && v && v === attr2.value) {
    alertWarn(`${v} is now attribute 1 - attribute 2 cleared`)
    link2?.set('')
    attr2.value = null
  }
}

function buildLinks() {
  if (attr1El.value) {
    link1 = makeLink(attr1El.value, { options: 'Item Attribute', filters: filters1, placeholder: 'Attribute 1 (required)',
      value: attr1.value, onPick: (v) => pick(1, v) })
  }
  if (attr2El.value) {
    link2 = makeLink(attr2El.value, { options: 'Item Attribute', filters: filters2, placeholder: 'Attribute 2 (optional)',
      value: attr2.value, onPick: (v) => pick(2, v) })
  }
  syncAttr2()
}

function syncAttr2() {
  filters2.name = ['not in', [VARIANT_NUMBER, attr1.value].filter(Boolean)]
  link2?.control.$input.prop('disabled', !attr1.value)
}

watch(attr1, (v) => {
  if (!v && attr2.value) { attr2.value = null; link2?.set('') }
  syncAttr2()
})
// a different attribute means a different grid
watch([attr1, attr2], () => { suggestion.value = null; rows.value = []; created.value = null })

onMounted(() => {
  nextTick(buildLinks)
  load()
})

// ---- grid rows ----
const keyOf = (values) => JSON.stringify(attributes.value.map((a) => values[a]))
const nameFor = (values) => [styleName.value, ...attributes.value.map((a) => values[a])].join(' - ')
const abbrOf = (a, v) => suggestion.value?.values[a]?.find((x) => x.value === v)?.abbr
const codeFor = (values) => [props.template, ...attributes.value.map((a) => codePart(abbrOf(a, values[a]), values[a]))].join('-')
const abbrIssueFor = (values) => attributes.value
  .filter((a) => !abbrUsable(abbrOf(a, values[a])))
  .map((a) => `${a} = ${values[a]} has abbreviation '${abbrOf(a, values[a]) || ''}' - the code uses '${codePart(abbrOf(a, values[a]), values[a])}'; check it`)

function makeRow(values, extra = {}) {
  return {
    key: keyOf(values), values, item_code: codeFor(values), item_name: nameFor(values), code_edited: false,
    name_edited: false, from_old: [], existing: null, qty: 0, ledger_count: 0, suggested: false, manual: true,
    abbr_issue: abbrIssueFor(values), tick: true, ...extra,
  }
}

const order = (values) => attributes.value.map((a) => (suggestion.value?.values[a] || []).findIndex((x) => x.value === values[a]))
function sortRows() {
  rows.value = [...rows.value].sort((x, y) => {
    const a = order(x.values)
    const b = order(y.values)
    return (a[0] - b[0]) || ((a[1] ?? 0) - (b[1] ?? 0))
  })
}

async function suggest() {
  suggesting.value = true
  try {
    const s = await itemMergeApi.suggestCombinations(props.template, attributes.value)
    suggestion.value = s
    styleName.value = s.style_name
    rows.value = s.combinations.map((c) => makeRow(c.values, {
      item_code: c.existing || c.item_code || c.suggested_code, item_name: c.item_name, from_old: c.from_old || [],
      existing: c.existing, qty: c.qty, ledger_count: c.ledger_count, suggested: c.suggested, manual: false,
      tick: !!c.suggested && !c.existing,
    }))
    sortRows()
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    suggesting.value = false
  }
}

watch(styleName, () => rows.value.forEach((r) => { if (!r.name_edited && !r.existing) r.item_name = nameFor(r.values) }))

const editCode = (r, v) => { r.item_code = v; r.code_edited = true }
const editName = (r, v) => { r.item_name = v; r.name_edited = true }
const resetCode = (r) => { r.item_code = codeFor(r.values); r.code_edited = false }
const resetName = (r) => { r.item_name = nameFor(r.values); r.name_edited = false }
const removeRow = (r) => { rows.value = rows.value.filter((x) => x !== r) }
const removeUnticked = () => { rows.value = rows.value.filter((r) => r.tick || r.existing) }
const tickAll = (on) => rows.value.forEach((r) => { if (!r.existing) r.tick = on })

const toCreate = computed(() => rows.value.filter((r) => r.tick && !r.existing))

// one problem (or '') per row, worked out once per change
const rowProblems = computed(() => {
  const counts = {}
  toCreate.value.forEach((r) => { const c = (r.item_code || '').trim(); counts[c] = (counts[c] || 0) + 1 })
  const have = new Set(variants.value.map((v) => v.item_code))
  const out = new Map()
  rows.value.forEach((r) => {
    let p = ''
    if (!r.existing && r.tick) {
      const code = (r.item_code || '').trim()
      if (!code) p = 'Item code is empty'
      else if (BAD_CODE.test(code)) p = "Item code can't contain spaces or / \\ % # ?"
      else if (counts[code] > 1) p = 'Same item code as another row'
      else if (have.has(code)) p = `${code} already exists under this template`
      else if (!(r.item_name || '').trim()) p = 'Item name is empty'
    }
    out.set(r, p)
  })
  return out
})
const problemOf = (r) => rowProblems.value.get(r) || ''
const codeInvalid = (r) => {
  const p = problemOf(r)
  return p.startsWith('Item code') || p.startsWith('Same') || p.includes('already exists')
}
const problems = computed(() => toCreate.value.map(problemOf).filter(Boolean))

// ---- bulk add modal ----
const bulkOpen = ref(false)
const bulkSel = ref([[], []])
const bulkQ = ref(['', ''])
const bulkTick = ref(true)
const bulkSearchEl = ref(null)

const bulkSets = computed(() => bulkSel.value.map((s) => new Set(s)))
const optionsFor = (a) => (suggestion.value?.values[a] || []).map((v) => ({ value: v.value, abbr: v.abbr, bad: !abbrUsable(v.abbr) }))
const shownOptions = (i) => {
  const q = (bulkQ.value[i] || '').trim().toLowerCase()
  const opts = optionsFor(attributes.value[i])
  return q ? opts.filter((o) => String(o.value).toLowerCase().includes(q)) : opts
}
function toggleBulk(i, value) {
  const sel = bulkSel.value[i]
  bulkSel.value[i] = sel.includes(value) ? sel.filter((x) => x !== value) : [...sel, value]
}
function selectShown(i) {
  const have = bulkSets.value[i]
  bulkSel.value[i] = [...bulkSel.value[i], ...shownOptions(i).map((o) => o.value).filter((v) => !have.has(v))]
}

async function openBulk() {
  // start from what the old variants already use, so the usual case is one click
  const used = (i) => [...new Set(rows.value.map((r) => r.values[attributes.value[i]]).filter(Boolean))]
  bulkSel.value = [used(0), attributes.value[1] ? used(1) : []]
  bulkQ.value = ['', '']
  bulkTick.value = true
  bulkOpen.value = true
  await nextTick()
  bulkSearchEl.value?.focus()
}

const bulkCombos = computed(() => {
  const [a1, a2] = attributes.value
  const [selA, selB] = bulkSel.value
  if (!a1 || !selA.length || (a2 && !selB.length)) return []
  return a2 ? selA.flatMap((x) => selB.map((y) => ({ [a1]: x, [a2]: y }))) : selA.map((x) => ({ [a1]: x }))
})
const bulkNew = computed(() => {
  const have = new Set(rows.value.map((r) => r.key))
  return bulkCombos.value.filter((v) => !have.has(keyOf(v)))
})

function addBulk() {
  const added = bulkNew.value.length
  const already = bulkCombos.value.length - added
  rows.value = [...rows.value, ...bulkNew.value.map((v) => makeRow(v, { tick: bulkTick.value }))]
  sortRows()
  alertOk(`${added} combination(s) added` + (already ? ` · ${already} were already in the grid` : ''))
  bulkOpen.value = false
}

const onKey = (e) => { if (e.key === 'Escape' && bulkOpen.value) bulkOpen.value = false }
watch(bulkOpen, (open) => {
  if (open) document.addEventListener('keydown', onKey)
  else document.removeEventListener('keydown', onKey)
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

// ---- create ----
async function create() {
  const n = toCreate.value.length
  const message = `Create ${n} new variant(s) under ${props.template} with ${attributes.value.join(' + ')}.\n` +
    (tmpl.value?.attributes.includes(attributes.value[0]) ? '' : 'These attributes are added to the template.\n') +
    'This creates the new Items now.'
  const ok = await confirmAction({ title: 'Create variants?', message, label: `Create ${n}` })
  if (!ok) return
  creating.value = true
  try {
    const res = await itemMergeApi.createVariants(props.template, attributes.value,
      toCreate.value.map((r) => ({ values: r.values, item_code: r.item_code.trim(), item_name: r.item_name.trim() })), styleName.value)
    created.value = res.variants
    // rows that now exist stop counting as "to create", so a retry only sends the ones that failed
    const made = new Set(res.variants.filter((v) => ['created', 'exists'].includes(v.status)).map((v) => v.item_code))
    rows.value.forEach((r) => { if (!r.existing && made.has((r.item_code || '').trim())) { r.existing = r.item_code.trim(); r.tick = false } })
    const done = res.variants.filter((v) => v.status === 'created').length
    const failed = res.variants.filter((v) => v.status === 'failed').length
    if (failed) alertWarn(`${done} variant(s) created · ${failed} failed - see the list`)
    else alertOk(`${done} variant(s) created under ${props.template}`)
    await load()
    if (!failed) await suggest()
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    creating.value = false
  }
}

const createdStatus = (code) => created.value?.find((v) => v.item_code === code)

async function refresh() {
  await load()
  if (suggestion.value) await suggest()
}

defineExpose({ refresh })
</script>
