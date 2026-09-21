import re
import frappe
from frappe import _
from nocodereport.utils.helpers import sanitize_alias

ALLOWED_AGG_FUNCTIONS = {"SUM", "COUNT", "AVG", "MIN", "MAX"}


class AggregationValidationError(frappe.ValidationError):
	pass


class AggregationBuilder:
	"""
	Validates and builds SQL aggregation clauses (SUM, COUNT, AVG, MIN, MAX).
	"""

	def __init__(self, table_instances: dict, base_table_key: str = ""):
		self.table_instances = table_instances
		self.base_table_key = base_table_key

	def build_aggregation(self, agg_spec: dict) -> tuple[str, str]:
		"""
		Takes an aggregation specification dict:
		{
			"func": "SUM",
			"field": "flight_price",
			"alias": "total_spent"
		}
		Returns (select_expression_sql, alias).
		"""
		func = agg_spec.get("func", "COUNT").strip().upper()
		if func not in ALLOWED_AGG_FUNCTIONS:
			frappe.throw(_("Aggregation function '{0}' is not allowed").format(func), exc=AggregationValidationError)

		field_path = agg_spec.get("field") or agg_spec.get("path")
		raw_alias = agg_spec.get("alias")

		if field_path == "*" or not field_path:
			if func != "COUNT":
				frappe.throw(_("Wildcard '*' is only valid with COUNT function"), exc=AggregationValidationError)
			alias = sanitize_alias(raw_alias, "total_count")
			return "COUNT(*)", alias

		# Resolve table and column
		parts = field_path.split(".")
		if len(parts) == 1:
			table = self.table_instances.get(self.base_table_key)
			col_name = parts[0]
		else:
			table_key = ".".join(parts[:-1])
			table = self.table_instances.get(table_key)
			col_name = parts[-1]

		if not table:
			frappe.throw(_("Table reference for field '{0}' not found").format(field_path), exc=AggregationValidationError)

		table_ref = table.get_table_name()
		if not re.match(r"^[A-Za-z0-9_]+$", col_name):
			frappe.throw(_("Invalid column in aggregation: {0}").format(col_name), exc=AggregationValidationError)

		col_sql = f"`{table_ref}`.`{col_name}`"
		default_alias = f"{func.lower()}_{col_name}"
		alias = sanitize_alias(raw_alias, default_alias)

		expr = f"{func}({col_sql})"
		return expr, alias
