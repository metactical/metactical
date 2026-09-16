<template>
  <div class="space-y-4">
    <!-- the template this screen is locked to -->
    <div class="im-locked">
      <span class="im-label">Template</span>
      <span class="im-code">{{ template }}</span>
      <a v-if="tmpl" class="im-link" :href="itemUrl(template)" target="_blank" rel="noopener">{{ tmpl.item_name }}</a>
      <button class="btn btn-default btn-xs ml-auto" @click="emit('back')">Back to variants</button>
    </div>

    <!-- the aligner -->
    <section class="im-card">
      <div class="flex items-center flex-wrap gap-2">
        <h3 class="im-card-title">Line up OLD and NEW</h3>
        <div class="flex flex-wrap gap-1 ml-auto">
          <span :class="pillClass('ready')">{{ counts.ready }} ready</span>
          <span v-if="counts.fix" :class="pillClass('fix')">{{ counts.fix }} need settings fixed</span>
          <span v-if="counts.blocked" :class="pillClass('blocked')">{{ counts.blocked }} blocked</span>
          <span v-if="counts.leftover" :class="pillClass('leftover')">{{ counts.leftover }} leftover</span>
          <span v-if="counts.unused" :class="pillClass('unused')">{{ counts.unused }} new with no old</span>
          <span v-if="mismatches" :class="pillClass('warn')">{{ mismatches }} name(s) differ</span>
        </div>
      </div>
      <p class="im-lede">
        Each row merges the OLD variant on the left into the NEW variant on the right. They start auto-aligned by colour and size;
        drag a row by its handle, or use the arrows, to line up anything that's wrong. Sorting a column reorders that side only.
      </p>

      <div class="flex flex-wrap items-center gap-2 mb-3">
        <button class="btn btn-default btn-xs" :disabled="busy" @click="load">⟳ Auto-align again</button>
        <button class="btn btn-default btn-xs" @click="addBlankRow">+ Add blank row</button>
        <button class="btn btn-default btn-xs" @click="compact">− Remove blank rows</button>
      </div>

      <div v-if="noNew" class="im-note warn mb-3">
        There are no new variants under <b>{{ template }}</b> yet.
        Go back to variants, pick the Item Attributes and create them, then line them up here.
      </div>

      <div v-if="loading" class="im-empty"><span class="animate-spin">⟳</span> Lining up variants…</div>
      <div v-else style="overflow-x: auto">
        <div class="im-aligner">
          <div class="side-head">
            <div class="ttl">OLD</div>
            <button v-for="c in COLUMNS" :key="'lh' + c[0]" class="im-sort" :class="{ active: isSorted('left', c[0]) }"
                    @click="sortSide('left', c[0])">{{ c[1] }} <span class="arrow">{{ sortArrow('left', c[0]) }}</span></button>
            <div></div>
          </div>
          <div class="mid-head">Merge</div>
          <div class="side-head">
            <div class="ttl">NEW</div>
            <button v-for="c in NEW_COLUMNS" :key="'rh' + c[0]" class="im-sort" :class="{ active: isSorted('right', c[0]) }"
                    @click="sortSide('right', c[0])">{{ c[1] }} <span class="arrow">{{ sortArrow('right', c[0]) }}</span></button>
            <div></div>
          </div>

          <template v-for="r in rows" :key="'row' + r.i">
            <!-- OLD side -->
            <div class="cell-row"
                 :class="{ empty: !r.o, 'drag-over': isOver('left', r.i), dragging: isDragging('left', r.i) }"
                 @dragover="onDragOver('left', r.i, $event)" @drop="onDrop('left', r.i)">
              <div class="handle" :draggable="!!r.o" @dragstart="onDragStart('left', r.i, $event)" @dragend="onDragEnd"
                   :title="r.o ? 'Drag to another row' : ''">{{ r.o ? '☰' : '' }}</div>
              <template v-if="r.o">
                <div class="txt font-mono" :title="r.o.item_code">{{ r.o.item_code }}</div>
                <div class="txt" :title="r.o.item_name">{{ r.o.item_name }}</div>
                <div class="txt font-mono text-muted" :title="r.o.retail_sku">{{ r.o.retail_sku }}</div>
              </template>
              <div v-else class="text-faint text-xs" style="grid-column: span 3">empty</div>
              <div class="movers">
                <button :disabled="r.i === 0" @click="swap('left', r.i, r.i - 1)" aria-label="Move old variant up">▲</button>
                <button :disabled="r.i === left.length - 1" @click="swap('left', r.i, r.i + 1)" aria-label="Move old variant down">▼</button>
              </div>
            </div>

            <!-- merge column -->
            <div class="mid-cell">
              <label v-if="r.status === 'leftover'" class="flex items-center gap-1 text-xs cursor-pointer" :title="r.notes.join(' · ')">
                <input type="checkbox" v-model="deleteLeftover[r.o.item_code]" /> delete
              </label>
              <span v-else-if="r.status !== 'blank'" :class="pillClass(r.status)" :title="r.notes.join(' · ')">{{ MID_LABEL[r.status] }}</span>
              <span v-if="r.mismatch" class="text-xs text-warn" :title="r.notes.join(' · ')">⚠ names differ</span>
            </div>

            <!-- NEW side -->
            <div class="cell-row"
                 :class="{ empty: !r.n, 'drag-over': isOver('right', r.i), dragging: isDragging('right', r.i) }"
                 @dragover="onDragOver('right', r.i, $event)" @drop="onDrop('right', r.i)">
              <div class="handle" :draggable="!!r.n" @dragstart="onDragStart('right', r.i, $event)" @dragend="onDragEnd"
                   :title="r.n ? 'Drag to another row' : ''">{{ r.n ? '☰' : '' }}</div>
              <template v-if="r.n && editable(r)">
                <div class="txt font-mono" :title="r.n.item_code">{{ r.n.item_code }}</div>
                <div class="im-edit" :class="{ changed: nameOf(r) !== r.n.item_name, invalid: !nameOf(r).trim() }">
                  <input :value="nameOf(r)" @input="setName(r, $event.target.value)" :aria-label="'Item name after merge for ' + r.n.item_code"
                         :title="'Now: ' + (r.n.item_name || '') + '  ·  Old: ' + (r.o.item_name || '')" />
                  <button v-if="nameOf(r) !== r.o.item_name" @click="setName(r, r.o.item_name || '')"
                          title="Copy the old item name" aria-label="Copy the old item name">↩</button>
                </div>
                <div class="im-edit font-mono" :class="{ changed: skuOf(r) !== r.n.retail_sku, invalid: !skuOf(r).trim() }">
                  <input :value="skuOf(r)" @input="setSku(r, $event.target.value)" :aria-label="'Retail SKU after merge for ' + r.n.item_code"
                         :title="'Now: ' + (r.n.retail_sku || '') + '  ·  Old: ' + (r.o.retail_sku || '')" />
                  <button v-if="skuOf(r) !== r.o.retail_sku" @click="setSku(r, r.o.retail_sku || '')"
                          title="Copy the old retail SKU" aria-label="Copy the old retail SKU">↩</button>
                </div>
              </template>
              <template v-else-if="r.n">
                <div class="txt font-mono" :title="r.n.item_code">{{ r.n.item_code }}</div>
                <div class="txt" :title="r.n.item_name">{{ r.n.item_name }}</div>
                <div class="txt font-mono text-muted" :title="r.n.retail_sku">{{ r.n.retail_sku }}</div>
              </template>
              <div v-else class="text-faint text-xs" style="grid-column: span 3">empty</div>
              <div class="movers">
                <button :disabled="r.i === 0" @click="swap('right', r.i, r.i - 1)" aria-label="Move new variant up">▲</button>
                <button :disabled="r.i === right.length - 1" @click="swap('right', r.i, r.i + 1)" aria-label="Move new variant down">▼</button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div v-if="blockedRows.length" class="im-note danger mt-3">
        <b>Blocked rows must be resolved before queueing:</b>
        <div v-for="r in blockedRows" :key="'b' + r.i" class="issue">
          <span class="font-mono">{{ (r.o || r.n).item_code }}</span> - {{ r.notes.join(' · ') }}
        </div>
      </div>
      <div v-if="editProblems.length" class="im-note danger mt-3">
        <div v-for="p in editProblems" :key="p" class="issue">{{ p }}</div>
      </div>
      <div v-if="problems.length" class="im-note danger mt-3">
        <div v-for="p in problems" :key="p" class="issue">{{ p }}</div>
      </div>
    </section>

    <!-- merge options + actions -->
    <section class="im-card">
      <div class="flex flex-wrap items-end gap-4">
        <div class="flex-1 space-y-2" style="min-width: 320px">
          <div class="im-label">Merge options</div>
          <div class="text-sm text-muted">Edit any item name or retail SKU in the NEW columns above, or fill them all at once:</div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm font-semibold" style="min-width: 90px">Item names</span>
            <button class="btn btn-xs" :class="options.fix_names ? 'btn-primary' : 'btn-default'" @click="fillAll('name', 'old')">Copy all from old</button>
            <button class="btn btn-xs" :class="!options.fix_names ? 'btn-primary' : 'btn-default'" @click="fillAll('name', 'new')">Keep new names</button>
            <span class="text-xs text-faint">{{ changedNames }} will change</span>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm font-semibold" style="min-width: 90px">Retail SKUs</span>
            <button class="btn btn-xs" :class="options.sku === 'keep' ? 'btn-primary' : 'btn-default'" @click="fillAll('sku', 'old')">Copy all from old</button>
            <button class="btn btn-xs" :class="options.sku === 'code' ? 'btn-primary' : 'btn-default'" @click="fillAll('sku', 'new')">Use new item codes</button>
            <span class="text-xs text-faint">{{ changedSkus }} will change</span>
          </div>
          <div class="text-xs text-faint">
            Item codes can be changed after the merge on the
            <a class="im-link" href="#" @click.prevent="go('codes', template)">Item codes</a> screen, e.g. to match the retail SKU.
          </div>
        </div>
        <div class="flex flex-col items-end gap-2 ml-auto">
          <div class="text-muted tabular-nums">{{ pairs.length }} to merge · {{ leftovers.length }} to delete</div>
          <div class="flex flex-wrap gap-2 justify-end">
            <button v-if="needsFix.length" class="btn btn-warning btn-sm" :disabled="busy" @click="fixSettings">
              {{ busy ? 'Working…' : 'Fix settings on ' + needsFix.length }}
            </button>
            <button class="btn btn-default btn-sm" :disabled="busy || !pairs.length" @click="check">
              {{ busy ? 'Working…' : 'Check' }}
            </button>
            <button class="btn btn-danger btn-sm" :disabled="!canQueue" @click="queue">Queue merge</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { itemMergeApi } from './api.js'
import { alertOk, confirmAction, go, itemUrl, pillClass } from './utils.js'

const props = defineProps({ template: { type: String, required: true } })
const emit = defineEmits(['queued', 'back'])

const SETTINGS = [
  ['stock_uom', 'UOM'], ['is_stock_item', 'Maintain Stock'], ['has_batch_no', 'Has Batch No'],
  ['has_serial_no', 'Has Serial No'], ['is_fixed_asset', 'Is Fixed Asset'],
]
const COLUMNS = [['item_code', 'Item code'], ['item_name', 'Item name'], ['retail_sku', 'Retail SKU']]
const NEW_COLUMNS = [['item_code', 'Item code'], ['item_name', 'Item name after merge'], ['retail_sku', 'Retail SKU after merge']]
const MID_LABEL = { ready: 'OLD > NEW', fix: 'fix settings', blocked: 'blocked', unused: 'no old' }

const loading = ref(true)
const tmpl = ref(null)
const left = ref([]) // old variants (or null) - row i pairs with right[i]
const right = ref([]) // new variants (or null)
const deleteLeftover = ref({}) // item_code -> bool
const sorts = ref({ left: null, right: null })
const problems = ref([])
const busy = ref(false)
const options = ref({ sku: 'keep', fix_names: true })
const drag = ref(null) // { side, index }
const over = ref(null)
const hints = ref({}) // old item_code -> why the server couldn't pair it

function place(data) {
  tmpl.value = data.template
  nameAliases.value = data.name_aliases || {}
  const l = []
  const r = []
  for (const row of data.rows) { l.push(row.old); r.push(row.new) }
  for (const n of data.unpaired_new) { l.push(null); r.push(n) }
  left.value = l
  right.value = r
  const h = {}
  data.rows.filter((x) => !x.new).forEach((x) => { h[x.old.item_code] = x.issues.filter((i) => !/=None/.test(i)) })
  hints.value = h
  const dl = {}
  data.rows.filter((x) => x.status === 'leftover').forEach((x) => { dl[x.old.item_code] = true })
  deleteLeftover.value = dl
  problems.value = []
}

async function load() {
  loading.value = true
  try {
    place(await itemMergeApi.getAlignment(props.template))
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    loading.value = false
  }
}
onMounted(load)

// refresh item settings (e.g. after a fix) without losing the order the user built
async function refreshItems() {
  const data = await itemMergeApi.getAlignment(props.template)
  const byCode = {}
  data.rows.forEach((x) => {
    if (x.old) byCode[x.old.item_code] = x.old
    if (x.new) byCode[x.new.item_code] = x.new
  })
  data.unpaired_new.forEach((n) => { byCode[n.item_code] = n })
  tmpl.value = data.template
  nameAliases.value = data.name_aliases || {}
  left.value = left.value.map((v) => v && (byCode[v.item_code] || v))
  right.value = right.value.map((v) => v && (byCode[v.item_code] || v))
}

function settingsDiff(o, n) {
  return SETTINGS.filter(([k]) => (k === 'stock_uom' ? (o[k] || '') !== (n[k] || '') : !!o[k] !== !!n[k]))
    .map(([k, label]) => ({ key: k, label, old: o[k], new: n[k] }))
}

// {value: [other wordings]}, sent with the alignment. Keeping a copy here meant it drifted from the
// tables the server pairs with - it had lost S, M, L and XXS, so every single-letter size raised a
// "names differ" warning on a pair the server had matched perfectly well.
const nameAliases = ref({})
function nameHas(name, value) {
  const parts = String(name || '').split(' - ').map((s) => s.trim().toLowerCase())
  return [value, ...(nameAliases.value[value] || [])].some((v) => parts.includes(String(v).toLowerCase()))
}

const rows = computed(() => left.value.map((o, i) => {
  const n = right.value[i]
  if (!o && !n) return { i, o, n, status: 'blank', notes: [] }
  if (o && !n) {
    const empty = !o.ledger_count && !o.qty
    return {
      i, o, n, status: empty ? 'leftover' : 'blocked',
      notes: [empty ? 'No stock history - delete as leftover, or line up a new variant'
        : `Has stock history (qty ${o.qty}) - needs a new variant to merge into`, ...(hints.value[o.item_code] || [])],
    }
  }
  if (!o && n) return { i, o, n, status: 'unused', notes: ['No old variant merges into this one'] }
  if (o.is_new) return { i, o, n, status: 'blocked', notes: [`${o.item_code} already uses real attributes`] }
  if (!n.is_new) return { i, o, n, status: 'blocked', notes: [`${n.item_code} is a Variant Number item`] }
  const diff = settingsDiff(o, n)
  if (diff.length && n.ledger_count) {
    return {
      i, o, n, status: 'blocked', diff,
      notes: diff.map((d) => `${d.label}: ${d.old} vs ${d.new}; new item already has stock history`),
    }
  }
  const missing = Object.values(n.attributes || {}).filter((v) => v && !nameHas(o.item_name, v))
  const nameNote = missing.length ? [`Old name doesn't mention ${missing.join(' / ')} - is this the right pair?`] : []
  if (diff.length) {
    return {
      i, o, n, status: 'fix', diff, mismatch: !!missing.length,
      notes: [...diff.map((d) => `${d.label}: set to ${d.old}`), ...nameNote],
    }
  }
  return { i, o, n, status: 'ready', mismatch: !!missing.length, notes: nameNote }
}))

const mismatches = computed(() => rows.value.filter((r) => r.mismatch).length)
const counts = computed(() => {
  const c = { ready: 0, fix: 0, blocked: 0, leftover: 0, unused: 0 }
  rows.value.forEach((r) => { if (r.status in c) c[r.status]++ })
  return c
})
const blockedRows = computed(() => rows.value.filter((r) => r.status === 'blocked'))

// ---- item name / retail SKU the new variant ends up with ----
// A default comes from the bulk choice (copy from old, or keep new). Typing in a cell stores an
// override keyed by the new item code, so it travels with the item when rows are moved.
const nameEdits = ref({})
const skuEdits = ref({})
const editable = (r) => !!(r.o && r.n && ['ready', 'fix'].includes(r.status))
const defaultName = (r) => (options.value.fix_names && r.o?.item_name ? r.o.item_name : r.n.item_name) || ''
const defaultSku = (r) => (options.value.sku === 'keep' ? (r.o?.retail_sku || r.n.retail_sku) : r.n.item_code) || ''
const nameOf = (r) => nameEdits.value[r.n.item_code] ?? defaultName(r)
const skuOf = (r) => skuEdits.value[r.n.item_code] ?? defaultSku(r)
const setName = (r, v) => { nameEdits.value = { ...nameEdits.value, [r.n.item_code]: v } }
const setSku = (r, v) => { skuEdits.value = { ...skuEdits.value, [r.n.item_code]: v } }
function fillAll(field, from) {
  if (field === 'name') {
    options.value.fix_names = from === 'old'
    nameEdits.value = {}
  } else {
    options.value.sku = from === 'old' ? 'keep' : 'code'
    skuEdits.value = {}
  }
}

const pairs = computed(() => rows.value.filter(editable)
  .map((r) => ({ old: r.o.item_code, new: r.n.item_code, item_name: nameOf(r).trim(), retail_sku: skuOf(r).trim() })))
const editProblems = computed(() => {
  const out = pairs.value.filter((p) => !p.item_name).map((p) => `${p.new}: item name is empty`)
    .concat(pairs.value.filter((p) => !p.retail_sku).map((p) => `${p.new}: retail SKU is empty`))
  const seen = {}
  pairs.value.forEach((p) => { if (p.retail_sku) seen[p.retail_sku] = (seen[p.retail_sku] || 0) + 1 })
  return out.concat(Object.keys(seen).filter((k) => seen[k] > 1).map((k) => `Retail SKU ${k} is on more than one new variant`))
})
const changedNames = computed(() => rows.value.filter(editable).filter((r) => nameOf(r).trim() !== (r.n.item_name || '')).length)
const changedSkus = computed(() => rows.value.filter(editable).filter((r) => skuOf(r).trim() !== (r.n.retail_sku || '')).length)
const leftovers = computed(() => rows.value.filter((r) => r.status === 'leftover' && deleteLeftover.value[r.o.item_code])
  .map((r) => r.o.item_code))
const needsFix = computed(() => rows.value.filter((r) => r.status === 'fix'))
const noNew = computed(() => !loading.value && right.value.every((v) => !v))
const canQueue = computed(() => pairs.value.length > 0 && counts.value.blocked === 0 && !editProblems.value.length && !busy.value)

// ---- moving rows: swap keeps every other pair where it is ----
const sideArr = (side) => (side === 'left' ? left : right)
function swap(side, a, b) {
  const arr = sideArr(side)
  if (b < 0 || b >= arr.value.length || a === b) return
  const copy = [...arr.value]
  ;[copy[a], copy[b]] = [copy[b], copy[a]]
  arr.value = copy
  sorts.value[side] = null
}
const isOver = (side, index) => !!over.value && over.value.side === side && over.value.index === index
const isDragging = (side, index) => !!drag.value && drag.value.side === side && drag.value.index === index
function onDragStart(side, index, e) {
  drag.value = { side, index }
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', `${side}:${index}`)
}
function onDragOver(side, index, e) {
  if (drag.value?.side === side) {
    e.preventDefault()
    over.value = { side, index }
  }
}
function onDrop(side, index) {
  if (drag.value?.side === side) swap(side, drag.value.index, index)
  drag.value = null
  over.value = null
}
function onDragEnd() {
  drag.value = null
  over.value = null
}

// sorting reorders one side only; blanks sink to the bottom
function sortSide(side, key) {
  const cur = sorts.value[side]
  const dir = cur && cur.key === key ? -cur.dir : 1
  const arr = sideArr(side)
  const items = arr.value.filter(Boolean).sort((a, b) =>
    String(a[key] ?? '').localeCompare(String(b[key] ?? ''), undefined, { numeric: true }) * dir)
  const blanks = arr.value.length - items.length
  arr.value = [...items, ...Array(blanks).fill(null)]
  sorts.value[side] = { key, dir }
}
const isSorted = (side, key) => sorts.value[side]?.key === key
const sortArrow = (side, key) => (isSorted(side, key) ? (sorts.value[side].dir > 0 ? '▲' : '▼') : '⇅')

function addBlankRow() {
  left.value = [...left.value, null]
  right.value = [...right.value, null]
}
function compact() {
  const keep = rows.value.filter((r) => r.o || r.n)
  left.value = keep.map((r) => r.o)
  right.value = keep.map((r) => r.n)
}

// ---- actions ----
async function fixSettings() {
  busy.value = true
  try {
    const res = await itemMergeApi.fixSettings(props.template,
      needsFix.value.map((r) => ({ old: r.o.item_code, new: r.n.item_code })))
    alertOk(`Settings aligned: ${res.changed.length} new variant(s) updated to match their old variant`)
    await refreshItems()
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

async function check() {
  busy.value = true
  try {
    const res = await itemMergeApi.checkAlignment(props.template, pairs.value, leftovers.value)
    problems.value = res.problems
    if (res.ok) alertOk(`Ready to queue: ${pairs.value.length} pair(s) check out`)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

async function queue() {
  const unused = counts.value.unused
  const message = `Merge ${pairs.value.length} old variant(s) into their new variant, OLD > NEW, one at a time.` +
    (needsFix.value.length ? ` ${needsFix.value.length} new variant(s) get their settings aligned first.` : '') +
    (leftovers.value.length ? ` Delete ${leftovers.value.length} leftover(s) with no stock history.` : '') +
    (unused ? ` ${unused} new variant(s) have no old variant and stay as they are.` : '') +
    (changedNames.value ? ` ${changedNames.value} item name(s) and` : ' No item names and') +
    ` ${changedSkus.value || 'no'} retail SKU(s) change as shown.` +
    (mismatches.value ? ` ${mismatches.value} pair(s) have names that don't match - make sure they're lined up right.` : '') +
    ' Old variants disappear once merged. This writes to ERPNext.'
  const ok = await confirmAction({ title: 'Queue the merge?', message, label: 'Queue merge', danger: true })
  if (!ok) return
  busy.value = true
  try {
    const res = await itemMergeApi.queueMerge(props.template, pairs.value, leftovers.value,
      { sku: options.value.sku, fix_names: options.value.fix_names })
    emit('queued', res.job)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

async function refresh() {
  try {
    await refreshItems()
  } catch (e) {
    // Frappe has shown the reason
  }
}

defineExpose({ refresh })
</script>
