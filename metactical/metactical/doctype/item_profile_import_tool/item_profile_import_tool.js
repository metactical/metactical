// Copyright (c) 2026, Techlift Technologies and contributors
// For license information, please see license.txt

const METHOD = 'metactical.metactical.doctype.item_profile_import_tool.item_profile_import_tool.';

frappe.ui.form.on('Item Profile Import Tool', {
	refresh: function(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__('Preview Import'), () => preview_import(frm));
		}
		if (frm.doc.docstatus === 1 && (frm.doc.results || []).length) {
			frm.add_custom_button(__('Download Exceptions'), () => {
				window.open(frappe.urllib.get_full_url(
					'/api/method/' + METHOD + 'download_results?docname=' + encodeURIComponent(frm.doc.name)));
			});
		}
	},

	supplier: function(frm) {
		if (!frm.doc.supplier) return;
		frappe.db.exists('Supplier Import Profile', frm.doc.supplier).then((exists) => {
			if (!exists) {
				frappe.msgprint(__('There is no Supplier Import Profile for {0}. Create one before importing.',
					[frm.doc.supplier]));
			}
		});
	}
});

function preview_import(frm) {
	frappe.call({
		method: METHOD + 'preview_import',
		args: {docname: frm.doc.name},
		freeze: true,
		freeze_message: __('Checking the file, nothing is being saved...'),
		callback: (r) => {
			if (!r.message) return;
			const {counts, samples, results} = r.message;
			const esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));

			let html = `<p>${__('Preview only - nothing has been changed yet.')}</p>
				<table class="table table-bordered table-sm">
					<tr><td>${__('Rows in file')}</td><td>${counts.total}</td></tr>
					<tr><td>${__('Items that would be updated')}</td><td>${counts.updated}</td></tr>
					<tr><td>${__('Items already up to date')}</td><td>${counts.unchanged}</td></tr>
					<tr><td>${__('Would be imported with issues')}</td><td>${counts.with_issues}</td></tr>
					<tr><td>${__('Would not be imported')}</td><td>${counts.not_imported}</td></tr>
				</table>`;

			html += `<h5>${__('Sample changes')}</h5>
				<table class="table table-bordered table-sm"><tr>
					<th>${__('Row')}</th><th>${__('Item')}</th><th>${__('Matched By')}</th>
					<th>${__('Field')}</th><th>${__('Current')}</th><th>${__('New')}</th></tr>`;
			samples.forEach((s) => {
				const lines = s.changes.map((c) => [c.field, c.old, c.new]);
				s.notes.filter((n) => !n.startsWith(__('Updated'))).forEach((n) => lines.push([n, '', '']));
				lines.forEach(([field, old, now], i) => {
					html += `<tr><td>${i ? '' : s.row_no}</td><td>${i ? '' : esc(s.item_code)}</td>
						<td>${i ? '' : esc(s.matched_by)}</td>
						<td>${esc(field)}</td><td>${esc(old)}</td><td>${esc(now)}</td></tr>`;
				});
			});
			html += '</table>';

			if (results.length) {
				html += `<h5>${__('Exceptions (first {0})', [results.length])}</h5>
					<table class="table table-bordered table-sm"><tr>
						<th>${__('Row')}</th><th>${__('Primary')}</th><th>${__('Fallback')}</th><th>${__('Item')}</th>
						<th>${__('Status')}</th><th>${__('Reason')}</th><th>${__('What Happened')}</th></tr>`;
				results.forEach((e) => {
					html += `<tr><td>${e.row_no}</td><td>${esc(e.match_value)}</td><td>${esc(e.fallback_value)}</td>
						<td>${esc(e.item_code)}</td><td>${esc(e.status)}</td>
						<td>${esc(e.reason)}</td><td>${esc(e.action_taken)}</td></tr>`;
				});
				html += '</table>';
			}

			const d = new frappe.ui.Dialog({
				title: __('Import Preview: {0}', [frm.doc.supplier]),
				size: 'extra-large',
				fields: [{fieldtype: 'HTML', fieldname: 'preview'}],
			});
			d.fields_dict.preview.$wrapper.html(html);
			d.show();
		}
	});
}
