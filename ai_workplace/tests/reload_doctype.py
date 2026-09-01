import frappe

def reload_both_doctypes():
    frappe.reload_doctype("AI Workplace Knowledge Source", force=True)
    frappe.reload_doctype("AI Knowledge Entry", force=True)
    frappe.db.commit()
    print("Both DocTypes reloaded successfully!")
