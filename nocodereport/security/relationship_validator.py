import frappe
from frappe import _
from nocodereport.security.permission_validator import validate_doctype_read_permission


class RelationshipValidationError(frappe.ValidationError):
	pass


MAX_RELATIONSHIP_DEPTH = 3


def validate_relationship_path(
	base_doctype: str,
	path_elements: list[str],
	visited: set[str] | None = None
) -> list[dict]:
	"""
	Validates a chain of relationships (e.g. ['customer', 'territory']).
	Ensures every link or child table exists, user has permission to read the target DocType,
	depth does not exceed MAX_RELATIONSHIP_DEPTH, and no cyclical dependencies occur.
	
	Returns a list of resolved relationship step dicts.
	"""
	if visited is None:
		visited = {base_doctype}

	if len(path_elements) > MAX_RELATIONSHIP_DEPTH:
		frappe.throw(
			_("Relationship depth exceeds maximum allowed limit of {0}").format(MAX_RELATIONSHIP_DEPTH),
			exc=RelationshipValidationError
		)

	current_doctype = base_doctype
	resolved_steps = []

	for fieldname in path_elements:
		meta = frappe.get_meta(current_doctype)
		df = meta.get_field(fieldname)

		if not df:
			frappe.throw(
				_("Field '{0}' not found on DocType '{1}'").format(fieldname, current_doctype),
				exc=RelationshipValidationError
			)

		if df.fieldtype == "Link":
			target_doctype = df.options
			rel_type = "link"
		elif df.fieldtype in ("Table", "Table MultiSelect"):
			target_doctype = df.options
			rel_type = "child_table"
		else:
			frappe.throw(
				_("Field '{0}' on DocType '{1}' is not a Link or Child Table relationship").format(
					fieldname, current_doctype
				),
				exc=RelationshipValidationError
			)

		if not target_doctype or not frappe.db.exists("DocType", target_doctype):
			frappe.throw(
				_("Target DocType '{0}' for field '{1}' does not exist").format(target_doctype, fieldname),
				exc=RelationshipValidationError
			)

		# Cycle detection
		if target_doctype in visited:
			frappe.throw(
				_("Cyclical relationship detected: '{0}' has already been traversed.").format(target_doctype),
				exc=RelationshipValidationError
			)

		# Permission validation on linked/child doctype
		validate_doctype_read_permission(target_doctype)

		visited.add(target_doctype)
		resolved_steps.append({
			"parent_doctype": current_doctype,
			"fieldname": fieldname,
			"target_doctype": target_doctype,
			"rel_type": rel_type
		})
		current_doctype = target_doctype

	return resolved_steps
