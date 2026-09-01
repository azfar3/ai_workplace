"""
Service-level PIN authorization middleware.
Extends auth/gateway.py (persona) with step-up PIN verification.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe
from frappe.utils import cint

from ai_workplace.security.support_pin import get_pin_status, is_profile_locked, get_or_create_security_profile
from ai_workplace.security.secure_session import has_valid_secure_session

from ai_workplace.security.menu_security import get_menu_item_security_policy

POLICY_NONE = "none"
POLICY_PIN_REQUIRED = "pin_required"
POLICY_PIN_PLUS_APPROVAL = "pin_plus_approval"

# Fallback for non-menu service keys (flows, navigation, internal actions).
_DEFAULT_POLICIES: dict[str, str] = {
    "main_menu": POLICY_NONE,
    "menu": POLICY_NONE,
    "help": POLICY_NONE,
    "language": POLICY_NONE,
    "hr_contact_phone": POLICY_NONE,
    "hr_contact_email": POLICY_NONE,
    "hr_contact_wait": POLICY_NONE,
    "prof_cnic_add": POLICY_PIN_PLUS_APPROVAL,
    "prof_bank_update": POLICY_PIN_PLUS_APPROVAL,
    "prof_contact_update": POLICY_PIN_REQUIRED,
    "prof_education_ticket": POLICY_PIN_PLUS_APPROVAL,
    "prof_work_history_ticket": POLICY_PIN_PLUS_APPROVAL,
    "svc_open_hrmis": POLICY_NONE,
    "svc_pin_set_done": POLICY_NONE,
}


def get_service_security_policy(service_key: str) -> str:
    if not service_key:
        return POLICY_NONE
    key = service_key.strip().lower()

    menu_policy = get_menu_item_security_policy(key)
    if menu_policy is not None:
        return menu_policy

    cached = frappe.cache().get_value(f"wa_sec_policy:{key}")
    if cached:
        return cached

    try:
        if frappe.db.exists("DocType", "WhatsApp Service Security Policy"):
            policy = frappe.db.get_value(
                "WhatsApp Service Security Policy",
                {"service_key": key, "is_active": 1},
                "security_level",
            )
            if policy:
                frappe.cache().set_value(f"wa_sec_policy:{key}", policy, expires_in_sec=300)
                return policy
    except Exception:
        pass

    return _DEFAULT_POLICIES.get(key, POLICY_NONE)


def requires_pin(service_key: str) -> bool:
    policy = get_service_security_policy(service_key)
    return policy in (POLICY_PIN_REQUIRED, POLICY_PIN_PLUS_APPROVAL)


def authorize_whatsapp_service(
    context: dict[str, Any],
    service_key: str,
    *,
    conversation_name: str = "",
) -> dict[str, Any]:
    """
    Returns:
      {allowed: True}
      {allowed: False, reason: PIN_NOT_CONFIGURED | PIN_REQUIRED | LOCKED, ...}
    """
    policy = get_service_security_policy(service_key)
    if policy == POLICY_NONE:
        return {"allowed": True, "policy": policy}

    employee = context.get("employee") or ""
    if not employee:
        return {"allowed": True, "policy": policy}

    pin_status = get_pin_status(employee)
    profile = get_or_create_security_profile(employee, user=context.get("user") or "")

    if is_profile_locked(profile):
        return {
            "allowed": False,
            "reason": "LOCKED",
            "locked_until": profile.locked_until,
            "policy": policy,
        }

    if not pin_status.get("configured"):
        return {
            "allowed": False,
            "reason": "PIN_NOT_CONFIGURED",
            "policy": policy,
        }

    if has_valid_secure_session(
        employee,
        conversation_name,
        cint(pin_status.get("security_version")),
    ):
        return {"allowed": True, "policy": policy}

    return {
        "allowed": False,
        "reason": "PIN_REQUIRED",
        "policy": policy,
        "pending_service_key": service_key,
    }


def store_pending_service(conv: Any, service_key: str, extra: Optional[dict] = None) -> str:
    payload = {"pending_service_key": service_key}
    if extra:
        payload.update(extra)
    return json.dumps(payload)


def get_pending_service(draft_payload: str) -> Optional[str]:
    if not draft_payload:
        return None
    try:
        data = json.loads(draft_payload)
        return data.get("pending_service_key")
    except Exception:
        return None
