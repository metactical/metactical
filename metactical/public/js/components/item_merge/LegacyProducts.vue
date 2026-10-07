<template>
  <!-- What the merge will drop from the websites, as it stands. The External IDs and slugs behind
       this were captured on the Find Template screen, before anything was combined - by now the
       templates they name are already gone, and the register is all that is left of them. -->
  <section class="im-card">
    <div class="flex items-center flex-wrap gap-2">
      <h3 class="im-card-title">Legacy website products</h3>
      <div class="flex flex-wrap gap-1 ml-auto">
        <span v-if="dropping.length" :class="pillClass('deleted')">{{ dropping.length }} to drop</span>
      </div>
      <button class="btn btn-default btn-xs" :disabled="busy" @click="load">{{ busy ? 'Reading…' : 'Refresh' }}</button>
    </div>
    <p class="im-lede">
      Each template this merge consolidated away is its own product on the websites. These are dropped
      once the merge is done, and not re-created. The surviving template's own product stays: the drop
      skips any slug a live item still publishes.
    </p>

    <div v-if="!dropping.length" class="text-sm text-muted">
      Nothing was captured for this template, so no website product is dropped.
    </div>
    <div v-else class="im-table-wrap">
      <table class="im-table">
        <thead>
          <tr><th>Legacy template</th><th>Website</th><th>Slug</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in dropping" :key="r.product + '|' + r.lead_source">
            <td class="font-mono whitespace-nowrap">{{ r.product }}</td>
            <td>
              <div class="text-muted">{{ r.lead_source }}</div>
              <div class="text-xs text-faint">{{ r.site }}</div>
            </td>
            <td class="font-mono">{{ r.slug }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { itemMergeApi } from './api.js'
import { pillClass } from './utils.js'

const props = defineProps({ template: { type: String, default: '' } })
const emit = defineEmits(['change'])

const rows = ref([])
const busy = ref(false)

const dropping = computed(() => rows.value.filter((r) => r.slug))

watch(dropping, () => emit('change', { dropping: dropping.value.length }), { immediate: true })

async function load() {
  if (!props.template) {
    rows.value = []
    return
  }
  busy.value = true
  try {
    const res = await itemMergeApi.legacyDropPlan(props.template)
    rows.value = res.rows || []
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

onMounted(load)
watch(() => props.template, load)

defineExpose({ load })
</script>
