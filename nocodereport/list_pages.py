import frappe
def run():
    pages = frappe.get_all('Page', filters={'name': ('like', '%report%')})
    for p in pages:
        print(f'Page Name: "{p.name}"')
