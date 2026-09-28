<template>
	<div class="pg" :class="{ 'pg--readonly': !editable }">
		<!-- no revision in the route: build one, or pick a recent one -->
		<div v-if="!state.name" class="pg-pick">
			<Builder />
			<div class="pg-pick__title">{{ t("Recent price revisions") }}</div>
			<div v-if="!recent.length" class="pg-muted">{{ t("None yet.") }}</div>
			<table v-else class="pg-pick__table">
				<tr v-for="r in recent" :key="r.name" @click="go(r.name)">
					<td><a :href="'/app/price-grid/' + encodeURIComponent(r.name)" @click.prevent>{{ r.name }}</a></td>
					<td>{{ r.supplier_name || r.supplier }}</td>
					<td class="pg-muted">{{ r.supplier_order_confirmation || r.rate_source }}</td>
					<td><span class="indicator-pill" :class="statusColour(r.status)">{{ r.status }}</span></td>
					<td class="pg-num">{{ r.total_items }} {{ t("items") }} · {{ r.total_price_changes }} {{ t("changes") }}</td>
					<td class="pg-muted">{{ prettyDate(r.modified) }}</td>
				</tr>
			</table>
		</div>

		<div v-else-if="error" class="pg-error">{{ error }}</div>
		<div v-else-if="!grid" class="pg-muted pg-loading">{{ t("Loading…") }}</div>

		<template v-else>
			<div v-if="busy" class="pg-job">
				<div class="pg-job__text">
					<b>{{ jobLabel }}</b> · {{ doc.job_message || t("Working…") }}
					<span class="pg-muted">{{ t("The grid is read-only until this finishes. You can leave the page; it keeps going.") }}</span>
				</div>
				<div class="pg-job__bar"><div class="pg-job__fill" :style="{ width: (doc.job_progress || 2) + '%' }"></div></div>
			</div>
			<div v-else-if="doc.job_status === 'Failed'" class="pg-banner pg-banner--red">
				<span>{{ t("The last background job ({0}) stopped: {1}", [jobLabel, doc.job_message || ""]) }}</span>
				<span class="pg-muted">{{ t("Nothing half-done is lost: run it again and it carries on from where it stopped.") }}</span>
			</div>
			<div v-if="banner" class="pg-banner" :class="'pg-banner--' + banner.tone">
				<span>{{ banner.text }}</span>
				<a v-if="banner.link" :href="banner.link" target="_blank">{{ banner.linkText }}</a>
			</div>

			<div class="pg-summary">
				<div class="pg-stat">
					<div class="pg-stat__label">{{ t("Supplier") }}</div>
					<div class="pg-stat__value">
						<a :href="'/app/supplier/' + encodeURIComponent(doc.supplier)" target="_blank">{{ doc.supplier_name }}</a>
					</div>
				</div>
				<div class="pg-stat">
					<div class="pg-stat__label">{{ doc.confirmation ? t("Cost change from") : t("Items") }}</div>
					<div class="pg-stat__value">
						<template v-if="doc.confirmation">
							<a :href="'/app/supplier-order-confirmation-v3/' + encodeURIComponent(doc.confirmation)" target="_blank">{{ doc.confirmation }}</a>
							<a v-if="doc.purchase_order_v3" class="pg-stat__aside" :href="'/app/purchase-order-v3/' + encodeURIComponent(doc.purchase_order_v3)" target="_blank">{{ doc.purchase_order_v3 }}</a>
						</template>
						<span v-else :title="doc.rate_source">{{ doc.total_items }} · {{ doc.rate_source }}</span>
					</div>
				</div>
				<div class="pg-stat">
					<div class="pg-stat__label">{{ t("Currency") }}</div>
					<div class="pg-stat__value">
						<template v-if="doc.supplier_currency !== doc.company_currency">
							1 {{ doc.supplier_currency }} = {{ doc.conversion_rate }} {{ doc.company_currency }}
						</template>
						<template v-else>{{ doc.company_currency }}</template>
					</div>
				</div>
				<div v-if="doc.avg_cost_change_pct" class="pg-stat">
					<div class="pg-stat__label">{{ t("Avg cost change") }}</div>
					<div class="pg-stat__value" :class="doc.avg_cost_change_pct > 0 ? 'pg-up' : 'pg-down'">{{ signed(doc.avg_cost_change_pct) }}%</div>
				</div>
				<div class="pg-stat">
					<div class="pg-stat__label">{{ t("Avg margin") }}</div>
					<div class="pg-stat__value">{{ num(doc.avg_margin_before, 1) }}% → {{ num(doc.avg_margin_after, 1) }}%</div>
				</div>
				<div class="pg-stat">
					<div class="pg-stat__label">{{ t("Price changes") }}</div>
					<div class="pg-stat__value">
						{{ doc.total_price_changes }}
						<span v-if="doc.total_new_listings" class="pg-stat__aside">{{ doc.total_new_listings }} {{ t("new") }}</span>
						<span v-if="doc.total_removals" class="pg-stat__aside">{{ doc.total_removals }} {{ t("removed") }}</span>
					</div>
				</div>
				<button class="pg-stat pg-stat--button" :class="{ 'pg-stat--alert': doc.lines_needing_review }" @click="setFilter('review')">
					<div class="pg-stat__label">{{ t("Needs a decision") }}</div>
					<div class="pg-stat__value">{{ doc.lines_needing_review }}</div>
				</button>
			</div>

			<div class="pg-toolbar">
				<div v-if="doc.confirmation" class="btn-group" :title="t('Which lines of the order are on this revision')">
					<button class="btn btn-xs" :class="!doc.whole_order ? 'btn-primary' : 'btn-default'" :disabled="!editable" @click="wholeOrder(false)">
						{{ t("Cost changes") }} <span class="pg-count">{{ doc.cost_changes }}</span>
					</button>
					<button class="btn btn-xs" :class="doc.whole_order ? 'btn-primary' : 'btn-default'" :disabled="!editable" @click="wholeOrder(true)">
						{{ t("Whole PO") }} <span class="pg-count">{{ doc.order_lines }}</span>
					</button>
				</div>
				<label
					class="pg-switch"
					:class="{ 'pg-switch--on': doc.use_suggested, 'pg-switch--disabled': !editable }"
					:title="t('On: lines whose cost changed take the suggested price. Off: current prices are kept; suggestions show as the placeholder in each cell.')"
				>
					<input type="checkbox" :checked="!!doc.use_suggested" :disabled="!editable" @change="toggleSuggested($event)" />
					<span class="pg-switch__track"><span class="pg-switch__knob"></span></span>
					{{ t("Use Suggested Price") }}
				</label>
				<div class="btn-group pg-filters">
					<template v-for="f in filters" :key="f.key">
						<button
							v-if="!f.hide && (f.always || counts[f.key])"
							class="btn btn-xs"
							:class="filter === f.key ? 'btn-primary' : 'btn-default'"
							@click="setFilter(f.key)"
						>
							{{ f.label }} <span class="pg-count">{{ counts[f.key] }}</span>
						</button>
					</template>
				</div>
				<input v-model="search" class="form-control input-xs pg-search" :placeholder="t('Search item, name, SKU or brand')" @input="limit = PAGE" />
				<label class="pg-check"><input v-model="showDetail" type="checkbox" /> {{ t("Show was / margin") }}</label>
				<button v-if="editable" class="btn btn-xs btn-default" @click.stop="openMenu($event, bulkMenu())">{{ t("Bulk") }} ▾</button>
				<button v-if="editable" class="btn btn-xs btn-default" @click="addPriceList">+ {{ t("Price List") }}</button>
				<span class="pg-spacer"></span>
				<span v-if="dirtyCount" class="pg-dirty">{{ dirtyCount }} {{ t("unsaved") }} · Ctrl+S</span>
				<span class="pg-legend">
					<span class="pg-key pg-key--up">{{ t("Update") }}</span>
					<span class="pg-key pg-key--hold">{{ t("Hold") }}</span>
					<span class="pg-key pg-key--review">{{ t("Decide") }}</span>
					<span class="pg-key pg-key--under">{{ t("Under cost") }}</span>
					<span class="pg-key pg-key--remove">{{ t("Remove") }}</span>
					<span class="pg-key pg-key--pending">{{ t("Unsaved") }}</span>
					<span class="pg-key pg-key--edited">{{ t("Set by hand") }}</span>
				</span>
			</div>

			<div ref="scroll" class="pg-scroll" @paste="onPaste">
				<table class="pg-table">
					<thead>
						<tr>
							<th class="pg-sticky pg-c-item" @click="sortBy('item')">
								{{ t("Item") }} <span class="pg-sort">{{ sortMark("item") }}</span>
							</th>
							<th class="pg-sticky pg-c-cost" @click="sortBy('cost')">
								{{ t("Cost") }} <span class="pg-ccy">{{ doc.supplier_currency }}</span>
								<span class="pg-sort">{{ sortMark("cost") }}</span>
							</th>
							<th class="pg-sticky pg-c-landed-usd" :title="t('Cost + duty in USD. A CAD supplier is converted at the latest rate on file.')">
								{{ t("Landed") }} <span class="pg-ccy">USD</span>
							</th>
							<th class="pg-sticky pg-c-landed">{{ t("Landed") }} <span class="pg-ccy">{{ doc.company_currency }}</span></th>
							<th v-for="l in lists" :key="l.name" class="pg-c-list">
								<div class="pg-lh">
									<div class="pg-lh__name" :title="l.name">{{ l.label }} <span class="pg-ccy">{{ l.currency }}</span></div>
									<div class="pg-lh__meta">
										<span v-if="l.markup" :title="markupTitle(l)" :class="{ 'pg-weak': l.low_confidence }">×{{ num(l.markup, 2) }}</span>
										<span v-if="l.exempt" :title="t('Exempt from the margin floor, but never priced under landed cost')">{{ t("no floor") }}</span>
										<span v-else-if="l.floor">{{ t("floor") }} {{ num(l.floor, 0) }}%</span>
										<span v-if="l.always" class="pg-badge" :title="t('Every item is priced on this list (ICL Pricing Settings)')">{{ t("all items") }}</span>
										<span v-else-if="l.every_item" class="pg-badge" :title="t('Added to this revision for every item')">{{ t("added") }}</span>
									</div>
									<button v-if="editable" class="pg-menu-btn" :title="t('Column actions')" @click.stop="openMenu($event, listMenu(l))">⋯</button>
								</div>
							</th>
						</tr>
					</thead>
					<tbody>
						<GridRow
							v-for="(row, r) in shown"
							:key="row.item_code"
							:row="row"
							:r="r"
							:lists="lists"
							:store="store"
							:editable="editable"
							:show-detail="showDetail"
						/>
						<tr v-if="!rows.length">
							<td class="pg-none" :colspan="4 + lists.length">{{ t("No items match this filter.") }}</td>
						</tr>
					</tbody>
				</table>
				<div v-if="rows.length > shown.length" class="pg-more">
					<button class="btn btn-default btn-xs" @click="limit += PAGE">
						{{ t("Show {0} more", [Math.min(PAGE, rows.length - shown.length)]) }}
					</button>
					<span class="pg-muted">{{ t("{0} of {1} items shown", [shown.length, rows.length]) }}</span>
				</div>
			</div>
			<div class="pg-foot pg-muted">
				{{ t("Arrow keys and Enter move between cells. Esc undoes a cell. Paste a block from Excel into any cell. × removes a price, + adds one. Hover a cell for how its price was worked out.") }}
			</div>
		</template>

		<div v-if="menu" class="dropdown-menu show pg-dropdown" :style="menu.style" @click.stop>
			<template v-for="(m, i) in menu.items" :key="i">
				<div v-if="m.divider" class="dropdown-divider"></div>
				<a v-else class="dropdown-item" :class="{ disabled: m.disabled }" @click="!m.disabled && ((menu = null), m.fn())">{{ m.label }}</a>
			</template>
		</div>
	</div>
</template>

<script>
import Builder from "./Builder.vue";
import GridRow from "./GridRow.vue";
import { cellView, key, landedFor, parse, roundUp, SEP } from "./cells";

const API = "metactical.pricing.api.";
const PAGE = 200;
const STATUS_COLOUR = { Draft: "blue", "Pending Review": "orange", Applied: "green", Reverted: "gray", Cancelled: "red" };

export default {
	name: "PriceGrid",
	components: { Builder, GridRow },
	props: {
		page: { type: Object, required: true },
		state: { type: Object, required: true },
	},
	provide() {
		return { g: this };
	},
	data() {
		return {
			PAGE,
			grid: null,
			error: null,
			recent: [],
			// unsaved work: edits "item␁list" -> raw ("" = back to suggestion),
			// removes "item␁list" -> bool, costs item -> raw
			store: { edits: {}, removes: {}, costs: {}, company_currency: null },
			filter: "all",
			search: "",
			showDetail: true,
			sort: { key: null, dir: 1 },
			limit: PAGE,
			menu: null,
		};
	},
	computed: {
		doc() {
			return this.grid ? this.grid.doc : {};
		},
		lists() {
			return this.grid ? this.grid.lists : [];
		},
		busy() {
			return !!this.grid && ["Queued", "Running"].includes(this.grid.doc.job_status);
		},
		editable() {
			return !!(this.grid && this.grid.doc.editable) && !this.busy;
		},
		jobLabel() {
			const op = this.doc.job_operation;
			return { build: __("Building"), edit: __("Saving"), apply: __("Applying prices"), revert: __("Reverting") }[op] || __("Working");
		},
		dirtyCount() {
			const s = this.store;
			return Object.keys(s.edits).length + Object.keys(s.removes).length + Object.keys(s.costs).length;
		},
		filters() {
			return [
				{ key: "all", label: __("All"), always: true },
				{ key: "cost", label: __("Cost changed"), always: true, hide: !this.doc.whole_order },
				{ key: "changed", label: __("Price changes"), always: true },
				{ key: "review", label: __("Needs a decision"), always: true },
				{ key: "hold", label: __("Held") },
				{ key: "new", label: __("New on a list") },
				{ key: "remove", label: __("Removing") },
				{ key: "edited", label: __("Set by hand") },
			];
		},
		// one pass over every cell; filters and counts both read it
		flags() {
			const out = new Map();
			if (!this.grid) return out;
			for (const row of this.grid.rows) {
				const f = {
					cost: Math.abs(row.new_cost - row.old_cost) >= 0.005 || row.item_code in this.store.costs,
					changed: false, review: false, hold: false, new: false, remove: false,
					edited: row.item_code in this.store.costs,
				};
				for (const l of this.lists) {
					const v = cellView(row, l, this.store);
					if (!v) continue;
					if (v.state === "up") f.changed = true;
					if (v.state === "review" || v.state === "under") f.review = true;
					if (v.state === "hold") f.hold = true;
					if (v.state === "remove") f.remove = true;
					if (v.isNew && v.state === "up") f.new = true;
					if (v.cell.edited || v.changed) f.edited = true;
				}
				out.set(row.item_code, f);
			}
			return out;
		},
		counts() {
			const out = { all: 0, cost: 0, changed: 0, review: 0, hold: 0, new: 0, remove: 0, edited: 0 };
			for (const f of this.flags.values()) {
				out.all += 1;
				for (const k in f) if (f[k]) out[k] += 1;
			}
			return out;
		},
		rows() {
			if (!this.grid) return [];
			const q = this.search.trim().toLowerCase();
			let rows = this.grid.rows.filter((row) => {
				if (this.filter !== "all" && !this.flags.get(row.item_code)[this.filter]) return false;
				if (!q) return true;
				return [row.item_code, row.item_name, row.brand, row.retail_sku].some((v) => v && String(v).toLowerCase().includes(q));
			});
			if (this.sort.key) {
				const k = this.sort.key === "cost" ? (r) => r.cost_change_pct : (r) => r.item_code;
				rows = rows.slice().sort((a, b) => (k(a) > k(b) ? 1 : k(a) < k(b) ? -1 : 0) * this.sort.dir);
			}
			return rows;
		},
		shown() {
			return this.rows.slice(0, this.limit);
		},
		banner() {
			const d = this.doc;
			if (d.status === "Applied")
				return {
					tone: "green",
					text: __("Applied {0} by {1}. These prices are live.", [this.prettyDate(d.applied_on), d.applied_by]),
					link: "/app/price-revision-log?price_revision=" + encodeURIComponent(d.name),
					linkText: __("What this changed"),
				};
			if (d.status === "Reverted")
				return { tone: "grey", text: __("Reverted {0}. Everything it changed was put back.", [this.prettyDate(d.reverted_on)]) };
			if (d.status === "Pending Review")
				return { tone: "orange", text: __("Submitted and waiting to be applied. Prices can no longer be edited here.") };
			if (d.status === "Cancelled") return { tone: "grey", text: __("Cancelled.") };
			return null;
		},
	},
	watch: {
		"state.nonce"() {
			this.open();
		},
		dirtyCount() {
			this.syncActions();
		},
		filter() {
			this.limit = PAGE;
		},
	},
	mounted() {
		this._outside = () => (this.menu = null);
		document.addEventListener("click", this._outside);
		this._unload = (e) => {
			if (this.dirtyCount) {
				e.preventDefault();
				e.returnValue = "";
			}
		};
		window.addEventListener("beforeunload", this._unload);
		this._onJob = (data) => this.onJob(data);
		frappe.realtime.on("price_revision_job", this._onJob);
		this.open();
	},
	unmounted() {
		document.removeEventListener("click", this._outside);
		window.removeEventListener("beforeunload", this._unload);
		frappe.realtime.off("price_revision_job", this._onJob);
		clearInterval(this._poll);
	},
	methods: {
		t(text, args) {
			return __(text, args);
		},

		// ------------------------------------------------------------ loading

		open() {
			if (!this.state.name) {
				this.grid = null;
				this.page.set_title(__("Price Revisions"));
				this.page.clear_indicator();
				this.syncActions();
				frappe.db
					.get_list("Price Revision", {
						fields: ["name", "supplier", "supplier_name", "status", "supplier_order_confirmation", "rate_source",
							"total_items", "total_price_changes", "modified"],
						filters: { docstatus: ["<", 2] },
						order_by: "modified desc",
						limit: 30,
					})
					.then((r) => (this.recent = r || []));
				return;
			}
			// coming back to the same revision keeps unsaved edits
			if (this.grid && this.grid.doc.name === this.state.name && this.dirtyCount) return;
			this.error = null;
			if (this.grid && this.grid.doc.name !== this.state.name) this.grid = null;
			this.call("get_grid", { name: this.state.name })
				.then((g) => this.take(g))
				.catch(() => (this.error = __("Could not load {0}.", [this.state.name])));
		},

		call(method, args, freeze) {
			return frappe
				.call({ method: API + method, args, freeze: !!freeze, freeze_message: freeze || undefined })
				.then((r) => r.message);
		},

		// A change to a large revision comes back {queued: true}: the work runs
		// as a background job and the grid follows it. Resolves to the fresh
		// grid when the change was made straight away, or null when queued.
		mutate(method, args, freeze) {
			return this.call(method, args, freeze).then((r) => {
				if (r && r.queued) {
					this.grid.doc.job_operation = { apply_grid: "apply", revert_grid: "revert" }[method] || "edit";
					this.grid.doc.job_status = "Queued";
					this.grid.doc.job_progress = 0;
					this.grid.doc.job_message = __("Waiting for a worker…");
					this.watchJob();
					frappe.show_alert({ message: __("Large revision: working on it in the background"), indicator: "blue" }, 4);
					return null;
				}
				return r;
			});
		},

		watchJob() {
			this.syncActions();
			clearInterval(this._poll);
			this._poll = setInterval(() => {
				if (!this.grid) return clearInterval(this._poll);
				this.call("job_state", { name: this.grid.doc.name }).then((j) => {
					if (!j || !this.grid) return;
					Object.assign(this.grid.doc, {
						job_status: j.job_status || "", job_progress: j.job_progress, job_message: j.job_message,
					});
					if (!["Queued", "Running"].includes(j.job_status)) this.jobEnded(j.job_status === "Failed");
					else this.syncActions();
				});
			}, 4000);
		},

		onJob(data) {
			if (!this.grid || !data || data.name !== this.grid.doc.name) return;
			if (data.status === "Done") return this.jobEnded(false);
			if (data.status === "Failed") {
				this.grid.doc.job_status = "Failed";
				this.grid.doc.job_message = data.message;
				return this.jobEnded(true);
			}
			Object.assign(this.grid.doc, {
				job_status: data.status,
				job_progress: data.progress == null ? this.grid.doc.job_progress : data.progress,
				job_message: data.message,
			});
			this.syncActions();
		},

		jobEnded(failed) {
			clearInterval(this._poll);
			this._poll = null;
			const name = this.grid.doc.name;
			this.call("get_grid", { name }).then((g) => {
				this.take(g, failed);  // a failed save keeps your unsaved edits
				if (failed) frappe.msgprint({ title: __("Background job stopped"), message: g.doc.job_message || "", indicator: "red" });
				else frappe.show_alert({ message: __("{0} is up to date", [name]), indicator: "green" }, 5);
			});
		},

		take(grid, keepEdits) {
			const old = this.store;
			this.grid = grid;
			if (["Queued", "Running"].includes(grid.doc.job_status) && !this._poll) this.$nextTick(() => this.watchJob());
			this.store = { edits: {}, removes: {}, costs: {}, company_currency: grid.doc.company_currency };
			if (keepEdits) {
				const present = new Set(grid.rows.map((r) => r.item_code));
				for (const part of ["edits", "removes"])
					for (const [k, v] of Object.entries(old[part])) if (present.has(k.split(SEP)[0])) this.store[part][k] = v;
				for (const [k, v] of Object.entries(old.costs)) if (present.has(k)) this.store.costs[k] = v;
			}
			this.syncActions();
		},

		go(name) {
			frappe.set_route("price-grid", name);
		},

		// ------------------------------------------------------- page actions

		syncActions() {
			const p = this.page;
			p.clear_primary_action();
			p.clear_secondary_action();
			p.clear_inner_toolbar();
			p.clear_menu();
			if (!this.grid) return;

			const d = this.doc;
			p.set_title(d.name + " · " + d.supplier_name);
			if (this.busy) {
				p.set_indicator(this.jobLabel + " " + Math.round(d.job_progress || 0) + "%", "orange");
				p.set_secondary_action(__("Reload"), () => this.reload(), "refresh");
				return;
			}
			p.set_indicator(this.dirtyCount ? __("Not Saved") : __(d.status), this.dirtyCount ? "orange" : STATUS_COLOUR[d.status] || "gray");

			if (this.editable && this.dirtyCount) {
				p.set_primary_action(__("Save"), () => this.save(), "save");
			} else if ((d.status === "Draft" || d.status === "Pending Review") && d.can_apply) {
				p.set_primary_action(__("Apply Prices"), () => this.apply());
			} else if (d.status === "Reverted" && d.confirmation) {
				p.set_primary_action(__("Start New Revision"), () => this.startNew());
			}
			if (d.status === "Applied" && d.can_apply) {
				p.add_inner_button(__("Revert"), () => this.revert());
			}
			p.set_secondary_action(__("Reload"), () => this.reload(), "refresh");

			p.add_menu_item(__("Open Revision Record"), () => frappe.set_route("Form", "Price Revision", d.name));
			if (d.confirmation)
				p.add_menu_item(__("Open Supplier Confirmation"), () =>
					frappe.set_route("Form", "Supplier Order Confirmation V3", d.confirmation)
				);
			p.add_menu_item(__("Pricing Matrix"), () =>
				frappe.set_route("List", "Pricing Matrix", { buying_price_list: d.buying_price_list })
			);
			p.add_menu_item(__("ICL Pricing Settings"), () => frappe.set_route("Form", "ICL Pricing Settings"));
			p.add_menu_item(__("New / All Price Revisions"), () => frappe.set_route("price-grid"));
		},

		reload() {
			const go = () => this.call("get_grid", { name: this.doc.name }).then((g) => this.take(g));
			if (!this.dirtyCount) return go();
			frappe.confirm(__("Throw away {0} unsaved change(s)?", [this.dirtyCount]), go);
		},

		payload() {
			const cells = {};
			const cellFor = (k) => {
				if (!cells[k]) {
					const [item_code, price_list] = k.split(SEP);
					cells[k] = { item_code, price_list };
				}
				return cells[k];
			};
			for (const [k, raw] of Object.entries(this.store.edits)) {
				const v = parse(raw);
				if (Number.isNaN(v) || (v !== null && v < 0)) return { bad: k.replace(SEP, " · ") };
				const [item_code, price_list] = k.split(SEP);
				const row = this.grid.rows.find((x) => x.item_code === item_code);
				if (v === null && !(row && row.cells[price_list])) continue; // an added cell left empty
				cellFor(k).new_price = v;
			}
			for (const [k, on] of Object.entries(this.store.removes)) cellFor(k).remove = on ? 1 : 0;
			const items = [];
			for (const [item_code, raw] of Object.entries(this.store.costs)) {
				const v = parse(raw);
				if (!(v > 0)) return { bad: item_code + " · " + __("cost") };
				items.push({ item_code, new_cost: v });
			}
			return { cells: Object.values(cells), items };
		},

		save() {
			const body = this.payload();
			if (body.bad) {
				frappe.msgprint(__("{0} is not a valid amount.", [body.bad]));
				return Promise.reject();
			}
			return this.mutate("save_grid", { name: this.doc.name, cells: body.cells, items: body.items }, __("Saving…")).then((g) => {
				if (!g) return;
				this.take(g);
				frappe.show_alert({ message: __("Saved"), indicator: "green" }, 3);
			});
		},

		apply() {
			const run = () => {
				const d = this.doc;
				const costs = this.grid.rows.filter((r) => r.apply && Math.abs(r.new_cost - r.old_cost) >= 0.005).length;
				let msg = __("Write {0} price change(s) and {1} supplier cost(s) to Item Price?", [d.total_price_changes, costs]);
				if (d.total_new_listings) msg += "<br>" + __("{0} of those are new prices on a list.", [d.total_new_listings]);
				if (d.total_removals) msg += "<br>" + __("<b>{0} price(s) will be removed</b> from their list.", [d.total_removals]);
				if (d.lines_needing_review)
					msg += "<br><br>" + __("<b>{0} cell(s) still need a decision</b> and will be left as they are.", [d.lines_needing_review]);
				frappe.confirm(msg, () =>
					this.mutate("apply_grid", { name: d.name }, __("Writing prices…")).then((r) => {
						if (!r) return;
						this.take(r.grid);
						frappe.show_alert({ message: __("{0} prices written, {1} removed", [r.written, r.removed || 0]), indicator: "green" }, 6);
					})
				);
			};
			// a large save runs in the background; apply once it has finished
			this.dirtyCount ? this.save().then(() => !this.busy && run()) : run();
		},

		revert() {
			frappe.confirm(__("Put everything this revision changed back to what it was?"), () =>
				this.mutate("revert_grid", { name: this.doc.name }, __("Reverting…")).then((r) => {
					if (!r) return;
					this.take(r.grid);
					frappe.show_alert({ message: __("{0} prices put back", [r.reverted]), indicator: "orange" }, 6);
				})
			);
		},

		startNew() {
			this.call("open_for_confirmation", { confirmation: this.doc.confirmation, new: 1 }, __("Building…")).then((name) =>
				this.go(name)
			);
		},

		toggleSuggested(ev) {
			const on = ev.target.checked;
			this.mutate("set_use_suggested", { name: this.doc.name, on: on ? 1 : 0 }, on ? __("Applying suggested prices…") : __("Keeping current prices…")).then((g) => {
				if (!g) return;
				this.take(g, true);
				frappe.show_alert({
					message: on ? __("{0} price changes suggested", [g.doc.total_price_changes]) : __("Current prices kept; set the ones you want"),
					indicator: on ? "green" : "blue",
				}, 4);
			});
		},

		wholeOrder(on) {
			if (!!this.doc.whole_order === on) return;
			const run = () =>
				this.mutate("set_whole_order", { name: this.doc.name, on: on ? 1 : 0 }, on ? __("Pulling in the whole order…") : __("Back to cost changes…")).then((g) => {
					if (!g) return;
					this.take(g, true);
					this.filter = "all";
				});
			const unchangedEdits = on ? 0 : this.grid.rows.filter(
				(r) => Math.abs(r.new_cost - r.old_cost) < 0.005 && !(r.item_code in this.store.costs) &&
					this.lists.some((l) => r.cells[l.name] && (r.cells[l.name].edited || r.cells[l.name].remove || key(r, l) in this.store.edits))
			).length;
			if (unchangedEdits)
				frappe.confirm(__("{0} line(s) without a cost change have prices set here. Taking them out drops those edits. Continue?", [unchangedEdits]), run);
			else run();
		},

		// Changing the columns saves the revision; unsaved cell edits ride along
		addPriceList() {
			this.call("selectable_price_lists", { name: this.doc.name }).then((options) => {
				if (!options.length) return frappe.msgprint(__("Every selling price list is already on this revision."));
				const d = new frappe.ui.Dialog({
					title: __("Add a price list"),
					fields: [
						{
							fieldname: "price_list", fieldtype: "Select", label: __("Price List"), reqd: 1,
							options: options.map((o) => ({ value: o.name, label: o.name + " (" + o.currency + ")" })),
						},
						{
							fieldtype: "HTML",
							options: `<div class="text-muted small">${__("Every item gets a cell on this list. Items already on it start from their current price; the rest are priced from the markup, or left for you to fill in.")}</div>`,
						},
					],
					primary_action_label: __("Add"),
					primary_action: ({ price_list }) => {
						d.hide();
						this.mutate("add_price_list", { name: this.doc.name, price_list }, __("Adding {0}…", [price_list])).then((g) =>
							g && this.take(g, true)
						);
					},
				});
				d.show();
			});
		},

		dropPriceList(l) {
			frappe.confirm(
				__("Take {0} out of this revision? Its prices are not touched; they just won't be revised here.", [l.name]),
				() => this.mutate("drop_price_list", { name: this.doc.name, price_list: l.name }).then((g) => g && this.take(g, true))
			);
		},

		// -------------------------------------------------------------- cells

		setCell(row, l, value) {
			const cell = row.cells[l.name];
			const k = key(row, l);
			if (!cell) {
				if (value === "" || !(value > 0)) delete this.store.edits[k];
				else this.store.edits[k] = this.fixed(value);
				return;
			}
			if (value === "") {
				// back to the suggestion: only meaningful if it was set by hand
				if (cell.edited) this.store.edits[k] = "";
				else delete this.store.edits[k];
				return;
			}
			if (!cell.edited && Math.abs(value - cell.new) < 0.005) delete this.store.edits[k];
			else this.store.edits[k] = this.fixed(value);
		},

		setRemove(row, l, on) {
			const cell = row.cells[l.name];
			if (!cell || !cell.old) return;
			const k = key(row, l);
			if (!!cell.remove === on) delete this.store.removes[k];
			else this.store.removes[k] = on;
		},

		// Removing a price deletes it from the list when applied, so it always
		// asks first. Putting one back does not.
		toggleRemove(row, l) {
			const v = cellView(row, l, this.store);
			if (!v) return;
			if (v.removing) return this.setRemove(row, l, false);
			frappe.confirm(
				__("Remove {0}'s price on {1} ({2}) when this revision is applied?<br><br>It is deleted from the list, not set to zero. Revert puts it back.", [
					row.item_code, l.label, this.money(v.cell.old),
				]),
				() => this.setRemove(row, l, true)
			);
		},

		startCell(row, l, r, c) {
			this.store.edits[key(row, l)] = "";
			this.$nextTick(() => {
				const el = this.input(r, c);
				if (el) el.focus();
			});
		},

		fill(rows, lists, fn) {
			for (const row of rows)
				for (const l of lists) {
					const v = cellView(row, l, this.store);
					if (v && !v.removing) this.setCell(row, l, fn(v.cell, row, l, v));
				}
		},

		useSuggested(rows, lists) {
			this.fill(rows, lists, (cell) => (cell.edited ? "" : cell.suggested || cell.old));
		},
		keepCurrent(rows, lists) {
			this.fill(rows, lists, (cell) => (cell.old ? cell.old : ""));
		},
		clearHandSet(rows, lists) {
			this.fill(rows, lists, (cell) => (cell.edited ? "" : cell.new));
		},
		removeAll(rows, lists, on) {
			const apply = () => {
				for (const row of rows) for (const l of lists) this.setRemove(row, l, on);
			};
			if (!on) return apply();
			const count = rows.filter((row) => lists.some((l) => row.cells[l.name] && row.cells[l.name].old)).length;
			if (!count) return;
			frappe.confirm(
				__("Remove {0} price(s) from {1} when this revision is applied?<br><br>They are deleted from the list, not set to zero. Revert puts them back.", [
					count, lists.map((l) => l.label).join(", "),
				]),
				apply
			);
		},
		raiseBy(rows, lists) {
			frappe.prompt(
				{ fieldname: "pct", fieldtype: "Float", label: __("Raise the current price by %"), reqd: 1 },
				({ pct }) => this.fill(rows, lists, (cell) => (cell.old ? roundUp(cell.old * (1 + pct / 100), this.rounding()) : "")),
				__("Raise prices"),
				__("Fill")
			);
		},
		priceAtMarkup(rows, l) {
			frappe.prompt(
				{ fieldname: "markup", fieldtype: "Float", label: __("Landed cost ×"), default: l.markup || 2, reqd: 1 },
				({ markup }) => {
					for (const row of rows) {
						const landed = landedFor(row, l, this.store);
						const v = cellView(row, l, this.store);
						if (landed && (!v || !v.removing)) this.setCell(row, l, roundUp(landed * markup, this.rounding()));
					}
				},
				__("Price at a markup"),
				__("Fill")
			);
		},
		rounding() {
			return this.doc.rounding_rule || "0.99";
		},

		bulkMenu() {
			const rows = this.rows;
			const n = rows.length;
			return [
				{ label: __("Use suggested prices ({0} rows)", [n]), fn: () => this.useSuggested(rows, this.lists) },
				{ label: __("Keep current prices ({0} rows)", [n]), fn: () => this.keepCurrent(rows, this.lists) },
				{ label: __("Raise current prices by %… ({0} rows)", [n]), fn: () => this.raiseBy(rows, this.lists) },
				{ divider: true },
				{ label: __("Clear hand-set prices"), fn: () => this.clearHandSet(rows, this.lists) },
				{ label: __("Undo unsaved changes"), fn: () => this.take(this.grid) },
			];
		},

		listMenu(l) {
			const rows = this.rows;
			return [
				{ label: __("Use suggested prices"), fn: () => this.useSuggested(rows, [l]) },
				{ label: __("Keep current prices"), fn: () => this.keepCurrent(rows, [l]) },
				{ label: __("Raise current prices by %…"), fn: () => this.raiseBy(rows, [l]) },
				{ label: __("Price at a markup…"), fn: () => this.priceAtMarkup(rows, l) },
				{ divider: true },
				{ label: __("Clear hand-set prices"), fn: () => this.clearHandSet(rows, [l]) },
				{ label: __("Remove these items from {0} ({1} rows)", [l.label, rows.length]), fn: () => this.removeAll(rows, [l], true) },
				{ label: __("Keep these items on {0}", [l.label]), fn: () => this.removeAll(rows, [l], false) },
				{ divider: true },
				{
					label: l.always ? __("Always included (see settings)") : __("Take this list out of the revision"),
					disabled: !!l.always,
					fn: () => this.dropPriceList(l),
				},
			];
		},

		rowMenu(row) {
			return [
				{ label: __("Use suggested prices"), fn: () => this.useSuggested([row], this.lists) },
				{ label: __("Keep current prices"), fn: () => this.keepCurrent([row], this.lists) },
				{ label: __("Raise current prices by %…"), fn: () => this.raiseBy([row], this.lists) },
				{ label: __("Clear hand-set prices"), fn: () => this.clearHandSet([row], this.lists) },
				{ label: __("Remove this item from every list"), fn: () => this.removeAll([row], this.lists, true) },
				{ divider: true },
				{
					label: row.apply ? __("Don't update the supplier cost list") : __("Update the supplier cost list"),
					fn: () =>
						this.mutate("save_grid", { name: this.doc.name, cells: [], items: [{ item_code: row.item_code, apply: row.apply ? 0 : 1 }] }).then((g) => g &&
							this.take(g, true)
						),
				},
				{ label: __("Open item"), fn: () => window.open("/app/item/" + encodeURIComponent(row.item_code)) },
			];
		},

		openMenu(ev, items) {
			const r = ev.currentTarget.getBoundingClientRect();
			const left = Math.min(r.left, window.innerWidth - 300);
			this.menu = { items, style: { position: "fixed", top: r.bottom + 4 + "px", left: left + "px" } };
		},

		setFilter(f) {
			this.filter = f;
		},

		// ----------------------------------------------------------- keyboard

		input(r, c) {
			return this.$refs.scroll && this.$refs.scroll.querySelector(`input[data-r="${r}"][data-c="${c}"]`);
		},

		focusCell(r, c, dr, dc) {
			const maxC = this.lists.length;
			for (let step = 0; step < 400; step++) {
				r += dr;
				c += dc;
				if (r < 0 || r >= this.shown.length || c < 0 || c > maxC) return;
				const el = this.input(r, c);
				if (el) {
					el.focus();
					el.scrollIntoView({ block: "nearest", inline: "nearest" });
					return;
				}
			}
		},

		onKey(e, r, c) {
			const el = e.target;
			const atStart = el.selectionStart === 0 && el.selectionEnd === 0;
			const atEnd = el.selectionStart === el.value.length;
			const allSelected = el.selectionStart === 0 && el.selectionEnd === el.value.length;
			if ((e.ctrlKey || e.metaKey) && (e.key || "").toLowerCase() === "s") {
				e.preventDefault();
				e.stopPropagation();
				if (this.dirtyCount) this.save();
				return;
			}
			if (e.key === "Escape") {
				const row = this.shown[r];
				if (c === 0) delete this.store.costs[row.item_code];
				else {
					const k = key(row, this.lists[c - 1]);
					delete this.store.edits[k];
					delete this.store.removes[k];
				}
				this.$nextTick(() => {
					const again = this.input(r, c);
					if (again) again.select();
				});
				return;
			}
			if (e.key === "ArrowDown" || (e.key === "Enter" && !e.shiftKey)) {
				e.preventDefault();
				return this.focusCell(r, c, 1, 0);
			}
			if (e.key === "ArrowUp" || (e.key === "Enter" && e.shiftKey)) {
				e.preventDefault();
				return this.focusCell(r, c, -1, 0);
			}
			if (e.key === "ArrowRight" && (atEnd || allSelected)) {
				e.preventDefault();
				return this.focusCell(r, c, 0, 1);
			}
			if (e.key === "ArrowLeft" && (atStart || allSelected)) {
				e.preventDefault();
				return this.focusCell(r, c, 0, -1);
			}
		},

		// A block copied from Excel fills rightwards and down from the cell
		onPaste(e) {
			if (!this.editable) return;
			const el = e.target;
			if (!el || !el.dataset || el.dataset.r === undefined) return;
			const text = (e.clipboardData || window.clipboardData).getData("text");
			if (!/[\t\n]/.test(text.trim())) return; // single value: let the input take it
			e.preventDefault();
			const r0 = +el.dataset.r;
			const c0 = +el.dataset.c;
			const lines = text.replace(/\r/g, "").replace(/\n$/, "").split("\n");
			lines.forEach((line, i) => {
				const row = this.rows[r0 + i];
				if (!row) return;
				line.split("\t").forEach((raw, j) => {
					const c = c0 + j;
					const v = parse(raw);
					if (v === null || Number.isNaN(v)) return;
					if (c === 0) this.store.costs[row.item_code] = this.fixed(v);
					else if (this.lists[c - 1]) this.setCell(row, this.lists[c - 1], v);
				});
			});
		},

		// ------------------------------------------------------------ helpers

		cellTitle(row, l, v) {
			const cell = v.cell;
			const lines = [l.name + " (" + l.currency + ")"];
			if (v.isNew) lines.push(__("Not on this list yet"));
			else
				lines.push(__("Current") + " " + this.money(cell.old) + (cell.old_margin != null ? " · " + __("margin") + " " + this.num(cell.old_margin, 1) + "%" : ""));
			if (v.removing) lines.push(__("Will be removed from this list"));
			else lines.push(__("New") + " " + this.money(v.price) + (v.margin != null ? " · " + __("margin") + " " + this.num(v.margin, 1) + "%" : ""));
			if (v.landed != null) lines.push(__("Landed") + " " + this.money(v.landed));
			if (cell.by_matrix) lines.push(__("By markup") + " ×" + this.num(cell.markup, 2) + " (" + (cell.markup_source || "") + ") → " + this.money(cell.by_matrix));
			if (cell.by_margin) lines.push(__("Keeping the old margin") + " → " + this.money(cell.by_margin));
			if (l.floor && !l.exempt) lines.push(__("Margin floor") + " " + this.num(l.floor, 0) + "%");
			if (cell.note) lines.push("", cell.note);
			if (v.changed) lines.push("", __("Unsaved"));
			return lines.join("\n");
		},

		sortBy(k) {
			this.sort = this.sort.key === k ? { key: k, dir: -this.sort.dir } : { key: k, dir: k === "cost" ? -1 : 1 };
		},
		sortMark(k) {
			return this.sort.key !== k ? "" : this.sort.dir > 0 ? "↑" : "↓";
		},

		markupTitle(l) {
			return __("Median markup this supplier's list → {0}, from {1} items", [l.name, l.sample_size || 0]) +
				(l.low_confidence ? " — " + __("small sample, treat with care") : "");
		},

		statusColour(status) {
			return STATUS_COLOUR[status] || "gray";
		},

		fixed(v) {
			return v == null || v === "" ? "" : Number(v).toFixed(2);
		},
		money(v) {
			return v == null || v === "" || Number.isNaN(v) ? "" : format_number(v, null, 2);
		},
		num(v, p) {
			return v == null ? "" : Number(v).toFixed(p);
		},
		signed(v) {
			return (v > 0 ? "+" : "") + this.num(v || 0, 1);
		},
		// plain text ("14 minutes ago"); comment_when returns HTML, which a
		// {{ }} binding prints as code
		prettyDate(v) {
			if (!v) return "";
			const pretty = window.prettyDate || (frappe.datetime && frappe.datetime.prettyDate);
			return pretty ? pretty(v) : frappe.datetime.str_to_user(v);
		},
	},
};
</script>
