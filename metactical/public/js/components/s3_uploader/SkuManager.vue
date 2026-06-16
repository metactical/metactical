<template>
  <!-- Native Frappe grid: Add Row, pick an Item Code (auto-loads SKU), select + Delete. -->
  <div ref="gridRef"></div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'

const props = defineProps({
  skuItems: { type: Array, default: () => [] },
  // The locked-in product template (null until one is chosen at the top of the page).
  template: { type: String, default: null },
  // Allowed variants for the template: [{ item_code, sku }]. The picker is limited to these.
  allowedVariants: { type: Array, default: () => [] },
})
const emit = defineEmits(['update'])

const gridRef = ref(null)
let control = null
let seeding = false

const toRows = () =>
  (props.skuItems || []).map((i, idx) => ({
    idx: idx + 1,
    __islocal: 1,
    nat_item_code: i.item_code,
    nat_sku: i.sku,
  }))

const committed = () =>
  (control?.grid?.df?.data || [])
    .filter((r) => r.nat_item_code && r.nat_sku)
    .map((r) => ({ item_code: r.nat_item_code, sku: r.nat_sku }))

const syncToParent = () => {
  if (!seeding) emit('update', committed())
}

const clearRow = (row) => {
  row.nat_item_code = ''
  row.nat_sku = ''
  control.grid.refresh()
  syncToParent()
}

// When an Item Code is picked in a row: it must be a variant of the locked template,
// and only that single variant is added (no family auto-add). Its SKU comes from the
// allowed-variants list passed down from the template selection.
const resolveSku = (field) => {
  const row = field.doc
  const code = field.value
  if (!code) {
    row.nat_sku = ''
    syncToParent()
    return
  }

  // A template must be chosen first.
  if (!props.template) {
    frappe.show_alert({ message: 'Select a product template first', indicator: 'orange' })
    clearRow(row)
    return
  }

  // Must be a variant of the selected template.
  const match = (props.allowedVariants || []).find((v) => v.item_code === code)
  if (!match) {
    frappe.show_alert({ message: `${code} is not a variant of ${props.template}`, indicator: 'red' })
    clearRow(row)
    return
  }

  // Already selected in another row? Don't add it again.
  const otherCodes = new Set(
    (control.grid.df.data || []).filter((r) => r !== row && r.nat_item_code).map((r) => r.nat_item_code)
  )
  if (otherCodes.has(code)) {
    frappe.show_alert({ message: `${code} is already selected`, indicator: 'orange' })
    clearRow(row)
    return
  }

  row.nat_sku = match.sku
  control.grid.refresh()
  syncToParent()
}

const buildGrid = () => {
  control = frappe.ui.form.make_control({
    parent: gridRef.value,
    render_input: true,
    df: {
      fieldname: 'skus',
      fieldtype: 'Table',
      options: 'S3 Product Image SKU',
      data: toRows(),
      on_add_row: () => syncToParent(),
      fields: [
        {
          fieldname: 'nat_item_code',
          fieldtype: 'Link',
          options: 'Item',
          label: 'Item Code',
          in_list_view: 1,
          columns: 6,
          // Limit the picker to the selected template's variants only. With no
          // template chosen, the empty name list resolves to nothing.
          get_query: () => ({
            filters: { name: ['in', (props.allowedVariants || []).map((v) => v.item_code)] },
          }),
          onchange: function () {
            resolveSku(this)
          },
        },
        {
          fieldname: 'nat_sku',
          fieldtype: 'Data',
          label: 'SKU',
          in_list_view: 1,
          columns: 4,
          read_only: 1,
        },
      ],
    },
  })
  control.refresh()

  // Synchronous, multi-row-safe delete (native one runs async / touches frm.doc).
  const grid = control.grid
  grid.delete_rows = () => {
    const drop = new Set((grid.df.data || []).filter((r) => r.__checked))
    if (!drop.size) return
    grid.df.data = (grid.df.data || []).filter((r) => !drop.has(r))
    grid.df.data.forEach((row, i) => (row.idx = i + 1))
    grid.refresh()
    syncToParent()
  }
  grid.delete_all_rows = () => {
    grid.df.data = []
    grid.refresh()
    syncToParent()
  }
}

const reseed = () => {
  if (!control) return
  seeding = true
  control.grid.df.data = toRows()
  control.grid.refresh()
  seeding = false
}

watch(
  () => props.skuItems,
  () => {
    if (JSON.stringify(committed()) !== JSON.stringify(props.skuItems || [])) reseed()
  },
  { deep: true }
)

onMounted(() => {
  frappe.model.with_doctype('S3 Product Image SKU', buildGrid)
})
</script>
