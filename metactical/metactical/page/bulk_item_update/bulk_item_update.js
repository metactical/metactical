/**
 * Bulk Item Update – Full Page Application
 *
 * Three views matching the wireframe:
 *   1. Initial Screen   – select saved rules, create new rule set
 *   2. Editor Screen    – build Search conditions + Actions inline
 *   3. Preview Screen   – table of matches with before/after, execute buttons top & bottom
 *
 * All rule creation/editing happens on this page.
 * Saving stores to the Bulk Update Rule doctype for reuse.
 */

// ─── Module path (adjust to your app) ───
const API = "metactical.metactical.doctype.bulk_update_rule.bulk_update_rule";

// ─── Field / operator options ───
// {value, label} pairs – price fields are tagged so users know they query Item Price
const FIELD_OPTIONS = [
    { value: "item_code",        label: "Item Code" },
    { value: "item_name",        label: "Item Name" },
    { value: "item_group",       label: "Item Group" },
    { value: "stock_uom",        label: "Stock UOM" },
    { value: "is_trashed",       label: "Is Trashed" },
    { value: "has_variants",     label: "Has Variants" },
    { value: "disabled",         label: "Disabled" },
    { value: "valuation_rate",   label: "Valuation Rate" },
    { value: "discounted_price", label: "Discounted Price" },
    { value: "standard_rate",    label: "Standard Rate (Item Price)" },
    { value: "price_list_rate",  label: "Price List Rate (Item Price)" },
    { value: "custom_field",     label: "Custom Field…" },
];

const OPERATOR_OPTIONS = [
    "Begins With", "Ends With", "Contains", "Does Not Contain",
	"Equals To", "Not Equal To", "Greater Than", "Less Than",
    "Greater Than Or Equal", "Less Than Or Equal",
    "In", "Not In", "Is Set", "Is Not Set"
];

const ACTION_TARGET_OPTIONS = [
    { value: "discounted_price", label: "Discounted Price" },
    { value: "valuation_rate",   label: "Valuation Rate" },
    { value: "disabled",         label: "Disabled" },
    { value: "item_group",       label: "Item Group" },
    { value: "stock_uom",        label: "Stock UOM" },
    { value: "standard_rate",    label: "Standard Rate (Item Price)" },
    { value: "price_list_rate",  label: "Price List Rate (Item Price)" },
    { value: "custom_field",     label: "Custom Field…" },
];

const ACTION_TYPE_OPTIONS = [
    "Set To Value", "Set To Formula", "Multiply By",
    "Add Value", "Subtract Value", "Set To Field Value"
];

// Fields that live on Item Price (always uses price list "RET - Camo an")
const PRICE_FIELDS = new Set(["price_list_rate", "standard_rate"]);


frappe.pages["bulk-item-update"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Bulk Item Update",
        single_column: true,
    });

    // ─── State ───
    let state = {
        view: "initial",          // initial | editor | preview
        rule_name: "",
        description: "",
        target_doctype: "Item",
        existing_rule: null,       // set when editing a saved rule
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
					<button id="biu-btn-new" class="btn btn-primary btn-sm">
						+ New Rule Set
					</button>
                </div>

                <div class="biu-section-label">Most Recent Rules</div>
                <div id="biu-recent-list"></div>
            </div>
        `);

        // Load rules
        frappe.call({
            method: API + ".get_recent_rules",
            args: { limit: 50 },
            callback(r) {
                const rules = r.message || [];
                const $sel = $app.find("#biu-rule-select");
                rules.forEach(rule => {
                    $sel.append(`<option value="${rule.name}">${rule.rule_name}</option>`);
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

                // Click on a recent rule card
                $list.find(".biu-rule-card").on("click", function () {
                    load_rule_into_editor($(this).data("rule"));
                });
            },
        });

        // Show Rule button
        $app.find("#biu-btn-show").on("click", () => {
            const v = $app.find("#biu-rule-select").val();
            if (!v) return frappe.show_alert({ message: "Select a rule first.", indicator: "orange" });
            load_rule_into_editor(v);
        });

        // New Rule Set
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
        return { target_field: "discounted_price", action_type: "Set To Value", action_value: "", custom_target_field: "" };
    }


    // ═══════════════════════════════════════════════════════════════════
    //  2. EDITOR SCREEN  (Search conditions + Actions, inline)
    // ═══════════════════════════════════════════════════════════════════
    function render_editor() {
        page.set_title(state.existing_rule ? `Edit Rule: ${state.rule_name}` : "New Rule Set");

        $app.html(`
            <div class="biu-editor">
                <!-- Top bar -->
                <div class="biu-topbar">
                    <button class="btn btn-xs btn-default biu-btn-back">← Back</button>
                    <div class="biu-rule-name-wrap">
                        <input type="text" id="biu-rule-name" class="form-control form-control-sm"
                               placeholder="Rule Name *" value="${frappe.utils.escape_html(state.rule_name)}">
                    </div>
                </div>

                <!-- SEARCH CONDITIONS -->
                <div class="biu-price-note">
                    <strong>Note:</strong> Price List Rate and Standard Rate fields are
                    read from / written to <strong>Item Price</strong> with price list
                    <strong>RET - Camo an</strong>.
                </div>

                <div class="biu-section">
                    <div class="biu-section-header">
                        <h5>Search Conditions</h5>
                        <button class="btn btn-xs btn-default biu-add-condition">+ Add Condition</button>
                    </div>
                    <div class="biu-conditions-summary" id="biu-cond-summary"></div>
                    <div class="biu-conditions-rows" id="biu-cond-rows"></div>
                </div>

                <!-- ACTIONS -->
                <div class="biu-section">
                    <div class="biu-section-header">
                        <h5>Actions</h5>
                        <button class="btn btn-xs btn-default biu-add-action">+ Add Action</button>
                    </div>
                    <div class="biu-actions-summary" id="biu-action-summary"></div>
                    <div class="biu-actions-rows" id="biu-action-rows"></div>
                </div>

                <!-- Bottom buttons -->
                <div class="biu-editor-buttons">
                    <button class="btn btn-default btn-sm biu-btn-preview">Preview</button>
                    <button class="btn btn-primary btn-sm biu-btn-save-preview">Save and Preview</button>
                </div>
            </div>
        `);

        // Render condition rows
        render_condition_rows();
        render_action_rows();
        render_conditions_summary();
        render_actions_summary();

        // ── Event bindings ──
        $app.find(".biu-btn-back").on("click", () => { state.view = "initial"; render(); });

		$app.find(".biu-btn-back").on("click", () => {
            $(document).off("keydown.biu_editor");
            state.view = "initial";
            render();
        });

		// ── Keyboard shortcut: CTRL+N to add row ──
        // Track which section was last focused to know where to add
        let last_focused_section = "conditions";

        $app.find("#biu-cond-rows, #biu-cond-summary, .biu-add-condition").on("click focus", () => {
            last_focused_section = "conditions";
        });
        $app.find("#biu-action-rows, #biu-action-summary, .biu-add-action").on("click focus", () => {
            last_focused_section = "actions";
        });

        $(document).off("keydown.biu_editor").on("keydown.biu_editor", (e) => {
			console.log(`Keydown: ${e.key}, Ctrl: ${e.ctrlKey}, Last focused section: ${last_focused_section}`);
            if (state.view !== "editor") return;
            if (e.ctrlKey && e.key === "b") {
                e.preventDefault();
                e.stopPropagation();
                if (last_focused_section === "actions") {
                    state.actions.push(default_action());
                    render_action_rows();
                    render_actions_summary();
                    // Focus the last action row's first select
                    $app.find("#biu-action-rows .biu-row:last select:first").focus();
                } else {
                    state.conditions.push(default_condition());
                    render_condition_rows();
                    render_conditions_summary();
                    $app.find("#biu-cond-rows .biu-row:last select:first").focus();
                }
            }
        });

        $app.find(".biu-add-condition").on("click", () => {
            state.conditions.push(default_condition());
            render_condition_rows();
        });

        $app.find(".biu-add-action").on("click", () => {
            state.actions.push(default_action());
            render_action_rows();
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
    }

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

    function render_actions_summary() {
        const $el = $app.find("#biu-action-summary");
        $el.empty();
        state.actions.forEach(a => {
            const tf = a.target_field === "custom_field" ? (a.custom_target_field || "custom_field") : a.target_field;
            const ptag = PRICE_FIELDS.has(tf) ? ' <small style="opacity:0.6">(Item Price)</small>' : "";
            $el.append(`<div class="biu-pill biu-pill-action">Set <strong>${tf}</strong>${ptag} → ${a.action_type}: <em>${frappe.utils.escape_html(a.action_value || "")}</em></div>`);
        });
    }

    function render_condition_rows() {
        const $wrap = $app.find("#biu-cond-rows");
        $wrap.empty();

        state.conditions.forEach((c, idx) => {
            const logic_sel = build_select("cond-logic-" + idx, ["And", "Or"], c.logic_operator);
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

        // Change events → live update state & summary
        $wrap.find("select, input").on("change input", () => {
            collect_conditions_from_dom();
            render_conditions_summary();
        });

        // Toggling custom_field → re-render
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

    function render_action_rows() {
        const $wrap = $app.find("#biu-action-rows");
        $wrap.empty();

        state.actions.forEach((a, idx) => {
            const tf_sel = build_select("act-tf-" + idx, ACTION_TARGET_OPTIONS, a.target_field);
            const at_sel = build_select("act-at-" + idx, ACTION_TYPE_OPTIONS, a.action_type);

            $wrap.append(`
                <div class="biu-row" data-idx="${idx}">
                    ${tf_sel}
                    ${a.target_field === "custom_field"
                        ? `<input type="text" class="form-control form-control-sm biu-input biu-act-custom"
                                  placeholder="Custom fieldname" value="${frappe.utils.escape_html(a.custom_target_field || "")}">`
                        : ""}
                    ${at_sel}
                    <input type="text" class="form-control form-control-sm biu-input biu-act-value"
                           placeholder="Value / Formula" value="${frappe.utils.escape_html(a.action_value || "")}">
                    <button class="btn btn-xs btn-danger biu-remove-action" data-idx="${idx}" title="Remove">&times;</button>
                </div>
            `);
        });

        $wrap.find("select, input").on("change input", () => {
            collect_actions_from_dom();
            render_actions_summary();
        });

        $wrap.find("select[id^='act-tf-']").on("change", function () {
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
            state.actions[i] = {
                target_field: $r.find("select[id^='act-tf']").val() || "discounted_price",
                custom_target_field: $r.find(".biu-act-custom").val() || "",
                action_type: $r.find("select[id^='act-at']").val() || "Set To Value",
                action_value: $r.find(".biu-act-value").val() || "",
            };
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
            if (!a.action_value) {
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
    function do_preview(start) {
        state.preview_start = start || 0;

        frappe.call({
            method: API + ".preview_from_data",
            args: {
                conditions: JSON.stringify(state.conditions),
                actions: JSON.stringify(state.actions),
                target_doctype: state.target_doctype,
                limit: state.preview_limit,
                start: state.preview_start,
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

        // Build rules summary
        let rules_html = "";
        state.conditions.forEach((c, i) => {
            const field = c.field_name === "custom_field" ? (c.custom_field_name || "custom_field") : c.field_name;
            const prefix = i === 0 ? "" : c.logic_operator + " ";
            rules_html += `<li>${prefix}${field} ${c.operator} ${frappe.utils.escape_html(c.value || "")}</li>`;
        });
        state.actions.forEach(a => {
            const tf = a.target_field === "custom_field" ? (a.custom_target_field || "custom_field") : a.target_field;
            rules_html += `<li class="biu-action-li">Set ${tf} → ${a.action_type}: ${frappe.utils.escape_html(a.action_value)}</li>`;
        });

        // Build table header
        let th = `<th class="biu-th">SKU</th><th class="biu-th">Name</th>`;
        cols.forEach(col => {
            const tag = PRICE_FIELDS.has(col) ? " <small>(Item Price)</small>" : "";
            th += `<th class="biu-th">${col}${tag}</th><th class="biu-th">${col} (After)</th>`;
        });

        // Build table rows
        let rows_html = "";
        if (preview.length) {
            preview.forEach(row => {
                let cells = `<td>${frappe.utils.escape_html(row.name || "")}</td>`;
                // Try to get item_name from the items data
                const item_data = d.items ? d.items.find(it => it.name === row.name) : null;
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
                <!-- Top action bar -->
                <div class="biu-preview-topbar">
                    <div>
                        <a class="biu-link biu-edit-link">← Edit Rules &amp; Actions</a>
                    </div>
                    <div>
                        <button class="btn btn-default btn-xs biu-btn-new-from-preview">New Rule Set</button>
                    </div>
                </div>

                <!-- Execute button TOP -->
                <div class="biu-execute-bar">
                    <div class="biu-match-count">
                        Showing ${start + 1}–${end} of <strong>${total}</strong> matches
                    </div>
                    <div class="biu-execute-buttons">
                        <button class="btn btn-default btn-xs biu-btn-export">Export for Review</button>
                        <button class="btn btn-default btn-xs biu-btn-save-changes">Save Rule</button>
                        <button class="btn btn-primary btn-sm biu-btn-execute ${!is_saved ? "disabled" : ""}">
                            Execute Update
                        </button>
                    </div>
                </div>

                <!-- Data table -->
                <div class="biu-table-wrap">
                    <table class="table table-bordered table-sm biu-table">
                        <thead><tr>${th}</tr></thead>
                        <tbody>${rows_html}</tbody>
                    </table>
                </div>

                <!-- Pagination -->
                <div class="biu-pagination">
                    <button class="btn btn-xs btn-default biu-page-prev" ${has_prev ? "" : "disabled"}>← Previous</button>
                    <span class="text-muted small">${start + 1}–${end} of ${total}</span>
                    <button class="btn btn-xs btn-default biu-page-next" ${has_next ? "" : "disabled"}>Next →</button>
                </div>

                <!-- Rules summary -->
                <div class="biu-rules-summary">
                    <div class="biu-section-label">Active Rules &amp; Actions</div>
                    <ul class="biu-summary-list">${rules_html}</ul>
                </div>

                <!-- Execute button BOTTOM -->
                <div class="biu-execute-bar biu-execute-bar-bottom">
                    <div class="biu-match-count">
                        <strong>${total}</strong> items will be updated
                    </div>
                    <div class="biu-execute-buttons">
                        <button class="btn btn-primary btn-sm biu-btn-execute ${!is_saved ? "disabled" : ""}">
                            Execute Update
                        </button>
                    </div>
                </div>
            </div>
        `);

        // ── Preview event bindings ──
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
                            frappe.show_alert({ message: "Rule saved.", indicator: "green" });
                            // Re-enable execute buttons
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
            frappe.confirm(
                `This will update <strong>${total}</strong> matching items in the background.<br>Are you sure?`,
                () => {
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
                }
            );
        });

        // ── Realtime progress ──
        frappe.realtime.off("bulk_update_progress");
        frappe.realtime.on("bulk_update_progress", (data) => {
            if (data.rule_name !== state.existing_rule) return;
            if (data.status === "Completed") {
                frappe.hide_progress();
                frappe.show_alert({
                    message: `Done! ${data.updated} items updated, ${data.errors} errors.`,
                    indicator: data.errors ? "orange" : "green",
                });
            } else if (data.status === "Failed") {
                frappe.hide_progress();
                frappe.show_alert({ message: "Update failed: " + (data.error || "Unknown error"), indicator: "red" });
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


    // ═══════════════════════════════════════════════════════════════════
    //  STYLES
    // ═══════════════════════════════════════════════════════════════════
    if (!document.getElementById("biu-styles")) {
        const style = document.createElement("style");
        style.id = "biu-styles";
        style.textContent = `
            /* ── Layout ── */
            #bulk-update-app { max-width: 1200px; margin: 0 auto; padding: 15px; }

            /* ── Initial Screen ── */
            .biu-initial { max-width: 80%; margin: 0 auto; }
            .biu-intro { color: var(--text-muted); line-height: 1.6; margin-bottom: 20px; }
            .biu-selector-row { display: flex; gap: 8px; align-items: center; }
            .biu-selector-row select { flex: 1; }
            .biu-section-label {
                font-weight: 600; font-size: 11px; text-transform: uppercase;
                letter-spacing: 0.6px; color: var(--text-muted);
                margin: 28px 0 10px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px;
            }
            .biu-rule-card {
                padding: 10px 14px; border: 1px solid var(--border-color);
                border-radius: var(--border-radius); margin-bottom: 6px; cursor: pointer;
                transition: background 0.15s;
            }
            .biu-rule-card:hover { background: var(--bg-light-gray); }
            .biu-rule-link { font-weight: 600; font-size: 13px; color: var(--primary); cursor: pointer; }

            /* ── Editor ── */
            .biu-editor { }
            .biu-topbar {
                display: flex; gap: 12px; align-items: center;
                margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid var(--border-color);
            }
            .biu-rule-name-wrap { flex: 1; }
            .biu-rule-name-wrap input { font-weight: 600; font-size: 15px; }

            .biu-section {
                border: 1px solid var(--border-color); border-radius: var(--border-radius);
                padding: 16px; margin-bottom: 16px; background: var(--fg-color);
            }
            .biu-section-header {
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 10px;
            }
            .biu-section-header h5 { margin: 0; font-size: 16px; font-weight: 700; }

            .biu-pill {
                display: inline-block; padding: 3px 10px; margin: 2px 4px 2px 0;
                background: var(--bg-light-gray); border-radius: 20px;
                font-size: 12px; color: var(--text-color);
            }
            .biu-pill-action { background: var(--blue-50, #eef2ff); }

            .biu-row {
                display: flex; gap: 6px; align-items: center;
                margin-bottom: 6px; flex-wrap: wrap;
            }
            .biu-select { min-width: 100px; max-width: 180px; font-size: 12px; }
            .biu-input { min-width: 80px; max-width: 200px; font-size: 12px; }

            .biu-editor-buttons {
                display: flex; gap: 10px; justify-content: flex-end;
                padding-top: 16px; border-top: 1px solid var(--border-color);
            }

            /* ── Preview ── */
            .biu-preview { }
            .biu-preview-topbar {
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 14px;
            }
            .biu-link { color: var(--primary); cursor: pointer; font-size: 13px; font-weight: 600; }
            .biu-link:hover { text-decoration: underline; }

            .biu-execute-bar {
                display: flex; justify-content: space-between; align-items: center;
                padding: 10px 14px; margin-bottom: 12px;
                background: var(--fg-color); border: 1px solid var(--border-color);
                border-radius: var(--border-radius);
            }
            .biu-execute-bar-bottom { margin-top: 12px; margin-bottom: 0; }
            .biu-execute-buttons { display: flex; gap: 8px; align-items: center; }
            .biu-match-count { font-size: 13px; }

            .biu-table-wrap { overflow-x: auto; }
            .biu-table { font-size: 12px; }
            .biu-table thead { background: var(--bg-light-gray); }
            .biu-th { font-weight: 600; font-size: 11px; text-transform: uppercase; white-space: nowrap; }
            .biu-changed { color: var(--green-600, #16a34a); font-weight: 700; background: var(--green-50, #f0fdf4); }

            .biu-pagination {
                display: flex; justify-content: space-between; align-items: center;
                margin-top: 10px;
            }

            .biu-rules-summary {
                margin-top: 20px; padding: 14px;
                background: var(--fg-color); border: 1px solid var(--border-color);
                border-radius: var(--border-radius);
            }
            .biu-summary-list { margin: 0; padding-left: 18px; font-size: 13px; }
            .biu-summary-list li { margin-bottom: 3px; }
            .biu-action-li { color: var(--primary); }

            .btn.disabled { opacity: 0.5; cursor: not-allowed; }

            .biu-price-note {
                font-size: 12px; color: var(--text-muted);
                background: var(--yellow-50, #fefce8); border: 1px solid var(--yellow-200, #fde68a);
                border-radius: var(--border-radius); padding: 8px 12px; margin-bottom: 14px;
            }
        `;
        document.head.appendChild(style);
    }

    // ── Initial render ──
    render();
};