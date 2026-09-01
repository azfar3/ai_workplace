"""
24-hour secure WhatsApp sessions bound to employee + conversation + security_version.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

import frappe
from frappe.utils import cint, now_datetime

SESSION_TTL_SECONDS = 24 * 60 * 60
CACHE_PREFIX = "whatsapp_secure_session"


def _session_key(employee: str, conversation: str) -> str:
    return f"{CACHE_PREFIX}:{employee}:{conversation}"


def _employee_prefix(employee: str) -> str:
    return f"{CACHE_PREFIX}:{employee}:"


def create_secure_session(
    employee: str,
    user: str,
    conversation: str,
    wa_id: str,
    security_version: int,
) -> dict[str, Any]:
    now = now_datetime()
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    session = {
        "employee": employee,
        "user": user,
        "conversation": conversation,
        "wa_id": wa_id,
        "security_version": security_version,
        "verified_at": str(now),
        "expires_at": str(expires_at),
    }
    frappe.cache().set_value(
        _session_key(employee, conversation),
        session,
        expires_in_sec=SESSION_TTL_SECONDS,
    )
    return session


def get_secure_session(employee: str, conversation: str) -> Optional[dict[str, Any]]:
    if not employee or not conversation:
        return None
    return frappe.cache().get_value(_session_key(employee, conversation))


def has_valid_secure_session(
    employee: str,
    conversation: str,
    security_version: int,
) -> bool:
    session = get_secure_session(employee, conversation)
    if not session:
        return False
    if cint(session.get("security_version")) != cint(security_version):
        return False
    expires_at = session.get("expires_at")
    if expires_at and frappe.utils.get_datetime(expires_at) < now_datetime():
        invalidate_session(employee, conversation)
        return False
    return True


def invalidate_session(employee: str, conversation: str) -> None:
    frappe.cache().delete_value(_session_key(employee, conversation))


def invalidate_sessions_for_employee(employee: str) -> None:
    """Best-effort invalidation when security_version changes."""
    if not employee:
        return
    try:
        conv_names = frappe.get_all(
            "WhatsApp Conversation",
            filters={"employee": employee, "conversation_status": "Active"},
            pluck="name",
        )
        for conv in conv_names:
            invalidate_session(employee, conv)
    except Exception:
        pass
