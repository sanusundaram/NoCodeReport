import frappe
import sys

frappe.init(site="site1.local", sites_path="/home/sindhu/bench1/sites")
frappe.connect()

results = []

# Test 1: page loads assets correctly
try:
    p = frappe.get_doc("Page", "universal-report-builder")
    p.load_assets()
    script_len = len(p.script or "")
    style_len = len(p.style or "")
    results.append(f"[OK] Page assets: script={script_len}b, style={style_len}b")
    if script_len < 100:
        results.append("[WARN] Script is suspiciously short!")
except Exception as e:
    results.append(f"[FAIL] Page load: {e}")

# Test 2: API module imports
try:
    from nocodereport.api import metadata, query_api, relationships, permissions
    results.append("[OK] API modules imported")
except Exception as e:
    results.append(f"[FAIL] API imports: {e}")

# Test 3: Query engine imports
try:
    from nocodereport.query_engine import (
        sql_generator, query_planner, filter_builder,
        aggregation_builder, group_builder, order_builder,
        join_builder, validator, calculated_field_builder
    )
    results.append("[OK] Query engine modules imported")
except Exception as e:
    results.append(f"[FAIL] Query engine imports: {e}")

# Test 4: Security module imports
try:
    from nocodereport.security import permission_validator, field_validator, relationship_validator
    results.append("[OK] Security modules imported")
except Exception as e:
    results.append(f"[FAIL] Security imports: {e}")

# Test 5: Workspace existence
ws = frappe.db.get_value("Workspace", "Report Builder", "name")
bld = frappe.db.get_value("Workspace", "Build", "name")
results.append(f"[{'OK' if ws else 'MISSING'}] Report Builder workspace: {ws or 'NOT FOUND'}")
results.append(f"[{'OK' if bld else 'MISSING'}] Build workspace: {bld or 'NOT FOUND'}")

# Test 6: Check Build workspace has our link
try:
    build_ws = frappe.get_doc("Workspace", "Build")
    has_shortcut = any(
        getattr(s, "link_to", "") == "universal-report-builder"
        for s in build_ws.shortcuts
    )
    has_link = any(
        getattr(l, "link_to", "") == "universal-report-builder"
        for l in build_ws.links
    )
    results.append(f"[{'OK' if has_shortcut else 'MISSING'}] Build WS shortcut to universal-report-builder")
    results.append(f"[{'OK' if has_link else 'MISSING'}] Build WS link to universal-report-builder")
except Exception as e:
    results.append(f"[FAIL] Build workspace check: {e}")

# Test 7: Quick SQL generation test
try:
    from nocodereport.api.query_api import generate_sql
    import json
    spec = {
        "base_doctype": "Customer",
        "fields": [{"path": "base", "fieldname": "name", "alias": "customer_name"}],
        "joins": [],
        "filters": {},
        "group_by": [],
        "aggregations": [],
        "order_by": [],
        "calculated_fields": []
    }
    result = generate_sql(json.dumps(spec))
    if result and result.get("success"):
        results.append(f"[OK] SQL generation works: {result['sql'][:60]}...")
    else:
        results.append(f"[FAIL] SQL generation: {result}")
except Exception as e:
    results.append(f"[FAIL] SQL generation: {e}")

frappe.destroy()

print("\n".join(results))
