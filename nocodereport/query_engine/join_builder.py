import re
import frappe
from frappe.query_builder import Table, DocType
from nocodereport.security.permission_validator import validate_doctype_read_permission
from nocodereport.security.relationship_validator import validate_relationship_path


def generate_short_alias(name: str, used_aliases: set[str]) -> str:
	"""
	Generates a concise, collision-free SQL table alias.
	e.g. Employee -> e
	     Department -> d
	     Workflow State -> w (or ws)
	"""
	clean = re.sub(r"[^a-zA-Z0-9_ ]", "", name).strip()
	words = [w for w in re.split(r"[_\s]+", clean) if w]

	candidate = ""
	if words:
		first_letter = words[0][0].lower()
		if first_letter not in used_aliases:
			candidate = first_letter
		else:
			initials = "".join(w[0].lower() for w in words)
			if len(initials) > 1 and initials not in used_aliases:
				candidate = initials
			else:
				for l in (2, 3, 4):
					prefix = words[0][:l].lower()
					if prefix not in used_aliases:
						candidate = prefix
						break

	if not candidate:
		base = words[0][:1].lower() if words else "t"
		num = 1
		while f"{base}{num}" in used_aliases:
			num += 1
		candidate = f"{base}{num}"

	used_aliases.add(candidate)
	return candidate


class JoinBuilder:
	"""
	Builds and deduplicates JOIN specifications for linked and child DocTypes
	using clean, short table aliases (e.g. e, d, w).
	"""

	def __init__(self, base_doctype: str, custom_join_types: dict | None = None):
		self.base_doctype = base_doctype
		self.custom_join_types = custom_join_types or {}
		self.joins = []
		self.table_instances = {}
		self.path_metadata = {}
		self.used_aliases = set()

		# Base table instance with short alias (e.g. 'e' for Employee)
		self.base_alias = generate_short_alias(base_doctype, self.used_aliases)
		self.base_table = Table(f"tab{base_doctype}").as_(self.base_alias)
		self.table_instances[""] = self.base_table

	def add_relationship_path(self, path_parts: list[str]) -> str:
		current_path = []
		parent_doctype = self.base_doctype
		parent_table_key = ""

		for fieldname in path_parts:
			current_path.append(fieldname)
			path_key = ".".join(current_path)

			if path_key in self.table_instances:
				parent_table_key = path_key
				parent_doctype = self.path_metadata[path_key]["target_doctype"]
				continue

			meta = frappe.get_meta(parent_doctype)
			df = meta.get_field(fieldname)
			if not df:
				frappe.throw(f"Relationship field '{fieldname}' not found on '{parent_doctype}'")

			target_doctype = df.options
			validate_doctype_read_permission(target_doctype)

			is_child = df.fieldtype in ("Table", "Table MultiSelect")
			join_type = self.custom_join_types.get(path_key, "LEFT JOIN")

			# Short alias derived from target doctype / fieldname (e.g. 'd' for Department, 'w' for Workflow State)
			alias_name = generate_short_alias(target_doctype, self.used_aliases)
			target_table = Table(f"tab{target_doctype}").as_(alias_name)

			parent_table = self.table_instances[parent_table_key]
			parent_alias = getattr(parent_table, "_alias", f"tab{parent_doctype}")

			if not is_child:
				join_condition = getattr(parent_table, fieldname) == getattr(target_table, "name")
				condition_expr = f"`{parent_alias}`.`{fieldname}` = `{alias_name}`.`name`"
			else:
				join_condition = (
					(target_table.parent == parent_table.name)
					& (target_table.parenttype == parent_doctype)
					& (target_table.parentfield == fieldname)
				)
				condition_expr = (
					f"`{alias_name}`.`parent` = `{parent_alias}`.`name` "
					f"AND `{alias_name}`.`parenttype` = '{parent_doctype}' "
					f"AND `{alias_name}`.`parentfield` = '{fieldname}'"
				)

			join_def = {
				"path": path_key,
				"parent_doctype": parent_doctype,
				"parent_table_key": parent_table_key,
				"target_doctype": target_doctype,
				"target_table": target_table,
				"alias_name": alias_name,
				"fieldname": fieldname,
				"is_child": is_child,
				"join_type": join_type,
				"condition": join_condition,
				"condition_expr": condition_expr
			}

			self.joins.append(join_def)
			self.table_instances[path_key] = target_table
			self.path_metadata[path_key] = {
				"target_doctype": target_doctype,
				"alias_name": alias_name,
				"is_child": is_child
			}

			parent_table_key = path_key
			parent_doctype = target_doctype

		return parent_table_key

	def get_table_for_path(self, path_parts: list[str]):
		path_key = ".".join(path_parts) if path_parts else ""
		return self.table_instances.get(path_key, self.base_table)
