import frappe
def run():
    ws = frappe.get_doc("Workspace", "Build")
    for s in ws.shortcuts:
        if "report" in s.link_to.lower():
            print(f"Shortcut link_to: '{s.link_to}', type: '{s.type}'")
