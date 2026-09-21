import re
import frappe
from frappe import _

IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sanitize_alias(alias: str | None, default: str) -> str:
	if not alias:
		alias = default
	alias = str(alias).strip()
	if not IDENTIFIER_REGEX.match(alias):
		alias = re.sub(r"[^A-Za-z0-9_]", "_", alias)
		if not alias or alias[0].isdigit():
			alias = f"col_{alias}"
	return alias[:64]


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
	parts = []
	current = []
	depth = 0
	in_quote = None
	i = 0
	d_len = len(delimiter)
	while i < len(text):
		ch = text[i]
		if in_quote:
			current.append(ch)
			if ch == in_quote:
				in_quote = None
		elif ch in ("'", '"', '`'):
			in_quote = ch
			current.append(ch)
		elif ch in ("(", "[", "{"):
			depth += 1
			current.append(ch)
		elif ch in (")", "]", "}"):
			depth -= 1
			current.append(ch)
		elif depth == 0 and text[i:i + d_len] == delimiter:
			parts.append("".join(current).strip())
			current = []
			i += d_len
			continue
		else:
			current.append(ch)
		i += 1
	if current:
		parts.append("".join(current).strip())
	return [p for p in parts if p]


def clean_operators(expr: str) -> str:
	return re.sub(r"(?<![!<>= ])([!=<>]=?)(?![= ])", r" \1 ", expr)


def clean_select_column(col_str: str) -> str:
	s = col_str.strip()
	alias_match = re.search(r'\s+(?:AS\s+)?["`]?([a-zA-Z0-9_]+)["`]?$', s, re.I)
	alias = None
	expr = s
	if alias_match and alias_match.start() > 0:
		alias = alias_match.group(1)
		expr = s[:alias_match.start()].strip()

	# Remove backticks or quotes around table.column: e.g. "e"."name" or `e`.`name` -> e.name
	expr = re.sub(r'["`]([a-zA-Z0-9_]+)["`]\.["`]([a-zA-Z0-9_]+)["`]', r'\1.\2', expr)
	expr = re.sub(r'^["`]([a-zA-Z0-9_]+)["`]$', r'\1', expr)

	if alias:
		if expr == alias or expr.endswith(f".{alias}"):
			return expr
		return f"{expr} AS {alias}"
	return expr


def format_table_clause(clause_str: str) -> str:
	s = clause_str.strip()
	m = re.match(r'^(?:["`]?tab([^"`]+)["`]?|["`]([^"`]+)["`]|([A-Za-z0-9_]+))\s+(?:AS\s+)?["`]?([a-zA-Z0-9_]+)["`]?$', s, re.I)
	if m:
		table_body = m.group(1) or m.group(2) or m.group(3)
		alias = m.group(4)
		table_name = f"tab{table_body}" if not table_body.startswith("tab") else table_body
		return f"`{table_name}` AS {alias}"
	return s


def clean_on_condition(on_cond: str) -> str:
	cleaned = clean_operators(on_cond.strip())
	cleaned = re.sub(r'["`]([a-zA-Z0-9_]+)["`]\.["`]([a-zA-Z0-9_]+)["`]', r'\1.\2', cleaned)
	return cleaned


def format_sql(sql: str) -> str:
	"""
	Formats generated SQL into a clean, human-readable layout matching user expectations:
	SELECT
	    e.name,
	    e.depart,
	    e.department_id,
	    d.idx AS department_id_idx,
	    w.docstatus AS workflow_docstatus
	FROM `tabEmployee` AS e
	RIGHT JOIN `tabDepartment` AS d
	    ON e.department_id = d.name
	LEFT JOIN `tabWorkflow State` AS w
	    ON e.workflow = w.name;
	"""
	if not sql:
		return ""

	raw = sql.strip().rstrip(";")

	clause_regex = re.compile(
		r"\b(SELECT|FROM|LEFT\s+OUTER\s+JOIN|LEFT\s+JOIN|RIGHT\s+OUTER\s+JOIN|RIGHT\s+JOIN|FULL\s+OUTER\s+JOIN|FULL\s+JOIN|INNER\s+JOIN|CROSS\s+JOIN|JOIN|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT)\b",
		re.I
	)

	matches = list(clause_regex.finditer(raw))
	if not matches:
		return raw + ";"

	sections = []
	for i in range(len(matches)):
		start = matches[i].start()
		end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
		kw = matches[i].group(1).upper()
		kw = re.sub(r"\s+", " ", kw)
		body = raw[matches[i].end():end].strip()
		sections.append((kw, body))

	formatted_lines = []

	for kw, body in sections:
		if kw == "SELECT":
			formatted_lines.append("SELECT")
			cols = split_top_level(body, ",")
			for idx, c in enumerate(cols):
				clean_c = clean_select_column(c)
				comma = "," if idx < len(cols) - 1 else ""
				formatted_lines.append(f"    {clean_c}{comma}")

		elif kw == "FROM":
			table_part = format_table_clause(body)
			formatted_lines.append(f"FROM {table_part}")

		elif "JOIN" in kw:
			on_match = re.search(r"\bON\b", body, re.I)
			if on_match:
				table_raw = body[:on_match.start()].strip()
				table_part = format_table_clause(table_raw)
				on_cond = clean_on_condition(body[on_match.end():].strip())
				formatted_lines.append(f"{kw} {table_part}")
				formatted_lines.append(f"    ON {on_cond}")
			else:
				table_part = format_table_clause(body)
				formatted_lines.append(f"{kw} {table_part}")

		elif kw == "WHERE":
			formatted_lines.append("WHERE")
			conds = re.split(r"\s+(AND|OR)\s+", body, flags=re.I)
			if len(conds) > 1:
				formatted_lines.append(f"    {clean_on_condition(conds[0].strip())}")
				for j in range(1, len(conds), 2):
					op = conds[j].upper()
					expr = clean_on_condition(conds[j + 1].strip())
					formatted_lines.append(f"    {op} {expr}")
			else:
				formatted_lines.append(f"    {clean_on_condition(body)}")

		elif kw in ("GROUP BY", "ORDER BY"):
			formatted_lines.append(kw)
			items = split_top_level(body, ",")
			for idx, it in enumerate(items):
				clean_it = clean_select_column(it)
				comma = "," if idx < len(items) - 1 else ""
				formatted_lines.append(f"    {clean_it}{comma}")

		elif kw == "LIMIT":
			formatted_lines.append(f"LIMIT {body}")

		else:
			formatted_lines.append(kw)
			if body:
				formatted_lines.append(f"    {body}")

	return "\n".join(formatted_lines) + ";"
