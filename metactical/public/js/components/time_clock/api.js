// Talks to metactical.time_tracker.api. Shared by the clock screen and the approvals screen.
const API = "metactical.time_tracker.api"

// Server rejections carry a human message in _server_messages; surface it instead of a stack trace.
// (frappe.call's error callback gets no response object here, so this talks to the endpoint directly.)
const serverMessage = (body, status) => {
  try {
    const msgs = JSON.parse(body._server_messages).map((m) => JSON.parse(m).message)
    const text = msgs.join(" ").replace(/<[^>]+>/g, "").trim()
    if (text) return text
  } catch (_) { /* fall through */ }
  if (status === 403) return "You don't have permission to do that."
  if (status === 401 || status === 410) return "Your session expired. Please log in again."
  return "Something went wrong. Please try again."
}

export const callBackend = async (method, args = {}) => {
  const res = await fetch(`/api/method/${API}.${method}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Frappe-CSRF-Token": frappe.csrf_token || window.csrf_token,
    },
    body: JSON.stringify(args),
  })
  let body = {}
  try { body = await res.json() } catch (_) { /* non-JSON error page */ }
  if (!res.ok) throw new Error(serverMessage(body, res.status))
  return body.message
}

export const errorText = (e) => (e && e.message) || "Something went wrong. Please try again."
