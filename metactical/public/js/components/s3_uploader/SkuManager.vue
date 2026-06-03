<template>
  <div ref="gridRef" class="s3-sku-grid"></div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'

const props = defineProps({
  skuItems: { type: Array, default: () => [] }
})
const emit = defineEmits(['update'])

const gridRef = ref(null)
let control = null
let seeding = false

// props.skuItems ({item_code, sku}) -> grid rows (child doctype fieldnames)
const toRows = () =>
  (props.skuItems || []).map((i, idx) => ({
    idx: idx + 1,
    __islocal: 1,
    nat_item_code: i.item_code,
    nat_sku: i.sku,
  }))

// grid rows -> committed {item_code, sku} (only fully-filled rows)
const committed = () =>
  (control?.grid?.df?.data || [])
    .filter((r) => r.nat_item_code && r.nat_sku)
    .map((r) => ({ item_code: r.nat_item_code, sku: r.nat_sku }))

const syncToParent = () => {
  if (!seeding) emit('update', committed())
}

// When an item is picked in a row, resolve its retail SKU into the SKU column.
const resolveSku = (field) => {
  const row = field.doc
  const code = field.value
  if (!code) {
    row.nat_sku = ''
    syncToParent()
    return
  }
  frappe.db.get_value('Item', code, 'ifw_retailskusuffix').then((r) => {
    const sku = r && r.message && r.message.ifw_retailskusuffix
    if (!sku) {
      frappe.show_alert({ message: `No RetailSKUSuffix for ${code}`, indicator: 'red' })
      row.nat_item_code = ''
      row.nat_sku = ''
    } else {
      row.nat_sku = sku
    }
    control.grid.refresh()
    syncToParent()
  })
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
          get_query: () => ({ filters: { disabled: 0 } }),
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

  // The native standalone delete runs over async tasks (so reading mid-delete
  // misses rows) and Delete-All touches frm.doc. Replace both with synchronous,
  // multi-row-safe versions that sync afterwards.
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

// Re-seed when the parent changes the list externally (cascade / load from S3).
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
