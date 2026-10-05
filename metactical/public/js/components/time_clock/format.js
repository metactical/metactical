// Date and duration formatting shared by the time clock screens. Dates read 01 - Jan - 2026.

// "2026-10-05 12:30:12.123456" is server-local wall time. Parse it as-is, never through UTC.
export const parse = (s) => {
  if (!s) return null
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : null
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
export const pad2 = (n) => String(n).padStart(2, "0")
export const dateParts = (d) => `${pad2(d.getDate())} - ${MONTHS[d.getMonth()]} - ${d.getFullYear()}`

export const asDate = (s) => parse(String(s).length === 10 ? s + " 00:00" : s)
export const fmtDate = (s) => { const d = s && asDate(s); return d ? dateParts(d) : "" }
export const fmtWeekday = (s) => { const d = s && asDate(s); return d ? d.toLocaleDateString("en", { weekday: "short" }) : "" }
export const fmtTime = (s) => {
  const d = parse(s)
  return d ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : ""
}
export const fmtDateTime = (s) => (s ? `${fmtDate(s)}, ${fmtTime(s)}` : "")

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
