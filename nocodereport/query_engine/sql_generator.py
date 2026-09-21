import frappe
from frappe.query_builder import DocType, Table
from pypika.terms import LiteralValue
from nocodereport.utils.helpers import format_sql


class SQLGenerator:
	"""
	Complete SQL generator supporting:
	- Multi-table JOINs with short table aliases (e.g. e, d, w)
	- Calculated field expressions
	- Aggregation functions (SUM, COUNT, AVG, MIN, MAX)
	- Parameterized WHERE clauses with nested AND/OR
	- GROUP BY (with date intervals)
	- ORDER BY (ASC/DESC)
	- LIMIT
	"""

	def __init__(self, plan: dict):
		self.plan = plan
		self.base_doctype = plan["base_doctype"]
		self.fields = plan.get("fields", [])
		self.joins = plan.get("joins", [])
		self.table_instances = plan.get("table_instances", {})
		self.where_clause = plan.get("where_clause", "")
		self.filter_params = plan.get("filter_params", {})
		self.group_by = plan.get("group_by", [])
		self.aggregations = plan.get("aggregations", [])
		self.calculated_fields = plan.get("calculated_fields", [])
		self.order_by = plan.get("order_by", [])
		self.limit = plan.get("limit")

	def generate(self) -> dict:
		base_table = self.table_instances.get("", Table(f"tab{self.base_doctype}"))
		query = frappe.qb.from_(base_table)

		# 1. Apply JOINs
		for j in self.joins:
			join_type = j.get("join_type", "LEFT JOIN").upper().strip()
			target_table = j["target_table"]
			condition = j.get("condition")

			if join_type in ("INNER JOIN", "INNER"):
				query = query.join(target_table).on(condition)
			elif join_type in ("RIGHT JOIN", "RIGHT", "RIGHT OUTER JOIN"):
				query = query.right_join(target_table).on(condition)
			elif join_type in ("FULL OUTER JOIN", "FULL JOIN", "FULL"):
				query = query.outer_join(target_table).on(condition)
			elif join_type in ("CROSS JOIN", "CROSS"):
				if condition is not None:
					query = query.cross_join(target_table).on(condition)
				else:
					query = query.cross_join(target_table)
			else:
				query = query.left_join(target_table).on(condition)

		# 2. Select items: fields + aggregations + calculated fields
		select_items = []

		for f in self.fields:
			table_key = f.get("table_key", "")
			table_inst = self.table_instances.get(table_key, base_table)
			col = getattr(table_inst, f["fieldname"])

			# If alias provided and different from fieldname, use AS alias
			if f.get("alias") and f["alias"] != f["fieldname"]:
				select_items.append(col.as_(f["alias"]))
			else:
				select_items.append(col)

		for c in self.calculated_fields:
			col = LiteralValue(c["sql_expr"])
			if c.get("alias"):
				col = col.as_(c["alias"])
			select_items.append(col)

		for a in self.aggregations:
			col = LiteralValue(a["sql_expr"])
			if a.get("alias"):
				col = col.as_(a["alias"])
			select_items.append(col)

		if select_items:
			query = query.select(*select_items)
		else:
			query = query.select(getattr(base_table, "name", base_table))

		raw_sql = query.get_sql()

		if self.where_clause:
			raw_sql += f" WHERE {self.where_clause}"

		if self.group_by:
			raw_sql += f" GROUP BY {', '.join(self.group_by)}"

		if self.order_by:
			raw_sql += f" ORDER BY {', '.join(self.order_by)}"

		if self.limit and isinstance(self.limit, int) and self.limit > 0:
			query = query.limit(self.limit)

		formatted = format_sql(raw_sql)

		return {
			"raw_sql": raw_sql,
			"sql": formatted,
			"params": self.filter_params,
			"joins_count": len(self.joins)
		}
