"""
ai_workplace/context/resolver.py
──────────────────────────────────
ERP Context Resolver — Phase 2.

Builds a controlled representation of an authenticated ERPNext user's context.
Determines person_type (Employee, Consultant, Guest), roles, allowed services,
and preferred language strictly from ERPNext records.
"""

from __future__ import annotations

from typing import Any, Optional
import frappe

from ai_workplace.identity.resolver import IdentityResult


def get_user_context(identity: IdentityResult | dict) -> dict[str, Any]:
    """
    Resolve the ERPNext context for the given identity.

    Parameters
    ----------
    identity : IdentityResult | dict
        Identity resolution object or dictionary.

    Returns
    -------
    dict
        Controlled ERPContext dictionary:
        {
            "user": str | None,
            "employee": str | None,
            "full_name": str | None,
            "person_type": "Employee" | "Consultant" | "Guest",
            "roles": list[str],
            "projects": list[str],
            "manager": str | None,
            "allowed_services": list[str],
            "preferred_language": "English" | "Urdu" | "Roman Urdu" | str,
            "whatsapp_identity": str | None,
        }
    """
    if isinstance(identity, dict):
        status = identity.get("status", "guest")
        user = identity.get("user")
        employee = identity.get("employee")
        full_name = identity.get("full_name")
        wa_identity_doc = identity.get("whatsapp_identity")
        normalized_phone = identity.get("normalized_phone")
    else:
        status = identity.status
        user = identity.user
        employee = identity.employee
        full_name = identity.full_name
        wa_identity_doc = identity.whatsapp_identity
        normalized_phone = identity.normalized_phone

    # Default guest context
    if status != "matched":
        pref_lang = _resolve_preferred_language(wa_identity_doc, user)
        return {
            "user": None,
            "employee": None,
            "full_name": None,
            "person_type": "Guest",
            "roles": [],
            "projects": [],
            "manager": None,
            "allowed_services": ["help"],
            "preferred_language": pref_lang,
            "whatsapp_identity": wa_identity_doc,
            "normalized_phone": normalized_phone,
        }

    # Retrieve user roles if user is present
    roles: list[str] = []
    if user:
        try:
            roles = frappe.get_roles(user) or []
        except Exception:
            roles = []

    # Retrieve employee data
    manager: Optional[str] = None
    employment_type: str = ""
    if employee and frappe.db.exists("Employee", employee):
        emp_doc = frappe.get_doc("Employee", employee)
        manager = getattr(emp_doc, "reports_to", None) or None
        employment_type = (getattr(emp_doc, "employment_type", "") or "").strip()
        if not full_name and getattr(emp_doc, "employee_name", None):
            full_name = emp_doc.employee_name

    # Determine Person Type (Employee vs Consultant vs Guest)
    # Check if employment_type or roles indicate a Consultant/Contractor
    person_type = "Employee"
    emp_type_lower = employment_type.lower()
    is_consultant = (
        "consultant" in emp_type_lower
        or "contractor" in emp_type_lower
        or any("consultant" in r.lower() or "contractor" in r.lower() for r in roles)
    )
    if is_consultant:
        person_type = "Consultant"

    # Define allowed services based on person_type
    if person_type == "Consultant":
        allowed_services = ["consultant", "policy", "travel", "help"]
    else:
        allowed_services = ["hr", "policy", "travel", "help"]

    # Preferred language resolution
    pref_lang = _resolve_preferred_language(wa_identity_doc, user)

    return {
        "user": user,
        "employee": employee,
        "full_name": full_name,
        "person_type": person_type,
        "roles": roles,
        "projects": [],
        "manager": manager,
        "allowed_services": allowed_services,
        "preferred_language": pref_lang,
        "whatsapp_identity": wa_identity_doc,
        "normalized_phone": normalized_phone,
    }


def _resolve_preferred_language(wa_identity_doc: Optional[str], user: Optional[str]) -> str:
    """Resolve preferred language from WhatsApp Identity, User, or Settings."""
    lang = "English"

    if wa_identity_doc and frappe.db.exists("WhatsApp Identity", wa_identity_doc):
        stored_lang = frappe.db.get_value("WhatsApp Identity", wa_identity_doc, "preferred_language")
        if stored_lang:
            lang = _normalize_language_name(stored_lang)
            return lang

    if user and frappe.db.exists("User", user):
        user_lang = frappe.db.get_value("User", user, "language")
        if user_lang:
            lang = _normalize_language_name(user_lang)
            return lang

    try:
        settings = frappe.get_single("AI Workplace Settings")
        default_lang = settings.get("default_language") or "English"
        lang = _normalize_language_name(default_lang)
    except Exception:
        lang = "English"

    return lang


def _normalize_language_name(lang_str: str) -> str:
    """Map language code or raw string to canonical English / Urdu / Roman Urdu."""
    if not lang_str:
        return "English"
    val = lang_str.strip().lower()
    if val in ("ur", "urdu", "اردو"):
        return "Urdu"
    if val in ("roman_urdu", "roman urdu", "roman-urdu", "ur_roman"):
        return "Roman Urdu"
    if val in ("en", "english"):
        return "English"
    return lang_str.title()
