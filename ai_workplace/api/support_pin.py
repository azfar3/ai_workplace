"""
Portal APIs for HRMIS Support PIN management.
WhatsApp verifies only — never set/reset PIN via WhatsApp.
"""

from __future__ import annotations

import frappe
from frappe import _

from ai_workplace.security.support_pin import (
    get_pin_status,
    set_support_pin_for_employee,
)


def _resolve_employee_for_user(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Not authenticated"), frappe.AuthenticationError)

    employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if not employee:
        frappe.throw(_("No active employee record linked to your account."))
    return employee


@frappe.whitelist()
def get_support_pin_status() -> dict:
    """Return PIN status for the authenticated HRMIS user. Never returns PIN or hash."""
    employee = _resolve_employee_for_user()
    status = get_pin_status(employee)
    return {
        "configured": status.get("configured"),
        "status": status.get("status"),
        "last_changed": status.get("last_changed"),
        "locked_until": status.get("locked_until"),
    }


@frappe.whitelist()
def set_support_pin(new_pin: str, confirm_pin: str) -> dict:
    """Set or change Support PIN for authenticated HRMIS user."""
    employee = _resolve_employee_for_user()
    user = frappe.session.user
    # Never log PIN parameters
    set_support_pin_for_employee(employee, new_pin, confirm_pin, user=user)
    return {
        "success": True,
        "message": _("Your MicroMerger Support PIN has been set successfully."),
        **get_support_pin_status(),
    }
