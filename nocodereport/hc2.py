def run():
    import frappe, json
    results = []

    # Page assets
    try:
        p = frappe.get_doc("Page", "universal-report-builder")
        p.load_assets()
        results.append("Page assets: script={}b style={}b".format(len(p.script or ""), len(p.style or "")))
    except Exception as e:
        results.append("FAIL page: {}".format(e))

    # API modules
    try:
        from nocodereport.api import metadata, query_api, relationships
        results.append("API modules: OK")
    except Exception as e:
        results.append("FAIL API: {}".format(e))

    # Query engine
    try:
        from nocodereport.query_engine import sql_generator, query_planner, filter_builder
        from nocodereport.query_engine import aggregation_builder, join_builder, validator
        results.append("Query engine: OK")
    except Exception as e:
        results.append("FAIL engine: {}".format(e))

    # Security
    try:
        from nocodereport.security import permission_validator, field_validator
        results.append("Security: OK")
    except Exception as e:
        results.append("FAIL security: {}".format(e))

    # Workspaces
    ws = frappe.db.get_value("Workspace", "Report Builder", "name")
    results.append("Report Builder WS: {}".format(ws or "MISSING"))

    bld_sc = None
    try:
        bld = frappe.get_doc("Workspace", "Build")
        bld_sc = any(getattr(s, "link_to", "") == "universal-report-builder" for s in bld.shortcuts)
        results.append("Build WS shortcut: {}".format("OK" if bld_sc else "MISSING"))
    except Exception as e:
        results.append("FAIL Build WS: {}".format(e))

    # SQL generation test
    try:
        from nocodereport.api.query_api import generate_sql
        spec = {
            "base_doctype": "Customer",
            "fields": [{"path": "base", "fieldname": "name", "alias": "cust_name"}],
            "joins": [],
            "filters": {},
            "group_by": [],
            "aggregations": [],
            "order_by": [],
            "calculated_fields": []
        }
        r = generate_sql(json.dumps(spec))
        if r and r.get("success"):
            results.append("SQL gen: OK => " + r["sql"][:60])
        else:
            results.append("SQL gen FAIL: " + str(r))
    except Exception as e:
        results.append("SQL gen FAIL: {}".format(e))

    print("\n".join(results))
