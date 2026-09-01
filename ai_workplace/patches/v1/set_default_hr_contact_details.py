"""Set default HR contact phone and email on existing AI Workplace Settings records."""

import frappe

DEFAULT_PHONE = "051 8444 777"
DEFAULT_EMAIL = "hr@MicroMerger.com"


def execute():
    if not frappe.db.exists("DocType", "AI Workplace Settings"):
        return

    phone = (frappe.db.get_single_value("AI Workplace Settings", "hr_contact_phone") or "").strip()
    email = (frappe.db.get_single_value("AI Workplace Settings", "hr_contact_email") or "").strip()

    updates = {}
    if not phone:
        updates["hr_contact_phone"] = DEFAULT_PHONE
    if not email:
        updates["hr_contact_email"] = DEFAULT_EMAIL

    if not updates:
        return

    for field, value in updates.items():
        frappe.db.set_single_value("AI Workplace Settings", field, value)
    frappe.db.commit()
