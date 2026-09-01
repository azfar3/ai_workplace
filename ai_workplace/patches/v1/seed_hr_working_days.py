"""Seed default HR working days on existing AI Workplace Settings records."""

import frappe


def execute():
    settings = frappe.get_single("AI Workplace Settings")
    if settings.get("hr_working_days"):
        return

    doc = frappe.get_doc("AI Workplace Settings", settings.name)
    doc.validate()
    doc.save(ignore_permissions=True)
    frappe.db.commit()
