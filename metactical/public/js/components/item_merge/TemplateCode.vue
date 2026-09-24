<template>
  <!-- The template code + item name in the locked header, with an inline edit of both. -->
  <span class="flex items-center flex-wrap gap-2 min-w-0">
    <template v-if="!editing">
      <span class="im-code">{{ template }}</span>
      <a v-if="template" class="im-link text-sm" :href="itemUrl(template)" target="_blank" rel="noopener">{{ itemName }}</a>
      <button class="btn btn-default btn-xs" :disabled="loading || !!lockedReason" :title="editTitle" @click="start">
        Edit SKU / name
      </button>
    </template>
    <template v-else>
      <form class="flex items-center flex-wrap gap-2" @submit.prevent="save" @keydown.esc="editing = false">
        <input ref="codeInput" v-model="code" class="form-control input-sm font-mono" style="width: 200px"
               :disabled="!!codeLockedReason" :title="codeLockedReason" aria-label="Template SKU" placeholder="Template SKU" />
        <input v-model="name" class="form-control input-sm" style="width: 360px; max-width: 100%" aria-label="Template item name" placeholder="Item name" />
        <button type="submit" class="btn btn-danger btn-xs" :disabled="!!problem || busy">{{ busy ? 'Saving…' : 'Save' }}</button>
        <button type="button" class="btn btn-default btn-xs" :disabled="busy" @click="editing = false">Cancel</button>
      </form>
      <span v-if="problem" class="text-xs text-muted">{{ problem }}</span>
    </template>
  </span>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { itemMergeApi } from './api.js'
import { BAD_CODE, alertOk, confirmAction, itemUrl } from './utils.js'

const props = defineProps({
  template: { type: String, required: true },
  itemName: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  codeLockedReason: { type: String, default: '' }, // non-empty: the code can't change here (the name still can)
  lockedReason: { type: String, default: '' }, // non-empty: nothing can change here
})
const emit = defineEmits(['renamed'])

const editing = ref(false)
const code = ref('')
const name = ref('')
const busy = ref(false)
const codeInput = ref(null)

// GOL1651-tempt -> GOL1651, NPTAB13RD-temp -> NPTAB13RD
const suggestion = computed(() => props.template.replace(/-temp?t?$/i, ''))
const codeChanged = computed(() => !!code.value.trim() && code.value.trim() !== props.template)
const nameChanged = computed(() => !!name.value.trim() && name.value.trim() !== (props.itemName || ''))
const editTitle = computed(() => props.lockedReason
  || (props.codeLockedReason ? `Change the template name (${props.codeLockedReason})` : 'Change the template SKU or name'))
const problem = computed(() => {
  if (!code.value.trim()) return 'Type the template code'
  if (!name.value.trim()) return 'Type the item name'
  if (BAD_CODE.test(code.value)) return "Item codes can't contain spaces or / \\ % # ?"
  if (!codeChanged.value && !nameChanged.value) return 'Change the code or the name'
  return ''
})

async function start() {
  code.value = props.codeLockedReason ? props.template : (suggestion.value || props.template)
  name.value = props.itemName || ''
  editing.value = true
  await nextTick()
  codeInput.value?.focus()
  codeInput.value?.select()
}

async function save() {
  if (problem.value) return
  const parts = []
  if (codeChanged.value) parts.push(`Rename template ${props.template} to ${code.value.trim()}. Its variants follow; new variant codes start with the new code.`)
  if (nameChanged.value) parts.push(`Change its item name to "${name.value.trim()}". Variants keep their own names.`)
  const ok = await confirmAction({ title: 'Update template?', message: parts.join('\n'), label: 'Save', danger: true })
  if (!ok) return
  busy.value = true
  try {
    const res = await itemMergeApi.renameTemplate(props.template, codeChanged.value ? code.value.trim() : null,
      nameChanged.value ? name.value.trim() : null)
    alertOk([res.renamed_from && `${res.renamed_from} → ${res.template}`, nameChanged.value && `name: ${res.item_name}`]
      .filter(Boolean).join(' · ') || 'Template updated')
    editing.value = false
    emit('renamed', res.template)
  } catch (e) {
    // Frappe has shown the reason
  } finally {
    busy.value = false
  }
}
</script>
