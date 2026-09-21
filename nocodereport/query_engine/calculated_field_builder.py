import re
import frappe
from frappe import _
from nocodereport.utils.helpers import sanitize_alias

ALLOWED_FUNCTIONS = {"ROUND", "COALESCE", "CONCAT", "IF", "DATEDIFF", "DATE_DIFF", "ABS", "CEIL", "FLOOR"}
DISALLOWED_KEYWORDS = {
	"DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
	"UNION", "SELECT", "EXEC", "EXECUTE", "BENCHMARK", "SLEEP",
	"SCHEMA", "DATABASE", "INFORMATION_SCHEMA", "INTO", "OUTFILE", "DUMPFILE"
}


class CalculatedFieldValidationError(frappe.ValidationError):
	pass


class CalculatedFieldBuilder:
	"""
	Validates and renders safe calculated field expressions without arbitrary code execution.
	Replaces field references with qualified table columns and whitelists approved SQL functions.
	"""

	def __init__(self, table_instances: dict, base_table_key: str = ""):
		self.table_instances = table_instances
		self.base_table_key = base_table_key

	def build(self, calc_spec: dict) -> tuple[str, str]:
		"""
		Takes a calculated field specification:
		{
			"expression": "flight_price * 1.18",
			"alias": "price_with_tax"
		}
		Returns (sql_expression, alias).
		"""
		expr = calc_spec.get("expression", "").strip()
		raw_alias = calc_spec.get("alias")
		if not expr:
			frappe.throw(_("Calculated field expression cannot be empty"), exc=CalculatedFieldValidationError)

		upper_expr = expr.upper()
		if ";" in expr or "--" in expr or "/*" in expr or "*/" in expr:
			frappe.throw(_("Disallowed characters in calculated field expression"), exc=CalculatedFieldValidationError)

		for kw in DISALLOWED_KEYWORDS:
			if re.search(rf"\b{kw}\b", upper_expr):
				frappe.throw(_("Disallowed SQL keyword '{0}' in calculated field expression").format(kw), exc=CalculatedFieldValidationError)

		token_pattern = re.compile(
			r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)"  # Identifiers / fields
			r"|(\d+(?:\.\d+)?)"                                          # Numbers
			r"|('(?:[^'\\]|\\.)*')"                                       # Single-quoted string
			r"|([+\-*/(),=><!]+)"                                        # Operators and parens
			r"|(\s+)"                                                    # Whitespace
		)

		pos = 0
		rendered_tokens = []
		while pos < len(expr):
			m = token_pattern.match(expr, pos)
			if not m:
				char = expr[pos]
				frappe.throw(_("Unsupported character '{0}' in calculated field expression").format(char), exc=CalculatedFieldValidationError)

			ident, num, string_lit, op, ws = m.groups()
			pos = m.end()

			if ws:
				rendered_tokens.append(ws)
			elif num:
				rendered_tokens.append(num)
			elif string_lit:
				rendered_tokens.append(string_lit)
			elif op:
				rendered_tokens.append(op)
			elif ident:
				upper_ident = ident.upper()
				if upper_ident in ALLOWED_FUNCTIONS:
					rendered_tokens.append(upper_ident)
				else:
					parts = ident.split(".")
					if len(parts) == 1:
						table = self.table_instances.get(self.base_table_key)
						col_name = parts[0]
					else:
						table_key = ".".join(parts[:-1])
						table = self.table_instances.get(table_key)
						col_name = parts[-1]

					if not table:
						frappe.throw(_("Field '{0}' in expression not found").format(ident), exc=CalculatedFieldValidationError)

					table_ref = table.get_table_name()
					rendered_tokens.append(f"`{table_ref}`.`{col_name}`")

		alias = sanitize_alias(raw_alias, "calc_field")
		sql_expr = "".join(rendered_tokens).strip()
		return sql_expr, alias
