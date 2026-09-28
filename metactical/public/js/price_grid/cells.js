// What a grid cell will be once saved, worked out on the client so the grid
// reacts as you type. The server recomputes on save and is the authority.

export const SEP = "";

export const key = (row, l) => row.item_code + SEP + l.name;

export function parse(raw) {
	if (raw === "" || raw == null) return null;
	const n = parseFloat(String(raw).replace(/[^0-9.\-]/g, ""));
	return isNaN(n) ? NaN : n;
}

// mirrors costing.apply_rounding: always UP to the ending, never to nearest
export function roundUp(price, rule) {
	if (!(price > 0) || !rule || rule === "none") return price;
	if (rule === "whole") return Math.ceil(price - 1e-9);
	const cents = rule === "0.95" ? 0.95 : 0.99;
	const whole = Math.floor(price);
	let candidate = whole + cents;
	if (price > candidate + 1e-9) candidate = whole + 1 + cents;
	return Math.round(candidate * 100) / 100;
}

// Landed cost in a list's currency when the server hasn't priced the cell yet
function listLanded(row, l, store) {
	if (l.currency === store.company_currency) return row.landed_new;
	if (l.currency === "USD") return row.landed_new_usd;
	return null;
}

// Landed cost for a cell, following an unsaved cost edit on the row
export function landedFor(row, l, store) {
	const cell = row.cells[l.name];
	const base = cell ? cell.landed : listLanded(row, l, store);
	const raw = store.costs[row.item_code];
	const cost = parse(raw);
	if (raw === undefined || !(cost > 0) || !row.new_cost || base == null) return base;
	return base * (cost / row.new_cost);
}

/**
 * null when the item isn't on the list and nobody is adding it; otherwise
 * { cell, price, landed, margin, state, pending, removing, isNew, lowMargin }
 * state: up | hold | review | under | remove
 */
export function cellView(row, l, store) {
	const k = key(row, l);
	const server = row.cells[l.name];
	const pending = k in store.edits;
	if (!server && !pending) return null;

	const cell = server || {
		old: 0, new: 0, suggested: null, landed: null, old_margin: null,
		action: "Review", edited: 0, remove: 0, note: null,
	};
	const removing = k in store.removes ? !!store.removes[k] : !!cell.remove;
	const costPending = row.item_code in store.costs;

	let price = cell.new;
	if (pending) {
		const v = parse(store.edits[k]);
		price = v === null ? (server ? cell.suggested || cell.old : 0) : v;
	}
	const landed = landedFor(row, l, store);
	const margin = price > 0 && landed != null ? ((price - landed) / price) * 100 : null;

	let state;
	if (removing) state = "remove";
	else if (server && !pending && !costPending && !cell.edited && !(k in store.removes)) {
		state =
			cell.action === "Update" ? "up"
			: cell.action === "Hold" ? "hold"
			: cell.action === "Delete" ? "remove"
			: landed && cell.new <= landed ? "under"
			: "review";
	} else if (!(price > 0) || Number.isNaN(price)) state = "review";
	else if (landed && price <= landed) state = "under";
	else if (Math.abs(price - cell.old) < 0.005) state = "hold";
	else state = "up";

	const lowMargin = !l.exempt && l.floor && margin !== null && margin < l.floor;
	return {
		key: k, cell, price, landed, margin, state, pending, removing, lowMargin,
		isNew: !cell.old,
		changed: pending || k in store.removes,
	};
}
