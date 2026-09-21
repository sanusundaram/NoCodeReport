def run():
    import frappe, json
    results = []

    # SQL generation with CORRECT spec (path = fieldname for base doctype fields)
    try:
        from nocodereport.api.query_api import generate_sql

        spec_simple = {
            "base_doctype": "Customer",
            "fields": [
                {"path": "name", "fieldname": "name", "alias": "cust_name"},
                {"path": "customer_name", "fieldname": "customer_name", "alias": "customer_name"}
            ],
            "joins": [],
            "filters": {},
            "group_by": [],
            "aggregations": [],
            "order_by": [],
            "calculated_fields": []
        }
        r = generate_sql(json.dumps(spec_simple))
        if r and r.get("success"):
            results.append("TEST 1 PASS - Simple SELECT:\n  " + r["sql"])
        else:
            results.append("TEST 1 FAIL: " + str(r))
    except Exception as e:
        results.append("TEST 1 EXCEPTION: {}".format(e))

    # Test with filter
    try:
        from nocodereport.api.query_api import generate_sql
        spec_filter = {
            "base_doctype": "Customer",
            "fields": [{"path": "name", "fieldname": "name", "alias": "name"}],
            "joins": [],
            "filters": {
                "operator": "AND",
                "conditions": [
                    {"field": "customer_type", "operator": "=", "value": "Company"}
                ]
            },
            "group_by": [],
            "aggregations": [],
            "order_by": [{"field": "customer_name", "direction": "ASC"}],
            "calculated_fields": []
        }
        r = generate_sql(json.dumps(spec_filter))
        if r and r.get("success"):
            results.append("TEST 2 PASS - Filter + ORDER BY:\n  " + r["sql"])
        else:
            results.append("TEST 2 FAIL: " + str(r))
    except Exception as e:
        results.append("TEST 2 EXCEPTION: {}".format(e))

    # Test aggregation + group by
    try:
        from nocodereport.api.query_api import generate_sql
        spec_agg = {
            "base_doctype": "Customer",
            "fields": [{"path": "customer_type", "fieldname": "customer_type", "alias": "customer_type"}],
            "joins": [],
            "filters": {},
            "group_by": [{"field": "customer_type"}],
            "aggregations": [{"func": "COUNT", "field": "name", "alias": "total"}],
            "order_by": [],
            "calculated_fields": []
        }
        r = generate_sql(json.dumps(spec_agg))
        if r and r.get("success"):
            results.append("TEST 3 PASS - Aggregation + GROUP BY:\n  " + r["sql"])
        else:
            results.append("TEST 3 FAIL: " + str(r))
    except Exception as e:
        results.append("TEST 3 EXCEPTION: {}".format(e))

    print("\n".join(results))
