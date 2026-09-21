// Universal Report Builder - Production Quality Desk Page Controller

frappe.pages["universal-report-builder"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Universal Report Builder"),
		single_column: true
	});

	frappe.require("/assets/nocodereport/page/universal_report_builder/universal_report_builder.css");

	init_builder(page, wrapper);
};

function init_builder(page, wrapper) {
	const state = {
		base_doctype: null,
		metadata: null,
		available_fields: [],
		selected_fields: [], // { path, fieldname, label, fieldtype, alias, doctype }
		relationships: [], // { fieldname, label, target_doctype, path, has_permission, rel_type }
		expanded_rel_fields: {},
		open_rel_nodes: {}, // path -> [fields]
		filters: [], // { field, operator, value }
		filter_operator: "AND",
		joins: {}, // path -> "LEFT JOIN" | "INNER JOIN"
		group_by: [], // { field, interval }
		aggregations: [], // { func, field, alias }
		order_by: [], // { field, direction }
		calculated_fields: [], // { expression, alias }
		sql: "",
		explanation: "",

	};

	function setup_dom(html) {
		$(page.main).html(html);
		bind_ui_events(page, state);
		load_doctypes(state);
	}

	if (frappe.templates && frappe.templates["universal_report_builder"]) {
		try {
			const html_content = frappe.render_template("universal_report_builder", {});
			setup_dom(html_content);
			return;
		} catch (e) {
			console.warn("frappe.render_template error, falling back to server fetch:", e);
		}
	}

	frappe.call({
		method: "nocodereport.nocodereport.page.universal_report_builder.universal_report_builder.get_page_html",
		callback: function (r) {
			const html_content = r && r.message ? r.message : get_fallback_html();
			setup_dom(html_content);
		},
		error: function () {
			setup_dom(get_fallback_html());
		}
	});
}

function bind_ui_events(page, state) {
	const $main = $(page.main);

	// Top actions
	$main.find("#urb-btn-new").on("click", function () { reset_state(state, $main); });
	$main.find("#urb-btn-generate").on("click", function () { trigger_generate_sql(state, $main, true); });
	$main.find("#urb-btn-copy-sql").on("click", function () {
		if (!state.sql) return frappe.show_alert({ message: __("No SQL query generated yet"), indicator: "orange" });
		copy_to_clipboard(state.sql, __("SQL copied successfully."));
	});




	$main.find("#urb-alert-close").on("click", function () { hide_alert($main); });

	// Available fields search
	$main.find("#urb-field-search").on("input", function () {
		const val = $(this).val().toLowerCase().trim();
		$main.find(".urb-field-item").each(function () {
			const label = $(this).attr("data-label") || "";
			const fieldname = $(this).attr("data-fieldname") || "";
			$(this).toggle(!val || label.includes(val) || fieldname.includes(val));
		});
	});

	// Select All / Clear
	$main.find("#urb-btn-select-all").on("click", function () {
		if (!state.metadata || !state.available_fields.length) return;
		state.available_fields.forEach(function (f) {
			if (!f.is_virtual && !['Section Break','Column Break','Tab Break','HTML'].includes(f.fieldtype) && !is_field_selected(state, f.fieldname)) {
				add_selected_field(state, f.fieldname, f.fieldname, f.label || f.fieldname, f.fieldtype, state.base_doctype);
			}
		});
		refresh_ui(state, $main);
	});

	$main.find("#urb-btn-clear-all").on("click", function () {
		state.selected_fields = [];
		refresh_ui(state, $main);
	});

	// Add Filter Dialog
	$main.find("#urb-btn-add-filter").on("click", function () { open_add_filter_dialog(state, $main); });

	// Add Group By Dialog
	$main.find("#urb-btn-add-group").on("click", function () { open_add_group_dialog(state, $main); });

	// Add Aggregation Dialog
	$main.find("#urb-btn-add-agg").on("click", function () { open_add_agg_dialog(state, $main); });

	// Add Order By Dialog
	$main.find("#urb-btn-add-order").on("click", function () { open_add_order_dialog(state, $main); });

	// Add Calculated Field Dialog
	$main.find("#urb-btn-add-calc").on("click", function () { open_add_calc_dialog(state, $main); });

	// Fit Graph

}

function load_doctypes(state) {
	frappe.call({
		method: "nocodereport.api.metadata.get_permitted_doctypes",
		callback: function (r) {
			if (r && r.message) {
				setup_doctype_autocomplete(state, r.message);
			}
		}
	});
}

function setup_doctype_autocomplete(state, doctype_list) {
	const $input = $("#urb-doctype-input");
	const options = doctype_list.map(function (d) {
		return { label: `${d.name} (${d.module})`, value: d.name };
	});

	const awesomplete = new Awesomplete($input[0], {
		list: options,
		minChars: 0,
		maxItems: 25,
		autoFirst: true
	});

	$input.on("focus", function () { awesomplete.evaluate(); });
	$input.on("awesomplete-selectcomplete", function (e) {
		on_doctype_selected(state, e.text.value || $(this).val());
	});
	$input.on("change", function () {
		const val = $(this).val().trim();
		if (val && val !== state.base_doctype) on_doctype_selected(state, val);
	});
}

function on_doctype_selected(state, doctype) {
	if (!doctype) return;
	const $main = $(".urb-container");
	hide_alert($main);

	$("#urb-doctype-status").html('<i class="fa fa-spinner fa-spin text-muted"></i>');

	frappe.call({
		method: "nocodereport.api.metadata.get_doctype_metadata",
		args: { doctype: doctype },
		callback: function (r) {
			$("#urb-doctype-status").empty();
			if (r && r.message) {
				state.base_doctype = doctype;
				state.metadata = r.message;
				state.available_fields = r.message.fields || [];
				state.selected_fields = [];
				state.filters = [];
				state.group_by = [];
				state.aggregations = [];
				state.order_by = [];
				state.calculated_fields = [];
				state.joins = {};

				$("#urb-perm-badge").removeClass("hidden");

				// Default select name
				const name_field = state.available_fields.find(function (f) { return f.fieldname === "name"; });
				if (name_field) {
					add_selected_field(state, "name", "name", name_field.label || "ID / Name", "Data", doctype);
				}

				load_relationships(state, $main);
				refresh_ui(state, $main);
			}
		},
		error: function (err) {
			$("#urb-doctype-status").empty();
			$("#urb-perm-badge").addClass("hidden");
			reset_state(state, $main);
			const err_msg = (err && err.message) ? err.message : __("Access Denied: You do not have permission to read this DocType.");
			show_alert($main, err_msg);
		}
	});
}

function load_relationships(state, $main) {
	frappe.call({
		method: "nocodereport.api.relationships.get_doctype_relationships",
		args: { doctype: state.base_doctype },
		callback: function (r) {
			if (r && r.message && r.message.has_permission) {
				state.relationships = (r.message.links || []).concat(r.message.tables || []);
				render_relationships_tree(state, $main);
			}
		}
	});
}

function render_relationships_tree(state, $main) {
	const $tree = $main.find("#urb-rel-tree");
	$tree.empty();
	$main.find("#urb-rel-count").text(state.relationships.length);

	if (!state.base_doctype) {
		$main.find("#urb-rel-hint").text(__("Select a Base DocType above to explore relationships."));
		$tree.html('<div class="text-muted text-center" style="font-size: 11px; padding: 12px;">Select a Base DocType above to discover available relationships</div>');
		return;
	}

	if (!state.relationships.length) {
		$main.find("#urb-rel-hint").text(__("No linked DocTypes or child tables found."));
		$tree.html('<div class="text-muted text-center" style="font-size: 11px; padding: 12px;">No linked DocTypes or child tables found</div>');
		return;
	}

	$main.find("#urb-rel-hint").text(__("{0} relationship(s) available. Click to explore fields.", [state.relationships.length]));

	state.relationships.forEach(function (rel) {
		const is_child = rel.rel_type === "child_table";
		const icon_cls = is_child ? "fa-table text-warning" : "fa-link text-info";
		const badge_txt = is_child ? "Child Table" : "Link";
		const is_node_open = !!(state.open_rel_nodes && state.open_rel_nodes[rel.path]);

		const $item = $(`
			<div class="urb-rel-node" data-path="${rel.path}" style="border: 1px solid #eef0f2; border-radius: 6px; margin-bottom: 6px; padding: 6px 10px; background: #fafafa;">
				<div class="urb-rel-node-header" style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;">
					<div>
						<i class="fa ${icon_cls}" style="margin-right: 6px;"></i>
						<strong>${frappe.utils.escape_html(rel.label)}</strong>
						<span style="font-size: 11px; color: #718096;">&rarr; ${frappe.utils.escape_html(rel.target_doctype)}</span>
					</div>
					<div>
						${!rel.has_permission ? '<span class="badge badge-danger" title="Permission Denied">ðŸ”’ Restricted</span>' : `<span class="urb-field-type-pill ${is_child ? 'table' : 'link'}">${badge_txt}</span> <i class="fa ${is_node_open ? 'fa-chevron-up' : 'fa-chevron-down'} text-muted urb-expand-icon"></i>`}
					</div>
				</div>
				<div class="urb-rel-node-fields ${is_node_open ? '' : 'hidden'}" style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
					<div class="urb-rel-loading text-muted text-center py-2" style="font-size: 11px;"><i class="fa fa-spinner fa-spin"></i> Loading fields...</div>
				</div>
			</div>
		`);

		const $fields_container = $item.find(".urb-rel-node-fields");

		if (state.expanded_rel_fields && state.expanded_rel_fields[rel.path]) {
			render_rel_fields_list(state, rel, state.expanded_rel_fields[rel.path], $fields_container, $main);
		}

		if (rel.has_permission) {
			$item.find(".urb-rel-node-header").on("click", function (e) {
				const is_open = !$fields_container.hasClass("hidden");
				const will_open = !is_open;
				$fields_container.toggleClass("hidden", !will_open);
				$item.find(".urb-expand-icon").toggleClass("fa-chevron-up", will_open).toggleClass("fa-chevron-down", !will_open);
				if (!state.open_rel_nodes) state.open_rel_nodes = {};
				state.open_rel_nodes[rel.path] = will_open;

				if (will_open) {
					if (state.expanded_rel_fields && state.expanded_rel_fields[rel.path]) {
						render_rel_fields_list(state, rel, state.expanded_rel_fields[rel.path], $fields_container, $main);
					} else {
						fetch_relationship_fields(state, rel, $fields_container, $main);
					}
				}
			});
		}

		$tree.append($item);
	});
}

function fetch_relationship_fields(state, rel, $container, $main) {
	frappe.call({
		method: "nocodereport.api.relationships.get_relationship_fields",
		args: {
			base_doctype: state.base_doctype,
			rel_path: rel.path
		},
		callback: function (r) {
			if (r && r.message && r.message.success) {
				state.expanded_rel_fields[rel.path] = r.message.fields;
				render_rel_fields_list(state, rel, r.message.fields, $container, $main);
			} else {
				$container.html(`<div class="text-danger p-2" style="font-size: 11px;">${(r && r.message && r.message.error) || 'Failed to load fields'}</div>`);
			}
		}
	});
}

function render_rel_fields_list(state, rel, fields, $container, $main) {
	$container.empty();
	if (!fields || !fields.length) {
		$container.html('<div class="text-muted text-center" style="font-size: 11px;">No queryable fields.</div>');
		return;
	}

	fields.forEach(function (f) {
		const full_path = `${rel.path}.${f.fieldname}`;
		const is_selected = is_field_selected(state, full_path);

		const $f_item = $(`
			<div class="urb-field-item ${is_selected ? 'selected' : ''}" data-path="${full_path}" style="font-size: 11px; padding: 4px 8px; margin-bottom: 2px;">
				<div class="urb-field-label-group">
					<input type="checkbox" ${is_selected ? 'checked' : ''}>
					<span>${frappe.utils.escape_html(f.label || f.fieldname)}</span>
				</div>
				<span class="urb-field-type-pill">${f.fieldtype}</span>
			</div>
		`);

		$f_item.on("click", function (e) {
			e.stopPropagation();
			const $cb = $f_item.find("input[type=checkbox]");
			const now_checked = !is_field_selected(state, full_path);
			$cb.prop("checked", now_checked);
			$f_item.toggleClass("selected", now_checked);
			toggle_path_selection(state, full_path, f.fieldname, f.label, f.fieldtype, rel.target_doctype, $main);
		});

		$container.append($f_item);
	});
}

function toggle_path_selection(state, path, fieldname, label, fieldtype, doctype, $main) {
	const idx = state.selected_fields.findIndex(function (sf) { return sf.path === path; });
	if (idx >= 0) {
		state.selected_fields.splice(idx, 1);
	} else {
		add_selected_field(state, path, fieldname, label, fieldtype, doctype);
	}
	refresh_ui(state, $main);
}

function add_selected_field(state, path, fieldname, label, fieldtype, doctype) {
	const clean_alias = path.replace(/\./g, "_");
	state.selected_fields.push({
		path: path,
		fieldname: fieldname,
		label: label || fieldname,
		fieldtype: fieldtype || "Data",
		alias: clean_alias,
		doctype: doctype
	});
}

function is_field_selected(state, path) {
	return state.selected_fields.some(function (sf) { return sf.path === path; });
}

function refresh_ui(state, $main) {
	render_available_fields(state, $main);
	if (!state.relationships_rendered_for || state.relationships_rendered_for !== state.base_doctype) {
		render_relationships_tree(state, $main);
		state.relationships_rendered_for = state.base_doctype;
	} else {
		sync_rel_field_checkboxes(state, $main);
	}
	render_joins_list(state, $main);
	render_selected_fields(state, $main);
	render_filters_list(state, $main);
	render_group_list(state, $main);
	render_agg_list(state, $main);
	render_order_list(state, $main);
	render_calc_list(state, $main);
	render_graph(state, $main);
}

function sync_rel_field_checkboxes(state, $main) {
	$main.find("#urb-rel-tree .urb-field-item").each(function () {
		const full_path = $(this).attr("data-path");
		if (full_path) {
			const is_sel = is_field_selected(state, full_path);
			$(this).toggleClass("selected", is_sel);
			$(this).find("input[type=checkbox]").prop("checked", is_sel);
		}
	});
}

function render_available_fields(state, $main) {
	const $container = $main.find("#urb-fields-list");
	$container.empty();

	if (!state.available_fields || !state.available_fields.length) {
		$container.html(`
			<div class="urb-empty-placeholder">
				<i class="fa fa-database"></i>
				<p>Select a Base DocType above to discover available fields</p>
			</div>
		`);
		return;
	}

	state.available_fields.forEach(function (f) {
		if (['Section Break', 'Column Break', 'Tab Break', 'HTML'].includes(f.fieldtype)) return;
		const is_selected = is_field_selected(state, f.fieldname);
		const is_virtual = f.is_virtual;
		let badge_cls = f.is_link ? "link" : (f.is_table ? "table" : "");

		const $item = $(`
			<div class="urb-field-item ${is_selected ? 'selected' : ''}" data-fieldname="${f.fieldname}" data-label="${(f.label || f.fieldname).toLowerCase()}">
				<div class="urb-field-label-group">
					<input type="checkbox" ${is_selected ? 'checked' : ''} ${is_virtual ? 'disabled title="Virtual field - cannot be used directly in SQL."' : ''}>
					<span title="${f.fieldname}">${frappe.utils.escape_html(f.label || f.fieldname)}</span>
				</div>
				<div>
					${is_virtual ? '<span class="urb-field-type-pill text-warning" title="Virtual field">Virtual</span>' : ''}
					<span class="urb-field-type-pill ${badge_cls}">${f.fieldtype || 'Data'}</span>
				</div>
			</div>
		`);

		if (!is_virtual) {
			$item.on("click", function (e) {
				if (!$(e.target).is("input[type=checkbox]")) {
					$item.find("input[type=checkbox]").prop("checked", !is_selected);
				}
				toggle_path_selection(state, f.fieldname, f.fieldname, f.label, f.fieldtype, state.base_doctype, $main);
			});
		}

		$container.append($item);
	});
}

function render_selected_fields(state, $main) {
	const $tbody = $main.find("#urb-selected-tbody");
	$tbody.empty();
	$main.find("#urb-selected-count").text(state.selected_fields.length);

	if (!state.selected_fields.length) {
		$tbody.html(`
			<tr class="urb-no-fields-row">
				<td colspan="6" class="text-center text-muted">
					No fields selected. Choose fields from the left sidebar to add them to your query.
				</td>
			</tr>
		`);
		return;
	}

	state.selected_fields.forEach(function (sf, i) {
		const $tr = $(`
			<tr data-index="${i}">
				<td class="text-center text-muted">${i + 1}</td>
				<td>
					<strong>${frappe.utils.escape_html(sf.label)}</strong>
					<br><small class="text-muted font-monospace">${frappe.utils.escape_html(sf.path)}</small>
				</td>
				<td><span class="badge badge-light">${frappe.utils.escape_html(sf.doctype)}</span></td>
				<td><span class="urb-field-type-pill">${frappe.utils.escape_html(sf.fieldtype)}</span></td>
				<td>
					<input type="text" class="form-control input-xs urb-alias-input" value="${frappe.utils.escape_html(sf.alias || sf.fieldname)}">
				</td>
				<td class="text-center">
					<button class="btn btn-xs btn-link text-danger urb-btn-remove-field" title="Remove Column">
						<i class="fa fa-times"></i>
					</button>
				</td>
			</tr>
		`);

		$tr.find(".urb-alias-input").on("change", function () {
			sf.alias = $(this).val().trim() || sf.fieldname;
			});

		$tr.find(".urb-btn-remove-field").on("click", function () {
			state.selected_fields.splice(i, 1);
			refresh_ui(state, $main);
		});

		$tbody.append($tr);
	});
}

// -------------------------------------------------------------
// Field Type Classification & Compatibility
// -------------------------------------------------------------

function getFieldCategory(field) {
	if (!field) return "other";
	let ft = "";
	if (typeof field === "string") {
		ft = field.trim();
	} else if (typeof field === "object") {
		ft = (field.fieldtype || "").trim();
	}

	// Layout / UI fields
	const layoutTypes = ["Section Break", "Column Break", "Tab Break", "Fold", "Heading", "HTML", "Button"];
	if (layoutTypes.includes(ft)) return "layout";

	// Table / Child fields
	const tableTypes = ["Table", "Table MultiSelect"];
	if (tableTypes.includes(ft)) return "table";

	// Attachment / Image fields
	const attachmentTypes = ["Attach", "Attach Image", "Image"];
	if (attachmentTypes.includes(ft)) return "attachment";

	// Numeric fields
	const numericTypes = ["Int", "Float", "Currency", "Percent", "Duration", "Rating"];
	if (numericTypes.includes(ft)) return "numeric";

	// Date / Time
	if (ft === "Date") return "date";
	if (ft === "Datetime") return "datetime";
	if (ft === "Time") return "time";

	// Boolean
	if (ft === "Check") return "boolean";

	// Link
	if (["Link", "Dynamic Link"].includes(ft)) return "link";

	// Select
	if (ft === "Select") return "select";

	// Text fields
	const textTypes = [
		"Data", "Small Text", "Text", "Long Text", "Code", "Text Editor",
		"Markdown Editor", "HTML Editor", "Password", "Phone", "Autocomplete",
		"Read Only", "Color", "Signature", "Barcode", "Geolocation"
	];
	if (textTypes.includes(ft)) return "text";

	return "other";
}

function isAggregationCompatible(field, aggregation) {
	if (!field || !aggregation) return false;
	if (typeof field === "object" && field.is_virtual) return false;

	const fn = String(aggregation).trim().toUpperCase();
	const cat = getFieldCategory(field);

	if (["layout", "table", "attachment"].includes(cat)) return false;

	if (fn === "COUNT") {
		return ["text", "numeric", "date", "datetime", "time", "boolean", "link", "select", "other"].includes(cat);
	}
	if (fn === "SUM" || fn === "AVG") {
		return cat === "numeric";
	}
	if (fn === "MIN" || fn === "MAX") {
		return ["numeric", "date", "datetime", "time"].includes(cat);
	}

	return false;
}

function isFilterCompatible(field, operator) {
	if (!field || !operator) return false;
	if (typeof field === "object" && field.is_virtual) return false;

	const op = String(operator).trim().toUpperCase();
	const cat = getFieldCategory(field);

	if (["layout", "table", "attachment"].includes(cat)) return false;

	if (op === "=" || op === "!=" || op === "<>") {
		return ["text", "numeric", "date", "datetime", "time", "boolean", "link", "select", "other"].includes(cat);
	}
	if (op === ">" || op === "<" || op === ">=" || op === "<=") {
		return ["numeric", "date", "datetime", "time"].includes(cat);
	}
	if (op === "LIKE" || op === "NOT LIKE") {
		return ["text", "link", "select"].includes(cat);
	}
	if (op === "IN" || op === "NOT IN") {
		return ["text", "numeric", "date", "datetime", "time", "boolean", "link", "select"].includes(cat);
	}
	if (op === "BETWEEN") {
		return ["numeric", "date", "datetime", "time"].includes(cat);
	}
	if (op === "IS NULL" || op === "IS NOT NULL") {
		return ["text", "numeric", "date", "datetime", "time", "boolean", "link", "select", "other"].includes(cat);
	}

	return true;
}

function get_all_field_entries(state) {
	const entries = [];
	(state.available_fields || []).forEach(function (f) {
		entries.push({
			id: f.fieldname,
			label: f.label ? `${f.label} (${f.fieldname})` : f.fieldname,
			fieldtype: f.fieldtype,
			is_virtual: f.is_virtual,
			raw: f
		});
	});
	Object.keys(state.expanded_rel_fields || {}).forEach(function (path) {
		const fields = state.expanded_rel_fields[path] || [];
		fields.forEach(function (f) {
			const label_text = f.label || f.fieldname;
			entries.push({
				id: `${path}.${f.fieldname}`,
				label: `${path} → ${label_text} (${f.fieldname})`,
				fieldtype: f.fieldtype,
				is_virtual: f.is_virtual,
				raw: f
			});
		});
	});
	return entries;
}

function get_compatible_agg_field_options(state, func) {
	const entries = get_all_field_entries(state);
	const fn = (func || "").toUpperCase();
	const options = [];

	if (fn === "COUNT") {
		options.push({ label: "* (All Rows)", value: "*" });
	}

	entries.forEach(function (entry) {
		if (isAggregationCompatible(entry.raw || entry, fn)) {
			options.push({ label: entry.label, value: entry.id });
		}
	});

	return options;
}

function get_compatible_filter_field_options(state, operator) {
	const entries = get_all_field_entries(state);
	const op = (operator || "=").toUpperCase();
	const options = [];

	entries.forEach(function (entry) {
		if (isFilterCompatible(entry.raw || entry, op)) {
			options.push({ label: entry.label, value: entry.id });
		}
	});

	return options;
}

// -------------------------------------------------------------
// Filters UI
// -------------------------------------------------------------
function render_filters_list(state, $main) {
	const $box = $main.find("#urb-filters-container");
	$box.empty();

	if (!state.filters.length) {
		$box.html('<div class="text-muted text-center" style="font-size: 11px; padding: 6px;">No filters configured</div>');
		return;
	}

	state.filters.forEach(function (f, idx) {
		let val_display = "";
		if (f.operator === "IS NULL" || f.operator === "IS NOT NULL") {
			val_display = "";
		} else if (f.operator === "BETWEEN") {
			if (Array.isArray(f.value) && f.value.length >= 2) {
				val_display = `<code>${frappe.utils.escape_html(String(f.value[0]))} AND ${frappe.utils.escape_html(String(f.value[1]))}</code>`;
			} else {
				val_display = `<code>${frappe.utils.escape_html(String(f.value))}</code>`;
			}
		} else if (f.operator === "IN" || f.operator === "NOT IN") {
			if (Array.isArray(f.value)) {
				val_display = `<code>(${f.value.map(v => frappe.utils.escape_html(String(v))).join(", ")})</code>`;
			} else {
				val_display = `<code>(${frappe.utils.escape_html(String(f.value))})</code>`;
			}
		} else {
			val_display = `<code>${frappe.utils.escape_html(String(f.value))}</code>`;
		}

		const $row = $(`
			<div class="urb-filter-chip" style="display: flex; justify-content: space-between; align-items: center; background: #f1f5f9; padding: 5px 8px; border-radius: 4px; margin-bottom: 4px; font-size: 11px;">
				<div>
					<strong>${frappe.utils.escape_html(f.field)}</strong>
					<span class="text-primary font-weight-bold mx-1">${frappe.utils.escape_html(f.operator)}</span>
					${val_display}
				</div>
				<button class="btn btn-xs btn-link text-danger urb-remove-filter" data-index="${idx}">&times;</button>
			</div>
		`);

		$row.find(".urb-remove-filter").on("click", function () {
			state.filters.splice(idx, 1);
			refresh_ui(state, $main);
		});

		$box.append($row);
	});
}

function open_add_filter_dialog(state, $main) {
	if (!state.base_doctype) return frappe.msgprint(__("Please select a Base DocType first"));

	const initial_op = "=";
	let initial_field_options = get_compatible_filter_field_options(state, initial_op);
	if (!initial_field_options.length) {
		initial_field_options = [{ label: __("-- No compatible fields found --"), value: "" }];
	}

	const d = new frappe.ui.Dialog({
		title: __("Add Filter"),
		fields: [
			{
				fieldname: "field",
				label: __("Field"),
				fieldtype: "Select",
				options: initial_field_options,
				reqd: 1
			},
			{
				fieldname: "operator",
				label: __("Operator"),
				fieldtype: "Select",
				options: ["=", "!=", ">", "<", ">=", "<=", "LIKE", "NOT LIKE", "IN", "NOT IN", "BETWEEN", "IS NULL", "IS NOT NULL"],
				default: initial_op,
				reqd: 1
			},
			{
				fieldname: "value",
				label: __("Value"),
				fieldtype: "Data",
				reqd: 1
			},
			{
				fieldname: "value_to",
				label: __("To Value"),
				fieldtype: "Data",
				hidden: 1
			}
		],
		primary_action_label: __("Add Filter"),
		primary_action: function (values) {
			if (!values.field) {
				return frappe.msgprint(__("Please select a valid compatible field."));
			}

			const op = values.operator;
			let final_val = values.value;

			if (op === "IS NULL" || op === "IS NOT NULL") {
				final_val = null;
			} else if (op === "BETWEEN") {
				if (values.value === undefined || values.value === null || values.value === "" ||
					values.value_to === undefined || values.value_to === null || values.value_to === "") {
					return frappe.msgprint(__("Please provide both From and To values for BETWEEN filter."));
				}
				final_val = [values.value, values.value_to];
			} else if (op === "IN" || op === "NOT IN") {
				if (!values.value || !String(values.value).trim()) {
					return frappe.msgprint(__("Please provide comma-separated values for IN filter."));
				}
				final_val = String(values.value).split(",").map(v => v.trim()).filter(Boolean);
			} else {
				if (values.value === undefined || values.value === null || values.value === "") {
					return frappe.msgprint(__("Please provide a filter value."));
				}
				final_val = values.value;
			}

			state.filters.push({
				field: values.field,
				operator: values.operator,
				value: final_val
			});
			d.hide();
			refresh_ui(state, $main);
		}
	});

	function update_ui_for_operator(op) {
		let new_options = get_compatible_filter_field_options(state, op);
		if (!new_options.length) {
			new_options = [{ label: __("-- No compatible fields found --"), value: "" }];
		}
		const current_field = d.get_value("field");
		const is_compat = new_options.some(function (opt) {
			return (opt.value || opt) === current_field && current_field !== "";
		});

		d.set_df_property("field", "options", new_options);
		const field_ctrl = d.get_field("field");
		if (field_ctrl && field_ctrl.$input) {
			field_ctrl.$input.empty();
			new_options.forEach(function (opt) {
				field_ctrl.$input.append($("<option>", { value: opt.value, text: opt.label }));
			});
		}

		if (is_compat && current_field) {
			d.set_value("field", current_field);
		} else {
			// Clear field selection if incompatible (Option A from Req 7)
			d.set_value("field", "");
		}

		// Adjust value inputs based on operator (Req 5)
		if (op === "IS NULL" || op === "IS NOT NULL") {
			d.set_df_property("value", "hidden", 1);
			d.set_df_property("value", "reqd", 0);
			d.set_df_property("value_to", "hidden", 1);
			d.set_df_property("value_to", "reqd", 0);
			d.set_value("value", "");
			d.set_value("value_to", "");
			if (d.get_field("value") && d.get_field("value").$wrapper) d.get_field("value").$wrapper.hide();
			if (d.get_field("value_to") && d.get_field("value_to").$wrapper) d.get_field("value_to").$wrapper.hide();
		} else if (op === "BETWEEN") {
			d.set_df_property("value", "hidden", 0);
			d.set_df_property("value", "label", __("From Value"));
			d.set_df_property("value", "reqd", 1);
			d.set_df_property("value_to", "hidden", 0);
			d.set_df_property("value_to", "label", __("To Value"));
			d.set_df_property("value_to", "reqd", 1);
			if (d.get_field("value") && d.get_field("value").$wrapper) {
				d.get_field("value").$wrapper.show();
				if (d.get_field("value").$label) d.get_field("value").$label.text(__("From Value"));
			}
			if (d.get_field("value_to") && d.get_field("value_to").$wrapper) {
				d.get_field("value_to").$wrapper.show();
				if (d.get_field("value_to").$label) d.get_field("value_to").$label.text(__("To Value"));
			}
		} else if (op === "IN" || op === "NOT IN") {
			d.set_df_property("value", "hidden", 0);
			d.set_df_property("value", "label", __("Values (comma separated)"));
			d.set_df_property("value", "reqd", 1);
			d.set_df_property("value_to", "hidden", 1);
			d.set_df_property("value_to", "reqd", 0);
			if (d.get_field("value") && d.get_field("value").$wrapper) {
				d.get_field("value").$wrapper.show();
				if (d.get_field("value").$label) d.get_field("value").$label.text(__("Values (comma separated)"));
			}
			if (d.get_field("value_to") && d.get_field("value_to").$wrapper) d.get_field("value_to").$wrapper.hide();
		} else {
			d.set_df_property("value", "hidden", 0);
			d.set_df_property("value", "label", __("Value"));
			d.set_df_property("value", "reqd", 1);
			d.set_df_property("value_to", "hidden", 1);
			d.set_df_property("value_to", "reqd", 0);
			if (d.get_field("value") && d.get_field("value").$wrapper) {
				d.get_field("value").$wrapper.show();
				if (d.get_field("value").$label) d.get_field("value").$label.text(__("Value"));
			}
			if (d.get_field("value_to") && d.get_field("value_to").$wrapper) d.get_field("value_to").$wrapper.hide();
		}
	}

	d.show();

	// Listen to operator changes
	const op_ctrl = d.get_field("operator");
	if (op_ctrl && op_ctrl.$input) {
		op_ctrl.$input.on("change", function () {
			const selected_op = $(this).val();
			update_ui_for_operator(selected_op);
		});
	}
}

// -------------------------------------------------------------
// Group By UI
// -------------------------------------------------------------
function render_group_list(state, $main) {
	const $box = $main.find("#urb-group-container");
	$box.empty();

	if (!state.group_by.length) {
		$box.html('<div class="text-muted text-center" style="font-size: 11px; padding: 6px;">No grouping</div>');
		return;
	}

	state.group_by.forEach(function (g, idx) {
		const desc = g.interval ? `${g.field} (${g.interval})` : g.field;
		const $chip = $(`
			<div class="badge badge-secondary mr-1 mb-1 p-1" style="font-size: 11px;">
				${frappe.utils.escape_html(desc)}
				<span class="ml-1 cursor-pointer urb-del-group" data-index="${idx}">&times;</span>
			</div>
		`);
		$chip.find(".urb-del-group").on("click", function () {
			state.group_by.splice(idx, 1);
			refresh_ui(state, $main);
		});
		$box.append($chip);
	});
}

function open_add_group_dialog(state, $main) {
	if (!state.base_doctype) return frappe.msgprint(__("Please select a Base DocType first"));

	const field_options = get_all_queryable_field_options(state);
	const d = new frappe.ui.Dialog({
		title: __("Add Group By"),
		fields: [
			{ fieldname: "field", label: __("Field"), fieldtype: "Select", options: field_options, reqd: 1 },
			{ fieldname: "interval", label: __("Date Interval (Optional)"), fieldtype: "Select", options: ["", "YEAR", "MONTH", "QUARTER", "DAY"] }
		],
		primary_action_label: __("Add Group"),
		primary_action: function (values) {
			state.group_by.push(values);
			d.hide();
			refresh_ui(state, $main);
		}
	});
	d.show();
}

// -------------------------------------------------------------
// Aggregations UI
// -------------------------------------------------------------
function render_agg_list(state, $main) {
	const $box = $main.find("#urb-agg-container");
	$box.empty();

	if (!state.aggregations.length) {
		$box.html('<div class="text-muted text-center" style="font-size: 11px; padding: 6px;">No aggregations</div>');
		return;
	}

	state.aggregations.forEach(function (a, idx) {
		const $chip = $(`
			<div class="badge badge-info mr-1 mb-1 p-1" style="font-size: 11px;">
				${a.func}(${frappe.utils.escape_html(a.field)}) AS ${frappe.utils.escape_html(a.alias)}
				<span class="ml-1 cursor-pointer urb-del-agg" data-index="${idx}">&times;</span>
			</div>
		`);
		$chip.find(".urb-del-agg").on("click", function () {
			state.aggregations.splice(idx, 1);
			refresh_ui(state, $main);
		});
		$box.append($chip);
	});
}

function open_add_agg_dialog(state, $main) {
	if (!state.base_doctype) return frappe.msgprint(__("Please select a Base DocType first"));

	const initial_func = "SUM";
	let initial_options = get_compatible_agg_field_options(state, initial_func);
	if (!initial_options.length) {
		initial_options = [{ label: __("-- No compatible fields found --"), value: "" }];
	}

	const d = new frappe.ui.Dialog({
		title: __("Add Aggregation"),
		fields: [
			{
				fieldname: "func",
				label: __("Function"),
				fieldtype: "Select",
				options: ["SUM", "COUNT", "AVG", "MIN", "MAX"],
				default: initial_func,
				reqd: 1
			},
			{
				fieldname: "field",
				label: __("Field"),
				fieldtype: "Select",
				options: initial_options,
				reqd: 1
			},
			{
				fieldname: "alias",
				label: __("Alias"),
				fieldtype: "Data",
				default: "total_val"
			}
		],
		primary_action_label: __("Add Aggregation"),
		primary_action: function (values) {
			if (!values.field) {
				return frappe.msgprint(__("Please select a valid compatible field."));
			}
			if (!values.alias) {
				const f_clean = values.field === "*" ? "all" : values.field.replace(/\./g, "_");
				values.alias = `${values.func.toLowerCase()}_${f_clean}`;
			}
			state.aggregations.push(values);
			d.hide();
			refresh_ui(state, $main);
		}
	});

	function update_fields_for_func(new_func) {
		let new_options = get_compatible_agg_field_options(state, new_func);
		if (!new_options.length) {
			new_options = [{ label: __("-- No compatible fields found --"), value: "" }];
		}
		const current_field = d.get_value("field");
		const is_compat = new_options.some(function (opt) {
			return (opt.value || opt) === current_field && current_field !== "";
		});

		d.set_df_property("field", "options", new_options);
		const field_ctrl = d.get_field("field");
		if (field_ctrl && field_ctrl.$input) {
			field_ctrl.$input.empty();
			new_options.forEach(function (opt) {
				field_ctrl.$input.append($("<option>", { value: opt.value, text: opt.label }));
			});
		}

		if (is_compat && current_field) {
			d.set_value("field", current_field);
		} else {
			// Clear field selection if incompatible (Option A from Req 7)
			d.set_value("field", "");
		}

		// Update default alias suggestion
		if (new_func === "COUNT") {
			if (!d.get_value("alias") || d.get_value("alias") === "total_val") {
				d.set_value("alias", "total_count");
			}
		}
	}

	d.show();

	// Attach change listener to func
	const func_ctrl = d.get_field("func");
	if (func_ctrl && func_ctrl.$input) {
		func_ctrl.$input.on("change", function () {
			const fn = $(this).val();
			update_fields_for_func(fn);
		});
	}

	// Also attach field change listener to update alias if empty or default
	const field_ctrl = d.get_field("field");
	if (field_ctrl && field_ctrl.$input) {
		field_ctrl.$input.on("change", function () {
			const fval = $(this).val();
			const fn = d.get_value("func") || "sum";
			if (fval) {
				const f_clean = fval === "*" ? "all" : fval.replace(/\./g, "_");
				d.set_value("alias", `${fn.toLowerCase()}_${f_clean}`);
			}
		});
	}
}
// -------------------------------------------------------------
// Order By UI
// -------------------------------------------------------------
function render_order_list(state, $main) {
	const $box = $main.find("#urb-order-container");
	$box.empty();

	if (!state.order_by.length) {
		$box.html('<div class="text-muted text-center" style="font-size: 11px; padding: 6px;">No ordering rules</div>');
		return;
	}

	state.order_by.forEach(function (o, idx) {
		const $chip = $(`
			<div class="badge badge-light mr-1 mb-1 p-1" style="font-size: 11px; border: 1px solid #cbd5e1;">
				${frappe.utils.escape_html(o.field)} <strong>${o.direction}</strong>
				<span class="ml-1 cursor-pointer urb-del-order" data-index="${idx}">&times;</span>
			</div>
		`);
		$chip.find(".urb-del-order").on("click", function () {
			state.order_by.splice(idx, 1);
			refresh_ui(state, $main);
		});
		$box.append($chip);
	});
}

function open_add_order_dialog(state, $main) {
	if (!state.base_doctype) return frappe.msgprint(__("Please select a Base DocType first"));

	const field_options = get_all_queryable_field_options(state);
	const d = new frappe.ui.Dialog({
		title: __("Add Order By"),
		fields: [
			{ fieldname: "field", label: __("Field / Column"), fieldtype: "Select", options: field_options, reqd: 1 },
			{ fieldname: "direction", label: __("Direction"), fieldtype: "Select", options: ["ASC", "DESC"], default: "ASC", reqd: 1 }
		],
		primary_action_label: __("Add Ordering"),
		primary_action: function (values) {
			state.order_by.push(values);
			d.hide();
			refresh_ui(state, $main);
		}
	});
	d.show();
}

// -------------------------------------------------------------
// Calculated Fields UI
// -------------------------------------------------------------
function render_calc_list(state, $main) {
	const $box = $main.find("#urb-calc-container");
	$box.empty();

	if (!state.calculated_fields.length) {
		$box.html('<div class="text-muted text-center" style="font-size: 11px; padding: 6px;">No calculated fields</div>');
		return;
	}

	state.calculated_fields.forEach(function (c, idx) {
		const $chip = $(`
			<div class="badge badge-warning mr-1 mb-1 p-1" style="font-size: 11px;">
				${frappe.utils.escape_html(c.expression)} AS ${frappe.utils.escape_html(c.alias)}
				<span class="ml-1 cursor-pointer urb-del-calc" data-index="${idx}">&times;</span>
			</div>
		`);
		$chip.find(".urb-del-calc").on("click", function () {
			state.calculated_fields.splice(idx, 1);
			refresh_ui(state, $main);
		});
		$box.append($chip);
	});
}

function open_add_calc_dialog(state, $main) {
	if (!state.base_doctype) return frappe.msgprint(__("Please select a Base DocType first"));

	const d = new frappe.ui.Dialog({
		title: __("Add Controlled Calculated Field"),
		fields: [
			{
				fieldname: "expression",
				label: __("Safe Expression (e.g. flight_price * 1.18 or ROUND(flight_price / 10, 2))"),
				fieldtype: "Data",
				reqd: 1
			},
			{
				fieldname: "alias",
				label: __("Alias"),
				fieldtype: "Data",
				default: "price_with_tax",
				reqd: 1
			}
		],
		primary_action_label: __("Add Field"),
		primary_action: function (values) {
			state.calculated_fields.push(values);
			d.hide();
			refresh_ui(state, $main);
		}
	});
	d.show();
}

function get_all_queryable_field_options(state) {
	const options = [];
	(state.available_fields || []).forEach(function (f) {
		if (!f.is_virtual && !['Section Break','Column Break','Tab Break','HTML'].includes(f.fieldtype)) options.push(f.fieldname);
	});
	Object.keys(state.expanded_rel_fields).forEach(function (path) {
		const fields = state.expanded_rel_fields[path] || [];
		fields.forEach(function (f) {
			options.push(`${path}.${f.fieldname}`);
		});
	});
	return options;
}

// -------------------------------------------------------------
// Interactive SVG Relationship Graph
// -------------------------------------------------------------

function highlight_sql(sql) {
	if (!sql) return "";
	let escaped = frappe.utils.escape_html(sql);

	// Multi-line and single line comments
	escaped = escaped.replace(/(--.*$)/gm, '<span class="sql-comment">$1</span>');

	// Strings
	escaped = escaped.replace(/('(?:''|[^'\\]|\\.)*')/g, '<span class="sql-str">$1</span>');

	// Parameters %(param_name)s


	// Backticked identifiers
	escaped = escaped.replace(/(`[^`]+`)/g, '<span class="sql-ident">$1</span>');

	// SQL Keywords
	const keywords = [
		"FULL OUTER JOIN", "FULL JOIN", "LEFT OUTER JOIN", "LEFT JOIN",
		"RIGHT OUTER JOIN", "RIGHT JOIN", "INNER JOIN", "CROSS JOIN", "JOIN",
		"SELECT", "FROM", "ON", "WHERE", "AND", "OR", "NOT",
		"IN", "LIKE", "BETWEEN", "IS", "NULL", "GROUP BY", "HAVING", "ORDER BY",
		"LIMIT", "OFFSET", "AS", "ASC", "DESC", "CASE", "WHEN", "THEN", "ELSE", "END",
		"UNION", "ALL", "DISTINCT"
	];
	const kwRegex = new RegExp(`\\b(${keywords.join("|")})\\b`, "gi");
	escaped = escaped.replace(kwRegex, function(m) {
		return `<span class="sql-kw">${m.toUpperCase()}</span>`;
	});

	// SQL Functions
	const functions = ["COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "CONCAT", "DATE", "YEAR", "MONTH", "NOW", "IFNULL"];
	const fnRegex = new RegExp(`\\b(${functions.join("|")})(?=\\s*\\()`, "gi");
	escaped = escaped.replace(fnRegex, function(m) {
		return `<span class="sql-fn">${m.toUpperCase()}</span>`;
	});

	// Numbers
	escaped = escaped.replace(/\\b(\\d+(?:\\.\\d+)?)\\b/g, '<span class="sql-num">$1</span>');

	return escaped;
}

function render_joins_list(state, $main) {
	const $joins_box = $main.find("#urb-joins-container");
	$joins_box.empty();

	const active_rels = [];
	if (state.base_doctype && state.selected_fields) {
		state.selected_fields.forEach(function (sf) {
			if (sf.path.includes(".")) {
				const rel_prefix = sf.path.split(".").slice(0, -1).join(".");
				if (!active_rels.includes(rel_prefix)) active_rels.push(rel_prefix);
			}
		});
	}

	$main.find("#urb-joins-count").text(active_rels.length);

	if (!active_rels.length) {
		$joins_box.html('<div class="text-muted text-center" style="font-size: 11px; padding: 10px;">Auto-detected joins will appear here</div>');
		return;
	}

	active_rels.forEach(function (r_path) {
		const rel_obj = state.relationships.find(function(r){ return r.path === r_path; });
		const target_dt = rel_obj ? rel_obj.target_doctype : r_path;
		const current_join_type = (state.joins[r_path] || "LEFT JOIN").toUpperCase();

		const $j_item = $(`
			<div style="display: flex; justify-content: space-between; align-items: center; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 10px; margin-bottom: 6px; font-size: 11px;">
				<div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 8px;">
					<strong>${frappe.utils.escape_html(r_path)}</strong> &rarr; <span style="color: #475569;">${frappe.utils.escape_html(target_dt)}</span>
				</div>
				<select class="form-control input-xs urb-join-type-sel" style="width: 135px; height: 26px; font-size: 10.5px; font-weight: 600; color: #1e293b;">
					<option value="LEFT JOIN" ${current_join_type === 'LEFT JOIN' ? 'selected' : ''}>LEFT JOIN</option>
					<option value="RIGHT JOIN" ${current_join_type === 'RIGHT JOIN' ? 'selected' : ''}>RIGHT JOIN</option>
					<option value="INNER JOIN" ${current_join_type === 'INNER JOIN' ? 'selected' : ''}>INNER JOIN</option>
					<option value="FULL OUTER JOIN" ${current_join_type === 'FULL OUTER JOIN' ? 'selected' : ''}>FULL OUTER JOIN</option>
					<option value="CROSS JOIN" ${current_join_type === 'CROSS JOIN' ? 'selected' : ''}>CROSS JOIN</option>
				</select>
			</div>
		`);

		$j_item.find(".urb-join-type-sel").on("change", function () {
			state.joins[r_path] = $(this).val();
			});

		$joins_box.append($j_item);
	});
}

























































































function render_graph(state, $main) {
	const $svg = $main.find("#urb-graph-svg");
	const $empty = $main.find("#urb-graph-empty");

	if (!state.base_doctype) {
		$empty.show();
		$svg.empty().hide();
		return;
	}
	$empty.hide();
	$svg.empty().show();

	// Collect active relationships
	const active_rels = [];
	state.selected_fields.forEach(function (sf) {
		if (sf.path.includes(".")) {
			const rel_prefix = sf.path.split(".").slice(0, -1).join(".");
			if (!active_rels.includes(rel_prefix)) active_rels.push(rel_prefix);
		}
	});

	let svg_nodes = "";
	let svg_edges = "";

	// Base Node
	const base_x = 40;
	const base_y = 60;
	const node_w = 170;
	const node_h = 75;

	svg_nodes += `
		<g transform="translate(${base_x}, ${base_y})">
			<rect width="${node_w}" height="${node_h}" rx="8" fill="#ffffff" stroke="#2563eb" stroke-width="2" filter="drop-shadow(0 2px 4px rgba(0,0,0,0.08))"/>
			<rect width="${node_w}" height="26" rx="8" fill="#2563eb"/>
			<text x="10" y="17" fill="#ffffff" font-size="12" font-weight="bold">${frappe.utils.escape_html(state.base_doctype)}</text>
			<text x="10" y="44" fill="#64748b" font-size="10">BASE DOCTYPE</text>
			<text x="10" y="60" fill="#059669" font-size="11" font-weight="600">${state.selected_fields.filter(function(s){return !s.path.includes(".");}).length} Selected Fields</text>
		</g>
	`;

	// Joined Nodes
	active_rels.forEach(function (r_path, i) {
		const node_x = base_x + 280;
		const node_y = 20 + (i * 95);
		const rel_obj = state.relationships.find(function(r){ return r.path === r_path; });
		const target_dt = rel_obj ? rel_obj.target_doctype : r_path;
		const is_child = rel_obj && rel_obj.rel_type === "child_table";
		const header_color = is_child ? "#d97706" : "#7c3aed";

		const rel_fields_count = state.selected_fields.filter(function(s){ return s.path.startsWith(r_path + "."); }).length;

		// Edge
		const from_x = base_x + node_w;
		const from_y = base_y + 35;
		const to_x = node_x;
		const to_y = node_y + 35;

		svg_edges += `
			<path d="M ${from_x} ${from_y} C ${from_x + 60} ${from_y}, ${to_x - 60} ${to_y}, ${to_x} ${to_y}" fill="none" stroke="#94a3b8" stroke-width="2" marker-end="url(#arrow)"/>
			<rect x="${(from_x + to_x)/2 - 40}" y="${(from_y + to_y)/2 - 10}" width="80" height="18" rx="4" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1"/>
			<text x="${(from_x + to_x)/2}" y="${(from_y + to_y)/2 + 2}" fill="#475569" font-size="10" text-anchor="middle">${frappe.utils.escape_html(r_path)}</text>
		`;

		// Node
		svg_nodes += `
			<g transform="translate(${node_x}, ${node_y})">
				<rect width="${node_w}" height="${node_h}" rx="8" fill="#ffffff" stroke="${header_color}" stroke-width="2" filter="drop-shadow(0 2px 4px rgba(0,0,0,0.08))"/>
				<rect width="${node_w}" height="26" rx="8" fill="${header_color}"/>
				<text x="10" y="17" fill="#ffffff" font-size="12" font-weight="bold">${frappe.utils.escape_html(target_dt)}</text>
				<text x="10" y="44" fill="#64748b" font-size="10">${is_child ? 'CHILD TABLE' : 'LINKED DOCTYPE'}</text>
				<text x="10" y="60" fill="#059669" font-size="11" font-weight="600">${rel_fields_count} Selected Fields</text>
			</g>
		`;
	});

	const full_svg = `
		<defs>
			<marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
				<path d="M 0 1 L 10 5 L 0 9 z" fill="#94a3b8"/>
			</marker>
		</defs>
		${svg_edges}
		${svg_nodes}
	`;

	$svg.html(full_svg);

}


function trigger_generate_sql(state, $main, user_initiated) {
	if (!state.base_doctype) {
		if (user_initiated) frappe.show_alert({ message: __("Please select a Base DocType first"), indicator: "orange" });
		clear_sql_display($main);
		return;
	}

	if (!state.selected_fields.length && !state.aggregations.length && !state.calculated_fields.length) {
		clear_sql_display($main);
		return;
	}

	const joins_list = Object.keys(state.joins).map(function (p) {
		return { path: p, join_type: state.joins[p] };
	});

	const spec = {
		base_doctype: state.base_doctype,
		fields: state.selected_fields.map(function (sf) {
			return { path: sf.path, fieldname: sf.fieldname, alias: sf.alias };
		}),
		joins: joins_list,
		filters: state.filters.length ? { operator: state.filter_operator, conditions: state.filters } : {},
		group_by: state.group_by,
		aggregations: state.aggregations,
		order_by: state.order_by,
		calculated_fields: state.calculated_fields
	};

	frappe.call({
		method: "nocodereport.api.query_api.generate_sql",
		args: { spec: spec },
		callback: function (r) {
			if (r && r.message && r.message.success) {
				state.sql = r.message.sql;
				state.explanation = r.message.explanation || "";


				$main.find("#urb-sql-output code").html(highlight_sql(state.sql));

				$main.find("#urb-query-explanation").html(
					`<div class="urb-explanation-text">${frappe.utils.escape_html(state.explanation).replace(/\n/g, '<br>')}</div>`
				);

				if (user_initiated) {
					frappe.show_alert({ message: __("SQL generated successfully"), indicator: "green" });
				}
			} else {
				const err = (r && r.message && r.message.error) ? r.message.error : __("Failed to generate SQL");
				show_alert($main, err);
			}
		},
		error: function (err) {
			show_alert($main, err.message || __("Error generating SQL"));
		}
	});
}

function clear_sql_display($main) {
	$main.find("#urb-sql-output code").html('<span class="sql-comment">-- Select fields or aggregations to generate SQL</span>');

	$main.find("#urb-query-explanation").html(
		'<div class="text-muted">A structured breakdown of the query construction will appear here.</div>'
	);
}

function reset_state(state, $main) {
	state.base_doctype = null;
	state.metadata = null;
	state.available_fields = [];
	state.selected_fields = [];
	state.relationships = [];
	state.expanded_rel_fields = {};
	state.filters = [];
	state.joins = {};
	state.group_by = [];
	state.aggregations = [];
	state.order_by = [];
	state.calculated_fields = [];
	state.sql = "";

	state.explanation = "";

	$main.find("#urb-doctype-input").val("");
	$main.find("#urb-doctype-status").empty();
	$main.find("#urb-perm-badge").addClass("hidden");
	$main.find("#urb-field-search").val("");
	$main.find("#urb-rel-count").text("0");
	$main.find("#urb-joins-count").text("0");
	hide_alert($main);

	refresh_ui(state, $main);
	clear_sql_display($main);

	frappe.show_alert({ message: __("Builder reset"), indicator: "blue" });
}

function show_alert($main, msg) {
	$main.find("#urb-alert-message").text(msg);
	$main.find("#urb-alert-box").removeClass("hidden");
}

function hide_alert($main) {
	$main.find("#urb-alert-box").addClass("hidden");
}

function copy_to_clipboard(text, success_msg) {
	if (navigator.clipboard && window.isSecureContext) {
		navigator.clipboard.writeText(text).then(function () {
			frappe.show_alert({ message: success_msg, indicator: "green" });
		}).catch(function () {
			fallback_copy(text, success_msg);
		});
	} else {
		fallback_copy(text, success_msg);
	}
}

function fallback_copy(text, success_msg) {
	const $temp = $("<textarea>");
	$("body").append($temp);
	$temp.val(text).select();
	document.execCommand("copy");
	$temp.remove();
	frappe.show_alert({ message: success_msg, indicator: "green" });
}

function get_fallback_html() {
	return `
		<div class="urb-container">
			<div class="alert alert-info">Loading Universal Report Builder...</div>
		</div>
	`;
}
