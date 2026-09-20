<template>
  <!-- What the merge will drop from the websites, as it stands. The slugs themselves are recorded a
       screen earlier, on Variants, while the old items still exist - this is the last look at them
       before the merge deletes those items for good. -->
  <section class="im-card">
    <div class="flex items-center flex-wrap gap-2">
      <h3 class="im-card-title">Legacy website products</h3>
      <div class="flex flex-wrap gap-1 ml-auto">
        <span v-if="dropping.length" :class="pillClass('deleted')">{{ dropping.length }} to drop</span>
        <span v-if="unchecked" :class="pillClass('warn')">{{ unchecked }} page(s) not live</span>
        <span v-if="withoutSlug.length" :class="pillClass('warn')">{{ withoutSlug.length }} item(s) with no slug</span>
      </div>
      <button class="btn btn-default btn-xs" :disabled="busy" @click="load">{{ busy ? 'Reading…' : 'Refresh' }}</button>
    </div>
    <p class="im-lede">
      Each old variant is its own product on the websites. These are dropped once the merge is done, and not re-created.
      To add or change a slug, go back to <a class="im-link" href="#" @click.prevent="emit('edit')">Variants</a> and open the
      item's row.
    </p>

    <div v-if="!products.length" class="text-sm text-muted">Nothing to merge yet, so there is nothing to drop.</div>

    <template v-else>
      <div v-if="withoutSlug.length" class="im-note warn mb-2 text-xs">
        <b>{{ withoutSlug.length }} old variant(s) have no website slug recorded:</b>
        <span class="font-mono">{{ withoutSlug.slice(0, 8).join(', ') }}{{ withoutSlug.length > 8 ? '…' : '' }}</span>.
        If they are live on a website, record the slug now - after the merge these items are gone and the products they
        leave behind cannot be found.
      </div>

      <div v-if="dropping.length" class="im-table-wrap">
        <table class="im-table">
          <thead>
            <tr><th>Legacy item</th><th>Website</th><th>Slug</th><th>Page</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in dropping" :key="r.product + '|' + r.lead_source">
              <td class="font-mono whitespace-nowrap">{{ r.product }}</td>
              <td>
                <div class="text-muted">{{ r.lead_source }}</div>
                <div class="text-xs text-faint">{{ r.site }}</div>
              </td>
              <td class="font-mono">{{ r.slug }}</td>
              <td>
                <span :class="pillClass(r.state === 'Live' ? 'ok' : r.state === 'Not Checked' ? 'skipped' : 'error')">
                  {{ (r.state || 'Not Checked').toLowerCase() }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-sm text-muted">No slugs recorded, so no website product is dropped.</div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { itemMergeApi } from './api.js'
import { pillClass } from './utils.js'

const props = defineProps({
  // The legacy item codes this merge deletes: the OLD side of every pair, plus the leftovers.
  products: { type: Array, default: () => [] },
})
const emit = defineEmits(['change', 'edit'])

const plan = ref(null)
const busy = ref(false)

const rows = computed(() => plan.value?.rows || [])
const dropping = computed(() => rows.value.filter((r) => r.slug))
const unchecked = computed(() => dropping.value.filter((r) => !r.verified).length)
const withoutSlug = computed(() => (plan.value?.without_slug || []).filter((c) => props.products.includes(c)))

watch([dropping, withoutSlug], () => emit('change', {
  dropping: dropping.value.length, unchecked: unchecked.value, withoutSlug: withoutSlug.value.length,
}), { immediate: true })

async function load() {
  if (!props.products.length) {
    plan.value = null
    return
  }
  busy.value = true
  try {
    plan.value = await itemMergeApi.legacyWebsitePlan(props.products)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}

onMounted(load)
watch(() => props.products.join(','), load)

defineExpose({ load })
</script>
