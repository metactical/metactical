<template>
  <label class="tc-zone">
    <span class="tc-zone-label">Show times in</span>
    <select :value="zoneState.mode" aria-label="Time zone for display" @change="choose($event.target.value)">
      <option value="server">Server time · {{ describe(zoneState.serverTz) }}</option>
      <option value="browser">My computer · {{ describe(browserTz()) }}</option>
      <option v-for="z in ZONES" :key="z.value" :value="z.value">{{ z.label }} · {{ abbr(z.value) }}</option>
    </select>
  </label>
</template>

<script setup>
import { callBackend } from "./api"
import { zoneState, browserTz, ZONES } from "./zone"
import { zoneAbbr } from "./format"

const abbr = (tz) => zoneAbbr(tz, Date.now())
const describe = (tz) => (tz === "UTC" ? "UTC" : `${tz.replace(/_/g, " ")}, ${abbr(tz)}`)

// Display only: it changes how times are shown, never what is stored. Remembered per user.
async function choose(value) {
  zoneState.mode = value
  try {
    await callBackend("set_display_zone", { zone: value })
  } catch (_) { /* still applied for this visit */ }
}
</script>
