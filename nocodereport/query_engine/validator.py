import frappe
from frappe import _
from nocodereport.security.permission_validator import validate_doctype_read_permission
from nocodereport.security.field_validator import validate_queryable_field


class QueryValidationError(frappe.ValidationError):
	pass


def validate_query_spec(spec: dict) -> dict:
	"""
	Validates the internal JSON query specification structure.
	"""
	if not isinstance(spec, dict):
		frappe.throw(_("Invalid query specification format: expected JSON object"), exc=QueryValidationError)

	base_doctype = spec.get("base_doctype")
	if not base_doctype or not isinstance(base_doctype, str):
		frappe.throw(_("Missing or invalid 'base_doctype' in query specification"), exc=QueryValidationError)

	# Validate base doctype read permission
	validate_doctype_read_permission(base_doctype)

	fields = spec.get("fields", [])
	aggregations = spec.get("aggregations", [])
	calculated_fields = spec.get("calculated_fields", [])

	if not isinstance(fields, list):
		frappe.throw(_("'fields' must be a list"), exc=QueryValidationError)

	if not fields and not aggregations and not calculated_fields:
		frappe.throw(_("At least one field or aggregation must be selected to generate a query"), exc=QueryValidationError)

	# Validate each field
	for idx, f in enumerate(fields):
		if isinstance(f, str):
			fieldname = f
		elif isinstance(f, dict):
			fieldname = f.get("path") or f.get("fieldname")
		else:
			frappe.throw(_("Field entry at index {0} is invalid").format(idx), exc=QueryValidationError)

		if not fieldname or not isinstance(fieldname, str):
			frappe.throw(_("Field entry at index {0} has an invalid name").format(idx), exc=QueryValidationError)

		# If simple field (no dot), validate on base_doctype
		if "." not in fieldname:
			validate_queryable_field(base_doctype, fieldname)

	return spec
