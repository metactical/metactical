<template>
  <div>
    <div class="im-split">
      <!-- search -->
      <section class="im-card">
        <h3 class="im-card-title">Find templates</h3>
        <p class="im-lede">
          Search by template SKU, template name, or both. Both boxes suggest from the templates that exist - pick one
          and it searches straight away - and part of a value still works: <span class="font-mono">RVX418</span> finds
          every RavenX 418x template, and every word of the name must appear, in any order (<i>fleece vest</i>).
        </p>
        <form class="flex flex-wrap items-end gap-2" @submit.prevent="search">
          <div style="flex: 1; min-width: 200px">
            <label class="control-label-sm block">Template SKU</label>
            <div ref="skuEl" class="im-link-control font-mono"></div>
          </div>
          <div style="flex: 1.4; min-width: 240px">
            <label class="control-label-sm block">Template name</label>
            <div ref="nameEl" class="im-link-control"></div>
          </div>
          <button type="submit" class="btn btn-primary btn-sm" :disabled="loading || (!sku.trim() && !name.trim())">
            {{ loading ? 'Searching…' : 'Search' }}
          </button>
        </form>
        <div v-if="searched" class="mt-4">
          <div v-if="!results.length" class="im-empty">No templates match <b>{{ searchedFor }}</b>.</div>
          <template v-else>
            <div class="im-table-wrap">
              <table class="im-table">
                <thead>
                  <tr>
                    <th style="width: 36px"><input type="checkbox" :checked="allSelected" @change="toggleAll" aria-label="Select all" /></th>
                    <th><button class="im-sort" :class="{ active: sortKey === 'item_code' }" @click="sortBy('item_code')">Template SKU <span class="arrow">{{ arrow('item_code') }}</span></button></th>
                    <th><button class="im-sort" :class="{ active: sortKey === 'item_name' }" @click="sortBy('item_name')">Item name <span class="arrow">{{ arrow('item_name') }}</span></button></th>
                    <th>Brand</th>
                    <th class="r"><button class="im-sort" :class="{ active: sortKey === 'variant_count' }" @click="sortBy('variant_count')">Variants <span class="arrow">{{ arrow('variant_count') }}</span></button></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in sorted" :key="r.item_code" class="clickable" :class="{ selected: selected.includes(r.item_code) }" @click="toggle(r.item_code)">
                    <td @click.stop><input type="checkbox" :checked="selected.includes(r.item_code)" @change="toggle(r.item_code)" :aria-label="'Select ' + r.item_code" /></td>
                    <td class="font-mono whitespace-nowrap">
                      {{ r.item_code }} <span v-if="r.disabled" class="indicator-pill gray">disabled</span>
                    </td>
                    <td>{{ r.item_name }}</td>
                    <td class="text-muted">{{ r.brand }}</td>
                    <td class="r tabular-nums">{{ r.variant_count }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="text-xs text-muted mt-2 mb-0">
              {{ results.length }} template(s){{ results.length >= 60 ? ' - showing the first 60, narrow the search' : '' }}
            </p>
          </template>
        </div>
      </section>

      <!-- selection -->
      <aside class="im-card space-y-3">
        <div class="im-label">Selection</div>
        <div v-if="!selected.length" class="text-muted text-sm">
          Tick one template to work on its variants, or several to merge them into one first.
        </div>

        <template v-else-if="selected.length === 1">
          <div><span class="font-mono font-semibold">{{ selected[0] }}</span> <span class="text-muted">· {{ totalVariants }} variant(s)</span></div>
          <div class="im-note info">All the variants you'll work on are already under this template.</div>
          <div v-if="!productsOk" class="im-note warn">
            Storebuilder has to answer for this template first - see <b>Storebuilder products</b> below.
          </div>
          <button class="btn btn-primary btn-sm w-full" :disabled="!productsOk || busy" @click="chooseOne">
            {{ busy ? 'Saving…' : 'Continue to variants →' }}
          </button>
        </template>

        <template v-else>
          <div class="text-muted text-sm">{{ selected.length }} templates · {{ totalVariants }} variants</div>
          <div>
            <label class="control-label-sm block">Surviving template</label>
            <div class="space-y-1">
              <label v-for="r in selectedRows" :key="r.item_code" class="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="im-survivor" :value="r.item_code" v-model="survivor" />
                <span class="font-mono">{{ r.item_code }}</span><span class="text-faint text-xs">{{ r.variant_count }}</span>
              </label>
            </div>
          </div>
          <div>
            <label class="control-label-sm block">Rename it to <span class="text-faint" style="font-weight: 400">(optional)</span></label>
            <input v-model="renameTo" class="form-control input-sm font-mono"
                   :placeholder="baseCode ? 'e.g. ' + baseCode : 'leave empty to keep ' + (survivor || '')" />
            <div class="text-xs text-muted mt-1">Empty keeps <span class="font-mono">{{ survivor }}</span>. New variant codes start with the final template code.</div>
          </div>

          <div>
            <label class="control-label-sm block">What you are merging</label>
            <div v-if="checking" class="text-muted text-sm"><span class="animate-spin">⟳</span> Checking…</div>
            <div v-else class="space-y-2">
              <div v-for="g in groupsOfSelection" :key="g.base_sku + g.product_name" class="im-kpi"
                   :class="{ 'im-note warn': groupsOfSelection.length > 1 }">
                <div><span class="font-mono font-semibold">{{ g.base_sku }}</span> · {{ g.product_name || '(no name)' }}</div>
                <div class="text-xs text-muted">{{ g.templates }} template(s) · {{ g.variants }} variant(s)</div>
                <div v-for="(n, grp) in g.group_counts" :key="grp" class="text-xs" :class="check && check.blocked ? 'text-danger' : 'text-muted'">
                  {{ grp }}: {{ n }} variant(s)
                </div>
              </div>
            </div>
          </div>

          <div v-if="check && check.blocked" class="im-note danger"><b>Can't merge yet:</b> {{ check.block_reason }}.</div>
          <div v-else-if="check && check.different_products" class="im-note warn">
            <b>These look like different products:</b> {{ check.product_names.join(' / ') }}.
            <label class="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="checkbox" v-model="confirmSame" /> I've checked - these are one product
            </label>
          </div>
          <div class="im-note warn">
            Every other selected template is merged into <b>{{ survivor }}</b> and removed. Their variants move with them. This can't be undone.
          </div>
          <div v-if="!productsOk" class="im-note warn">
            Storebuilder has to answer for every selected template first - see <b>Storebuilder products</b> below.
            Their slugs are the only handle left on the products this merge removes.
          </div>
          <button class="btn btn-danger btn-sm w-full" :disabled="!survivor || !mergeAllowed || busy || !productsOk" @click="consolidate">
            {{ busy ? 'Merging…' : 'Merge ' + selected.length + ' templates into ' + (renameTo.trim() || survivor) }}
          </button>
        </template>
      </aside>
    </div>

    <TemplateProducts v-if="selected.length" ref="products" :templates="selected" @update:ok="(v) => productsOk = v" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { itemMergeApi, TEMPLATE_CODE_QUERY, TEMPLATE_NAME_QUERY } from './api.js'
import { alertOk, confirmAction, makeAutocomplete } from './utils.js'
import TemplateProducts from './TemplateProducts.vue'

const emit = defineEmits(['chosen'])

const sku = ref('')
const name = ref('')
const searchedFor = ref('')
const results = ref([])
const searched = ref(false)
const loading = ref(false)
const selected = ref([])
const survivor = ref(null)
const renameTo = ref('')
const busy = ref(false)
const products = ref(null)
const productsOk = ref(false)

// ---- the two search boxes, both native Frappe Autocompletes fed from Item ----
// Autocomplete rather than Link: they suggest what exists, but a partial term ("RVX418") is a valid
// search here and a Link would reject it and blank the box on blur. Picking a suggestion searches
// immediately, which is how you get to one known template in a single action.
const skuEl = ref(null)
const nameEl = ref(null)
let skuBox = null
let nameBox = null

onMounted(() => nextTick(() => {
  skuBox = makeAutocomplete(skuEl.value, {
    query: TEMPLATE_CODE_QUERY,
    placeholder: 'e.g. RVX4184',
    onInput: (v) => { sku.value = v },
    onPick: (v) => { sku.value = v; search() },
  })
  nameBox = makeAutocomplete(nameEl.value, {
    query: TEMPLATE_NAME_QUERY,
    placeholder: 'e.g. fleece vest',
    onInput: (v) => { name.value = v },
    onPick: (v) => { name.value = v; search() },
  })
  skuBox.control.$input.trigger('focus')
}))

// ---- results table ----
const sortKey = ref('item_code')
const sortDir = ref(1)
const sorted = computed(() => [...results.value].sort((a, b) => {
  const x = a[sortKey.value]
  const y = b[sortKey.value]
  return (typeof x === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''))) * sortDir.value
}))
const sortBy = (k) => { sortDir.value = sortKey.value === k ? -sortDir.value : 1; sortKey.value = k }
const arrow = (k) => (sortKey.value === k ? (sortDir.value > 0 ? '▲' : '▼') : '⇅')

const selectedRows = computed(() => results.value.filter((r) => selected.value.includes(r.item_code)))
const totalVariants = computed(() => selectedRows.value.reduce((n, r) => n + r.variant_count, 0))
const baseCode = computed(() => {
  const s = (survivor.value || '').replace(/[A-Za-z]+$/, '')
  return /\d$/.test(s) ? s : ''
})

async function search() {
  // read straight off the controls: a pick made with the mouse lands here before Vue's watcher runs
  sku.value = skuBox?.value() ?? sku.value
  name.value = nameBox?.value() ?? name.value
  if (!sku.value.trim() && !name.value.trim()) return
  loading.value = true
  try {
    results.value = (await itemMergeApi.searchTemplates(sku.value.trim(), name.value.trim())).templates
    searchedFor.value = [sku.value.trim(), name.value.trim()].filter(Boolean).join(' + ')
    searched.value = true
    selected.value = []
    survivor.value = null
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    loading.value = false
  }
}

function keepSurvivor() {
  if (!selected.value.includes(survivor.value)) survivor.value = selected.value[0] || null
}
function toggle(code) {
  const i = selected.value.indexOf(code)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(code)
  keepSurvivor()
}
const allSelected = computed(() => results.value.length > 0 && selected.value.length === results.value.length)
function toggleAll() {
  selected.value = allSelected.value ? [] : results.value.map((r) => r.item_code)
  keepSurvivor()
}

// ---- before merging templates: one product? one item group? ----
const check = ref(null)
const checking = ref(false)
const confirmSame = ref(false)
let checkSeq = 0
watch([selected, survivor], async () => {
  confirmSame.value = false
  if (selected.value.length < 2 || !survivor.value) { check.value = null; return }
  const seq = ++checkSeq
  checking.value = true
  try {
    const res = await itemMergeApi.checkConsolidation(survivor.value, selected.value.filter((c) => c !== survivor.value))
    if (seq === checkSeq) check.value = res
  } catch (e) {
    if (seq === checkSeq) check.value = null
  } finally {
    if (seq === checkSeq) checking.value = false
  }
}, { deep: true })

// group the selection by base SKU + product name, so a mix of products stands out
const groupsOfSelection = computed(() => {
  const out = {}
  ;(check.value?.templates || []).forEach((t) => {
    const key = t.base_sku + ' · ' + (t.product_name || '?')
    out[key] = out[key] || { base_sku: t.base_sku, product_name: t.product_name, templates: 0, variants: 0, group_counts: {} }
    out[key].templates++
    out[key].variants += t.variant_count
    Object.entries(t.group_counts || {}).forEach(([g, n]) => { out[key].group_counts[g] = (out[key].group_counts[g] || 0) + n })
  })
  return Object.values(out)
})
const mergeAllowed = computed(() => !!check.value && !check.value.blocked
  && (!check.value.different_products || confirmSame.value) && !checking.value)

// Both ways out of this step write the register first: consolidate_templates deletes the source
// templates, and after that their Storebuilder products can never be found again.
async function chooseOne() {
  busy.value = true
  try {
    await products.value.save(selected.value[0])
    emit('chosen', selected.value[0])
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

async function consolidate() {
  const sources = selected.value.filter((c) => c !== survivor.value)
  const finalCode = renameTo.value.trim() || survivor.value
  const ok = await confirmAction({
    title: 'Merge templates?',
    message: `Merge ${sources.length} template(s) into ${survivor.value}` +
      (renameTo.value.trim() ? `, then rename it to ${finalCode}` : '') +
      `.\n${totalVariants.value} variants will sit under ${finalCode}. The other templates are removed.`,
    label: 'Merge templates',
    danger: true,
  })
  if (!ok) return
  busy.value = true
  try {
    // The rows go with the call rather than in a save of their own: consolidate_templates records
    // them in the same transaction as the renames, so a consolidation that fails does not leave
    // register records behind for a merge that never happened.
    const res = await itemMergeApi.consolidateTemplates(survivor.value, sources,
      renameTo.value.trim() || null, confirmSame.value, products.value.rows)
    alertOk(`${res.variants_moved} variant(s) now under ${res.template}`)
    emit('chosen', res.template)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

function refresh() {
  if (searched.value) search()
  products.value?.refresh()
}


defineExpose({ refresh })
</script>
