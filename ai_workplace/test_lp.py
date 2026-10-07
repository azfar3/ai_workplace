import frappe
def run():
    lp = frappe.get_meta("Leave Policy")
    for field in lp.fields:
        if field.fieldname == "custom_leave_type_policy":
            print(field.options)
            clt = frappe.get_meta(field.options)
            for f in clt.fields:
                print(f.fieldname, f.fieldtype)
