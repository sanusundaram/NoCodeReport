import frappe
from frappe import _


class PermissionValidationError(frappe.PermissionError):
	pass


def validate_doctype_read_permission(doctype: str, user: str | None = None) -> bool:
	"""
	Validates that the specified DocType exists and that the user has read permission.
	Raises PermissionValidationError if the user does not have permission.
	"""
	if not doctype or not isinstance(doctype, str):
		frappe.throw(_("Invalid DocType specified"), exc=PermissionValidationError)

	doctype = doctype.strip()

	if not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType '{0}' does not exist").format(doctype), exc=frappe.DoesNotExistError)

	user = user or frappe.session.user

	# System Manager or Administrator can read everything
	# Use Frappe's actual effective permission model
	has_read = frappe.has_permission(doctype, ptype="read", user=user)

	if not has_read:
		frappe.throw(
			_("Access Denied: You do not have read permission for {0}.").format(doctype),
			exc=PermissionValidationError
		)

	return True


def check_doctype_read_permission(doctype: str, user: str | None = None) -> tuple[bool, str | None]:
	"""
	Non-throwing permission check. Returns (has_permission, error_message).
	"""
	try:
		validate_doctype_read_permission(doctype, user)
		return True, None
	except Exception as e:
		return False, str(e)
