// Date and duration formatting shared by the time clock screens. Dates read 01 - Jan - 2026.
//
// Instants arrive from the API as ISO strings WITH a UTC offset, so they are unambiguous and can be shown in
// any zone (see zone.js). Plain dates (2026-10-05) are calendar days in server time and are never converted.
import { activeTz, zoneState } from "./zone"

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
export const pad2 = (n) => String(n).padStart(2, "0")
const HAS_OFFSET = /([zZ]|[+-]\d{2}:?\d{2})$/
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

// ---- zone arithmetic (no library: Intl knows the rules, including daylight saving)

const partsOf = (ms, tz) => {
  const f = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  })
  const o = {}
  f.formatToParts(new Date(ms)).forEach((x) => { if (x.type !== "literal") o[x.type] = +x.value })
  return { y: o.year, m: o.month, d: o.day, h: o.hour === 24 ? 0 : o.hour, mi: o.minute, s: o.second }
}

const offsetMs = (ms, tz) => {
  const p = partsOf(ms, tz)
  return Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s) - Math.floor(ms / 1000) * 1000
}

// Wall-clock time in `tz` -> the instant it names (two passes settle the offset around daylight saving).
export const wallToMs = (y, m, d, h, mi, s, tz) => {
  const naive = Date.UTC(y, m - 1, d, h, mi, s)
  let t = naive
  for (let i = 0; i < 2; i++) t = naive - offsetMs(t, tz)
  return t
}

// "2026-10-05T16:18" as it reads on a wall in `tz` (for <input type="datetime-local">)
export const wallInZone = (ms, tz) => {
  const p = partsOf(ms, tz)
  return `${p.y}-${pad2(p.m)}-${pad2(p.d)}T${pad2(p.h)}:${pad2(p.mi)}`
}

// "2026-10-05T16:18" typed on a wall in `tz` -> instant
export const wallStrToMs = (str, tz) => {
  const m = String(str).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)
  return m ? wallToMs(+m[1], +m[2], +m[3], +m[4], +m[5], +(m[6] || 0), tz) : null
}

// ---- parsing

// An instant (ISO with offset) -> Date. A string with no offset is server wall-clock time.
export const parse = (s) => {
  if (!s) return null
  if (s instanceof Date) return s
  const str = String(s)
  if (HAS_OFFSET.test(str)) {
    const d = new Date(str)
    return isNaN(d) ? null : d
  }
  const ms = wallStrToMs(str, zoneState.serverTz)
  return ms === null ? null : new Date(ms)
}

// A calendar day (no time zone involved).
export const asDate = (s) => {
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})/)
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null
}
const dayParts = (y, m, d) => `${pad2(d)} - ${MONTHS[m - 1]} - ${y}`

// ---- display in the chosen zone

const inZone = (d, opts) => new Intl.DateTimeFormat("en", { timeZone: activeTz.value, ...opts }).format(d)

export const fmtTime = (s) => { const d = parse(s); return d ? inZone(d, { hour: "numeric", minute: "2-digit" }) : "" }

export const fmtDate = (s) => {
  if (!s) return ""
  if (DATE_ONLY.test(String(s))) { const d = asDate(s); return dayParts(d.getFullYear(), d.getMonth() + 1, d.getDate()) }
  const d = parse(s)
  if (!d) return ""
  const p = partsOf(d.getTime(), activeTz.value)
  return dayParts(p.y, p.m, p.d)
}

export const fmtWeekday = (s) => {
  if (!s) return ""
  if (DATE_ONLY.test(String(s))) return asDate(s).toLocaleDateString("en", { weekday: "short" })
  const d = parse(s)
  return d ? inZone(d, { weekday: "short" }) : ""
}

export const fmtDateTime = (s) => (s ? `${fmtDate(s)}, ${fmtTime(s)}` : "")

// the live clock (takes milliseconds)
export const fmtClock = (ms) => inZone(new Date(ms), { hour: "numeric", minute: "2-digit", second: "2-digit" })
export const fmtDateMs = (ms) => { const p = partsOf(ms, activeTz.value); return dayParts(p.y, p.m, p.d) }
export const fmtWeekdayLong = (ms) => inZone(new Date(ms), { weekday: "long" })

// "America/Toronto (EDT)"
export const zoneAbbr = (tz, ms) => {
  const part = new Intl.DateTimeFormat("en", { timeZone: tz, timeZoneName: "short" })
    .formatToParts(new Date(ms)).find((x) => x.type === "timeZoneName")
  return part ? part.value : ""
}
export const zoneLabelFor = (tz, ms = Date.now()) => (tz === "UTC" ? "UTC" : `${tz.replace(/_/g, " ")} (${zoneAbbr(tz, ms)})`)

// ---- durations

export const fmtDuration = (h) => {
  const mins = Math.round((h || 0) * 60)
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`
}
// +0h 30m / -0h 25m
export const fmtDelta = (h) => {
  const mins = Math.round((h || 0) * 60)
  const sign = mins < 0 ? "-" : "+"
  const a = Math.abs(mins)
  return `${sign}${Math.floor(a / 60)}h ${pad2(a % 60)}m`
}
