"""
ai_workplace/auth/gateway.py
───────────────────────────────
Authorization Gateway — Phase 2.

Enforces deterministic authorization rules before any conversation, service routing,
or AI context creation takes place.  The AI NEVER decides authorization.
"""

from __future__ import annotations

from typing import Any, Optional


def authorize(
    identity: Any,
    context: dict[str, Any],
    service: str,
    action: Optional[str] = None,
) -> dict[str, Any]:
    """
    Evaluate authorization for a specific service and action.

    Parameters
    ----------
    identity : Any
        IdentityResult object or dictionary.
    context : dict
        Resolved ERP user context from get_user_context.
    service : str
        Target service name (e.g. "hr", "policy", "travel", "consultant", "help").
    action : str, optional
        Specific action within the service.

    Returns
    -------
    dict
        Authorization decision:
        {
            "allowed": bool,
            "service": str,
            "action": str | None,
            "reason": str | None,
        }
    """
    service_clean = (service or "").strip().lower()
    person_type = context.get("person_type", "Guest")
    allowed_services = [s.lower() for s in context.get("allowed_services", [])]

    # Guest user restriction: Guest can ONLY access 'help'
    if person_type == "Guest":
        if service_clean == "help":
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }
        return {
            "allowed": False,
            "service": service_clean,
            "action": action,
            "reason": "GUEST_RESTRICTED",
        }

    # Authenticated user (Employee / Consultant): Check allowed services
    if service_clean in allowed_services:
        return {
            "allowed": True,
            "service": service_clean,
            "action": action or "view",
            "reason": None,
        }

    # Reject unauthorized service request
    return {
        "allowed": False,
        "service": service_clean,
        "action": action,
        "reason": "SERVICE_NOT_ALLOWED",
    }
