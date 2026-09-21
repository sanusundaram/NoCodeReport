def run():
    import frappe
    meta = frappe.get_meta("Customer")
    fields = [df.fieldname for df in meta.fields if df.fieldtype == "Select"]
    print("Select fields on Customer:", fields[:10])
    all_fn = [df.fieldname for df in meta.fields]
    print("customer_type in meta.fields:", "customer_type" in all_fn)
    print("customer_group in meta.fields:", "customer_group" in all_fn)
