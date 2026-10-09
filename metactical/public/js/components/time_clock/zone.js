// Which time zone the screens DISPLAY times in. Stored times never change: they are server time.
import { reactive, computed } from "vue"

export const zoneState = reactive({
  serverTz: "UTC", // IANA name of the site (server) time zone, from the API
  mode: "server", // "server" | "browser" | an IANA name from ZONES
})

export const browserTz = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"

// The IANA zone currently used for display.
export const activeTz = computed(() => {
  if (zoneState.mode === "server") return zoneState.serverTz
  if (zoneState.mode === "browser") return browserTz()
  return zoneState.mode
})

// Keep in step with DISPLAY_ZONES in time_tracker/core.py
export const ZONES = [
  { value: "America/Vancouver", label: "Pacific" },
  { value: "America/Edmonton", label: "Mountain" },
  { value: "America/Winnipeg", label: "Central" },
  { value: "America/Toronto", label: "Eastern" },
  { value: "America/Halifax", label: "Atlantic" },
  { value: "UTC", label: "UTC" },
]
