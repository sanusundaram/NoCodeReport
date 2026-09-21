import re
import frappe
from frappe import _


ALLOWED_OPERATORS = {
	"=": "eq",
	"!=": "ne",
	"<>": "ne",
	">": "gt",
	"<": "lt",
	">=": "gte",
	"<=": "lte",
	"LIKE": "like",
	"NOT LIKE": "not_like",
	"IN": "in",
	"NOT IN": "not_in",
	"BETWEEN": "between",
	"IS NULL": "is_null",
	"IS NOT NULL": "is_not_null",
}


class FilterValidationError(frappe.ValidationError):
	pass


class FilterBuilder:
	"""
	Validates and compiles an AST filter tree into parameterized SQL WHERE clauses.
	Maintains a parameter dictionary to prevent SQL injection.
	"""

	def __init__(self, table_instances: dict, base_table_key: str = ""):
		self.table_instances = table_instances
		self.base_table_key = base_table_key
		self.params = {}
		self.param_counter = 0

	def _next_param_key(self, fieldname: str) -> str:
		self.param_counter += 1
		clean_name = re.sub(r"[^A-Za-z0-9_]", "_", fieldname)
		return f"p_{clean_name}_{self.param_counter}"

	def build(self, filter_spec: dict | list) -> tuple[str, dict]:
		"""
		Takes an AST filter specification and returns (where_clause_sql, params_dict).
		"""
		if not filter_spec:
			return "", {}

		if isinstance(filter_spec, list):
			filter_spec = {"operator": "AND", "conditions": filter_spec}

		clause = self._process_group(filter_spec)
		return clause, self.params

	def _process_group(self, group: dict) -> str:
		operator = group.get("operator", "AND").upper()
		if operator not in ("AND", "OR"):
			frappe.throw(_("Invalid logical operator '{0}'. Allowed: AND, OR").format(operator), exc=FilterValidationError)

		conditions = group.get("conditions", [])
		if not conditions:
			return ""

		compiled_parts = []
		for item in conditions:
			if "conditions" in item or ("operator" in item and item.get("operator") in ("AND", "OR")):
				sub_sql = self._process_group(item)
				if sub_sql:
					compiled_parts.append(f"({sub_sql})")
			else:
				cond_sql = self._process_condition(item)
				if cond_sql:
					compiled_parts.append(cond_sql)

		if not compiled_parts:
			return ""

		joiner = f" {operator} "
		return joiner.join(compiled_parts)

	def _process_condition(self, cond: dict) -> str:
		field_path = cond.get("field") or cond.get("path") or cond.get("fieldname")
		if not field_path or not isinstance(field_path, str):
			return ""

		op = cond.get("operator", "=").strip().upper()
		if op not in ALLOWED_OPERATORS:
			frappe.throw(_("Filter operator '{0}' is not permitted").format(op), exc=FilterValidationError)

		val = cond.get("value")

		# Resolve table and column reference
		parts = field_path.split(".")
		if len(parts) == 1:
			table = self.table_instances.get(self.base_table_key)
			col_name = parts[0]
		else:
			table_key = ".".join(parts[:-1])
			table = self.table_instances.get(table_key)
			col_name = parts[-1]

		if not table:
			frappe.throw(_("Table reference for filter field '{0}' not found").format(field_path), exc=FilterValidationError)

		table_ref = table.get_table_name()
		if not re.match(r"^[A-Za-z0-9_]+$", col_name):
			frappe.throw(_("Invalid column name in filter: {0}").format(col_name), exc=FilterValidationError)

		col_sql = f"`{table_ref}`.`{col_name}`"

		# Render condition based on operator
		if op == "IS NULL":
			return f"{col_sql} IS NULL"
		if op == "IS NOT NULL":
			return f"{col_sql} IS NOT NULL"

		if op in ("IN", "NOT IN"):
			if not isinstance(val, (list, tuple)):
				val = [v.strip() for v in str(val).split(",") if v.strip()]
			if not val:
				return "1=1" if op == "IN" else "1=0"

			placeholders = []
			for v in val:
				pk = self._next_param_key(col_name)
				self.params[pk] = v
				placeholders.append(f"%({pk})s")
			return f"{col_sql} {op} ({', '.join(placeholders)})"

		if op == "BETWEEN":
			if isinstance(val, (list, tuple)) and len(val) >= 2:
				val1, val2 = val[0], val[1]
			else:
				vals = str(val).split("AND")
				val1 = vals[0].strip() if len(vals) > 0 else ""
				val2 = vals[1].strip() if len(vals) > 1 else ""

			pk1 = self._next_param_key(f"{col_name}_start")
			pk2 = self._next_param_key(f"{col_name}_end")
			self.params[pk1] = val1
			self.params[pk2] = val2
			return f"{col_sql} BETWEEN %({pk1})s AND %({pk2})s"

		# Standard binary comparison
		pk = self._next_param_key(col_name)
		self.params[pk] = val
		return f"{col_sql} {op} %({pk})s"
