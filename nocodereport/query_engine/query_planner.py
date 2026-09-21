import frappe
from nocodereport.security.permission_validator import validate_doctype_read_permission
from nocodereport.security.field_validator import validate_queryable_field
from nocodereport.security.relationship_validator import validate_relationship_path
from nocodereport.query_engine.join_builder import JoinBuilder
from nocodereport.query_engine.filter_builder import FilterBuilder
from nocodereport.query_engine.aggregation_builder import AggregationBuilder
from nocodereport.query_engine.group_builder import GroupBuilder
from nocodereport.query_engine.order_builder import OrderBuilder
from nocodereport.query_engine.calculated_field_builder import CalculatedFieldBuilder
from nocodereport.utils.helpers import sanitize_alias


class QueryPlanner:
	"""
	Complete query planning engine.
	Validates base DocType, resolves relationship paths across fields, filters,
	groupings, aggregations, orderings, and calculated expressions.
	"""

	def __init__(self, spec: dict):
		self.raw_spec = spec
		self.base_doctype = spec.get("base_doctype")
		self.fields_spec = spec.get("fields", [])
		self.joins_spec = spec.get("joins", [])
		self.filters_spec = spec.get("filters", {})
		self.group_by_spec = spec.get("group_by", [])
		self.aggregations_spec = spec.get("aggregations", [])
		self.order_by_spec = spec.get("order_by", [])
		self.calculated_fields_spec = spec.get("calculated_fields", [])
		self.limit = spec.get("limit")

		# Custom join type overrides: { "path": "INNER JOIN" }
		self.custom_joins = {}
		if isinstance(self.joins_spec, list):
			for j in self.joins_spec:
				if isinstance(j, dict) and j.get("path") and j.get("join_type"):
					self.custom_joins[j["path"]] = j["join_type"]

		# Join builder
		self.join_builder = JoinBuilder(self.base_doctype, self.custom_joins)

		# Resolved structures
		self.resolved_fields = []
		self.resolved_aggregations = []
		self.resolved_groups = []
		self.resolved_orders = []
		self.resolved_calculated_fields = []
		self.explanation = []

	def plan(self) -> dict:
		"""
		Executes full planning pipeline.
		"""
		# 1. Base DocType
		validate_doctype_read_permission(self.base_doctype)
		self.explanation.append(f"Base DocType: {self.base_doctype}")

		# 2. Pre-scan and register all relationship paths across all clauses
		self._scan_all_relationship_paths()

		# 3. Resolve selected fields
		self._resolve_fields()

		# 4. Resolve calculated fields
		calc_builder = CalculatedFieldBuilder(self.join_builder.table_instances)
		for c in self.calculated_fields_spec:
			sql_expr, alias = calc_builder.build(c)
			self.resolved_calculated_fields.append({"sql_expr": sql_expr, "alias": alias})
		if self.resolved_calculated_fields:
			self.explanation.append(
				f"Calculated Fields ({len(self.resolved_calculated_fields)}): "
				+ ", ".join([f"{c['sql_expr']} AS {c['alias']}" for c in self.resolved_calculated_fields])
			)

		# 5. Resolve aggregations
		agg_builder = AggregationBuilder(self.join_builder.table_instances)
		for a in self.aggregations_spec:
			agg_expr, alias = agg_builder.build_aggregation(a)
			self.resolved_aggregations.append({"sql_expr": agg_expr, "alias": alias})
		if self.resolved_aggregations:
			self.explanation.append(
				f"Aggregations ({len(self.resolved_aggregations)}): "
				+ ", ".join([f"{a['sql_expr']} AS {a['alias']}" for a in self.resolved_aggregations])
			)

		# 6. Resolve filters
		filter_builder = FilterBuilder(self.join_builder.table_instances)
		where_clause, filter_params = filter_builder.build(self.filters_spec)
		if where_clause:
			self.explanation.append(f"Filters:\n  • {where_clause}")

		# 7. Resolve Group By
		group_builder = GroupBuilder(self.join_builder.table_instances)
		for g in self.group_by_spec:
			g_expr = group_builder.build_group_expr(g)
			if g_expr:
				self.resolved_groups.append(g_expr)
		if self.resolved_groups:
			self.explanation.append(f"Group By:\n  • " + ", ".join(self.resolved_groups))

		# 8. Resolve Order By
		order_builder = OrderBuilder(self.join_builder.table_instances)
		for o in self.order_by_spec:
			o_expr = order_builder.build_order_expr(o)
			if o_expr:
				self.resolved_orders.append(o_expr)
		if self.resolved_orders:
			self.explanation.append(f"Order By:\n  • " + ", ".join(self.resolved_orders))

		# 9. Relationships summary
		if self.join_builder.joins:
			join_lines = []
			for j in self.join_builder.joins:
				kind = "Child Table" if j["is_child"] else "Link"
				join_lines.append(f"  • {j['join_type']} {j['target_doctype']} ({kind} on `{j['fieldname']}`)")
			self.explanation.insert(1, f"Relationships / Joins ({len(self.join_builder.joins)}):\n" + "\n".join(join_lines))

		return {
			"base_doctype": self.base_doctype,
			"fields": self.resolved_fields,
			"joins": self.join_builder.joins,
			"table_instances": self.join_builder.table_instances,
			"where_clause": where_clause,
			"filter_params": filter_params,
			"group_by": self.resolved_groups,
			"aggregations": self.resolved_aggregations,
			"calculated_fields": self.resolved_calculated_fields,
			"order_by": self.resolved_orders,
			"limit": self.limit,
			"explanation": "\n".join(self.explanation)
		}

	def _scan_all_relationship_paths(self):
		"""
		Pre-registers any relationship path referenced in filters, aggregations, groups, or orders.
		"""
		paths_to_register = []

		def extract_paths_from_filters(filter_item):
			if isinstance(filter_item, dict):
				if "field" in filter_item:
					f = filter_item["field"]
					if "." in f:
						paths_to_register.append(f.split(".")[:-1])
				for c in filter_item.get("conditions", []):
					extract_paths_from_filters(c)
			elif isinstance(filter_item, list):
				for item in filter_item:
					extract_paths_from_filters(item)

		extract_paths_from_filters(self.filters_spec)

		for a in self.aggregations_spec:
			f = a.get("field") or a.get("path")
			if f and "." in f:
				paths_to_register.append(f.split(".")[:-1])

		for g in self.group_by_spec:
			f = g if isinstance(g, str) else g.get("field") or g.get("path")
			if f and "." in f:
				paths_to_register.append(f.split(".")[:-1])

		for o in self.order_by_spec:
			f = o.strip().split()[0] if isinstance(o, str) else o.get("field") or o.get("path")
			if f and "." in f:
				paths_to_register.append(f.split(".")[:-1])

		for p in paths_to_register:
			self.join_builder.add_relationship_path(p)

	def _resolve_fields(self):
		field_names_selected = []
		for item in self.fields_spec:
			if isinstance(item, str):
				raw_path = item
				raw_alias = None
			elif isinstance(item, dict):
				raw_path = item.get("path") or item.get("fieldname")
				raw_alias = item.get("alias")
			else:
				continue

			if not raw_path:
				continue

			parts = raw_path.split(".")

			if len(parts) == 1:
				fieldname = parts[0]
				f_meta = validate_queryable_field(self.base_doctype, fieldname)
				alias = sanitize_alias(raw_alias, fieldname)

				self.resolved_fields.append({
					"doctype": self.base_doctype,
					"rel_path": [],
					"table_key": "",
					"fieldname": fieldname,
					"alias": alias,
					"fieldtype": f_meta.get("fieldtype"),
					"label": f_meta.get("label"),
					"path": raw_path
				})
				field_names_selected.append(f"{f_meta.get('label')} ({fieldname})")
			else:
				relation_parts = parts[:-1]
				target_fieldname = parts[-1]

				table_key = self.join_builder.add_relationship_path(relation_parts)
				target_doctype = self.join_builder.path_metadata[table_key]["target_doctype"]

				f_meta = validate_queryable_field(target_doctype, target_fieldname)
				alias = sanitize_alias(raw_alias, f"{relation_parts[-1]}_{target_fieldname}")

				self.resolved_fields.append({
					"doctype": target_doctype,
					"rel_path": relation_parts,
					"table_key": table_key,
					"fieldname": target_fieldname,
					"alias": alias,
					"fieldtype": f_meta.get("fieldtype"),
					"label": f_meta.get("label"),
					"path": raw_path
				})
				field_names_selected.append(f"{target_doctype}.{f_meta.get('label')} ({raw_path})")

		if self.resolved_fields:
			self.explanation.append(f"Selected Fields ({len(self.resolved_fields)}): " + ", ".join(field_names_selected))
