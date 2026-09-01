"""
Seed WhatsApp Service Security Policy records from defaults.
"""

from __future__ import annotations

import frappe

from ai_workplace.security.authorization import _DEFAULT_POLICIES


def setup_default_security_policies(force: bool = False) -> None:
    if not frappe.db.exists("DocType", "WhatsApp Service Security Policy"):
        return

    for service_key, level in _DEFAULT_POLICIES.items():
        if not force and frappe.db.exists("WhatsApp Service Security Policy", service_key):
            continue
        doc = frappe.get_doc(
            {
                "doctype": "WhatsApp Service Security Policy",
                "service_key": service_key,
                "title": service_key.replace("_", " ").title(),
                "security_level": level,
                "is_active": 1,
            }
        )
        if frappe.db.exists("WhatsApp Service Security Policy", service_key):
            existing = frappe.get_doc("WhatsApp Service Security Policy", service_key)
            existing.security_level = level
            existing.is_active = 1
            existing.flags.ignore_permissions = True
            existing.save(ignore_permissions=True)
        else:
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    frappe.cache().delete_value("wa_sec_policy:*")
