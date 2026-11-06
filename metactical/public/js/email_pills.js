frappe.provide("metactical.email_pills");

// A CC / BCC field shown the way a mail client shows recipients: each address a
// pill with a remove button, and a box after them to add more. Typing an address
// and pressing Enter, comma, ; or Tab (or leaving the box, or pasting a list)
// adds it. The field itself (Small Text) keeps holding the addresses
// comma-separated, which is what the server reads (procurement_v3.utils.email_list).
//
// Call it from the form's refresh, and from the field's own change event so a
// value set by code (e.g. copied from the Supplier) is redrawn.
metactical.email_pills.render = function (frm, fieldname) {
	const field = frm.fields_dict[fieldname];
	if (!field || !field.$wrapper) return;
	metactical.email_pills.add_style();

	const editable = field.disp_status === "Write";
	const emails = metactical.email_pills.split(frm.doc[fieldname]);
	const $control = field.$wrapper.find(".control-input-wrapper");

	let $box = field.$wrapper.find(".mt-email-pills");
	if (!$box.length) {
		$box = $(`<div class="mt-email-pills"></div>`).prependTo($control);
	}
	// the plain textarea / read-only text is replaced by the pills. By class, not
	// toggle(): Frappe shows them again every time it refreshes the field.
	field.$wrapper.addClass("mt-has-email-pills");
	$box.empty();

	emails.forEach((email, i) => {
		const $pill = $(`<span class="mt-email-pill"></span>`).text(email).appendTo($box);
		if (editable) {
			$(`<button type="button" class="mt-email-pill-remove" title="${__("Remove")}">
					${frappe.utils.icon("close", "xs")}
				</button>`)
				.appendTo($pill)
				.on("click", () => {
					emails.splice(i, 1);
					metactical.email_pills.set(frm, fieldname, emails);
				});
		}
	});

	if (!editable) {
		if (!emails.length) $box.append(`<span class="text-muted">${__("None")}</span>`);
		return;
	}

	const $input = $(`<input type="text" class="mt-email-pills-input" autocomplete="off">`)
		.attr("placeholder", __("Add a recipient"))
		.appendTo($box);

	const commit = () => {
		const typed = metactical.email_pills.split($input.val());
		if (!typed.length) return true;
		const bad = typed.filter((e) => !frappe.utils.validate_type(e, "email"));
		if (bad.length) {
			frappe.show_alert({ message: __("Not a valid email address: {0}", [bad.join(", ")]), indicator: "red" });
			$input.val(bad.join(", "));
		} else {
			$input.val("");
		}
		const added = typed.filter((e) => !bad.includes(e));
		const all = emails.concat(added.filter((e) => !emails.some((x) => x.toLowerCase() === e.toLowerCase())));
		if (all.length !== emails.length) metactical.email_pills.set(frm, fieldname, all, bad.join(", "));
		return !bad.length;
	};

	$input.on("keydown", (e) => {
		if (["Enter", ",", ";"].includes(e.key) || (e.key === "Tab" && $input.val().trim())) {
			e.preventDefault();
			commit();
		} else if (e.key === "Backspace" && !$input.val() && emails.length) {
			emails.pop();
			metactical.email_pills.set(frm, fieldname, emails);
		}
	});
	$input.on("blur", commit);
	$input.on("paste", () => setTimeout(commit, 0));
	$box.on("click", (e) => {
		if (e.target === $box[0]) $input.trigger("focus");
	});
};

metactical.email_pills.split = function (value) {
	return (value || "")
		.split(/[,;\n]+/)
		.map((e) => e.trim())
		.filter(Boolean);
};

// writes the list back to the field, redraws, and puts the cursor back in the box
// (with any rejected text still in it) so the next address can be typed straight away
metactical.email_pills.set = function (frm, fieldname, emails, leftover) {
	frm.set_value(fieldname, emails.join(", ") || null).then(() => {
		metactical.email_pills.render(frm, fieldname);
		const $input = frm.fields_dict[fieldname].$wrapper.find(".mt-email-pills-input");
		if (leftover) $input.val(leftover);
		$input.trigger("focus");
	});
};

metactical.email_pills.add_style = function () {
	if (document.getElementById("mt-email-pills-style")) return;
	$(`<style id="mt-email-pills-style">
		.mt-has-email-pills .control-input,
		.mt-has-email-pills .control-value { display: none !important; }
		.mt-email-pills {
			display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
			min-height: var(--input-height, 28px); padding: 4px 6px;
			background: var(--control-bg); border-radius: var(--border-radius);
			cursor: text;
		}
		.mt-email-pill {
			display: inline-flex; align-items: center; gap: 4px;
			padding: 2px 4px 2px 10px; border-radius: var(--border-radius-full, 999px);
			background: var(--mt-pill-bg); color: var(--mt-pill-fg); font-size: var(--text-sm);
		}
		.mt-email-pills { --mt-pill-bg: var(--gray-200); --mt-pill-fg: var(--gray-800); }
		[data-theme="dark"] .mt-email-pills { --mt-pill-bg: var(--gray-700); --mt-pill-fg: var(--gray-100); }
		.mt-email-pill-remove {
			display: inline-flex; align-items: center; justify-content: center;
			width: 18px; height: 18px; padding: 0; border: 0; border-radius: 50%;
			background: var(--gray-500); color: var(--white, #fff);
		}
		.mt-email-pill-remove .icon { stroke: currentColor; }
		.mt-email-pill-remove:hover { background: var(--gray-700); }
		.mt-email-pills-input {
			flex: 1 1 140px; min-width: 140px; border: 0; outline: 0;
			background: transparent; color: var(--text-color); font-size: var(--text-md);
		}
	</style>`).appendTo("head");
};
