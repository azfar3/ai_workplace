"""
ai_workplace/identity/resolver.py
──────────────────────────────────
ERPNext Identity Resolver — Phase 1.

Resolves an incoming WhatsApp phone number against ERPNext User and Employee
records.  Returns a structured result dict describing the identity status.

Identity resolution strategy (based on field inspection):
  - Employee.cell_number      — personal mobile (most commonly used field)
  - Employee.company_mobile   — official/work mobile
  - User.phone                — phone field on User record
  - User.mobile_no            — mobile number on User record

Resolution rules:
  1. Normalize the incoming phone number to E.164.
  2. Query Employee records for matching cell_number / company_mobile.
  3. Query User records for matching phone / mobile_no.
  4. Merge results (an Employee links to a User via Employee.user_id).
  5. Evaluate status:
       matched   — exactly one active ERPNext identity found
       guest     — no identity found
       ambiguous — multiple distinct identities found
       inactive  — identity found but not active (user disabled / employee left)

Return schema:
  {
      "status":           "matched" | "guest" | "ambiguous" | "inactive",
      "user":             "email@example.com" | None,
      "employee":         "HR-EMP-0001" | None,
      "full_name":        "John Doe" | None,
      "normalized_phone": "+923001234567",
  }

Security:
  - Guest / ambiguous / inactive responses MUST NOT expose ERPNext data.
  - The caller is responsible for not forwarding internal fields to end users.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import frappe

from ai_workplace.identity.phone import normalize_phone_number, PhoneNormalizationError


# ──────────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IdentityResult:
    """Structured result returned by :func:`resolve_identity`."""

    status: str                         # matched | guest | ambiguous | inactive
    normalized_phone: str               # always set
    user: Optional[str] = None          # User.name (email)
    employee: Optional[str] = None      # Employee.name
    full_name: Optional[str] = None     # display name
    whatsapp_identity: Optional[str] = None # Docname of WhatsApp Identity record


    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "normalized_phone": self.normalized_phone,
            "user": self.user,
            "employee": self.employee,
            "full_name": self.full_name,
            "whatsapp_identity": self.whatsapp_identity,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Internal helper dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _Candidate:
    user: Optional[str] = None
    employee: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    project: Optional[str] = None

    def identity_key(self) -> str:
        """
        Returns a stable key representing this candidate's identity.
        Two candidates with the same (user, employee) pair are the same identity.
        """
        return f"{self.user or ''}::{self.employee or ''}"


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def resolve_identity(phone_number: str) -> IdentityResult:
    """
    Resolve *phone_number* to an ERPNext identity.

    Parameters
    ----------
    phone_number : str
        Raw phone number (any format).  Will be normalized internally.

    Returns
    -------
    IdentityResult
        Structured resolution result.  Always returns a result — never raises
        for business-logic reasons (only for genuine system errors).
    """
    # 1. Normalize
    try:
        normalized = normalize_phone_number(phone_number)
    except PhoneNormalizationError as exc:
        frappe.log_error(
            title="AI Workplace: Phone Normalization Failed",
            message=str(exc),
        )
        # Treat un-parseable numbers as guest.
        # Use the raw number as best we can.
        return IdentityResult(
            status="guest",
            normalized_phone=phone_number,
        )

    # 2. Search
    candidates = _find_candidates(normalized)

    # 3. Classify
    res = _classify(candidates, normalized)
    return res


def get_or_create_whatsapp_identity(identity: IdentityResult | dict, wa_id: str = "") -> str:
    """
    Ensure a WhatsApp Identity record exists in ERPNext for the given identity result.
    Returns the docname of the WhatsApp Identity record.
    """
    if isinstance(identity, dict):
        status = identity.get("status", "guest")
        normalized_phone = identity.get("normalized_phone", "")
        user = identity.get("user")
        employee = identity.get("employee")
    else:
        status = identity.status
        normalized_phone = identity.normalized_phone
        user = identity.user
        employee = identity.employee

    if not wa_id:
        import re
        wa_id = re.sub(r"\D", "", normalized_phone or "")

    status_map = {
        "matched": "Active",
        "guest": "Guest",
        "ambiguous": "Ambiguous",
        "inactive": "Inactive",
    }
    db_status = status_map.get(status, "Guest")

    docname = None
    if wa_id:
        docname = frappe.db.get_value("WhatsApp Identity", {"whatsapp_id": wa_id}, "name")
    if not docname and normalized_phone:
        docname = frappe.db.get_value("WhatsApp Identity", {"normalized_phone": normalized_phone}, "name")

    if docname:
        doc = frappe.get_doc("WhatsApp Identity", docname)
        doc.status = db_status
        if user:
            doc.erp_user = user
        if employee:
            doc.employee = employee
        doc.last_seen_at = frappe.utils.now_datetime()
        doc.flags.ignore_links = True
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    else:
        doc = frappe.new_doc("WhatsApp Identity")
        doc.whatsapp_id = wa_id or "unknown"
        doc.phone_number = normalized_phone
        doc.normalized_phone = normalized_phone
        doc.status = db_status
        doc.erp_user = user or None
        doc.employee = employee or None
        doc.preferred_language = "en"
        doc.last_seen_at = frappe.utils.now_datetime()
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name


# ──────────────────────────────────────────────────────────────────────────────
# Internal search helpers
# ──────────────────────────────────────────────────────────────────────────────

def _find_candidates(normalized_phone: str) -> list[_Candidate]:
    """
    Search Employee and User tables for *normalized_phone*.

    We compare the stored phone values (which may be in raw format) by
    normalizing them on-the-fly.  This is safe for the typical data volumes
    in an ERPNext installation (hundreds to low thousands of employees).

    For very large installations a custom index / stored normalized column
    (e.g. a Custom Field on Employee/User) would be more efficient and can
    be added in a future phase without changing this interface.
    """
    candidates: dict[str, _Candidate] = {}

    # ── Search Employees ──────────────────────────────────────────────────────
    employees = frappe.get_all(
        "Employee",
        fields=["name", "employee_name", "user_id", "status",
                "cell_number", "company_mobile", "project"],
        filters={"status": ["in", ["Active", "Left", "Inactive"]]},
        ignore_permissions=True,
    )

    for emp in employees:
        if _phone_field_matches(emp.get("cell_number"), normalized_phone) or \
           _phone_field_matches(emp.get("company_mobile"), normalized_phone):

            is_active = (emp.get("status") == "Active")
            c = _Candidate(
                employee=emp["name"],
                user=emp.get("user_id") or None,
                full_name=emp.get("employee_name"),
                is_active=is_active,
                project=emp.get("project") or None,
            )
            candidates[c.identity_key()] = c

    # ── Search Users ──────────────────────────────────────────────────────────
    # Only search enabled users (enabled=1) or disabled (0) to flag inactive.
    users = frappe.get_all(
        "User",
        fields=["name", "full_name", "enabled", "phone", "mobile_no"],
        filters={"name": ["not in", ["Guest", "Administrator"]]},
        ignore_permissions=True,
    )

    for usr in users:
        if _phone_field_matches(usr.get("phone"), normalized_phone) or \
           _phone_field_matches(usr.get("mobile_no"), normalized_phone):

            is_active = bool(usr.get("enabled"))
            # Try to find an existing candidate with this user already
            # (linked via Employee.user_id).  If found, enrich; else add.
            merged = False
            for key, cand in candidates.items():
                if cand.user == usr["name"]:
                    # Already captured via Employee; update active flag from User.
                    cand.is_active = cand.is_active and is_active
                    if not cand.full_name:
                        cand.full_name = usr.get("full_name")
                    merged = True
                    break

            if not merged:
                c = _Candidate(
                    user=usr["name"],
                    employee=None,
                    full_name=usr.get("full_name"),
                    is_active=is_active,
                    project=None,
                )
                candidates[c.identity_key()] = c

    return list(candidates.values())


def _phone_field_matches(stored: str | None, normalized_target: str) -> bool:
    """
    Return True if *stored* phone, when normalized, equals *normalized_target*.
    Returns False on any parse failure (do not crash on dirty data).
    """
    if not stored:
        return False
    try:
        from ai_workplace.identity.phone import normalize_phone_number
        return normalize_phone_number(stored) == normalized_target
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Classification
# ──────────────────────────────────────────────────────────────────────────────

def _classify(candidates: list[_Candidate], normalized_phone: str) -> IdentityResult:
    """
    Apply identity matching rules to the candidate list.
    
    Disambiguation Logic:
    1. Filter to candidates with is_active == True.
    2. If exactly 1 active profile exists -> matched.
    3. If > 1 active profiles exist:
       Check the 'project' field on each active profile.
       Prefer the active profile where 'project' is empty / not filled.
       If exactly 1 active profile has an empty project field -> matched.
    4. If all checks fail (e.g. multiple active with empty project or multiple with filled project) -> ambiguous.
    5. If 0 active candidates exist, but inactive candidates exist -> inactive.
    6. Otherwise -> guest.
    """
    if not candidates:
        return IdentityResult(
            status="guest",
            normalized_phone=normalized_phone,
        )

    active = [c for c in candidates if c.is_active]
    inactive = [c for c in candidates if not c.is_active]

    # Rule 1: Single active candidate found
    if len(active) == 1:
        c = active[0]
        return IdentityResult(
            status="matched",
            normalized_phone=normalized_phone,
            user=c.user,
            employee=c.employee,
            full_name=c.full_name,
        )

    # Rule 2: Multiple active candidates found -> Disambiguate by empty 'project' field
    if len(active) > 1:
        no_project_candidates = [c for c in active if not (c.project or "").strip()]

        if len(no_project_candidates) == 1:
            c = no_project_candidates[0]
            return IdentityResult(
                status="matched",
                normalized_phone=normalized_phone,
                user=c.user,
                employee=c.employee,
                full_name=c.full_name,
            )

        # Ambiguous if disambiguation fails
        return IdentityResult(
            status="ambiguous",
            normalized_phone=normalized_phone,
        )

    # Rule 3: No active candidates; check for inactive
    if inactive:
        return IdentityResult(
            status="inactive",
            normalized_phone=normalized_phone,
        )

    return IdentityResult(
        status="guest",
        normalized_phone=normalized_phone,
    )
