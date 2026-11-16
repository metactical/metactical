// Copyright (c) 2025, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('POS User Settings', {
	refresh: function(frm) {
		if (frappe.user.has_role('System Manager')) {
			frm.add_custom_button(__('Show Password'), function() {
				frm.call({
					method: 'metactical.custom_scripts.utils.metactical_utils.get_password',
					args: { doc: frm.doc },
					freeze: true,
					callback: function(r) {
						frappe.msgprint(r.message);
					}
				});
			});

			if (!frm.doc.badge_id) {
				frm.add_custom_button(__('Generate Badge'), function() {
					if (frm.is_dirty()) {
						frappe.msgprint(__('Please save the document before generating a badge.'));
						return;
					}
					frappe.call({
						method: 'metactical.metactical.doctype.pos_user_settings.pos_user_settings.generate_badge',
						args: { docname: frm.doc.name },
						freeze: true,
						freeze_message: __('Generating badge…'),
						callback: function(r) {
							if (!r.message) return;
							frm.reload_doc();
							pos_user_settings_download_badge(r.message);
						}
					});
				});
			} else {
				frm.add_custom_button(__('Download Badge'), function() {
					frappe.call({
						method: 'metactical.metactical.doctype.pos_user_settings.pos_user_settings.get_badge',
						args: { docname: frm.doc.name },
						freeze: true,
						freeze_message: __('Preparing badge…'),
						callback: function(r) {
							if (!r.message) return;
							pos_user_settings_download_badge(r.message);
						}
					});
				});
			}
		}
	}
});

function pos_user_settings_download_badge(data) {
	const BADGE_W = 300;
	const BADGE_H = 420;
	const PHOTO_SIZE = 110;
	const QR_SIZE = 140;
	const PAD = 20;

	const canvas = document.createElement('canvas');
	canvas.width = BADGE_W;
	canvas.height = BADGE_H;
	const ctx = canvas.getContext('2d');

	const fullName = [data.first_name, data.last_name].filter(Boolean).join(' ') || 'Unknown';
	const qrB64 = data.qr_code || '';
	const photoUrl = data.user_image || '';

	function drawBackground() {
		const grad = ctx.createLinearGradient(0, 0, 0, BADGE_H);
		grad.addColorStop(0, '#1a1a2e');
		grad.addColorStop(1, '#16213e');
		ctx.fillStyle = grad;
		ctx.fillRect(0, 0, BADGE_W, BADGE_H);

	}

	function drawPhoto(photoImg) {
		const cx = BADGE_W / 2;
		const cy = PAD + 6 + PHOTO_SIZE / 2 + 20;

		ctx.save();
		ctx.beginPath();
		ctx.arc(cx, cy, PHOTO_SIZE / 2, 0, Math.PI * 2);
		ctx.clip();

		if (photoImg) {
			ctx.drawImage(photoImg, cx - PHOTO_SIZE / 2, cy - PHOTO_SIZE / 2, PHOTO_SIZE, PHOTO_SIZE);
		}
		ctx.restore();

		return cy + PHOTO_SIZE / 2;
	}

	function drawName(afterY) {
		const cy = afterY + 22;
		ctx.fillStyle = '#ffffff';
		ctx.font = 'bold 20px Arial, sans-serif';
		ctx.textAlign = 'center';
		ctx.textBaseline = 'top';
		ctx.fillText(fullName, BADGE_W / 2, cy);
		return cy + 28;
	}

	function drawQR(qrImg, afterY) {
		const qrX = (BADGE_W - QR_SIZE) / 2;
		const qrY = afterY + 16;

		ctx.fillStyle = '#ffffff';
		ctx.fillRect(qrX - 4, qrY - 4, QR_SIZE + 8, QR_SIZE + 8);

		if (qrImg) {
			ctx.drawImage(qrImg, qrX, qrY, QR_SIZE, QR_SIZE);
		}
	}

	function finish(photoImg, qrImg) {
		drawBackground();
		const afterPhoto = drawPhoto(photoImg);
		const afterName = drawName(afterPhoto);
		drawQR(qrImg, afterName);

		const link = document.createElement('a');
		link.download = 'badge_' + fullName.replace(/\s+/g, '_') + '.png';
		link.href = canvas.toDataURL('image/png');
		link.click();
	}

	const loadQR = new Promise(resolve => {
		if (!qrB64) return resolve(null);
		const img = new Image();
		img.onload = () => resolve(img);
		img.onerror = () => resolve(null);
		img.src = 'data:image/png;base64,' + qrB64;
	});

	const loadPhoto = new Promise(resolve => {
		const DEFAULT_AVATAR = '/assets/frappe/images/default-avatar.png';
		const src = photoUrl || DEFAULT_AVATAR;
		const img = new Image();
		img.crossOrigin = 'anonymous';
		img.onload = () => resolve(img);
		img.onerror = () => {
			if (src === DEFAULT_AVATAR) return resolve(null);
			const fallback = new Image();
			fallback.crossOrigin = 'anonymous';
			fallback.onload = () => resolve(fallback);
			fallback.onerror = () => resolve(null);
			fallback.src = DEFAULT_AVATAR;
		};
		img.src = src;
	});

	Promise.all([loadPhoto, loadQR]).then(([photoImg, qrImg]) => finish(photoImg, qrImg));
}
