import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields, default_fields


class FieldValidationError(frappe.ValidationError):
	pass


# Common standard database columns present on every DocType table
STANDARD_COLUMNS = {
	"name": {"fieldname": "name", "label": "ID / Name", "fieldtype": "Data"},
	"creation": {"fieldname": "creation", "label": "Created At", "fieldtype": "Datetime"},
	"modified": {"fieldname": "modified", "label": "Last Modified", "fieldtype": "Datetime"},
	"modified_by": {"fieldname": "modified_by", "label": "Last Modified By", "fieldtype": "Link", "options": "User"},
	"owner": {"fieldname": "owner", "label": "Owner", "fieldtype": "Link", "options": "User"},
	"docstatus": {"fieldname": "docstatus", "label": "Document Status", "fieldtype": "Int"},
	"idx": {"fieldname": "idx", "label": "Index", "fieldtype": "Int"},
}

CHILD_STANDARD_COLUMNS = {
	**STANDARD_COLUMNS,
	"parent": {"fieldname": "parent", "label": "Parent Document", "fieldtype": "Data"},
	"parenttype": {"fieldname": "parenttype", "label": "Parent DocType", "fieldtype": "Data"},
	"parentfield": {"fieldname": "parentfield", "label": "Parent Fieldname", "fieldtype": "Data"},
}


def get_doctype_fields_dict(doctype: str) -> dict[str, dict]:
	"""
	Returns a dictionary of all database fields for the DocType keyed by fieldname.
	"""
	meta = frappe.get_meta(doctype)
	is_child = bool(meta.istable)
	fields_dict = dict(CHILD_STANDARD_COLUMNS if is_child else STANDARD_COLUMNS)

	for df in meta.fields:
		is_virtual = bool(getattr(df, "is_virtual", 0))
		is_no_value = df.fieldtype in no_value_fields and df.fieldtype not in table_fields

		fields_dict[df.fieldname] = {
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"fieldtype": df.fieldtype,
			"options": df.options,
			"reqd": bool(df.reqd),
			"hidden": bool(df.hidden),
			"read_only": bool(df.read_only),
			"is_virtual": is_virtual,
			"is_no_value": is_no_value,
			"is_table": df.fieldtype in table_fields,
			"is_link": df.fieldtype == "Link",
			"is_dynamic_link": df.fieldtype == "Dynamic Link",
		}

	return fields_dict


def validate_queryable_field(doctype: str, fieldname: str) -> dict:
	"""
	Validates that a field exists on the DocType and can be safely included in SQL SELECT.
	Raises FieldValidationError if invalid or virtual.
	"""
	if not fieldname or not isinstance(fieldname, str):
		frappe.throw(_("Invalid fieldname specified"), exc=FieldValidationError)

	fields_dict = get_doctype_fields_dict(doctype)

	if fieldname not in fields_dict:
		frappe.throw(
			_("Field '{0}' not found on DocType '{1}'").format(fieldname, doctype),
			exc=FieldValidationError
		)

	f_info = fields_dict[fieldname]

	if f_info.get("is_virtual"):
		frappe.throw(
			_("Virtual / non-database field '{0}' cannot be used directly in SQL.").format(fieldname),
			exc=FieldValidationError
		)

	if f_info.get("is_no_value") and not f_info.get("is_table"):
		frappe.throw(
			_("Field '{0}' is of type '{1}' and is not physically stored in the database.").format(
				fieldname, f_info.get("fieldtype")
			),
			exc=FieldValidationError
		)

	return f_info
