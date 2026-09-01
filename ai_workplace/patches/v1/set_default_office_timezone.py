"""Set default office timezone on existing AI Workplace Settings records."""

import frappe

from ai_workplace.ai_workplace.doctype.ai_workplace_settings.ai_workplace_settings import (
    DEFAULT_OFFICE_TIMEZONE,
)


def execute():
    if not frappe.db.exists("DocType", "AI Workplace Settings"):
        return

    current = (
        frappe.db.get_single_value("AI Workplace Settings", "office_timezone")
        or frappe.db.get_single_value("AI Workplace Settings", "hr_office_timezone")
    )
    if (current or "").strip():
        return

    frappe.db.set_single_value(
        "AI Workplace Settings",
        "office_timezone",
        DEFAULT_OFFICE_TIMEZONE,
    )
    try:
        frappe.db.set_single_value(
            "AI Workplace Settings",
            "hr_office_timezone",
            DEFAULT_OFFICE_TIMEZONE,
        )
    except Exception:
        pass
    frappe.db.commit()
