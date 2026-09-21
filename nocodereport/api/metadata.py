import frappe
from frappe import _
from nocodereport.security.permission_validator import validate_doctype_read_permission
from nocodereport.security.field_validator import get_doctype_fields_dict, STANDARD_COLUMNS, CHILD_STANDARD_COLUMNS


@frappe.whitelist()
def get_permitted_doctypes(search_term: str | None = None) -> list[dict]:
	"""
	Returns a list of all non-single, non-table DocTypes that the current user has read permission for.
	"""
	user = frappe.session.user

	filters = {
		"issingle": 0,
		"istable": 0,
	}

	if search_term and search_term.strip():
		filters["name"] = ["like", f"%{search_term.strip()}%"]

	doctypes = frappe.get_all(
		"DocType",
		filters=filters,
		fields=["name", "module", "description", "custom"],
		order_by="name asc",
		limit_page_length=200
	)

	permitted = []
	for dt in doctypes:
		if frappe.has_permission(dt.name, ptype="read", user=user):
			permitted.append({
				"name": dt.name,
				"module": dt.module,
				"description": dt.description or "",
				"custom": dt.custom
			})

	return permitted


@frappe.whitelist()
def get_doctype_metadata(doctype: str) -> dict:
	"""
	Validates user read permission and returns dynamic metadata for the DocType.
	Includes queryable fields, link fields, and child tables.
	"""
	validate_doctype_read_permission(doctype)

	meta = frappe.get_meta(doctype)
	fields_dict = get_doctype_fields_dict(doctype)

	fields_list = []
	link_fields = []
	table_fields = []
	dynamic_link_fields = []

	for fname, finfo in fields_dict.items():
		fields_list.append(finfo)
		if finfo.get("is_link") and finfo.get("options"):
			link_fields.append({
				"fieldname": finfo["fieldname"],
				"label": finfo["label"],
				"target_doctype": finfo["options"]
			})
		elif finfo.get("is_table") and finfo.get("options"):
			table_fields.append({
				"fieldname": finfo["fieldname"],
				"label": finfo["label"],
				"target_doctype": finfo["options"]
			})
		elif finfo.get("is_dynamic_link"):
			dynamic_link_fields.append({
				"fieldname": finfo["fieldname"],
				"label": finfo["label"],
				"options": finfo["options"]
			})

	# Sort fields alphabetically by label/name
	fields_list.sort(key=lambda x: (x["label"] or x["fieldname"]).lower())

	return {
		"doctype": doctype,
		"module": meta.module,
		"is_submittable": bool(meta.is_submittable),
		"istable": bool(meta.istable),
		"fields": fields_list,
		"link_fields": link_fields,
		"table_fields": table_fields,
		"dynamic_link_fields": dynamic_link_fields,
		"standard_columns": list(CHILD_STANDARD_COLUMNS.keys() if meta.istable else STANDARD_COLUMNS.keys())
	}
