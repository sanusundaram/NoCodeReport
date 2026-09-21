import json
import frappe
from frappe import _
from nocodereport.query_engine.validator import validate_query_spec
from nocodereport.query_engine.query_planner import QueryPlanner
from nocodereport.query_engine.sql_generator import SQLGenerator


@frappe.whitelist()
def generate_sql(spec: str | dict) -> dict:
	"""
	Whitelisted endpoint to validate query configuration and generate safe, formatted SQL.
	"""
	if isinstance(spec, str):
		try:
			spec = json.loads(spec)
		except Exception as e:
			return {
				"success": False,
				"error": _("Invalid JSON specification: {0}").format(str(e))
			}

	try:
		# 1. Validate spec schema and permissions
		validate_query_spec(spec)

		# 2. Plan the query
		planner = QueryPlanner(spec)
		plan = planner.plan()

		# 3. Generate formatted SQL
		generator = SQLGenerator(plan)
		gen_res = generator.generate()

		return {
			"success": True,
			"sql": gen_res["sql"],
			"raw_sql": gen_res["raw_sql"],
			"params": gen_res["params"],
			"explanation": plan["explanation"],
			"fields_count": len(plan["fields"]),
			"joins_count": gen_res.get("joins_count", len(plan.get("joins", []))),
		}
	except Exception as e:
		frappe.log_error(title="Universal Report Builder Query Error")
		return {
			"success": False,
			"error": str(e)
		}
