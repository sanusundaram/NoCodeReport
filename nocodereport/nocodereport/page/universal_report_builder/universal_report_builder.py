import os
import frappe


@frappe.whitelist()
def get_page_html() -> str:
	"""
	Returns the HTML content for the Universal Report Builder page.
	"""
	curr_dir = os.path.dirname(__file__)
	html_path = os.path.join(curr_dir, "universal_report_builder.html")
	if os.path.exists(html_path):
		with open(html_path, "r", encoding="utf-8") as f:
			return f.read()
	return ""
