// Small helpers shared by the Item Merge screens: Frappe dialogs and alerts, status pills, routing.

export const BAD_CODE = /[\s/\\%#?]/

// Status -> Frappe indicator colour (indicator-pill <colour>)
const PILL = {
  ready: 'green', ok: 'green', done: 'green', created: 'green', exists: 'green', deleted: 'green',
  fix: 'orange', attention: 'orange', interrupted: 'orange', notfound: 'orange', warn: 'orange', check: 'orange',
  blocked: 'red', failed: 'red', mismatch: 'red', error: 'red',
  running: 'blue', syncing: 'blue', unused: 'blue', planned: 'blue', added: 'blue', new: 'blue',
  queued: 'gray', skipped: 'gray', kept: 'gray', leftover: 'gray', waiting: 'gray', empty: 'gray', old: 'gray',
}
export const pillClass = (status) => `indicator-pill ${PILL[String(status || '').toLowerCase()] || 'gray'}`

export const alertOk = (message) => frappe.show_alert({ message, indicator: 'green' })
export const alertInfo = (message) => frappe.show_alert({ message, indicator: 'blue' })
export const alertWarn = (message) => frappe.show_alert({ message, indicator: 'orange' })

// A Frappe confirmation for anything that writes. Resolves true when confirmed.
// danger: the primary button is red (frappe.warn), for merges, renames and deletes.
export const confirmAction = ({ title, message, label = __('Continue'), danger = false }) =>
  new Promise((resolve) => {
    const html = `<div style="white-space:pre-line">${frappe.utils.escape_html(message)}</div>`
    const d = new frappe.ui.Dialog({
      title,
      fields: [{ fieldtype: 'HTML', fieldname: 'message', options: html }],
      primary_action_label: label,
      primary_action: () => { d.hide(); resolve(true) },
      secondary_action_label: __('Cancel'),
      secondary_action: () => { d.hide(); resolve(false) },
    })
    if (danger) d.get_primary_btn().removeClass('btn-primary').addClass('btn-danger')
    d.onhide = () => resolve(false)
    d.show()
  })

export const fmtDateTime = (s) => (s ? frappe.datetime.str_to_user(String(s).slice(0, 19)) : '-')
export const prettyDate = (s) => (s ? frappe.datetime.prettyDate(String(s).slice(0, 19)) : 'never')
export const num = (v) => (v === null || v === undefined || v === '' ? '-' : Number(v).toLocaleString())

// Routes inside the page: /app/item-merge[/view[/argument]]
//   (none)               step 1 - find templates
//   variants/<template>  step 2
//   align/<template>     step 3
//   jobs[/<job>]         jobs list, or one job (step 4)
//   codes[/<template>]   item codes, names and retail SKUs - any time, e.g. after a merge
export const PAGE = 'item-merge'
export const go = (...parts) => frappe.set_route(PAGE, ...parts.filter((p) => p !== undefined && p !== null && p !== ''))
export const itemUrl = (code) => `/app/item/${encodeURIComponent(code)}`

export function parseRoute(route = frappe.get_route()) {
  const [page, view, arg] = route || []
  if (page !== PAGE) return null
  if (view === 'jobs' && arg) return { view: 'job', job: arg }
  if (view === 'jobs') return { view: 'jobs' }
  if (view === 'codes') return { view: 'codes', template: arg || '' }
  if ((view === 'variants' || view === 'align') && arg) return { view, template: arg }
  return { view: 'templates' }
}

// A native Frappe Link control mounted into a DOM node; onPick(value) runs on a real change.
export function makeLink(parent, { options, placeholder, filters, onPick, value }) {
  parent.innerHTML = ''
  const control = frappe.ui.form.make_control({
    parent,
    render_input: true,
    df: { fieldtype: 'Link', options, placeholder, get_query: filters ? () => ({ filters }) : undefined },
  })
  control.refresh()
  if (value) control.set_value(value)
  let last = value || ''
  // `awesomplete-selectcomplete` for a pick from the dropdown, `change` for a typed value on blur;
  // one pick usually fires both, so only a different value counts.
  control.$input.on('change awesomplete-selectcomplete', () => {
    setTimeout(() => {
      const v = control.get_value() || ''
      if (v !== last) { last = v; onPick(v) }
    }, 0)
  })
  return {
    control,
    set(v) { last = v || ''; control.set_value(v || '') },
  }
}
