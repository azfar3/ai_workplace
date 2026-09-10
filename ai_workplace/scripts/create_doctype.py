import frappe

def create_doctype():
    if not frappe.db.exists("DocType", "Web Push Subscription"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Web Push Subscription",
            "module": "AI Workplace",
            "custom": 0,
            "naming_rule": "Random",
            "autoname": "hash",
            "permissions": [
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1
                }
            ],
            "fields": [
                {"fieldname": "user", "label": "User", "fieldtype": "Link", "options": "User", "reqd": 1, "in_list_view": 1},
                {"fieldname": "endpoint", "label": "Endpoint", "fieldtype": "Small Text", "reqd": 1},
                {"fieldname": "p256dh", "label": "p256dh", "fieldtype": "Data", "reqd": 1},
                {"fieldname": "auth", "label": "auth", "fieldtype": "Data", "reqd": 1},
                {"fieldname": "user_agent", "label": "User Agent", "fieldtype": "Data", "reqd": 0},
                {"fieldname": "enabled", "label": "Enabled", "fieldtype": "Check", "default": "1"}
            ]
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Created Web Push Subscription Doctype")
    else:
        print("Web Push Subscription already exists")

create_doctype()
