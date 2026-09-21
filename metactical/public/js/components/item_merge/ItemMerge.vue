<template>
  <div class="p-4 space-y-4">
    <p class="text-sm text-muted mb-0">Replace the Variant Number attribute with real Item Attributes, one template family at a time.</p>

    <div class="im-tabs" role="tablist">
      <button role="tab" :class="{ active: inFlow }" :aria-selected="inFlow" @click="go()">New merge</button>
      <button role="tab" :class="{ active: route.view === 'codes' }" :aria-selected="route.view === 'codes'" @click="go('codes', route.template)">Item codes</button>
      <button role="tab" :class="{ active: !inFlow && route.view !== 'codes' }" :aria-selected="!inFlow && route.view !== 'codes'" @click="go('jobs')">Jobs</button>
    </div>

    <div v-if="inFlow" class="im-stepper" role="list">
      <div v-for="(s, i) in STEPS" :key="s.view" role="listitem" class="im-step"
           :class="{ current: i === stepIndex, done: i < stepIndex }" :aria-current="i === stepIndex ? 'step' : null">
        <span class="n">{{ i < stepIndex ? '✓' : i + 1 }}</span>
        <span class="min-w-0"><div class="t">{{ s.t }}</div><div class="s">{{ s.s }}</div></span>
      </div>
    </div>

    <StepTemplates v-if="route.view === 'templates'" ref="view" @chosen="(t) => go('variants', t)" />
    <StepVariants v-else-if="route.view === 'variants'" ref="view" :key="'v' + route.template" :template="route.template"
                  @next="go('align', route.template)" @back="go()" @renamed="(t) => go('variants', t)" />
    <StepAlign v-else-if="route.view === 'align'" ref="view" :key="'a' + route.template" :template="route.template"
               @queued="queued" @back="go('variants', route.template)" />
    <JobView v-else-if="route.view === 'job'" ref="view" :key="'j' + route.job" :job="route.job" />
    <ItemCodes v-else-if="route.view === 'codes'" ref="view" :template="route.template"
               @open="(t) => go('codes', t)" @queued="(job) => go('jobs', job)" />
    <JobsList v-else ref="view" @open="(job) => go('jobs', job)" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import StepTemplates from './StepTemplates.vue'
import StepVariants from './StepVariants.vue'
import StepAlign from './StepAlign.vue'
import JobView from './JobView.vue'
import JobsList from './JobsList.vue'
import ItemCodes from './ItemCodes.vue'
import { go, parseRoute } from './utils.js'

const STEPS = [
  { view: 'templates', t: 'Templates', s: 'Find and combine' },
  { view: 'variants', t: 'Variants', s: 'Attributes and new variants' },
  { view: 'align', t: 'Align', s: 'Line up OLD and NEW' },
  { view: 'job', t: 'Merge', s: 'Queue and track' },
]

const route = ref(parseRoute() || { view: 'templates' })
const view = ref(null)
// the job screen belongs to the stepper only when reached by queueing a merge from step 3
const fromFlow = ref(false)

const inFlow = computed(() => ['templates', 'variants', 'align'].includes(route.value.view)
  || (route.value.view === 'job' && fromFlow.value))
const stepIndex = computed(() => STEPS.findIndex((s) => s.view === route.value.view))

function syncRoute() {
  const next = parseRoute()
  if (!next) return  // another page is showing
  if (next.view !== 'job') fromFlow.value = false
  route.value = next
}

function queued(job) {
  fromFlow.value = true
  go('jobs', job)
}

// the page's refresh button in the Frappe toolbar
function refresh() {
  if (view.value && typeof view.value.refresh === 'function') view.value.refresh()
}

onMounted(() => frappe.router.on('change', syncRoute))
onBeforeUnmount(() => frappe.router.off && frappe.router.off('change', syncRoute))

defineExpose({ refresh, syncRoute })
</script>
