// Small helpers shared by the Item Merge screens: Frappe dialogs and alerts, status pills, routing.

export const BAD_CODE = /[\s/\\%#?]/

// Status -> Frappe indicator colour (indicator-pill <colour>)
const PILL = {
  ready: 'green', ok: 'green', done: 'green', created: 'green', exists: 'green', deleted: 'green',
  fix: 'orange', attention: 'orange', interrupted: 'orange', notfound: 'orange', warn: 'orange', check: 'orange',
  blocked: 'red', failed: 'red', mismatch: 'red', error: 'red',
  running: 'blue', syncing: 'blue', unused: 'blue', planned: 'blue', added: 'blue', new: 'blue', issued: 'blue',
  queued: 'gray', skipped: 'gray', kept: 'gray', leftover: 'gray', waiting: 'gray', empty: 'gray', old: 'gray',
  validated: 'gray',
  // step 1, what Storebuilder holds for a template
  full: 'green', noexternalid: 'orange', wrongexternalid: 'orange', noslug: 'orange',
  notconfigured: 'orange', missing: 'red', unchecked: 'gray', nowebsite: 'gray',
  zeroprice: 'gray', stale: 'orange',
}
export const pillClass = (status) => `indicator-pill ${PILL[String(status || '').toLowerCase()] || 'gray'}`

export const alertOk = (message) => frappe.show_alert({ message, indicator: 'green' })
export const alertInfo = (message) => frappe.show_alert({ message, indicator: 'blue' })
export const alertWarn = (message) => frappe.show_alert({ message, indicator: 'orange' })

// A Frappe confirmation for anything that writes. Resolves true when confirmed.
// danger: the primary button is red (frappe.warn), for merges, renames and deletes.
export const confirmAction = ({ title, message, label = __('Continue'), danger = false }) =>
  new Promise((resolve) => {
    // Decide BEFORE hiding, and only once. onhide is what catches a dismissal (Esc, the X, the
    // backdrop), but hide() triggers it too - and whether that lands before or after the line under
    // it depends on the modal's fade transition. Settling first makes the answer not depend on that.
    let settled = false
    const settle = (value) => {
      if (settled) return
      settled = true
      resolve(value)
    }
    const html = `<div style="white-space:pre-line">${frappe.utils.escape_html(message)}</div>`
    const d = new frappe.ui.Dialog({
      title,
      fields: [{ fieldtype: 'HTML', fieldname: 'message', options: html }],
      primary_action_label: label,
      primary_action: () => { settle(true); d.hide() },
      secondary_action_label: __('Cancel'),
      secondary_action: () => { settle(false); d.hide() },
    })
    if (danger) d.get_primary_btn().removeClass('btn-primary').addClass('btn-danger')
    d.onhide = () => settle(false)
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

// A native Frappe Autocomplete mounted into a DOM node, fed by a whitelisted method that takes `txt`.
//
// Used where the value must be offered from ERP but does not have to BE one of the offers: the
// template search boxes take half a code ("RVX418") or a couple of words, which a Link control
// would refuse and blank out on blur. onInput(value) fires on every keystroke and on a pick.
export function makeAutocomplete(parent, { query, placeholder, value, onInput, onPick }) {
  parent.innerHTML = ''
  const control = frappe.ui.form.make_control({
    parent,
    render_input: true,
    df: {
      fieldtype: 'Autocomplete',
      placeholder,
      ignore_validation: true, // a partial search term is a valid thing to type here
      get_query: () => ({ query }),
    },
  })
  control.refresh()
  if (value) control.set_value(value)
  // Awesomplete highlights the first suggestion by default, so Enter would replace a deliberate
  // partial term with a full code. Leave nothing highlighted until the user arrows onto it.
  if (control.awesomplete) control.awesomplete.autoFirst = false
  const report = () => onInput?.(control.$input.val() || '')
  control.$input.on('input change awesomplete-selectcomplete', () => setTimeout(report, 0))
  // a pick from the dropdown is a decision, not just typing: it can act straight away
  control.$input.on('awesomplete-selectcomplete', () => setTimeout(() => onPick?.(control.$input.val() || ''), 0))
  return {
    control,
    set(v) { control.set_value(v || '') },
    value: () => control.$input.val() || '',
  }
}
