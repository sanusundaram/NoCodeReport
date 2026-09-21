import frappe
def run():
    p = frappe.get_doc("Page", "universal-report-builder")
    p.load_assets()
    print("Script last 1000 chars:")
    print(p.script[-1000:] if p.script else "None")
