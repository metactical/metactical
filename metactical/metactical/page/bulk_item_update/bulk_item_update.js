/**
 * Bulk Item Update – Full Page Application
 *
 * Three views:
 *   1. Initial Screen   – select saved rules, create new
 *   2. Editor Screen    – build Search conditions + Actions inline
 *   3. Preview Screen   – table with before/after, execute buttons top & bottom
 *
 * Actions use a message-type pattern:
 *   action_type (e.g. UpdatePrice, DisableItem) + action_value
 *
 * CTRL+N adds a new row to whichever section (conditions/actions) was last focused.
 */

const API = "metactical.metactical.doctype.bulk_update_rule.bulk_update_rule";

// ─── Search condition field options ───
const FIELD_OPTIONS = [
    { value: "item_code",        label: "Item Code" },
    { value: "item_name",        label: "Item Name" },
    { value: "item_group",       label: "Item Group" },
    { value: "is_trashed",       label: "Is Trashed" },
    { value: "has_variants",     label: "Has Variants" },
    { value: "disabled",         label: "Disabled" },
    { value: "ifw_retailskusuffix", label: "Retail SKU" },
    { value: "brand",           label: "Brand" },
    { value: "supplier",        label: "Supplier (Item Supplier)" },
    { value: "default_supplier", label: "Default Supplier (Item Default)" },
    { value: "has_inventory",   label: "Has Inventory" },
    { value: "variants_have_no_inventory", label: "All Variants Have No Inventory" },
    { value: "standard_rate",    label: "Standard Rate (Item Price)" },
    { value: "price_list_rate",  label: "Price List Rate (Item Price)" },
    { value: 'variant_of',                label: 'Variant Of' },
    { value: 'neb_variantavailabilityrule', label: 'Variant Availability Rule' },
    { value: 'sb_tag',                    label: 'SB Tag' },
    { value: 'website_specification_label', label: 'Website Specification Label' },
];

const OPERATOR_OPTIONS = [
    "Begins With", "Ends With", "Contains",
    "Equals To", "Not Equal To", "Does Not Contain", 
    "Greater Than", "Less Than",
    "Greater Than Or Equal", "Less Than Or Equal",
    "In", "Not In", "Is Set", "Is Not Set"
];

// ─── Action types ───
const ACTION_TYPE_OPTIONS = [
    { value: "UpdateItemGroup",              label: "Update Item Group" },
    { value: "AddTag",                       label: "Add Tag" },
    { value: "RemoveTag",                    label: "Remove Tag" },
    { value: "AddSBTag",                     label: "Add SB Tag" },
    { value: "RemoveSBTag",                  label: "Remove SB Tag" },
    { value: "DisableItem",                  label: "Disable Item" },
    { value: "EnableItem",                   label: "Enable Item" },
    { value: "UpdateValuationRate",          label: "Update Valuation Rate" },
    { value: "UpdateBrand",                  label: "Update Brand" },
    { value: "UpdateLastPingedOn",           label: "Update Last Pinged On" },
    { value: "UpdateVariantAvailabilityRule", label: "Update Variant Availability Rule" },
];

const NO_VALUE_ACTIONS = new Set(["DisableItem", "EnableItem", "UpdateLastPingedOn"]);
const OPTIONAL_VALUE_ACTIONS = new Set(["UpdateVariantAvailabilityRule"]);

// Action types that should render a Link field instead of a text input
const ACTION_LINK_MAP = {
    "UpdateItemGroup":               "Item Group",
    "UpdateBrand":                   "Brand",
    "UpdateDefaultWarehouse":        "Warehouse",
    "AddTag":                        "Tag",
    "RemoveTag":                     "Tag",
    "AddSBTag":                      "SB Tag",
    "RemoveSBTag":                   "SB Tag",
    "UpdateVariantAvailabilityRule": "Variant Availability Rule",
};

const PRICE_FIELDS = new Set(["price_list_rate", "standard_rate"]);

frappe.pages["bulk-item-update"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Bulk Item Update",
        single_column: true,
    });

    // ─── State ───
    let state = {
        view: "initial",
        rule_name: "",
        description: "",
        target_doctype: "Item",
        existing_rule: null,
        conditions: [],
        actions: [],
        preview_data: null,
        preview_start: 0,
        preview_limit: 20,
    };

    const $main = $(page.main);
    $main.html('<div id="bulk-update-app"></div>');
    const $app = $main.find("#bulk-update-app");

    // ═══════════════════════════════════════════════════════════════════
    //  RENDER ROUTER
    // ═══════════════════════════════════════════════════════════════════
    function render() {
        $app.empty();
        $(document).off("keydown.biu_editor");
        if (state.view === "initial") render_initial();
        else if (state.view === "editor") render_editor();
        else if (state.view === "preview") render_preview();
    }

    // ═══════════════════════════════════════════════════════════════════
    //  1. INITIAL SCREEN
    // ═══════════════════════════════════════════════════════════════════
    function render_initial() {
        page.set_title("Bulk Item Update");

        $app.html(`
            <div class="biu-initial">
                <p class="biu-intro">
                    Create rules to bulk-update Item fields. Each rule has
                    <strong>search conditions</strong> (which items to match) and
                    <strong>actions</strong> (what to change). Rules are saved for reuse.
                    Updates run in the background.
                </p>

                <div class="biu-selector-row">
                    <select id="biu-rule-select" class="form-control">
                        <option value="">-- Saved Rules List --</option>
                    </select>
                    <button id="biu-btn-show" class="btn btn-default btn-sm">Show Rule</button>
                </div>

                <button id="biu-btn-new" class="btn btn-primary btn-sm btn-block mt-3">
                    + New Rule Set
                </button>

                <div class="biu-section-label">Most Recent Rules</div>
                <div id="biu-recent-list"></div>
            </div>
        `);

        frappe.call({
            method: API + ".get_recent_rules",
            args: { limit: 50 },
            callback(r) {
                const rules = r.message || [];
                const $sel = $app.find("#biu-rule-select");
                rules.forEach(rule => {
                    $sel.append(`<option value="${rule.name}">${frappe.utils.escape_html(rule.rule_name)}</option>`);
                });

                const $list = $app.find("#biu-recent-list");
                if (!rules.length) {
                    $list.html('<p class="text-muted">No rules yet. Create your first rule set.</p>');
                    return;
                }

                rules.slice(0, 15).forEach(rule => {
                    const sc = { Completed: "green", Running: "blue", Queued: "orange", Failed: "red" }[rule.execution_status] || "gray";
                    $list.append(`
                        <div class="biu-rule-card" data-rule="${rule.name}">
                            <div class="d-flex justify-content-between align-items-center">
                                <a class="biu-rule-link">${frappe.utils.escape_html(rule.rule_name)}</a>
                                ${rule.execution_status
                                    ? `<span class="indicator-pill ${sc}">${rule.execution_status}</span>`
                                    : ""}
                            </div>
                            ${rule.description
                                ? `<p class="text-muted small mb-0">${frappe.utils.escape_html(rule.description)}</p>`
                                : ""}
                            <div class="text-muted text-xs mt-1">
                                ${rule.last_executed_on
                                    ? `Last run: ${frappe.datetime.prettyDate(rule.last_executed_on)} · ${rule.last_match_count || 0} matches`
                                    : "Never executed"}
                            </div>
                        </div>
                    `);
                });

                $list.find(".biu-rule-card").on("click", function () {
                    load_rule_into_editor($(this).data("rule"));
                });
            },
        });

        $app.find("#biu-btn-show").on("click", () => {
            const v = $app.find("#biu-rule-select").val();
            if (!v) return frappe.show_alert({ message: "Select a rule first.", indicator: "orange" });
            load_rule_into_editor(v);
        });

        $app.find("#biu-btn-new").on("click", () => {
            state.existing_rule = null;
            state.rule_name = "";
            state.description = "";
            state.conditions = [default_condition()];
            state.actions = [default_action()];
            state.view = "editor";
            render();
        });
    }

    function load_rule_into_editor(rule_name) {
        frappe.call({
            method: API + ".load_rule_data",
            args: { rule_name },
            callback(r) {
                const d = r.message;
                state.existing_rule = d.name;
                state.rule_name = d.rule_name;
                state.description = d.description;
                state.target_doctype = d.target_doctype;
                state.conditions = d.conditions.length ? d.conditions : [default_condition()];
                state.actions = d.actions.length ? d.actions : [default_action()];
                state.view = "editor";
                render();
            },
        });
    }

    function default_condition() {
        return { logic_operator: "And", field_name: "item_code", operator: "Equals To", value: "", custom_field_name: "" };
    }

    function default_action() {
        return { action_type: "UpdateItemGroup", action_value: "" };
    }

    // ═══════════════════════════════════════════════════════════════════
    //  2. EDITOR SCREEN
    // ═══════════════════════════════════════════════════════════════════
    function render_editor() {
        page.set_title(state.existing_rule ? `Edit Rule: ${state.rule_name}` : "New Rule Set");

        $app.html(`
            <div class="biu-editor">
                <div class="biu-topbar">
                    <button class="btn btn-xs btn-default biu-btn-back">← Back</button>
                    <div class="biu-rule-name-wrap">
                        <input type="text" id="biu-rule-name" class="form-control form-control-sm"
                               placeholder="Rule Name *" value="${frappe.utils.escape_html(state.rule_name)}">
                    </div>
                </div>

                <div class="biu-price-note">
                    <kbd>Ctrl+B</kbd> add row to filters
                    <kbd>Ctrl+S</kbd> save
                </div>

                <!-- SEARCH CONDITIONS -->
                <div class="biu-section" id="biu-section-conditions">
                    <div class="biu-section-header">
                        <h5>Search</h5>
                        <button class="btn btn-xs btn-default biu-add-condition">+ Add Condition</button>
                    </div>
                    <div class="biu-conditions-summary" id="biu-cond-summary"></div>
                    <div class="biu-conditions-rows" id="biu-cond-rows"></div>
                </div>

                <!-- ACTIONS -->
                <div class="biu-section" id="biu-section-actions">
                    <div class="biu-section-header">
                        <h5>Actions</h5>
                        <button class="btn btn-xs btn-default biu-add-action">+ Add Action</button>
                    </div>
                    <div class="biu-actions-summary" id="biu-action-summary"></div>
                    <div class="biu-actions-rows" id="biu-action-rows"></div>
                </div>

                <div class="biu-editor-buttons">
                    <button class="btn btn-default btn-sm biu-btn-preview">Preview</button>
                    <button class="btn btn-primary btn-sm biu-btn-save-preview">Save and Preview</button>
                </div>
            </div>
        `);

        render_condition_rows();
        render_action_rows();
        render_conditions_summary();
        render_actions_summary();

        // ── Navigation ──
        $app.find(".biu-btn-back").on("click", () => {
            state.view = "initial";
            render();
        });

        $app.find(".biu-add-condition").on("click", () => {
            state.conditions.push(default_condition());
            render_condition_rows();
            render_conditions_summary();
        });

        $app.find(".biu-add-action").on("click", () => {
            state.actions.push(default_action());
            render_action_rows();
            render_actions_summary();
        });

        $app.find(".biu-btn-preview").on("click", () => {
            collect_editor_values();
            if (!validate_editor()) return;
            do_preview();
        });

        $app.find(".biu-btn-save-preview").on("click", () => {
            collect_editor_values();
            if (!validate_editor()) return;
            do_save(() => do_preview());
        });

        // ── Keyboard shortcuts ──
        let last_focused_section = "conditions";

        $app.find("#biu-section-conditions").on("click focus", () => { last_focused_section = "conditions"; });
        $app.find("#biu-section-actions").on("click focus", () => { last_focused_section = "actions"; });

        $(document).off("keydown.biu_editor").on("keydown.biu_editor", (e) => {
            if (state.view !== "editor") return;
            if (!e.ctrlKey) return;

            // CTRL+N → add row to last focused section
            if (e.key === "n") {
                e.preventDefault();
                e.stopPropagation();
                if (last_focused_section === "actions") {
                    state.actions.push(default_action());
                    render_action_rows();
                    render_actions_summary();
                    $app.find("#biu-action-rows .biu-row:last select:first").focus();
                } else {
                    state.conditions.push(default_condition());
                    render_condition_rows();
                    render_conditions_summary();
                    $app.find("#biu-cond-rows .biu-row:last select:first").focus();
                }
            }

            // CTRL+B → add row to filters only
            if (e.key === "b") {
                e.preventDefault();
                e.stopPropagation();
                state.conditions.push(default_condition());
                render_condition_rows();
                render_conditions_summary();
                $app.find("#biu-cond-rows .biu-row:last select:first").focus();
            }

            // CTRL+S → save
            if (e.key === "s") {
                e.preventDefault();
                e.stopPropagation();
                collect_editor_values();
                if (!validate_editor()) return;
                do_save();
            }
        });
    }

    // ── Condition summary pills ──
    function render_conditions_summary() {
        const $el = $app.find("#biu-cond-summary");
        $el.empty();
        state.conditions.forEach((c, i) => {
            const field = c.field_name === "custom_field" ? (c.custom_field_name || "custom_field") : c.field_name;
            const prefix = i === 0 ? "" : c.logic_operator + " ";
            const ptag = PRICE_FIELDS.has(field) ? ' <small style="opacity:0.6">(Item Price)</small>' : "";
            $el.append(`<div class="biu-pill">${prefix}<strong>${field}</strong>${ptag} ${c.operator} <em>${frappe.utils.escape_html(c.value || "")}</em></div>`);
        });
    }

    // ── Action summary pills ──
    function render_actions_summary() {
        const $el = $app.find("#biu-action-summary");
        $el.empty();
        state.actions.forEach(a => {
            const label = ACTION_TYPE_OPTIONS.find(o => o.value === a.action_type)?.label || a.action_type;
            const val_display = NO_VALUE_ACTIONS.has(a.action_type)
                ? ""
                : `: <em>${frappe.utils.escape_html(a.action_value || "")}</em>`;
            $el.append(`<div class="biu-pill biu-pill-action"><strong>${label}</strong>${val_display}</div>`);
        });
    }

    // ── Condition rows ──
    function render_condition_rows() {
        const $wrap = $app.find("#biu-cond-rows");
        $wrap.empty();

        state.conditions.forEach((c, idx) => {
            const logic_sel = idx === 0
                ? `<select class="form-control form-control-sm biu-logic-select" disabled style="visibility:hidden;"></select>`
                : build_select("cond-logic-" + idx, ["And", "Or"], c.logic_operator).replace('biu-select', 'biu-select biu-logic-select');
            const field_sel = build_select("cond-field-" + idx, FIELD_OPTIONS, c.field_name);
            const op_sel = build_select("cond-op-" + idx, OPERATOR_OPTIONS, c.operator);

            $wrap.append(`
                <div class="biu-row" data-idx="${idx}">
                    ${logic_sel}
                    ${field_sel}
                    ${c.field_name === "custom_field"
                        ? `<input type="text" class="form-control form-control-sm biu-input biu-cond-custom"
                                  placeholder="Custom fieldname" value="${frappe.utils.escape_html(c.custom_field_name || "")}">`
                        : ""}
                    ${op_sel}
                    <input type="text" class="form-control form-control-sm biu-input biu-cond-value"
                           placeholder="Value" value="${frappe.utils.escape_html(c.value || "")}">
                    <button class="btn btn-xs btn-danger biu-remove-cond" data-idx="${idx}" title="Remove">&times;</button>
                </div>
            `);
        });

        $wrap.find("select, input").on("change input", () => {
            collect_conditions_from_dom();
            render_conditions_summary();
        });

        $wrap.find("select[id^='cond-field-']").on("change", function () {
            collect_conditions_from_dom();
            render_condition_rows();
            render_conditions_summary();
        });

        $wrap.find(".biu-remove-cond").on("click", function () {
            const i = $(this).data("idx");
            if (state.conditions.length <= 1) return frappe.show_alert({ message: "Need at least one condition.", indicator: "orange" });
            state.conditions.splice(i, 1);
            render_condition_rows();
            render_conditions_summary();
        });
    }

    // ── Action rows ──
    function render_action_rows() {
        const $wrap = $app.find("#biu-action-rows");
        $wrap.empty();

        state.actions.forEach((a, idx) => {
            const at_sel = build_select("act-at-" + idx, ACTION_TYPE_OPTIONS, a.action_type);
            const needs_value = !NO_VALUE_ACTIONS.has(a.action_type);
            const link_doctype = ACTION_LINK_MAP[a.action_type] || null;

            let value_html;
            if (!needs_value) {
                value_html = '<span class="text-muted small" style="padding:0 8px;">(no value needed)</span>';
            } else if (link_doctype) {
                // Placeholder div — frappe.ui.form.make_control will mount here
                value_html = `<div class="biu-link-field" data-idx="${idx}" style="min-width:180px;max-width:250px;"></div>`;
            } else {
                value_html = `<input type="text" class="form-control form-control-sm biu-input biu-act-value"
                              placeholder="Value" value="${frappe.utils.escape_html(a.action_value || "")}">`;
            }

            $wrap.append(`
                <div class="biu-row" data-idx="${idx}">
                    ${at_sel}
                    ${value_html}
                    <button class="btn btn-xs btn-danger biu-remove-action" data-idx="${idx}" title="Remove">&times;</button>
                </div>
            `);

            // Mount Frappe Link control if needed
            if (needs_value && link_doctype) {
                const $mount = $wrap.find(`.biu-link-field[data-idx="${idx}"]`);
                const control = frappe.ui.form.make_control({
                    df: {
                        fieldname: "act_value_" + idx,
                        fieldtype: "Link",
                        options: link_doctype,
                        placeholder: link_doctype,
                    },
                    parent: $mount,
                    render_input: true,
                });
                control.set_value(a.action_value || "");
                control.$input.on("change", () => {
                    state.actions[idx].action_value = control.get_value() || "";
                    render_actions_summary();
                });
                // Store reference so we can read it later
                $mount.data("control", control);
            }
        });

        // Plain text inputs — live sync
        $wrap.find("input.biu-act-value").on("change input", () => {
            collect_actions_from_dom();
            render_actions_summary();
        });

        // Action type dropdown change → re-render (to swap between link/text/none)
        $wrap.find("select[id^='act-at-']").on("change", function () {
            collect_actions_from_dom();
            render_action_rows();
            render_actions_summary();
        });

        $wrap.find(".biu-remove-action").on("click", function () {
            const i = $(this).data("idx");
            if (state.actions.length <= 1) return frappe.show_alert({ message: "Need at least one action.", indicator: "orange" });
            state.actions.splice(i, 1);
            render_action_rows();
            render_actions_summary();
        });
    }

    // ── DOM collectors ──
    function collect_conditions_from_dom() {
        const $rows = $app.find("#biu-cond-rows .biu-row");
        $rows.each(function (i) {
            const $r = $(this);
            state.conditions[i] = {
                logic_operator: $r.find("select[id^='cond-logic']").val() || "And",
                field_name: $r.find("select[id^='cond-field']").val() || "item_code",
                custom_field_name: $r.find(".biu-cond-custom").val() || "",
                operator: $r.find("select[id^='cond-op']").val() || "Equals To",
                value: $r.find(".biu-cond-value").val() || "",
            };
        });
    }

    function collect_actions_from_dom() {
        const $rows = $app.find("#biu-action-rows .biu-row");
        $rows.each(function (i) {
            const $r = $(this);
            const action_type = $r.find("select[id^='act-at']").val() || "UpdatePrice";

            let action_value = "";
            if (action_type === "DisableItem") {
                action_value = "1";
            } else if (action_type === "EnableItem") {
                action_value = "0";
            } else {
                // Check if there's a Link control
                const $link = $r.find(".biu-link-field");
                if ($link.length && $link.data("control")) {
                    action_value = $link.data("control").get_value() || "";
                } else {
                    action_value = $r.find(".biu-act-value").val() || "";
                }
            }

            state.actions[i] = { action_type, action_value };
        });
    }

    function collect_editor_values() {
        state.rule_name = ($app.find("#biu-rule-name").val() || "").trim();
        collect_conditions_from_dom();
        collect_actions_from_dom();
    }

    function validate_editor() {
        if (!state.conditions.length) {
            frappe.show_alert({ message: "Add at least one search condition.", indicator: "orange" });
            return false;
        }
        if (!state.actions.length) {
            frappe.show_alert({ message: "Add at least one action.", indicator: "orange" });
            return false;
        }
        for (const a of state.actions) {
            if (!NO_VALUE_ACTIONS.has(a.action_type) && !OPTIONAL_VALUE_ACTIONS.has(a.action_type) && !a.action_value) {
                frappe.show_alert({ message: "All actions need a value.", indicator: "orange" });
                return false;
            }
        }
        return true;
    }

    // ── Save ──
    function do_save(callback) {
        if (!state.rule_name) {
            frappe.show_alert({ message: "Please enter a Rule Name.", indicator: "orange" });
            return;
        }
        frappe.call({
            method: API + ".save_rule_from_page",
            args: {
                rule_name: state.rule_name,
                conditions: JSON.stringify(state.conditions),
                actions: JSON.stringify(state.actions),
                target_doctype: state.target_doctype,
                description: state.description,
                existing_rule: state.existing_rule || "",
            },
            callback(r) {
                if (r.message) {
                    state.existing_rule = r.message.name;
                    state.rule_name = r.message.rule_name;
                    frappe.show_alert({ message: `Rule "${state.rule_name}" saved.`, indicator: "green" });
                    if (callback) callback();
                }
            },
            error() {
                frappe.show_alert({ message: "Failed to save rule.", indicator: "red" });
            },
        });
    }

    // ── Preview ──
    function do_preview(start, exclude_unchanged) {
        state.preview_start = start || 0;
        frappe.call({
            method: API + ".preview_from_data",
            args: {
                conditions: JSON.stringify(state.conditions),
                actions: JSON.stringify(state.actions),
                target_doctype: state.target_doctype,
                limit: state.preview_limit,
                start: state.preview_start,
                exclude_unchanged: exclude_unchanged ? 1 : 0,
            },
            callback(r) {
                if (r.message) {
                    state.preview_data = r.message;
                    state.view = "preview";
                    render();
                }
            },
            error() {
                frappe.show_alert({ message: "Preview failed. Check conditions.", indicator: "red" });
            },
        });
    }

    // ═══════════════════════════════════════════════════════════════════
    //  3. PREVIEW SCREEN
    // ═══════════════════════════════════════════════════════════════════
    function render_preview() {
        page.set_title("Preview: " + (state.rule_name || "Unsaved Rule"));

        const d = state.preview_data;
        const total = d.total || 0;
        const cols = d.action_columns || [];
        const preview = d.preview || [];
        const start = state.preview_start;
        const limit = state.preview_limit;
        const end = Math.min(start + limit, total);
        const has_prev = start > 0;
        const has_next = (start + limit) < total;
        const is_saved = !!state.existing_rule;
        const max_allowed = d.max_allowed || 0;
        const exceeds_max = max_allowed > 0 && total > max_allowed;

        // Rules summary
        let rules_html = "";
        state.conditions.forEach((c, i) => {
            const field = c.field_name === "custom_field" ? (c.custom_field_name || "custom_field") : c.field_name;
            const prefix = i === 0 ? "" : c.logic_operator + " ";
            rules_html += `<li>${prefix}${field} ${c.operator} ${frappe.utils.escape_html(c.value || "")}</li>`;
        });
        state.actions.forEach(a => {
            const label = ACTION_TYPE_OPTIONS.find(o => o.value === a.action_type)?.label || a.action_type;
            const val_display = NO_VALUE_ACTIONS.has(a.action_type) ? "" : `: ${frappe.utils.escape_html(a.action_value)}`;
            rules_html += `<li class="biu-action-li">${label}${val_display}</li>`;
        });

        // Table header
        let th = `<th class="biu-th">SKU</th><th class="biu-th">Name</th>`;
        cols.forEach(col => {
            const tag = PRICE_FIELDS.has(col) ? " <small>(Item Price)</small>" : "";
            th += `<th class="biu-th">${col}${tag}</th><th class="biu-th">${col} (After)</th>`;
        });

        // Table rows
        let rows_html = "";
        if (preview.length) {
            preview.forEach(row => {
                const item_data = d.items ? d.items.find(it => it.name === row.name) : null;
                let cells = `<td>${frappe.utils.escape_html(row.name || "")}</td>`;
                cells += `<td>${frappe.utils.escape_html(item_data ? (item_data.item_name || "") : "")}</td>`;
                cols.forEach(col => {
                    const before = row[col + "_before"];
                    const after = row[col + "_after"];
                    const changed = String(before ?? "") !== String(after ?? "");
                    cells += `<td>${before ?? ""}</td>`;
                    cells += `<td class="${changed ? "biu-changed" : ""}">${after ?? ""}</td>`;
                });
                rows_html += `<tr>${cells}</tr>`;
            });
        } else {
            rows_html = `<tr><td colspan="${2 + cols.length * 2}" class="text-center text-muted p-4">No items match these conditions.</td></tr>`;
        }

        $app.html(`
            <div class="biu-preview">
                <div class="biu-preview-topbar">
                    <a class="biu-link biu-edit-link">← Edit Rules &amp; Actions</a>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-default btn-xs biu-btn-refresh">↻ Refresh</button>
                        <button class="btn btn-default btn-xs biu-btn-new-from-preview">New Rule Set</button>
                    </div>
                </div>

                <!-- Execute bar TOP -->
                <div class="biu-execute-bar">
                    <div class="biu-match-count">
                        Showing ${start + 1}–${end} of <strong>${total}</strong> matches
                    </div>
                    <div class="biu-execute-buttons">
                        <button class="btn btn-default btn-xs biu-btn-export">Export for Review</button>
                        <button class="btn btn-default btn-xs biu-btn-save-changes">Save Rule</button>
                        ${exceeds_max
                            ? `<span class="biu-exceeds-warning">
                                ⚠ ${total.toLocaleString()} items exceeds the limit of ${max_allowed.toLocaleString()}.
                            </span>
                            <button class="btn btn-warning btn-sm biu-btn-execute biu-btn-execute-capped ${!is_saved ? "disabled" : ""}">
                                Execute First ${max_allowed.toLocaleString()}
                            </button>`
                            : `<button class="btn btn-primary btn-sm biu-btn-execute ${!is_saved ? "disabled" : ""}">
                                Execute Update
                            </button>`
                        }
                    </div>
                </div>

                <div class="biu-table-wrap">
                    <table class="table table-bordered table-sm biu-table">
                        <thead><tr>${th}</tr></thead>
                        <tbody>${rows_html}</tbody>
                    </table>
                </div>

                <div class="biu-pagination">
                    <button class="btn btn-xs btn-default biu-page-prev" ${has_prev ? "" : "disabled"}>← Previous</button>
                    <span class="text-muted small">${start + 1}–${end} of ${total}</span>
                    <button class="btn btn-xs btn-default biu-page-next" ${has_next ? "" : "disabled"}>Next →</button>
                </div>

                <div class="biu-rules-summary">
                    <div class="biu-section-label">Active Rules &amp; Actions</div>
                    <ul class="biu-summary-list">${rules_html}</ul>
                </div>

                <!-- Execute bar BOTTOM -->
                <div class="biu-execute-bar biu-execute-bar-bottom">
                    <div class="biu-match-count">
                        <strong>${exceeds_max ? max_allowed.toLocaleString() : total}</strong> items will be updated
                    </div>
                    <div class="biu-execute-buttons">
                        ${exceeds_max
                            ? `<span class="biu-exceeds-warning">
                                ⚠ ${total.toLocaleString()} items exceeds the limit of ${max_allowed.toLocaleString()}.
                            </span>
                            <button class="btn btn-warning btn-sm biu-btn-execute biu-btn-execute-capped ${!is_saved ? "disabled" : ""}">
                                Execute First ${max_allowed.toLocaleString()}
                            </button>`
                            : `<button class="btn btn-primary btn-sm biu-btn-execute ${!is_saved ? "disabled" : ""}">
                                Execute Update
                            </button>`
                        }
                    </div>
                </div>
            </div>
        `);

        // ── Events ──
        $app.find(".biu-btn-refresh").on("click", () => do_preview(state.preview_start, true));
        $app.find(".biu-edit-link").on("click", () => { state.view = "editor"; render(); });
        $app.find(".biu-btn-new-from-preview").on("click", () => {
            state.existing_rule = null;
            state.rule_name = "";
            state.conditions = [default_condition()];
            state.actions = [default_action()];
            state.view = "editor";
            render();
        });

        $app.find(".biu-page-prev").on("click", () => do_preview(Math.max(0, start - limit)));
        $app.find(".biu-page-next").on("click", () => do_preview(start + limit));

        $app.find(".biu-btn-save-changes").on("click", () => {
            if (!state.rule_name) {
                frappe.prompt(
                    { fieldname: "rule_name", fieldtype: "Data", label: "Rule Name", reqd: 1 },
                    (values) => {
                        state.rule_name = values.rule_name;
                        do_save(() => {
                            $app.find(".biu-btn-execute").removeClass("disabled");
                        });
                    },
                    "Enter Rule Name"
                );
            } else {
                do_save(() => {
                    $app.find(".biu-btn-execute").removeClass("disabled");
                });
            }
        });

        $app.find(".biu-btn-export").on("click", () => {
            if (!is_saved) {
                frappe.show_alert({ message: "Save the rule first to export.", indicator: "orange" });
                return;
            }
            frappe.call({
                method: API + ".export_preview",
                args: { rule_name: state.existing_rule },
                callback(r) {
                    if (r.message && r.message.file_url) window.open(r.message.file_url);
                },
            });
        });

        $app.find(".biu-btn-execute").on("click", function () {
            if ($(this).hasClass("disabled")) {
                frappe.show_alert({ message: "Save the rule first before executing.", indicator: "orange" });
                return;
            }
            const is_capped = $(this).hasClass("biu-btn-execute-capped");
            const confirm_msg = is_capped
                ? `This will update the first <strong>${max_allowed.toLocaleString()}</strong> of ${total.toLocaleString()} matching items in the background.<br>Are you sure?`
                : `This will update <strong>${total.toLocaleString()}</strong> matching items in the background.<br>Are you sure?`;

            frappe.confirm(confirm_msg, () => {
                frappe.call({
                    method: API + ".execute_rule",
                    args: { rule_name: state.existing_rule },
                    callback(r) {
                        if (r.message && r.message.status === "queued") {
                            frappe.show_alert({
                                message: "Bulk update queued. You'll be notified when it completes.",
                                indicator: "blue",
                            });
                        }
                    },
                });
            });
        });

        // Realtime progress
        frappe.realtime.off("bulk_update_progress");
        frappe.realtime.on("bulk_update_progress", (data) => {
            if (data.rule_name !== state.existing_rule) return;
            if (data.status === "Completed") {
                // Force-close any open progress dialogs
                frappe.hide_progress();
                $('.frappe-control .progress').closest('.modal').modal('hide');
                setTimeout(() => {
                    frappe.hide_progress();
                    frappe.msgprint({
                        title: __("Bulk Update Complete"),
                        message: `<strong>${data.updated}</strong> items updated. ${data.errors ? data.errors + " errors." : "No errors."}`,
                        indicator: data.errors ? "orange" : "green",
                    });
                }, 300);
            } else if (data.status === "Failed") {
                frappe.hide_progress();
                setTimeout(() => {
                    frappe.hide_progress();
                    frappe.msgprint({
                        title: __("Bulk Update Failed"),
                        message: data.error || "Unknown error",
                        indicator: "red",
                    });
                }, 300);
            } else {
                frappe.show_progress("Executing Bulk Update", data.current, data.total,
                    `Processing ${data.current} of ${data.total}`);
            }
        });
    }

    // ═══════════════════════════════════════════════════════════════════
    //  HELPERS
    // ═══════════════════════════════════════════════════════════════════
    function build_select(id, options, selected) {
        let html = `<select id="${id}" class="form-control form-control-sm biu-select">`;
        options.forEach(opt => {
            const val = (typeof opt === "object") ? opt.value : opt;
            const label = (typeof opt === "object") ? opt.label : opt;
            html += `<option value="${val}" ${val === selected ? "selected" : ""}>${label}</option>`;
        });
        html += "</select>";
        return html;
    }

    render();
};