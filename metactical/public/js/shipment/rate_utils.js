// Shared rate helpers for the Shipment rate dialog.
//
// A rate selection is always a single (provider, service) choice for the WHOLE
// shipment - the backend takes one provider per call, and mixing carriers across
// parcels means one carrier receives another's service code. These helpers
// collapse a provider's rate rows into one summary row per service, which is the
// unit both the table and the default seeding select on.

export function serviceKey(item) {
	return `${item.provider}_${item.carrier_service}_${item.service_name}`;
}

// Collapse `rows` (a provider's rates.data) into one row per distinct service.
// `total_amount` is the price for the whole shipment: the sum across parcels for a
// per-parcel carrier (Canada Post), or the single quote for a carrier that prices
// all pieces at once (Purolator).
export function summarizeRates(rows, provider) {
	if (!rows || !rows.length) return [];

	const serviceMap = new Map();

	rows.forEach((row) => {
		(row.items || []).forEach((item) => {
			const summary = { ...item, provider: provider || item.provider };
			const key = serviceKey(summary);

			if (!serviceMap.has(key)) {
				serviceMap.set(key, {
					...summary,
					total_base: parseFloat(item.base) || 0,
					total_amount: parseFloat(item.shipment_amount) || 0,
					parcels: [row.idx],
					idx: "All",
				});
				return;
			}

			const existing = serviceMap.get(key);
			existing.total_base += parseFloat(item.base) || 0;
			existing.total_amount += parseFloat(item.shipment_amount) || 0;
			existing.parcels.push(row.idx);

			if (item.expected_delivery_date) {
				const currentDate = new Date(existing.expected_delivery_date);
				const newDate = new Date(item.expected_delivery_date);
				if (newDate > currentDate) {
					existing.expected_delivery_date = item.expected_delivery_date;
					existing.expected_transit_time = item.expected_transit_time;
				}
			}
		});
	});

	return Array.from(serviceMap.values());
}

// That parcel's own price for the chosen service, for display in the per-parcel
// state. Returns 0 when the provider did not quote this parcel (Purolator quotes
// the shipment as a whole, so only one parcel carries a price).
export function parcelRate(rows, parcelIdx, carrier_service, service_name) {
	const row = (rows || []).find((r) => r.idx === parcelIdx);
	if (!row) return 0;

	const match = (row.items || []).find(
		(item) =>
			item.carrier_service === carrier_service &&
			item.service_name === service_name
	);
	return match ? parseFloat(match.shipment_amount) || 0 : 0;
}
