// The only place the Item Merge screens talk to the backend.
// Dotted path to the whitelisted endpoints for this page (metactical/metactical/page/item_merge).
const API = 'metactical.metactical.page.item_merge.item_merge'

// Thin wrapper around frappe.call that returns the `message` payload. A frappe.throw on the server
// is shown by Frappe as its usual message dialog; the promise rejects so the screen can stop spinning.
//
// The screens deliberately swallow the rejection, on the understanding that the reason is already on
// screen. That only holds for frappe.throw, which comes back with _server_messages. Anything else - a
// 500 with a traceback, a permission failure, a timeout, a dropped connection - would leave the
// button doing nothing at all with no explanation, so those are reported here instead.
const callBackend = (method, args = {}) =>
  new Promise((resolve, reject) => {
    frappe.call({
      method: `${API}.${method}`,
      args,
      callback: (r) => resolve(r.message),
      error: (r) => {
        reportIfSilent(method, r)
        reject(r)
      },
    })
  })

function reportIfSilent(method, response) {
  const shown = response && (response._server_messages || response.responseJSON?._server_messages)
  // always leave a breadcrumb: "it did nothing" is the hardest bug to chase
  console.error(`[item_merge] ${method} failed`, response)
  if (shown) return
  const status = response?.status || response?.responseJSON?.http_status_code
  frappe.show_alert({
    message: __('Item Merge: {0} failed{1}. See the browser console for details.',
      [method, status ? ` (HTTP ${status})` : '']),
    indicator: 'red',
  }, 10)
}

const json = (v) => JSON.stringify(v ?? null)

// The Autocomplete controls call these two themselves, by dotted path, so they are named here only
// to keep every server method the page uses in one file.
export const TEMPLATE_CODE_QUERY = `${API}.template_code_options`
export const TEMPLATE_NAME_QUERY = `${API}.template_name_options`

export const itemMergeApi = {
  // step 1: templates
  searchTemplates: (sku, name) => callBackend('search_templates', { sku, name }),
  checkConsolidation: (target, sources) => callBackend('check_consolidation', { target, sources: json(sources) }),
  consolidateTemplates: (target, sources, renameTo, confirmDifferentProducts = false) =>
    callBackend('consolidate_templates', {
      target, sources: json(sources), rename_to: renameTo, confirm_different_products: confirmDifferentProducts ? 1 : 0,
    }),
  renameTemplate: (template, newCode, itemName) => callBackend('rename_template', { template, new_code: newCode, item_name: itemName }),

  // step 2: variants
  getVariants: (template) => callBackend('get_variants', { template }),
  getAttributeValues: (attribute) => callBackend('get_attribute_values', { attribute }),
  suggestCombinations: (template, attributes) => callBackend('suggest_combinations', { template, attributes: json(attributes) }),
  createVariants: (template, attributes, combinations, styleName) =>
    callBackend('create_variants', { template, attributes: json(attributes), combinations: json(combinations), style_name: styleName }),

  // step 3: align
  getAlignment: (template) => callBackend('get_alignment', { template }),
  checkAlignment: (template, pairs, leftovers) =>
    callBackend('check_alignment', { template, pairs: json(pairs), leftovers: json(leftovers) }),
  fixSettings: (template, pairs) => callBackend('fix_settings', { template, pairs: json(pairs) }),

  // step 4: jobs
  queueMerge: (template, pairs, leftovers, options) =>
    callBackend('queue_merge', { template, pairs: json(pairs), leftovers: json(leftovers), options: json(options) }),
  queueItemChanges: (template, changes) => callBackend('queue_item_changes', { template, changes: json(changes) }),
  listJobs: (template) => callBackend('list_jobs', { template }),
  getJob: (job, live = true) => callBackend('get_job', { job, live: live ? 1 : 0 }),
  resumeJob: (job) => callBackend('resume_job', { job }),
  getReposts: (template) => callBackend('get_reposts', { template }),

  // website Item Detail rows (price list + slug) from the Storebuilder sites
  getWebsitePlan: (template) => callBackend('get_website_plan', { template }),
  applyWebsites: (template) => callBackend('apply_websites', { template }),
  checkWebsites: (template) => callBackend('check_websites', { template }),

  // the legacy Storebuilder products a merge consolidates away
  legacyWebsitePlan: (products) => callBackend('legacy_website_plan', { products: json(products) }),
  lookupLegacySlugs: (products, leadSources) =>
    callBackend('lookup_legacy_slugs', { products: json(products), lead_sources: json(leadSources) }),
  checkLegacySlugs: (rows) => callBackend('check_legacy_slugs', { rows: json(rows) }),
  saveLegacySlugs: (template, rows) => callBackend('save_legacy_slugs', { template, rows: json(rows) }),
  markNotPublished: (template, itemCode, on) =>
    callBackend('mark_not_published', { template, item_code: itemCode, on: on ? 1 : 0 }),
}

// Realtime progress pushed by metactical.item_merge.jobs while a job runs.
export const PROGRESS_EVENT = 'item_merge_progress'
