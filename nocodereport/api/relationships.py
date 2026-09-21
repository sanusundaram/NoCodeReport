import frappe
from frappe import _
from nocodereport.security.permission_validator import check_doctype_read_permission
from nocodereport.security.field_validator import get_doctype_fields_dict


MAX_EXPLORATION_DEPTH = 3


@frappe.whitelist()
def get_doctype_relationships(doctype: str, current_path: str = "", visited: str | list | None = None) -> dict:
	"""
	Returns all outbound Link and Child Table relationships for a DocType.
	Recursively checks read permissions for each target DocType.
	If permission is denied, marks the node as restricted without exposing internal fields.
	"""
	if not doctype or not isinstance(doctype, str):
		return {"error": _("Invalid DocType")}

	doctype = doctype.strip()
	has_perm, err = check_doctype_read_permission(doctype)
	if not has_perm:
		return {
			"doctype": doctype,
			"has_permission": False,
			"error": err or _("Access Denied: You do not have permission to read this DocType.")
		}

	if isinstance(visited, str):
		try:
			import json
			visited = json.loads(visited)
		except Exception:
			visited = [doctype]
	elif visited is None:
		visited = [doctype]

	meta = frappe.get_meta(doctype)
	fields_dict = get_doctype_fields_dict(doctype)

	links = []
	tables = []

	for fname, f in fields_dict.items():
		if f.get("is_link") and f.get("options"):
			target = f["options"]
			# Check permission on target doctype
			target_has_perm, target_err = check_doctype_read_permission(target)
			rel_path = f"{current_path}.{fname}" if current_path else fname
			is_cycle = target in visited

			link_info = {
				"fieldname": fname,
				"label": f.get("label") or fname,
				"target_doctype": target,
				"path": rel_path,
				"has_permission": target_has_perm,
				"is_cycle": is_cycle,
				"rel_type": "link"
			}
			if not target_has_perm:
				link_info["restriction_message"] = _("Access to this DocType is not available for your current user.")
			links.append(link_info)

		elif f.get("is_table") and f.get("options"):
			target = f["options"]
			target_has_perm, target_err = check_doctype_read_permission(target)
			rel_path = f"{current_path}.{fname}" if current_path else fname
			is_cycle = target in visited

			table_info = {
				"fieldname": fname,
				"label": f.get("label") or fname,
				"target_doctype": target,
				"path": rel_path,
				"has_permission": target_has_perm,
				"is_cycle": is_cycle,
				"rel_type": "child_table"
			}
			if not target_has_perm:
				table_info["restriction_message"] = _("Access to this DocType is not available for your current user.")
			tables.append(table_info)

	return {
		"doctype": doctype,
		"has_permission": True,
		"path": current_path,
		"links": links,
		"tables": tables
	}


@frappe.whitelist()
def get_relationship_fields(base_doctype: str, rel_path: str) -> dict:
	"""
	Returns the fields of a linked or child DocType reached via `rel_path` (e.g. 'passenger' or 'flight.airplane').
	Validates permissions at every step.
	"""
	parts = rel_path.split(".")
	current_doctype = base_doctype
	visited = [base_doctype]

	for step in parts:
		meta = frappe.get_meta(current_doctype)
		df = meta.get_field(step)
		if not df or df.fieldtype not in ("Link", "Table", "Table MultiSelect"):
			return {"success": False, "error": _("Invalid relationship path: {0}").format(rel_path)}

		target = df.options
		has_perm, err = check_doctype_read_permission(target)
		if not has_perm:
			return {
				"success": False,
				"error": _("Access Denied: You do not have permission for {0}.").format(target),
				"restricted": True
			}
		if target in visited:
			return {"success": False, "error": _("Cyclical relationship detected at {0}").format(target)}
		visited.append(target)
		current_doctype = target

	# Return target doctype fields
	fields_dict = get_doctype_fields_dict(current_doctype)
	fields_list = [f for f in fields_dict.values() if not f.get("is_no_value") or f.get("is_table")]
	fields_list.sort(key=lambda x: (x.get("label") or x["fieldname"]).lower())

	return {
		"success": True,
		"doctype": current_doctype,
		"path": rel_path,
		"fields": fields_list
	}
