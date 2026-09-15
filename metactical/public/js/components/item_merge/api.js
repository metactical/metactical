// The only place the Item Merge screens talk to the backend.
// Dotted path to the whitelisted endpoints for this page (metactical/metactical/page/item_merge).
const API = 'metactical.metactical.page.item_merge.item_merge'

// Thin wrapper around frappe.call that returns the `message` payload. A frappe.throw on the server
// is shown by Frappe as its usual message dialog; the promise rejects so the screen can stop spinning.
const callBackend = (method, args = {}) =>
  new Promise((resolve, reject) => {
    frappe.call({
      method: `${API}.${method}`,
      args,
      callback: (r) => resolve(r.message),
      error: (r) => reject(r),
    })
  })

const json = (v) => JSON.stringify(v ?? null)

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
}

// Realtime progress pushed by metactical.item_merge.jobs while a job runs.
export const PROGRESS_EVENT = 'item_merge_progress'
