<template>
  <!-- Storebuilder maps a product's variants through its External ID, which must equal the ERP template
       code. Per website row: External ID vs template code and variant counts, read from that site's
       Storebuilder copy in Metabase and dated with the age of the copy. -->
  <div class="space-y-2">
    <div class="flex items-center flex-wrap gap-2">
      <span class="im-label">Website check</span>
      <span v-if="result && !result.rows.length" class="text-sm text-muted">No website rows with a slug yet.</span>
      <span v-else-if="result && mismatches" class="indicator-pill red">{{ mismatches }} mismatch(es)</span>
      <span v-else-if="result && problems" class="indicator-pill orange">{{ problems }} not checked</span>
      <span v-else-if="notConfigured" class="indicator-pill orange" :title="notConfigured">Metabase not set up</span>
      <span v-else-if="result" class="indicator-pill green">maps to {{ template }}</span>
      <span class="ml-auto text-xs text-muted" v-if="checkedAt">checked {{ checkedAt }}</span>
      <button class="btn btn-default btn-xs" :disabled="busy" @click="run">
        {{ busy ? 'Checking…' : result ? 'Recheck' : 'Check websites' }}
      </button>
    </div>
    <div v-if="result && result.rows.length" class="im-table-wrap">
      <table class="im-table">
        <thead>
          <tr>
            <th>Price list</th><th>Website</th><th>External ID</th><th class="r">Variants site / ERP</th><th>Status</th>
            <th>Copy as of</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in result.rows" :key="r.price_list">
            <td class="whitespace-nowrap">{{ r.price_list }}</td>
            <td><div class="text-muted">{{ r.site }}</div><div class="font-mono text-xs text-faint">{{ r.slug }}</div></td>
            <td class="font-mono whitespace-nowrap" :class="{ 'text-danger font-semibold': r.external_id_match === false }">
              {{ r.external_id === null ? '-' : (r.external_id || '(blank)') }}
            </td>
            <td class="r tabular-nums whitespace-nowrap" :class="{ 'text-danger font-semibold': r.count_match === false }">
              {{ r.sb_variants ?? '-' }} / {{ r.erp_variants }}
            </td>
            <td>
              <span :class="pillClass(r.status)">{{ r.status === 'notFound' ? 'not found' : r.status }}</span>
              <div v-if="r.note" class="text-xs mt-1" :class="{ 'text-danger': r.status === 'mismatch' }">{{ r.note }}</div>
              <div v-if="r.unmatched_skus && r.unmatched_skus.length" class="text-xs text-muted">
                site variant SKUs not in ERP (info): <span class="font-mono">{{ r.unmatched_skus.slice(0, 6).join(', ') }}</span>
              </div>
            </td>
            <td class="whitespace-nowrap text-xs tabular-nums" :class="r.as_of ? 'text-muted' : 'text-faint'">
              {{ r.as_of || '-' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="result && result.rows.length" class="text-xs text-muted mb-0">
      Read from each site's Storebuilder copy in Metabase, which can be days behind the live site - a mismatch right after a
      merge is expected until the copy refreshes. Fix the External ID in Storebuilder admin, then Recheck once it has.
    </p>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { itemMergeApi } from './api.js'
import { pillClass } from './utils.js'

const props = defineProps({
  template: { type: String, required: true },
  initial: { type: Object, default: null }, // a check the job already ran
  auto: { type: Boolean, default: false }, // run on mount when there is no initial result
})

const result = ref(props.initial)
const busy = ref(false)
const checkedAt = ref(props.initial ? 'when the job ran' : '')

async function run() {
  busy.value = true
  try {
    result.value = await itemMergeApi.checkWebsites(props.template)
    checkedAt.value = new Date().toLocaleTimeString()
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

onMounted(() => { if (!result.value && props.auto) run() })
watch(() => props.initial, (v) => { if (v) { result.value = v; checkedAt.value = 'when the job ran' } })
watch(() => props.template, () => { result.value = null; if (props.auto) run() })

const mismatches = computed(() => (result.value?.rows || []).filter((r) => r.status === 'mismatch').length)
const problems = computed(() => (result.value?.rows || []).filter((r) => ['notFound', 'error'].includes(r.status)).length)
const notConfigured = computed(() => result.value?.not_configured || '')

defineExpose({ run })
</script>
