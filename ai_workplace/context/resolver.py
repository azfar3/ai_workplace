"""
ai_workplace/context/resolver.py
──────────────────────────────────
ERP Context Resolver — Phase 2.

Builds a controlled representation of an authenticated ERPNext user's context.
Determines person_type, staff_category (permanent / project_contract / project_deliverable),
roles, allowed services, and preferred language strictly from ERPNext records.
"""

from __future__ import annotations

from typing import Any, Optional
import frappe
from frappe.utils import getdate, today

from ai_workplace.identity.resolver import IdentityResult

EMPLOYMENT_TYPE_CONTRACT = "Contract"
EMPLOYMENT_TYPE_DELIVERABLE = "Contract (Deliverable)"

EXPENSE_CLAIM_STRUCTURE_ASSIGNMENT_DOCTYPE = "Expense Claim Structure Assigment"

FULL_EMPLOYEE_SERVICES = [
    "hr",
    "attendance_leave",
    "payroll",
    "travel",
    "documents",
    "staff_support",
    "policies",
    "concerns",
    "contact_hr",
]

CONTRACT_STAFF_SERVICES = [
    "hr",
    "attendance_leave",
    "payroll",
    "travel",
    "documents",
    "staff_support",
    "policies",
    "concerns",
    "contact_hr",
]

DELIVERABLE_STAFF_SERVICES = [
    "hr",
    "deliverables",
    "payroll",
    "pay_tax_deduction",
    "pay_bank_letter",
    "pay_bank_faysal",
    "pay_bank_scb",
    "policies",
    "concerns",
    "contact_hr",
]

# Payroll submenu keys used to detect partial (documents-only) payroll access.
PAYROLL_SUBMENU_KEYS = frozenset(
    {
        "pay_download_slip",
        "pay_previous_slips",
        "pay_tax_deduction",
        "pay_experience_letter",
        "pay_bank_letter",
        "pay_bank_faysal",
        "pay_bank_scb",
    }
)


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
            "person_type": "Employee" | "Guest" | "Former Employee",
            "employment_type": str,
            "staff_category": "permanent" | "project_contract" | "project_deliverable",
            "has_travel_expense_structure": bool,
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

    # Guest or inactive identities — return public / former employee service context
    if status != "matched":
        pref_lang = _resolve_preferred_language(wa_identity_doc, user)
        is_inactive = status == "inactive"
        person_type = "Former Employee" if is_inactive else "Guest"

        if is_inactive:
            allowed_services = [
                "former_letter",
                "former_payslip",
                "former_verification",
                "former_concern",
                "former_careers",
                "contact_hr",
            ]
        else:
            allowed_services = [
                "guest_careers",
                "guest_job_status",
                "guest_verification",
                "guest_vendor",
                "guest_concern",
                "contact_hr",
                "guest_number_changed",
            ]

        image_url = _resolve_profile_image_url(employee, user)
        return {
            "user": user or None,
            "employee": employee or None,
            "full_name": full_name or None,
            "person_type": person_type,
            "identity_status": status,
            "roles": [],
            "projects": [],
            "manager": None,
            "allowed_services": allowed_services,
            "preferred_language": pref_lang,
            "whatsapp_identity": wa_identity_doc,
            "normalized_phone": normalized_phone,
            "image_url": image_url,
            "employment_type": "",
            "staff_category": "",
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

    person_type = "Employee"
    staff_category = _resolve_staff_category(employment_type)
    has_travel_expense_structure = has_active_expense_claim_structure_assignment(employee)
    allowed_services = _allowed_services_for_staff(staff_category, employee)

    # Preferred language resolution
    pref_lang = _resolve_preferred_language(wa_identity_doc, user)
    image_url = _resolve_profile_image_url(employee, user)

    return {
        "user": user,
        "employee": employee,
        "full_name": full_name,
        "person_type": person_type,
        "identity_status": status,
        "employment_type": employment_type,
        "staff_category": staff_category,
        "has_travel_expense_structure": has_travel_expense_structure,
        "roles": roles,
        "projects": [],
        "manager": manager,
        "allowed_services": allowed_services,
        "preferred_language": pref_lang,
        "whatsapp_identity": wa_identity_doc,
        "normalized_phone": normalized_phone,
        "image_url": image_url,
    }


def _resolve_staff_category(employment_type: str) -> str:
    """Map Employee.employment_type to staff_category for menu routing."""
    et = (employment_type or "").strip()
    if et == EMPLOYMENT_TYPE_DELIVERABLE:
        return "project_deliverable"
    if et == EMPLOYMENT_TYPE_CONTRACT:
        return "project_contract"
    return "permanent"


def _allowed_services_for_staff(staff_category: str, employee_id: Optional[str] = None) -> list[str]:
    if staff_category == "permanent":
        return list(FULL_EMPLOYEE_SERVICES)

    if staff_category == "project_deliverable":
        services = list(DELIVERABLE_STAFF_SERVICES)
    elif staff_category == "project_contract":
        services = list(CONTRACT_STAFF_SERVICES)
    else:
        return list(FULL_EMPLOYEE_SERVICES)

    if employee_id and has_active_expense_claim_structure_assignment(employee_id):
        _insert_travel_service(services)

    return services


def _insert_travel_service(services: list[str]) -> None:
    if "travel" in services:
        return
    if "policies" in services:
        services.insert(services.index("policies"), "travel")
    else:
        services.append("travel")


def has_active_expense_claim_structure_assignment(employee_id: Optional[str]) -> bool:
    """True when employee has an Expense Claim Structure Assigment effective on or before today."""
    if not employee_id or not getattr(frappe, "db", None):
        return False
    if not frappe.db.exists("Employee", employee_id):
        return False

    today_date = getdate(today())
    return bool(
        frappe.db.sql(
            """
            SELECT 1
            FROM `tabExpense Claim Structure Assigment`
            WHERE employee = %s
              AND (from_date IS NULL OR from_date <= %s)
            LIMIT 1
            """,
            (employee_id, today_date),
        )
    )


def _resolve_profile_image_url(employee: Optional[str], user: Optional[str]) -> Optional[str]:
    """Retrieve absolute profile picture URL from Employee or User document if present and publicly accessible."""
    image_path = None
    if employee and frappe.db and frappe.db.exists("Employee", employee):
        try:
            image_path = frappe.db.get_value("Employee", employee, "image")
        except Exception:
            image_path = None

    if not image_path and user and frappe.db and frappe.db.exists("User", user):
        try:
            image_path = frappe.db.get_value("User", user, "user_image")
        except Exception:
            image_path = None

    if not image_path:
        return None

    url = image_path
    if not (url.startswith("http://") or url.startswith("https://")):
        try:
            public_base = getattr(frappe.conf, "public_site_url", None)
            if public_base:
                url = f"{public_base.rstrip('/')}/{image_path.lstrip('/')}"
            elif hasattr(frappe, "utils") and hasattr(frappe.utils, "get_url"):
                url = frappe.utils.get_url(image_path)
        except Exception:
            url = image_path

    if _is_public_url(url):
        return url
    return None


def _is_public_url(url: str) -> bool:
    """Check if a URL is publicly accessible (http/https and not a local/private IP address)."""
    import ipaddress
    import urllib.parse

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        host_lower = hostname.lower()
        if host_lower in ("localhost", "127.0.0.1", "0.0.0.0") or host_lower.endswith(".local") or host_lower.endswith(".test"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False



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
