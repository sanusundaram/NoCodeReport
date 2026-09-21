# Implementation Plan: Universal No-Code Report Builder

Build a production-grade, permission-aware, visual query builder and SQL generator native to Frappe Desk (`nocodereport`), combining capabilities of Report Builder, Query Report, and Script Report into a developer-oriented workspace.

## User Review Required

> [!IMPORTANT]
> **Implementation Scope & Roadmap**: Per requirements, we will implement this incrementally starting with **Phase 1**:
> 1. **Phase 1**: Core application architecture, Desk Page structure, permission check, metadata discovery, field selection, basic `SELECT` generation, and comprehensive backend validation.
> 2. **Phase 2**: Link field discovery, recursive relationship resolution with cycle prevention & depth limits, automatic JOIN generation, and relationship graph.
> 3. **Phase 3**: Filters with nested AND/OR AST groups, GROUP BY (including date intervals), Aggregations (SUM/COUNT/AVG/MIN/MAX), and ORDER BY.
> 4. **Phase 4**: Child table support (`parent`/`parenttype`/`parentfield`), multi-level relationships, parameterization, SQL formatting, and clipboard actions.
> 5. **Phase 5**: Safe calculated fields (no eval/exec), Query Explainer, interactive graph controls, and developer UI polish.

> [!NOTE]
> The target environment is running **Frappe 16.27.0** on **MariaDB 10.11** under WSL, with the app `nocodereport` already installed on site `site1.local`. We will build the modules directly within `nocodereport` and expose the Desk Page as `universal-report-builder`.

---

## Architecture & Module Structure

```
apps/nocodereport/nocodereport/
├── api/
│   ├── __init__.py
│   ├── metadata.py            # DocType & field discovery, link & child detection
│   ├── permissions.py         # Effective read permission validation
│   ├── relationships.py      # Recursive relationship discovery with cycle/depth checks
│   └── query_api.py           # Endpoint to plan, validate, and generate SQL
│
├── query_engine/
│   ├── __init__.py
│   ├── query_planner.py       # Resolves paths, table aliases, deduplicates joins
│   ├── sql_generator.py       # Builds formatted SQL via frappe.qb / PyPika with parameterization
│   ├── join_builder.py        # Generates ON conditions for Link and Child Table relations
│   ├── filter_builder.py      # Translates AST filter trees to safe parameterized SQL clauses
│   ├── aggregation_builder.py # Builds aggregation expressions and aliases
│   ├── group_builder.py       # Handles GROUP BY (fields & date parts: month, year, quarter, day)
│   ├── order_builder.py       # Handles ORDER BY ASC/DESC
│   └── validator.py           # Validates DocTypes, fields, operators, and syntax integrity
│
├── security/
│   ├── __init__.py
│   ├── permission_validator.py # Server-side permission enforcement on all nodes
│   ├── field_validator.py      # Asserts field existence, virtual status, and column type
│   └── relationship_validator.py# Asserts link paths and child table parents
│
├── utils/
│   ├── __init__.py
│   └── helpers.py              # String formatting, SQL pretty printing, sanitization
│
└── nocodereport/
    └── page/
        └── universal_report_builder/
            ├── universal_report_builder.json # Page doc definition
            ├── universal_report_builder.js   # Native Desk Page UI logic
            ├── universal_report_builder.css  # Developer tool styling
            └── universal_report_builder.html # Base markup container
```

---

## Proposed Changes

### 1. Security & Permissions Layer
#### [NEW] [permission_validator.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/security/permission_validator.py)
- Validates user read permission using `frappe.has_permission(doctype, ptype="read", user=frappe.session.user)`.
- Rejects unauthorized DocTypes immediately with informative error messages before any metadata inspection.
- Recursively validates every referenced DocType (base, linked, child) in every query request.

#### [NEW] [field_validator.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/security/field_validator.py)
- Inspects DocType metadata to ensure fields physically exist in the database table (`tab<DocType>`).
- Disallows virtual fields (`is_virtual=1`) and non-database fields (`frappe.model.no_value_fields` like Section Break, HTML, Fold).
- Validates data types against requested operations (e.g. numeric only for SUM/AVG).

#### [NEW] [relationship_validator.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/security/relationship_validator.py)
- Validates that a link field actually points to the target DocType.
- Validates child table `parent`/`parenttype`/`parentfield` integrity.
- Caps maximum relationship exploration depth to 3 (configurable) and tracks visited sets to prevent cyclical references (e.g. `Customer -> Lead -> Customer`).

---

### 2. API Endpoints
#### [NEW] [metadata.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/api/metadata.py)
- `@frappe.whitelist()` `get_permitted_doctypes(search_term=None)`: Returns list of non-single, non-table DocTypes the current user has permission to read.
- `@frappe.whitelist()` `get_doctype_metadata(doctype)`: Validates permission; returns fields with metadata (`fieldname`, `label`, `fieldtype`, `options`, `is_virtual`, `reqd`, `hidden`), identifies Link fields and Child Table fields.

#### [NEW] [relationships.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/api/relationships.py)
- `@frappe.whitelist()` `get_doctype_relationships(doctype, current_depth=1, visited=None)`: Returns permission-checked outgoing Links and Child Tables with cycle prevention.

#### [NEW] [query_api.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/api/query_api.py)
- `@frappe.whitelist()` `generate_query(spec)`: Accepts internal query representation (JSON), passes through `QueryPlanner`, validates every element, builds SQL via `SQLGenerator`, and returns `{ "sql": formatted_sql, "params": params, "explanation": explanation, "graph": graph_data }`.

---

### 3. Query Engine
#### [NEW] [query_planner.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/query_planner.py)
- Resolves dot-notated paths (e.g. `passenger.first_name`, `add_ons.amount`).
- Assigns deterministic, safe table aliases to prevent collision when joining tables multiple times.
- Deduplicates JOIN paths so multiple fields through the same relationship reuse a single JOIN.
- Assembles query specifications into a clean internal AST before handing off to the SQL generator.

#### [NEW] [sql_generator.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/sql_generator.py)
- Uses `frappe.qb` (PyPika backend) to construct syntactically correct queries matching MariaDB/Postgres.
- Formats output with clean indentation, uppercase SQL keywords, and separated clauses.
- Emits parameterized values (`%(param_name)s`) for WHERE clauses and maintains parameter dictionaries to prevent SQL injection.

#### [NEW] [filter_builder.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/filter_builder.py)
- Evaluates AST filter specifications with nested `AND` and `OR` groups.
- Restricts operators strictly to approved whitelist: `=`, `!=`, `>`, `<`, `>=`, `<=`, `LIKE`, `NOT LIKE`, `IN`, `NOT IN`, `BETWEEN`, `IS NULL`, `IS NOT NULL`.

#### [NEW] [join_builder.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/join_builder.py)
- Computes standard `LEFT JOIN` / `INNER JOIN` conditions:
  - Link fields: `tabParent.link_field = tabChild.name`
  - Child tables: `tabChild.parent = tabParent.name AND tabChild.parenttype = 'Parent' AND tabChild.parentfield = 'child_field'`

#### [NEW] [aggregation_builder.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/aggregation_builder.py)
- Supports `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`, and `COUNT(*)`. Validates numeric types for mathematical aggregates.

#### [NEW] [group_builder.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/group_builder.py)
- Handles simple column grouping and date functions (`YEAR`, `MONTH`, `QUARTER`, `DAY`).

#### [NEW] [order_builder.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/order_builder.py)
- Generates `ORDER BY` with ASC/DESC direction.

#### [NEW] [validator.py](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/query_engine/validator.py)
- Validates the overall query payload schema and ensures no arbitrary or unescaped SQL syntax is present.

---

### 4. Desk Page Frontend UI
#### [NEW] [universal_report_builder.json](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/nocodereport/page/universal_report_builder/universal_report_builder.json)
- Desk Page metadata record registering `universal-report-builder` into Frappe Desk.

#### [NEW] [universal_report_builder.js](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/nocodereport/page/universal_report_builder/universal_report_builder.js)
- Responsive multi-panel developer interface:
  - **Top Bar**: DocType selector (Awesomeplete/searchable), Action buttons ([New], [Clear], [Generate SQL], [Copy SQL], [Copy SQL + Params]).
  - **Left Sidebar (Collapsible Accordion)**:
    - 1. Data Source (Base DocType, permission status badge)
    - 2. Fields (search filter, fieldtype badges, check to select)
    - 3. Relationships (tree view of Link fields and Child tables, expand on click)
    - 4. Filters (nested group builder with AND/OR toggles, operator picker, parameter input)
    - 5. Joins (auto-detected join condition preview, JOIN type selector)
    - 6. Group By (field picker, date grain selector)
    - 7. Aggregations (function, field, alias)
    - 8. Order By (field, ASC/DESC)
    - 9. Calculated Fields (preset expressions, arithmetic operations)
  - **Center Panel (Visual Designer)**:
    - Selected fields table with column alias editing and remove buttons.
    - Active filter chips and relationship badges.
  - **Right Panel (Live SQL & Explanation)**:
    - Formatted SQL display with copy action.
    - Parameter dictionary view.
    - Query explanation breakdown.
  - **Bottom Panel (Relationship Graph)**:
    - SVG/Canvas visual relationship node graph showing Base DocType, linked DocTypes, child tables, and connecting edges.
- Real-time debounced updates when query elements change.

#### [NEW] [universal_report_builder.css](file:///home/sindhu/bench1/apps/nocodereport/nocodereport/nocodereport/page/universal_report_builder/universal_report_builder.css)
- Sleek modern developer styling: clean borders, high-contrast dark/light mode compatibility using Frappe CSS variables, monospaced SQL preview, interactive pill badges.

---

## Verification Plan

### Automated & Backend Tests
- **Unit / Script Tests**:
  1. Test permission checking on permitted vs unauthorized DocTypes (`Customer`, `User` vs restricted doctypes).
  2. Test field discovery for standard, virtual, Link, and Table fields.
  3. Test SQL generation:
     - Basic `SELECT col1, col2 FROM \`tabDocType\``
     - Link field `LEFT JOIN`
     - Child table `LEFT JOIN` with `parent`/`parenttype`/`parentfield`
     - Nested filters with parameterized values
     - Aggregations and `GROUP BY`
  4. Test SQL injection resistance (parameterization check, rejection of invalid operators/arbitrary strings).
  5. Test cycle detection in relationship traversal.

### Manual & Desk UI Verification
1. Open Desk at `http://localhost/app/universal-report-builder`.
2. Verify page loads cleanly with modern 3-column + bottom graph layout.
3. Search and select a DocType (`Airplane Ticket` or `Customer`).
4. Select fields, add a filter, add a link join, inspect live SQL output.
5. Click **Copy SQL** and verify clipboard notification.
6. Verify visual relationship graph displays connected nodes.
