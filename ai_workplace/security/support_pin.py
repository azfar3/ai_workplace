"""
Support PIN — hash, verify, lockout, profile management.
PIN is set only via HRMIS Portal APIs; WhatsApp verifies only.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

import frappe
from frappe.utils import cint, now_datetime

from frappe.utils.password import passlibctx

from ai_workplace.security.security_events import log_pin_security_event

WEAK_PINS = frozenset(
    {
        "0000",
        "1111",
        "2222",
        "3333",
        "4444",
        "5555",
        "6666",
        "7777",
        "8888",
        "9999",
        "1234",
        "4321",
        "1212",
        "1122",
    }
)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 30
PIN_PATTERN = re.compile(r"^\d{4}$")


def validate_pin_format(pin: str) -> tuple[bool, str]:
    """Return (valid, error_message)."""
    if not pin or not PIN_PATTERN.match(str(pin).strip()):
        return False, "Please enter a 4-digit numeric PIN."
    if pin in WEAK_PINS:
        return False, "Please choose a less predictable 4-digit PIN."
    return True, ""


def hash_pin(pin: str) -> str:
    return passlibctx.hash(pin)


def verify_pin_hash(pin: str, pin_hash: str) -> bool:
    if not pin_hash:
        return False
    try:
        return passlibctx.verify(pin, pin_hash)
    except Exception:
        return False


def employee_support_pin_is_set(employee: str) -> bool:
    """True when Employee.custom_support_pin has a value (HRMIS profile field)."""
    if not employee:
        return False
    if not frappe.db.has_column("Employee", "custom_support_pin"):
        return False
    val = frappe.db.get_value("Employee", employee, "custom_support_pin")
    return bool(val and str(val).strip())


def verify_employee_support_pin(employee: str, pin: str) -> bool:
    """Verify PIN against Employee.custom_support_pin (Data field)."""
    if not employee_support_pin_is_set(employee):
        return False
    try:
        stored = frappe.db.get_value("Employee", employee, "custom_support_pin")
        if not stored:
            return False
        return str(stored).strip() == str(pin).strip()
    except Exception:
        return False


def _save_employee_support_pin(employee: str, pin: str) -> None:
    """Persist PIN to Employee.custom_support_pin (Data field) for HRMIS parity."""
    if not frappe.db.has_column("Employee", "custom_support_pin"):
        return
    frappe.db.set_value("Employee", employee, "custom_support_pin", str(pin).strip())


def get_security_profile_name(employee: str) -> Optional[str]:
    if not employee:
        return None
    return frappe.db.get_value("WhatsApp Security Profile", {"employee": employee}, "name")


def get_or_create_security_profile(employee: str, user: str = "") -> frappe.Document:
    name = get_security_profile_name(employee)
    if name:
        return frappe.get_doc("WhatsApp Security Profile", name)

    doc = frappe.new_doc("WhatsApp Security Profile")
    doc.employee = employee
    doc.user = user or frappe.db.get_value("Employee", employee, "user_id") or ""
    doc.pin_is_set = 0
    doc.pin_status = "Not Set"
    doc.failed_attempts = 0
    doc.security_version = 1
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def get_pin_status(employee: str) -> dict[str, Any]:
    configured = employee_support_pin_is_set(employee)
    profile_name = get_security_profile_name(employee)
    profile = frappe.get_doc("WhatsApp Security Profile", profile_name) if profile_name else None
    locked = is_profile_locked(profile) if profile else False
    return {
        "configured": configured,
        "status": (profile.pin_status if profile else ("Active" if configured else "Not Set")),
        "last_changed": profile.pin_changed_on if profile else None,
        "locked_until": profile.locked_until if profile and locked else None,
        "security_version": cint(profile.security_version) if profile else 1,
    }


def is_profile_locked(profile: frappe.Document) -> bool:
    if profile.pin_status == "Locked" and profile.locked_until:
        if profile.locked_until > now_datetime():
            return True
        _clear_lock(profile)
    return False


def _clear_lock(profile: frappe.Document) -> None:
    profile.failed_attempts = 0
    profile.locked_until = None
    if profile.pin_is_set:
        profile.pin_status = "Active"
    else:
        profile.pin_status = "Not Set"
    profile.flags.ignore_permissions = True
    profile.save(ignore_permissions=True)


def set_support_pin_for_employee(
    employee: str,
    new_pin: str,
    confirm_pin: str,
    user: str = "",
) -> dict[str, Any]:
    if new_pin != confirm_pin:
        frappe.throw("PIN and confirmation do not match.")

    valid, err = validate_pin_format(new_pin)
    if not valid:
        frappe.throw(err)

    profile = get_or_create_security_profile(employee, user=user)
    now = now_datetime()
    profile.pin_hash = hash_pin(new_pin)
    profile.pin_is_set = 1
    profile.pin_status = "Active"
    profile.failed_attempts = 0
    profile.locked_until = None
    profile.security_version = cint(profile.security_version) + 1
    if not profile.pin_created_on:
        profile.pin_created_on = now
    profile.pin_changed_on = now
    if user:
        profile.user = user
    profile.flags.ignore_permissions = True
    profile.save(ignore_permissions=True)

    _save_employee_support_pin(employee, new_pin)

    from ai_workplace.security.secure_session import invalidate_sessions_for_employee

    invalidate_sessions_for_employee(employee)
    _sync_employee_mirror_fields(employee, profile)
    log_pin_security_event("PIN_SET", employee=employee, user=user or profile.user)
    frappe.db.commit()

    return get_pin_status(employee)


def verify_support_pin(
    employee: str,
    pin: str,
    *,
    conversation: str = "",
    wa_id: str = "",
    user: str = "",
) -> dict[str, Any]:
    if not employee_support_pin_is_set(employee):
        profile = get_security_profile_name(employee)
        if not profile or not frappe.db.get_value("WhatsApp Security Profile", profile, "pin_is_set"):
            return {"success": False, "reason": "PIN_NOT_CONFIGURED"}

    profile = get_or_create_security_profile(employee, user=user)

    if is_profile_locked(profile):
        return {
            "success": False,
            "reason": "LOCKED",
            "locked_until": profile.locked_until,
        }

    pin_valid = False
    if employee_support_pin_is_set(employee):
        pin_valid = verify_employee_support_pin(employee, pin)
    elif profile.pin_is_set:
        pin_valid = verify_pin_hash(pin, profile.pin_hash or "")

    if not pin_valid:
        profile.failed_attempts = cint(profile.failed_attempts) + 1
        profile.last_failed_verification = now_datetime()
        if profile.failed_attempts >= MAX_FAILED_ATTEMPTS:
            profile.pin_status = "Locked"
            profile.locked_until = now_datetime() + timedelta(minutes=LOCKOUT_MINUTES)
            log_pin_security_event(
                "PIN_LOCKED",
                employee=employee,
                user=profile.user,
                metadata={"failed_attempts": profile.failed_attempts},
            )
        else:
            log_pin_security_event(
                "PIN_VERIFICATION_FAILED",
                employee=employee,
                user=profile.user,
                metadata={"failed_attempts": profile.failed_attempts},
            )
        profile.flags.ignore_permissions = True
        profile.save(ignore_permissions=True)
        frappe.db.commit()
        return {
            "success": False,
            "reason": "INVALID_PIN",
            "attempts_remaining": max(0, MAX_FAILED_ATTEMPTS - cint(profile.failed_attempts)),
            "locked_until": profile.locked_until,
        }

    profile.failed_attempts = 0
    profile.locked_until = None
    profile.pin_status = "Active"
    profile.pin_is_set = 1 if employee_support_pin_is_set(employee) else profile.pin_is_set
    profile.last_successful_verification = now_datetime()
    profile.flags.ignore_permissions = True
    profile.save(ignore_permissions=True)

    from ai_workplace.security.secure_session import create_secure_session

    session = create_secure_session(
        employee=employee,
        user=profile.user or user,
        conversation=conversation,
        wa_id=wa_id,
        security_version=cint(profile.security_version),
    )
    log_pin_security_event("PIN_VERIFICATION_SUCCESS", employee=employee, user=profile.user)
    frappe.db.commit()

    return {"success": True, "session": session}


def _sync_employee_mirror_fields(employee: str, profile: frappe.Document) -> None:
    """Optional read-only mirror fields on Employee for reporting."""
    try:
        if not frappe.db.has_column("Employee", "custom_whatsapp_support_pin_configured"):
            return
        frappe.db.set_value(
            "Employee",
            employee,
            {
                "custom_whatsapp_support_pin_configured": 1 if profile.pin_is_set else 0,
                "custom_whatsapp_support_pin_status": profile.pin_status,
                "custom_whatsapp_support_pin_last_changed": profile.pin_changed_on,
            },
            update_modified=False,
        )
    except Exception:
        pass
