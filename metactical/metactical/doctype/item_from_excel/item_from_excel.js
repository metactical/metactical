// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
var running = false;

frappe.ui.form.on('Item From Excel', {
	refresh: function(frm) {
		$('[data-fieldname="preview"]').html("")

		// Trigger validation when form is refreshed
		if (frm.doc.excel_file && !frm.doc.__islocal && frm.doc.docstatus == 0) {
			validate_excel_file(frm);
		}
		else{
			frm.set_value("preview", "");
		}
	}
});

function validate_excel_file(frm) {
	if (!running) 
		running = true;
	else
		return; // Prevent multiple simultaneous runs

	// Show loading indicator
	frm.set_df_property('preview', 'options', 
		'<div class="text-muted"><i class="fa fa-spinner fa-spin"></i> Validating file structure and content...</div>'
	);
	
	// Step 1: Basic file validation
	frappe.call({
		method: 'metactical.metactical.doctype.item_from_excel.item_from_excel.validate_excel_structure',
		args: {
			file_url: frm.doc.excel_file
		},
		callback: function(r) {
			if (r.message) {
				const validationResult = r.message;
				
				// Start building HTML
				let html = '<div class="validation-container">';
				
				// File Overview Section
				html += render_file_overview(validationResult.file_overview);
				
				// Only continue if file overview is valid
				if (validationResult.is_valid) {
					html += '</div>' + get_validation_styles();
					frm.set_df_property('preview', 'options', html);
					
					// Store validation result for later use
					frm.validation_result = validationResult;
					
					// First do website validation (this will be at the top)
					extract_and_validate_excel(frm);
				} else {
					// Validation failed - stop here
					html += '</div>' + get_validation_styles();
					frm.set_df_property('preview', 'options', html);
				}

				running = false;
			}
		},
		error: function(r) {
			frm.set_df_property('preview', 'options', 
				'<div class="alert alert-danger">Error loading file. Please check the file format and try again.</div>'
			);
		}
	});
}

function render_collapsible_section(id, title, icon, content, expanded = false, hasWarning = false) {
	const expandedClass = expanded ? 'expanded' : '';
	const warningClass = hasWarning ? 'has-warning' : '';
	const warningIcon = hasWarning ? '<i class="fa fa-exclamation-triangle warning-indicator"></i>' : '';
	
	return `
		<div class="collapsible-section ${expandedClass} ${warningClass}" data-section="${id}">
			<div class="collapsible-header">
				<div class="header-left">
					<i class="fa ${icon} section-icon"></i>
					<h5 class="section-title">${title}</h5>
					${warningIcon}
				</div>
				<i class="fa fa-chevron-down toggle-icon"></i>
			</div>
			<div class="collapsible-content" style="display: ${expanded ? 'block' : 'none'};">
				${content}
			</div>
		</div>
	`;
}

function setup_collapsible_handlers(frm) {
	frm.get_field('preview').$wrapper.find('.collapsible-header').on('click', function() {
		const section = $(this).closest('.collapsible-section');
		const content = section.find('.collapsible-content');
		const isExpanded = section.hasClass('expanded');
		
		if (isExpanded) {
			section.removeClass('expanded');
			content.slideUp(200);
		} else {
			section.addClass('expanded');
			content.slideDown(200);
		}
	});
}

function render_file_overview(overview) {
	if (!overview) return '';
	
	let html = '<div class="validation-section file-overview">';
	html += '<h5><i class="fa fa-file-excel-o"></i> File Overview</h5>';
	
	if (!overview.is_valid) {
		html += '<div class="alert alert-danger">';
		html += '<i class="fa fa-times-circle"></i> <strong>File Structure Issues:</strong><br>';
		overview.errors.forEach(error => {
			html += `<div class="mt-2">• ${error}</div>`;
		});
		html += '</div>';
	} else {
		// Only show success if sheets are correct
		html += '<div class="info-card success-card">';
		html += `<i class="fa fa-check-circle"></i> Found ${overview.sheet_count} sheets: <strong>${overview.sheet_names.join(', ')}</strong>`;
		html += '</div>';
	}
	
	html += '</div>';
	return html;
}

function render_sheet_info_content(sheet_info) {
	let html = '';
	
	['template', 'variants'].forEach(sheet_type => {
		const info = sheet_info[sheet_type];
		if (!info) return;
		
		const sheet_name = sheet_type.charAt(0).toUpperCase() + sheet_type.slice(1);
		
		if (info.has_errors) {
			html += `<div class="sheet-info-card error-card">`;
			html += `<h6><i class="fa fa-exclamation-triangle"></i> ${sheet_name} Sheet</h6>`;
			html += '<div class="error-message">';
			html += `<strong>The '${sheet_name}' sheet is missing:</strong> ${info.missing_fields.join(', ')}`;
			html += '</div>';
			html += '</div>';
		} else {
			html += `<div class="sheet-info-card valid-card">`;
			html += `<h6><i class="fa fa-check-circle"></i> ${sheet_name} Sheet</h6>`;
			html += '<div class="info-grid">';
			html += `<div class="info-item"><strong>Rows:</strong> ${info.row_count}</div>`;
			html += `<div class="info-item"><strong>Columns:</strong> ${info.column_count}</div>`;
			html += '</div>';
			
			if (info.headers && info.headers.length > 0) {
				html += '<details class="mt-2">';
				html += '<summary class="summary-link">View Headers</summary>';
				html += '<div class="headers-list mt-2">';
				info.headers.forEach(header => {
					if (header) {
						html += `<span class="header-badge">${header}</span>`;
					}
				});
				html += '</div>';
				html += '</details>';
			}
			
			html += '</div>';
		}
	});
	
	return html;
}

function render_mandatory_validation_content(validation) {
	if (!validation || !validation.has_errors) {
		return '<div class="info-message"><i class="fa fa-check-circle"></i> All mandatory fields have values.</div>';
	}
	
	let html = '<div class="alert alert-warning">';
	html += '<strong><i class="fa fa-warning"></i> Missing Values Found:</strong>';
	html += '<div class="error-details mt-2">';
	
	validation.errors.forEach(error => {
		html += '<div class="error-detail-item">';
		html += `Row${error.rows.length > 1 ? 's' : ''} <strong>#${error.rows.join(', #')}</strong> `;
		html += `with SKU <strong>${error.sku}</strong> `;
		html += `in sheet <strong>${error.sheet}</strong> `;
		html += `has missing value${error.columns.length > 1 ? 's' : ''} for column${error.columns.length > 1 ? 's' : ''}: `;
		html += `<strong>${error.columns.join(', ')}</strong>`;
		html += '</div>';
	});
	
	html += '</div></div>';
	return html;
}

function render_variant_relationships_content(relationships) {
	let html = '<div class="relationship-stats">';
	html += `<div class="stat-card">`;
	html += `<div class="stat-value">${relationships.template_count}</div>`;
	html += `<div class="stat-label">Template Items Referenced</div>`;
	html += `</div>`;
	html += `<div class="stat-card">`;
	html += `<div class="stat-value">${relationships.variant_count}</div>`;
	html += `<div class="stat-label">Variant Items</div>`;
	html += `</div>`;
	html += '</div>';
	
	// Missing templates warning
	if (relationships.missing_templates && relationships.missing_templates.length > 0) {
		html += '<div class="alert alert-danger mt-3">';
		html += '<i class="fa fa-exclamation-triangle"></i> ';
		html += '<strong>Variants referencing non-existing templates:</strong>';
		html += '<div class="mt-2">';
		relationships.missing_templates.forEach(item => {
			html += `<div class="missing-template-item">`;
			html += `• Variant <code>${item.variant}</code> references template <code>${item.template}</code> which was not found`;
			html += `</div>`;
		});
		html += '</div></div>';
	}
	
	return html;
}

function render_item_summary_content(summary) {
	let html = '';
	
	// Item Groups
	if (summary.item_groups && Object.keys(summary.item_groups).length > 0) {
		html += '<div class="summary-subsection">';
		html += '<h6><i class="fa fa-folder"></i> Item Groups</h6>';
		html += '<div class="summary-list">';
		Object.keys(summary.item_groups).sort().forEach(group => {
			const count = summary.item_groups[group];
			html += `<div class="summary-item success-item">`;
			html += `<span class="count-badge">${count}</span> `;
			html += `item${count > 1 ? 's' : ''} will be assigned to <strong>${group}</strong>`;
			html += `</div>`;
		});
		html += '</div></div>';
	}
	
	// Brands
	if (summary.brands && Object.keys(summary.brands).length > 0) {
		html += '<div class="summary-subsection">';
		html += '<h6><i class="fa fa-copyright"></i> Brands</h6>';
		html += '<div class="summary-list">';
		Object.keys(summary.brands).sort().forEach(brand => {
			const count = summary.brands[brand];
			html += `<div class="summary-item success-item">`;
			html += `<span class="count-badge">${count}</span> `;
			html += `item${count > 1 ? 's' : ''} will be assigned to <strong>${brand}</strong>`;
			html += `</div>`;
		});
		html += '</div></div>';
	}
	
	// Website Specification Labels
	if (summary.website_spec_labels && Object.keys(summary.website_spec_labels).length > 0) {
		html += '<div class="summary-subsection">';
		html += '<h6><i class="fa fa-tags"></i> Website Specification Labels</h6>';
		html += '<div class="summary-list">';
		Object.keys(summary.website_spec_labels).sort().forEach(label => {
			const count = summary.website_spec_labels[label];
			html += `<div class="summary-item success-item">`;
			html += `<span class="count-badge">${count}</span> `;
			html += `item${count > 1 ? 's' : ''} will have website specification <strong>${label}</strong>`;
			html += `</div>`;
		});
		html += '</div></div>';
	}
	
	// Specs (from attributes)
	if (summary.specs && Object.keys(summary.specs).length > 0) {
		html += '<div class="summary-subsection">';
		html += '<h6><i class="fa fa-tag"></i> Unique Specifications</h6>';
		html += '<div class="summary-list">';
		Object.keys(summary.specs).sort().forEach(spec => {
			const count = summary.specs[spec];
			html += `<div class="summary-item success-item">`;
			html += `<span class="count-badge">${count}</span> `;
			html += `item${count > 1 ? 's' : ''} will have specification <strong>${spec}</strong>`;
			html += `</div>`;
		});
		html += '</div></div>';
	}
	
	// Availability Rules
	if (summary.availability_rules && Object.keys(summary.availability_rules).length > 0) {
		html += '<div class="summary-subsection">';
		html += '<h6><i class="fa fa-cog"></i> Unique Availability Rules</h6>';
		html += '<div class="summary-list">';
		Object.keys(summary.availability_rules).sort().forEach(rule => {
			const count = summary.availability_rules[rule];
			html += `<div class="summary-item success-item">`;
			html += `<span class="count-badge">${count}</span> `;
			html += `item${count > 1 ? 's' : ''} will use availability rule <strong>${rule}</strong>`;
			html += `</div>`;
		});
		html += '</div></div>';
	}
	
	return html;
}

function render_price_list_summary_content(summary) {
	let html = '';
	
	if (summary.price_lists && Object.keys(summary.price_lists).length > 0) {
		html += '<div class="price-list-assignments">';
		
		Object.keys(summary.price_lists).sort().forEach(priceListCombo => {
			const count = summary.price_lists[priceListCombo];
			const lists = priceListCombo.split(',').map(s => s.trim());
			
			html += '<div class="price-assignment-item success-item">';
			html += `<span class="count-badge primary">${count}</span> `;
			
			if (lists.length > 1) {
				html += `item${count > 1 ? 's' : ''} will be assigned to sites: `;
				html += lists.map(pl => `<span class="site-badge">${pl.replace("RET -", "")}</span>`).join(', ');
			} else {
				html += `item${count > 1 ? 's' : ''} will be assigned to <span class="site-badge">${lists[0]}</span> only`;
			}
			
			html += '</div>';
		});
		
		html += '</div>';
	} else {
		html += '<div class="alert alert-info">';
		html += '<i class="fa fa-info-circle"></i> No price lists detected in the file.';
		html += '</div>';
	}
	
	return html;
}

function extract_and_validate_excel(frm) {
	// Add loading message for website validation
	const loadingHtml = '<div class="validation-section loading-section"><div class="text-muted"><i class="fa fa-spinner fa-spin"></i> Validating against configured websites...</div></div>';
	
	// Insert loading message after file overview
	frm.get_field('preview').$wrapper.find('.file-overview').after(loadingHtml);
	
	// Call existing validation method
	frappe.call({
		method: 'metactical.metactical.doctype.item_from_excel.item_from_excel.extract_and_validate_excel_data',
		args: {
			file_url: frm.doc.excel_file
		},
		callback: function(r) {
			if (r.message) {
				if (Object.keys(r.message).length === 0 && !frm.doc.all_valid) {
					frm.set_value("all_valid", true);
					frm.save()
				}

				const priceListResults = r.message;
				
				// Remove loading message
				frm.get_field('preview').$wrapper.find('.loading-section').remove();
				
				// Add website validation section right after file overview (NOT collapsible, always visible)
				const websiteValidationHtml = get_website_validation_html(priceListResults);
				frm.get_field('preview').$wrapper.find('.file-overview').after(websiteValidationHtml);
				
				// Now add all the collapsible sections
				add_collapsible_sections(frm);
				
				// Show summary
				show_multi_pricelist_summary(frm, priceListResults);
				
				// Store data
				frm.price_list_results = priceListResults;
			}
		},
		error: function(r) {
			frm.get_field('preview').$wrapper.find('.loading-section').remove();
			frm.get_field('preview').$wrapper.find('.file-overview').after(
				'<div class="alert alert-danger">Error validating with websites. Please try again.</div>'
			);
		}
	});
}

function add_collapsible_sections(frm) {
	const validationResult = frm.validation_result;
	if (!validationResult) return;
	
	let html = '';

	// Price List Summary (Collapsible - Hidden by default)
	if (validationResult.price_list_summary) {
		html += render_collapsible_section(
			'price-list-summary',
			'Price List Summary',
			'fa-money',
			render_price_list_summary_content(validationResult.price_list_summary),
			true
		);
	}
	
	// Sheet Information Section (Collapsible - Hidden by default)
	if (validationResult.sheet_info) {
		html += render_collapsible_section(
			'sheet-info',
			'Sheet Information',
			'fa-table',
			render_sheet_info_content(validationResult.sheet_info),
			false // collapsed by default
		);
	}
	
	// Mandatory Field Validation (Collapsible - Hidden by default)
	if (validationResult.mandatory_validation) {
		html += render_collapsible_section(
			'mandatory-validation',
			'Mandatory Field Validation',
			'fa-exclamation-circle',
			render_mandatory_validation_content(validationResult.mandatory_validation),
			false,
			validationResult.mandatory_validation.has_errors
		);
	}
	
	// Variant Relationship Overview (Collapsible - Hidden by default)
	if (validationResult.variant_relationships) {
		html += render_collapsible_section(
			'variant-relationships',
			'Variant Relationship Overview',
			'fa-sitemap',
			render_variant_relationships_content(validationResult.variant_relationships),
			false,
			validationResult.variant_relationships.missing_templates && 
			validationResult.variant_relationships.missing_templates.length > 0
		);
	}
	
	// Item Summary (Collapsible - Hidden by default)
	if (validationResult.item_summary) {
		html += render_collapsible_section(
			'item-summary',
			'Item Group, Brand, and Other Lookups Summary',
			'fa-list',
			render_item_summary_content(validationResult.item_summary),
			false
		);
	}
	
	// Append all collapsible sections to the container
	frm.get_field('preview').$wrapper.find('.validation-container').append(html);
	
	// Add click handlers for collapsible sections
	setup_collapsible_handlers(frm);
}

function get_website_validation_html(priceListResults) {
	// This section is NOT collapsible - always visible
	let html = '<div class="validation-section website-validation">';
	html += '<h5><i class="fa fa-globe"></i> Site Specific Validation</h5>';
	html += '<p class="text-muted">Validation results from configured website APIs</p>';
	
	// Categorize and sort
	const categorized = {
		errors: [],
		issues: [],
		empty: [],
		success: []
	};
	
	Object.keys(priceListResults).forEach(function(priceList) {
		const result = priceListResults[priceList];
		
		if (result.status === 'error') {
			categorized.errors.push(priceList);
		} else if (is_empty_payload(result.payload)) {
			categorized.empty.push(priceList);
		} else {
			const validation = result.response;
			let has_issues = false;
			
			if (validation && validation.length > 0) {
				validation.forEach(function(item) {
					if (!item.allValid) {
						has_issues = true;
					}
				});
			}
			
			if (has_issues) {
				categorized.issues.push(priceList);
			} else {
				categorized.success.push(priceList);
			}
		}
	});
	
	categorized.errors.sort();
	categorized.issues.sort();
	categorized.empty.sort();
	categorized.success.sort();
	
	const displayOrder = [
		...categorized.errors,
		...categorized.issues,
		...categorized.empty,
		...categorized.success
	];
	
	// Display each price list
	displayOrder.forEach(function(priceList) {
		const result = priceListResults[priceList];
		html += render_price_list_section(priceList, result);
	});
	
	html += '</div>';
	
	return html;
}

function render_price_list_section(priceList, result) {
	// API error
	if (result.status === 'error') {
		return `
			<div class="price-list-section api-error">
				<div class="price-list-header">
					<span><i class="fa fa-list"></i> ${priceList}</span>
					<span class="badge badge-danger">API Error</span>
				</div>
				<div class="validation-summary-box api-error-box">
					<i class="fa fa-times-circle"></i>
					<strong>API Error:</strong> ${result.error}
				</div>
			</div>
		`;
	}
	
	const payload = result.payload;
	
	// Empty payload
	if (is_empty_payload(payload)) {
		return `
			<div class="price-list-section empty">
				<div class="price-list-header">
					<span><i class="fa fa-list"></i> ${priceList}</span>
					<span class="badge badge-secondary">No Items</span>
				</div>
				<div class="empty-message-box">
					<h6>No Items Will Be Synced</h6>
					<p class="text-muted mb-0">
						No items have prices set for this price list.
					</p>
				</div>
			</div>
		`;
	}
	
	const validationResponse = result.response;
	
	let validation = {
		specifications: { notFound: [], allValid: true },
		categories: { notFound: [], allValid: true },
		brands: { notFound: [], allValid: true },
		availabilityRules: { notFound: [], allValid: true }
	};
	
	if (validationResponse && validationResponse.length > 0) {
		validationResponse.forEach(function(item) {
			validation[item.type] = {
				notFound: item.notFound || [],
				allValid: item.allValid
			};
		});
	}
	
	const allValid = validation.specifications.allValid && 
	                 validation.categories.allValid && 
	                 validation.brands.allValid && 
	                 validation.availabilityRules.allValid;
	
	const sectionClass = allValid ? 'all-valid' : 'has-errors';
	const statusBadge = allValid ? 
		'<span class="badge badge-success">Matched</span>' : 
		'<span class="badge badge-danger">Not Matched</span>';
	
	let html = `
		<div class="price-list-section ${sectionClass}">
			<div class="price-list-header">
				<span><i class="fa fa-list"></i> ${priceList}</span>
				${statusBadge}
			</div>
			${get_validation_summary_html(validation, allValid, payload, priceList)}
		</div>
	`;
	
	return html;
}

function get_validation_summary_html(validation, allValid, payload, priceList) {
	if (allValid) {
		// Count total items
		const totalItems = Math.max(
			payload.CategoriesExternalIds.length,
			payload.BrandsExternalIds.length,
			1
		);
		
		return `
			<div class="validation-summary-box all-valid-box">
				<i class="fa fa-check-circle"></i>
				<strong>All items matched on site!</strong>
				<div class="mt-2">
					<div class="match-detail">• <strong>${totalItems}</strong> item${totalItems > 1 ? 's' : ''} assigned to categories/groups matched on site <strong>${priceList}</strong></div>
					${payload.BrandsExternalIds.length > 0 ? `<div class="match-detail">• <strong>${payload.BrandsExternalIds.length}</strong> brand${payload.BrandsExternalIds.length > 1 ? 's' : ''} matched on site <strong>${priceList}</strong></div>` : ''}
					${payload.SpecsExternalIds.length > 0 ? `<div class="match-detail">• <strong>${payload.SpecsExternalIds.length}</strong> specification${payload.SpecsExternalIds.length > 1 ? 's' : ''} matched on site <strong>${priceList}</strong></div>` : ''}
				</div>
			</div>
		`;
	} else {
		let matchedItems = [];
		let notMatchedItems = [];
		
		// Categories
		if (validation.categories.allValid) {
			matchedItems.push(`<div class="match-detail">• <strong>${payload.CategoriesExternalIds.length}</strong> categor${payload.CategoriesExternalIds.length > 1 ? 'ies' : 'y'} matched</strong></div>`);
		} else {
			notMatchedItems.push(`<strong>Categories not matched:</strong> ${validation.categories.notFound.join(', ')}`);
		}
		
		// Brands
		if (validation.brands.allValid && payload.BrandsExternalIds.length > 0) {
			matchedItems.push(`<div class="match-detail">• <strong>${payload.BrandsExternalIds.length}</strong> brand${payload.BrandsExternalIds.length > 1 ? 's' : ''} matched</strong></div>`);
		} else if (!validation.brands.allValid) {
			notMatchedItems.push(`<strong>Brands not matched:</strong> ${validation.brands.notFound.join(', ')}`);
		}
		
		// Specs
		if (validation.specifications.allValid && payload.SpecsExternalIds.length > 0) {
			matchedItems.push(`<div class="match-detail">• <strong>${payload.SpecsExternalIds.length}</strong> specification${payload.SpecsExternalIds.length > 1 ? 's' : ''} matched</strong></div>`);
		} else if (!validation.specifications.allValid) {
			notMatchedItems.push(`<strong>Specs not matched:</strong> ${validation.specifications.notFound.join(', ')}`);
		}
		
		// Availability Rules
		if (!validation.availabilityRules.allValid) {
			notMatchedItems.push(`<strong>Availability Rules not matched:</strong> ${validation.availabilityRules.notFound.join(', ')}`);
		}
		
		priceList = priceList.replace("RET - ", ""); // Simplify display name

		return `
			<div class="validation-summary-box has-errors-box">
				<i class="fa fa-exclamation-triangle"></i>
				<strong>Partial Match:</strong>
				${matchedItems.length > 0 ? '<div class="mt-2">' + matchedItems.join('') + '</div>' : ''}
				<div class="mt-1">
					${notMatchedItems.map(msg => `<div class="error-line">• ${msg}</div>`).join('')}
				</div>
			</div>
		`;
	}
}

function show_multi_pricelist_summary(frm, priceListResults) {
	let total_price_lists = Object.keys(priceListResults).length;
	let success_count = 0;
	let error_count = 0;
	let empty_count = 0;
	let issues = [];
	
	Object.keys(priceListResults).forEach(function(priceList) {
		const result = priceListResults[priceList];
		
		if (result.status === 'error') {
			error_count++;
			issues.push(`<b>${priceList}:</b> API Error - ${result.error}`);
		} else if (is_empty_payload(result.payload)) {
			empty_count++;
		} else {
			const validation = result.response;
			let has_issues = false;
			
			if (validation && validation.length > 0) {
				validation.forEach(function(item) {
					if (!item.allValid) {
						has_issues = true;
						issues.push(`<b>${priceList} - ${capitalize(item.type)}:</b> ${item.notFound.join(', ')}`);
					}
				});
			}
			
			if (!has_issues) {
				if (!frm.doc.all_valid)
					frm.set_value("all_valid", true);
				success_count++;
			}
			else{
				if (frm.doc.all_valid == true)
					frm.set_value("all_valid", false);
			}
		}
	});
	
	if (error_count === 0 && issues.length === 0) {
		frappe.show_alert({
			message: __(`All ${total_price_lists} price lists validated successfully!`),
			indicator: 'green'
		}, 5);
	} else {
		let message = `<b>Website Validation Summary:</b><br><br>`;
		message += `✅ Success: ${success_count}<br>`;
		message += `⚠️ Issues: ${total_price_lists - success_count - empty_count}<br>`;
		if (empty_count > 0) {
			message += `📭 Empty: ${empty_count} (no items with prices)<br>`;
		}
		message += `<br>`;
		
		if (issues.length > 0) {
			message += '<b>Details:</b><br>' + issues.join('<br>');
		}
		
		frappe.msgprint({
			title: __('Website Validation Results'),
			message: message,
			indicator: issues.length > 0 ? 'orange' : 'green'
		});
	}
}

function is_empty_payload(payload) {
	return (
		(!payload.SpecsExternalIds || payload.SpecsExternalIds.length === 0) &&
		(!payload.CategoriesExternalIds || payload.CategoriesExternalIds.length === 0) &&
		(!payload.BrandsExternalIds || payload.BrandsExternalIds.length === 0) &&
		(!payload.AvailabilityRulesAliases || payload.AvailabilityRulesAliases.length === 0)
	);
}

function get_validation_styles() {
	return `
		<style>
			.validation-container {
				padding: 15px;
			}
			.validation-section {
				margin-bottom: 20px;
				padding: 20px;
				background: #fff;
				border: 1px solid #d1d8dd;
				border-radius: 8px;
				box-shadow: 0 1px 3px rgba(0,0,0,0.05);
			}
			.validation-section.file-overview,
			.validation-section.website-validation {
				/* These sections are always visible */
			}
			.validation-section h5 {
				margin-top: 0;
				margin-bottom: 15px;
				color: #36414c;
				font-weight: 600;
				font-size: 18px;
			}
			
			/* Collapsible Section Styles */
			.collapsible-section {
				margin-bottom: 15px;
				border: 2px solid #d1d8dd;
				border-radius: 8px;
				background: #fff;
				overflow: hidden;
				transition: all 0.2s ease;
			}
			.collapsible-section.has-warning {
				border-color: #ffc107;
				background: #fffbf0;
			}
			.collapsible-header {
				padding: 15px 20px;
				background: #f8f9fa;
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: space-between;
				user-select: none;
				transition: background 0.2s ease;
			}
			.collapsible-header:hover {
				background: #e9ecef;
			}
			.collapsible-section.has-warning .collapsible-header {
				background: #fff3cd;
			}
			.collapsible-section.has-warning .collapsible-header:hover {
				background: #ffeaa7;
			}
			.header-left {
				display: flex;
				align-items: center;
				gap: 10px;
			}
			.section-icon {
				color: #6c757d;
				font-size: 16px;
			}
			.section-title {
				margin: 0;
				font-size: 16px;
				font-weight: 600;
				color: #36414c;
			}
			.warning-indicator {
				color: #ffc107;
				font-size: 18px;
				animation: pulse 2s ease-in-out infinite;
			}
			@keyframes pulse {
				0%, 100% { opacity: 1; }
				50% { opacity: 0.5; }
			}
			.toggle-icon {
				color: #6c757d;
				transition: transform 0.2s ease;
			}
			.collapsible-section.expanded .toggle-icon {
				transform: rotate(180deg);
			}
			.collapsible-content {
				padding: 20px;
				border-top: 1px solid #dee2e6;
			}
			
			/* Rest of existing styles */
			.info-card {
				padding: 12px 15px;
				border-radius: 6px;
				background: #f8f9fa;
				border-left: 4px solid #6c757d;
			}
			.info-card.success-card {
				background: #d4edda;
				border-left-color: #28a745;
				color: #155724;
			}
			.info-message {
				padding: 12px 15px;
				border-radius: 6px;
				background: #d4edda;
				color: #155724;
				border-left: 4px solid #28a745;
			}
			.sheet-info-card {
				padding: 15px;
				margin-bottom: 15px;
				border-radius: 6px;
				border: 2px solid #d1d8dd;
			}
			.sheet-info-card.valid-card {
				background: #f0f9f4;
				border-color: #28a745;
			}
			.sheet-info-card.error-card {
				background: #fff5f5;
				border-color: #dc3545;
			}
			.sheet-info-card h6 {
				margin: 0 0 10px 0;
				font-size: 15px;
			}
			.info-grid {
				display: grid;
				grid-template-columns: repeat(2, 1fr);
				gap: 10px;
				margin-top: 10px;
			}
			.info-item {
				padding: 8px 12px;
				background: #fff;
				border-radius: 4px;
				border: 1px solid #e9ecef;
			}
			.error-message {
				color: #dc3545;
				padding: 10px;
				background: #fff;
				border-radius: 4px;
				border: 1px solid #f5c6cb;
			}
			.summary-link {
				cursor: pointer;
				color: #2490ef;
				font-weight: 500;
			}
			.summary-link:hover {
				text-decoration: underline;
			}
			.headers-list {
				display: flex;
				flex-wrap: wrap;
				gap: 6px;
			}
			.header-badge {
				display: inline-block;
				padding: 4px 10px;
				background: #e9ecef;
				border-radius: 4px;
				font-size: 12px;
				border: 1px solid #dee2e6;
			}
			.error-details {
				margin-top: 10px;
			}
			.error-detail-item {
				padding: 10px;
				margin-bottom: 8px;
				background: #fff;
				border-left: 3px solid #ffc107;
				border-radius: 4px;
			}
			.relationship-stats {
				display: flex;
				gap: 20px;
				flex-wrap: wrap;
			}
			.stat-card {
				flex: 1;
				min-width: 150px;
				text-align: center;
				padding: 20px;
				background: #f8f9fa;
				border-radius: 8px;
				border: 2px solid #dee2e6;
			}
			.stat-value {
				font-size: 36px;
				font-weight: 700;
				color: #2490ef;
				margin-bottom: 5px;
			}
			.stat-label {
				font-size: 13px;
				color: #6c757d;
				font-weight: 500;
			}
			.missing-template-item {
				padding: 6px 0;
			}
			.summary-subsection {
				margin-bottom: 20px;
			}
			.summary-subsection h6 {
				margin-top: 0;
				margin-bottom: 10px;
				font-weight: 600;
				font-size: 15px;
				color: #495057;
			}
			.summary-list {
				margin-top: 10px;
			}
			.summary-item {
				padding: 10px 12px;
				margin-bottom: 6px;
				border-radius: 4px;
				background: #f8f9fa;
				border-left: 3px solid #6c757d;
			}
			.summary-item.success-item {
				background: #d4edda;
				border-left-color: #28a745;
			}
			.count-badge {
				display: inline-block;
				padding: 2px 8px;
				background: #2490ef;
				color: #fff;
				border-radius: 10px;
				font-weight: 600;
				font-size: 12px;
				min-width: 24px;
				text-align: center;
			}
			.count-badge.primary {
				background: #28a745;
			}
			.price-list-assignments {
				margin-top: 10px;
			}
			.price-assignment-item {
				padding: 12px 15px;
				margin-bottom: 8px;
				border-radius: 6px;
				background: #d4edda;
				border-left: 4px solid #28a745;
			}
			.site-badge {
				display: inline-block;
				padding: 3px 10px;
				background: #2490ef;
				color: #fff;
				border-radius: 4px;
				font-weight: 500;
				font-size: 13px;
				margin: 0 2px;
			}
			.price-list-section {
				margin-bottom: 15px;
				padding: 15px;
				border: 2px solid #d1d8dd;
				border-radius: 6px;
				background: #fafbfc;
			}
			.price-list-section.has-errors {
				border-color: #dc3545;
				background: #fff5f5;
			}
			.price-list-section.all-valid {
				border-color: #28a745;
				background: #f0f9f4;
			}
			.price-list-section.api-error {
				border-color: #ffc107;
				background: #fffbf0;
			}
			.price-list-section.empty {
				border-color: #6c757d;
				background: #f8f9fa;
			}
			.price-list-header {
				font-size: 15px;
				font-weight: 600;
				margin-bottom: 10px;
				display: flex;
				align-items: center;
				justify-content: space-between;
			}
			.validation-summary-box {
				padding: 12px 15px;
				border-radius: 5px;
				margin-top: 10px;
			}
			.validation-summary-box.all-valid-box {
				background-color: #d4edda;
				border: 1px solid #c3e6cb;
				color: #155724;
			}
			.validation-summary-box.has-errors-box {
				background-color: #fff3cd;
				border: 1px solid #ffeaa7;
				color: #856404;
			}
			.validation-summary-box.api-error-box {
				background-color: #f8d7da;
				border: 1px solid #f5c6cb;
				color: #721c24;
			}
			.match-detail {
				padding: 4px 0;
			}
			.empty-message-box {
				text-align: center;
				padding: 0px 20px;
				color: #6c757d;
			}
			.empty-message-box i {
				font-size: 48px;
				opacity: 0.4;
				margin-bottom: 10px;
			}
			.empty-message-box h6 {
				margin: 10px 0 5px 0;
				color: #495057;
			}
			.error-line {
				padding: 4px 0;
			}
		</style>
	`;
}

function capitalize(str) {
	return str.charAt(0).toUpperCase() + str.slice(1);
}