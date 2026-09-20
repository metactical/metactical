<template>
  <!-- One old variant's Storebuilder products: a native Frappe grid of website + slug, the same
       control the S3 uploader uses for item code + SKU. Nothing cascades - picking a website fills
       nothing in and changes no other row; the slug is whatever the operator pastes, or whatever
       the lookup found. -->
  <div class="im-slug-grid space-y-2">
    <div class="flex items-center flex-wrap gap-2">
      <span class="im-label">Storebuilder products for {{ itemCode }}</span>
      <span v-if="dirty" :class="pillClass('warn')">unsaved</span>
      <span v-else-if="saved" :class="pillClass('ok')">saved</span>
      <label class="flex items-center gap-1 text-xs cursor-pointer mb-0 ml-auto" :title="'Nothing to drop for ' + itemCode">
        <input type="checkbox" :checked="notPublished" :disabled="busy || hasRows" @change="toggleNotPublished($event.target.checked)" />
        <span>not on any website</span>
      </label>
      <button class="btn btn-primary btn-xs" :disabled="busy || !dirty" @click="save">
        {{ busy ? 'Checking…' : 'Check and save' }}
      </button>
    </div>

    <div v-show="!notPublished" ref="gridEl"></div>
    <p v-if="notPublished" class="text-xs text-muted mb-0">
      {{ itemCode }} is recorded as having no Storebuilder product. Nothing is dropped for it; untick to add a slug.
    </p>

    <div v-if="problems.length" class="im-note danger text-xs mb-0">
      <b>Not saved:</b>
      <div v-for="p in problems" :key="p" class="issue">{{ p }}</div>
      <div class="issue mt-1">
        Everything else on this item was saved, and each website above keeps whatever it had before.
      </div>
    </div>
    <div v-if="warnings.length" class="im-note warn text-xs mb-0">
      <b>Saved, but the website could not answer:</b>
      <div v-for="w in warnings" :key="w" class="issue">{{ w }}</div>
      <div class="issue mt-1">Worth opening the link yourself once the site is back.</div>
    </div>
    <p v-else-if="!notPublished" class="text-xs text-muted mb-0">
      <b>Add Row</b>, pick the website, paste the slug, then <b>Check and save</b> - which opens
      <span class="font-mono">https://&lt;website domain&gt;/&lt;slug&gt;</span> to see whether the product is really there.
      A slug the website has no page for is <b>not saved</b>, and no two items may claim the same slug on the same
      website. One row per website this item is live on; a website with no row here is left alone by the merge. If it
      was never published anywhere, tick <b>not on any website</b> instead.
    </p>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { itemMergeApi } from './api.js'
import { pillClass } from './utils.js'

const props = defineProps({
  template: { type: String, required: true },
  itemCode: { type: String, required: true },
  // Every website, as legacy_products.plan() returned them for this item.
  rows: { type: Array, default: () => [] },
  notPublished: { type: Boolean, default: false },
})
const emit = defineEmits(['saved'])

const gridEl = ref(null)
const busy = ref(false)
const saved = ref(false)
const problems = ref([])
const warnings = ref([])
const dirty = ref(false)
let control = null
let seeding = false

const hasRows = computed(() => props.rows.some((r) => r.slug))
const websites = computed(() => props.rows.map((r) => r.lead_source))
// Only the websites that have a slug: an empty grid is the honest picture of an item that was
// never published, and Add Row is how one gets added.
const toGridRows = () => props.rows.filter((r) => r.slug).map((r, i) => ({
  idx: i + 1, __islocal: 1, lead_source: r.lead_source, slug: r.slug,
}))

const gridData = () => (control?.grid?.df?.data || []).filter((r) => r.lead_source && (r.slug || '').trim())

const onEdit = () => {
  if (seeding) return
  dirty.value = true
  saved.value = false
}

function buildGrid() {
  control = frappe.ui.form.make_control({
    parent: gridEl.value,
    render_input: true,
    df: {
      fieldname: 'legacy_slugs',
      fieldtype: 'Table',
      options: 'Legacy Website Slug',
      data: toGridRows(),
      on_add_row: onEdit,
      fields: [
        {
          fieldname: 'lead_source',
          fieldtype: 'Link',
          options: 'Lead Source',
          label: 'Website',
          in_list_view: 1,
          columns: 4,
          // Every Lead Source with a domain set - the websites, as an operator names one.
          get_query: () => ({ filters: { name: ['in', websites.value] } }),
          onchange: onEdit,
        },
        // Frappe gives a grid ten column units in total; asking for more silently drops a column.
        { fieldname: 'slug', fieldtype: 'Data', label: 'Slug', in_list_view: 1, columns: 6, onchange: onEdit },
      ],
    },
  })
  control.refresh()

  // Same reason as the S3 uploader: the native delete is async and reaches for frm.doc.
  const grid = control.grid
  grid.delete_rows = () => {
    const drop = new Set((grid.df.data || []).filter((r) => r.__checked))
    if (!drop.size) return
    grid.df.data = (grid.df.data || []).filter((r) => !drop.has(r))
    grid.df.data.forEach((row, i) => (row.idx = i + 1))
    grid.refresh()
    onEdit()
  }
  grid.delete_all_rows = () => {
    grid.df.data = []
    grid.refresh()
    onEdit()
  }
}

function reseed() {
  if (!control) return
  seeding = true
  control.grid.df.data = toGridRows()
  control.grid.refresh()
  seeding = false
}

async function toggleNotPublished(on) {
  busy.value = true
  try {
    await itemMergeApi.markNotPublished(props.template, props.itemCode, on)
    emit('saved', props.itemCode)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

async function save() {
  const rows = gridData()
  const seen = {}
  const dupes = []
  rows.forEach((r) => {
    seen[r.lead_source] = (seen[r.lead_source] || 0) + 1
    if (seen[r.lead_source] === 2) dupes.push(r.lead_source)
  })
  if (dupes.length) {
    problems.value = dupes.map((ls) => `${ls} is on more than one row - one slug per website`)
    warnings.value = []
    return
  }

  // Every website is sent, so a row the operator deleted is saved as "not on this site" and clears
  // what was registered before.
  const bySite = {}
  rows.forEach((r) => { bySite[r.lead_source] = (r.slug || '').trim() })
  const payload = websites.value.map((ls) => ({ product: props.itemCode, lead_source: ls, slug: bySite[ls] || '' }))

  busy.value = true
  problems.value = []
  warnings.value = []
  try {
    const res = await itemMergeApi.saveLegacySlugs(props.template, payload)
    problems.value = res.problems || []
    // A page the website would not serve is still recorded - the row saved, so it is not "dirty".
    warnings.value = res.warnings || []
    dirty.value = problems.value.length > 0
    saved.value = !problems.value.length
    emit('saved', props.itemCode)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

// A reseed from the parent (the lookup filled something in, or the save came back) must not look
// like the operator typing.
watch(() => props.rows, () => { if (!dirty.value) reseed() }, { deep: true })

onMounted(() => frappe.model.with_doctype('Legacy Website Slug', buildGrid))
onBeforeUnmount(() => { control = null })

defineExpose({ save })
</script>
