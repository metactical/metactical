// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Manifest', {
	refresh: function (frm) {
		if (frm.doc.items?.length && !frm.doc.po_number) {
			frm.add_custom_button(__("Make Manifest"), () => {
				frm.call("create_manifest",{}, r => {
					console.log({"r": r});
					frm.reload_doc()
					let html = ''
					r.message.forEach(file => {
						html += `<embed src="${file}" type="application/pdf" frameBorder="0" scrolling="auto"
						height="100%"
						width="100%"
					></embed>`
					})
					let newWindow = window.open('', '_new')
					newWindow.document.write(html)
					newWindow.document.close()
				})
			})
		}
	}
});
