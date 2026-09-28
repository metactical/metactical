<template>
	<tr>
		<td class="pg-sticky pg-c-item">
			<div class="pg-item">
				<a class="pg-item__code" :href="'/app/item/' + encodeURIComponent(row.item_code)" target="_blank">{{ row.item_code }}</a>
				<span v-if="!row.apply" class="pg-tag" :title="t('The supplier cost list will not be updated for this item')">{{ t("cost not written") }}</span>
				<div class="pg-item__name" :title="row.item_name">{{ row.item_name }}</div>
				<div class="pg-item__meta">
					<template v-if="row.retail_sku">{{ row.retail_sku }} · </template>{{ row.brand || "" }}<template v-if="row.duty_pct"> · {{ t("duty") }} {{ g.num(row.duty_pct, 1) }}%</template>
				</div>
			</div>
			<button v-if="editable" class="pg-menu-btn pg-menu-btn--row" :title="t('Row actions')" @click.stop="g.openMenu($event, g.rowMenu(row))">⋯</button>
		</td>

		<td class="pg-sticky pg-c-cost" :class="{ 'pg-pending': costPending }">
			<input
				class="pg-input"
				:data-r="r"
				data-c="0"
				:value="costPending ? store.costs[row.item_code] : g.fixed(row.new_cost)"
				:readonly="!editable"
				inputmode="decimal"
				@focus="$event.target.select()"
				@input="store.costs[row.item_code] = $event.target.value"
				@keydown="g.onKey($event, r, 0)"
			/>
			<div class="pg-sub">
				<template v-if="costChanged">
					<span>{{ t("was") }} {{ g.money(row.old_cost) }}</span>
					<span :class="row.cost_change_pct > 0 ? 'pg-up' : 'pg-down'">{{ g.signed(row.cost_change_pct) }}%</span>
				</template>
				<span v-else>{{ t("no cost change") }}</span>
			</div>
		</td>

		<td class="pg-sticky pg-c-landed-usd">
			<div class="pg-landed">{{ row.landed_new_usd == null ? "—" : g.money(row.landed_new_usd) }}</div>
			<div class="pg-sub"><span v-if="row.landed_old_usd != null && costChanged">{{ t("was") }} {{ g.money(row.landed_old_usd) }}</span></div>
		</td>
		<td class="pg-sticky pg-c-landed">
			<div class="pg-landed">{{ g.money(row.landed_new) }}</div>
			<div class="pg-sub"><span v-if="costChanged">{{ t("was") }} {{ g.money(row.landed_old) }}</span></div>
		</td>

		<td
			v-for="(v, c) in views"
			:key="lists[c].name"
			class="pg-c-list"
			:class="classes(v)"
			@mouseenter="v && ($event.currentTarget.title = g.cellTitle(row, lists[c], v))"
		>
			<template v-if="v">
				<input
					class="pg-input"
					:data-r="r"
					:data-c="c + 1"
					:value="v.key in store.edits ? store.edits[v.key] : v.cell.new > 0 ? g.fixed(v.cell.new) : ''"
					:placeholder="g.money(v.cell.suggested || v.cell.old) || t('price')"
					:readonly="!editable || v.removing"
					inputmode="decimal"
					@focus="$event.target.select()"
					@input="store.edits[v.key] = $event.target.value"
					@keydown="g.onKey($event, r, c + 1)"
				/>
				<div v-if="showDetail" class="pg-sub">
					<span v-if="v.removing">{{ t("removing") }}</span>
					<a
						v-else-if="offerSuggestion(v)"
						class="pg-sugg"
						:title="t('Take the suggested price')"
						@click.stop="g.setCell(row, lists[c], v.cell.suggested)"
					>{{ t("sugg") }} {{ g.money(v.cell.suggested) }}</a>
					<span v-else-if="v.isNew">{{ t("new on list") }}</span>
					<span v-else>{{ t("was") }} {{ g.money(v.cell.old) }}</span>
					<span :class="marginClass(v)">{{ marginText(v) }}</span>
				</div>
				<button
					v-if="editable && !v.isNew"
					class="pg-x"
					:title="v.removing ? t('Keep this price') : t('Remove this price from the list')"
					@click.stop="g.toggleRemove(row, lists[c])"
				>{{ v.removing ? "↺" : "×" }}</button>
			</template>
			<button v-else-if="editable" class="pg-add" :title="t('Add a price on {0}', [lists[c].name])" @click="g.startCell(row, lists[c], r, c + 1)">+</button>
			<span v-else class="pg-na">—</span>
		</td>
	</tr>
</template>

<script>
import { cellView } from "./cells";

export default {
	name: "GridRow",
	inject: ["g"],
	props: {
		row: { type: Object, required: true },
		r: { type: Number, required: true },
		lists: { type: Array, required: true },
		store: { type: Object, required: true },
		editable: Boolean,
		showDetail: Boolean,
	},
	computed: {
		// only this row's keys are read here, so typing re-renders one row
		views() {
			return this.lists.map((l) => cellView(this.row, l, this.store));
		},
		costPending() {
			return this.row.item_code in this.store.costs;
		},
		costChanged() {
			return Math.abs(this.row.new_cost - this.row.old_cost) >= 0.005;
		},
	},
	methods: {
		t(text, args) {
			return __(text, args);
		},
		classes(v) {
			if (!v) return "pg-cell--na";
			return {
				["pg-cell--" + v.state]: true,
				"pg-pending": v.changed,
				"pg-edited": v.cell.edited && !v.changed,
			};
		},
		// with suggested prices off, a held cell offers its suggestion
		offerSuggestion(v) {
			return (
				this.editable && !this.g.doc.use_suggested && !v.changed && !v.cell.edited &&
				v.cell.suggested && Math.abs(v.cell.suggested - v.price) >= 0.005
			);
		},
		marginText(v) {
			if (v.margin === null || v.removing) return "";
			const old = v.cell.old_margin;
			const arrow = old == null || v.isNew ? "" : v.margin > old + 0.05 ? " ▲" : v.margin < old - 0.05 ? " ▼" : "";
			return this.g.num(v.margin, 1) + "%" + arrow;
		},
		marginClass(v) {
			if (v.state === "under") return "pg-bad";
			if (v.lowMargin) return "pg-warn";
			return "";
		},
	},
};
</script>
