import re
import frappe
from frappe import _


class OrderValidationError(frappe.ValidationError):
	pass


class OrderBuilder:
	"""
	Validates and builds ORDER BY clauses.
	"""

	def __init__(self, table_instances: dict, base_table_key: str = ""):
		self.table_instances = table_instances
		self.base_table_key = base_table_key

	def build_order_expr(self, order_spec: dict | str) -> str:
		"""
		Takes an order item, e.g. {"field": "grand_total", "direction": "DESC"} or "grand_total DESC"
		"""
		if isinstance(order_spec, str):
			parts = order_spec.strip().split()
			field_path = parts[0]
			direction = parts[1].upper() if len(parts) > 1 else "ASC"
		elif isinstance(order_spec, dict):
			field_path = order_spec.get("field") or order_spec.get("path")
			direction = str(order_spec.get("direction", "ASC")).strip().upper()
		else:
			return ""

		if direction not in ("ASC", "DESC"):
			direction = "ASC"

		if not field_path:
			return ""

		parts = field_path.split(".")
		if len(parts) == 1:
			col_name = parts[0]
			if not re.match(r"^[A-Za-z0-9_]+$", col_name):
				frappe.throw(_("Invalid order by column: {0}").format(col_name), exc=OrderValidationError)

			# If it's a simple alias or column name, return without prepending wrong table if alias
			base_table = self.table_instances.get(self.base_table_key)
			table_ref = base_table.get_table_name()
			col_sql = f"`{col_name}`"
		else:
			table_key = ".".join(parts[:-1])
			table = self.table_instances.get(table_key)
			col_name = parts[-1]
			if not table or not re.match(r"^[A-Za-z0-9_]+$", col_name):
				frappe.throw(_("Invalid order by field: {0}").format(field_path), exc=OrderValidationError)
			table_ref = table.get_table_name()
			col_sql = f"`{table_ref}`.`{col_name}`"

		return f"{col_sql} {direction}"
