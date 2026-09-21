import re
import frappe
from frappe import _


ALLOWED_DATE_INTERVALS = {"YEAR", "MONTH", "QUARTER", "DAY"}


class GroupValidationError(frappe.ValidationError):
	pass


class GroupBuilder:
	"""
	Validates and builds GROUP BY clauses, including date grouping (Year, Month, Quarter, Day).
	"""

	def __init__(self, table_instances: dict, base_table_key: str = ""):
		self.table_instances = table_instances
		self.base_table_key = base_table_key

	def build_group_expr(self, group_spec: str | dict) -> str:
		"""
		Takes a group item, e.g. "customer" or {"field": "transaction_date", "interval": "MONTH"}
		Returns the SQL group expression.
		"""
		if isinstance(group_spec, str):
			field_path = group_spec
			interval = None
		elif isinstance(group_spec, dict):
			field_path = group_spec.get("field") or group_spec.get("path")
			interval = group_spec.get("interval")
		else:
			return ""

		if not field_path:
			return ""

		parts = field_path.split(".")
		if len(parts) == 1:
			table = self.table_instances.get(self.base_table_key)
			col_name = parts[0]
		else:
			table_key = ".".join(parts[:-1])
			table = self.table_instances.get(table_key)
			col_name = parts[-1]

		if not table:
			frappe.throw(_("Table reference for grouping field '{0}' not found").format(field_path), exc=GroupValidationError)

		table_ref = table.get_table_name()
		if not re.match(r"^[A-Za-z0-9_]+$", col_name):
			frappe.throw(_("Invalid column in group by: {0}").format(col_name), exc=GroupValidationError)

		col_sql = f"`{table_ref}`.`{col_name}`"

		if interval:
			interval = interval.strip().upper()
			if interval not in ALLOWED_DATE_INTERVALS:
				frappe.throw(_("Date interval '{0}' is not supported").format(interval), exc=GroupValidationError)
			return f"EXTRACT({interval} FROM {col_sql})"

		return col_sql
