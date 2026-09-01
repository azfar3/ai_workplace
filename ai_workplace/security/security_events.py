"""Security audit events for Support PIN."""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe


PIN_EVENT_MAP = {
    "PIN_SET": ("PIN Set", "Low"),
    "PIN_VERIFICATION_SUCCESS": ("PIN Verification Success", "Low"),
    "PIN_VERIFICATION_FAILED": ("PIN Verification Failed", "Medium"),
    "PIN_LOCKED": ("PIN Locked", "High"),
    "PIN_SESSION_INVALID": ("PIN Session Invalid", "Medium"),
    "PIN_GATE_BLOCKED": ("PIN Gate Blocked", "Low"),
}


def log_pin_security_event(
    event_key: str,
    *,
    employee: str = "",
    user: str = "",
    description: str = "",
    metadata: Optional[dict[str, Any]] = None,
    trace_id: str = "",
) -> None:
    event_type, severity = PIN_EVENT_MAP.get(event_key, ("Other", "Medium"))
    try:
        doc = frappe.new_doc("AI Security Event")
        doc.event_type = event_type if event_type in _allowed_event_types() else "Other"
        doc.severity = severity
        doc.timestamp = frappe.utils.now_datetime()
        doc.trace_id = trace_id
        doc.employee = employee or None
        doc.erp_user = user or None
        doc.description = description or event_key
        if metadata:
            doc.metadata = json.dumps(metadata, default=str)
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title=f"PIN security event failed: {event_key}")


def _allowed_event_types() -> set[str]:
    return {
        "Invalid Webhook Signature",
        "Invalid Webhook Verification",
        "Duplicate Message",
        "Unknown Identity",
        "Ambiguous Identity",
        "Inactive Identity",
        "Rate Limit Exceeded",
        "Unauthorized Service Access",
        "Invalid Conversation State",
        "Expired Conversation",
        "Invalid Menu Selection",
        "Other",
    }
