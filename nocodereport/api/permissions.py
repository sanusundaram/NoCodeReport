import frappe
from nocodereport.security.permission_validator import check_doctype_read_permission


@frappe.whitelist()
def check_permission(doctype: str) -> dict:
	"""
	Whitelisted API to check if the current user has read permission on a DocType.
	"""
	has_perm, err = check_doctype_read_permission(doctype)
	return {
		"doctype": doctype,
		"has_permission": has_perm,
		"error": err
	}
