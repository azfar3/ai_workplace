"""
ai_workplace/auth/gateway.py
───────────────────────────────
Authorization Gateway — Phase 2.

Enforces deterministic authorization rules before any conversation, service routing,
or AI context creation takes place.  The AI NEVER decides authorization.
"""

from __future__ import annotations

from typing import Any, Optional


import frappe


PAYROLL_DOCUMENT_KEYS = frozenset(
    {
        "pay_tax_deduction",
        "pay_bank_letter",
        "pay_bank_faysal",
        "pay_bank_scb",
    }
)

PAYROLL_SALARY_SLIP_KEYS = frozenset(
    {
        "pay_slip_1m",
        "pay_slip_3m",
        "pay_slip_6m",
        "pay_download_slip",
        "pay_previous_slips",
    }
)

PROFILE_FLOW_KEYS = frozenset(
    {
        "update_profile",
        "prof_my_requests",
        "prof_cnic_add",
        "prof_bank_update",
        "prof_contact_update",
        "prof_photo_upload",
        "prof_doc_upload",
        "prof_education_ticket",
        "prof_work_history_ticket",
    }
)


def _has_full_payroll_access(allowed_services: list[str]) -> bool:
    """True when staff may download salary slips, not just tax/bank documents."""
    allowed = {s.lower() for s in allowed_services if s}
    if allowed & PAYROLL_SALARY_SLIP_KEYS:
        return True
    if "payroll" in allowed and not (allowed & PAYROLL_DOCUMENT_KEYS):
        return True
    return False


def authorize(
    identity: Any,
    context: dict[str, Any],
    service: str,
    action: Optional[str] = None,
) -> dict[str, Any]:
    """
    Evaluate authorization for a specific service and action.
    """
    service_clean = (service or "").strip().lower()
    allowed_services = [s.lower() for s in context.get("allowed_services", [])]

    # Unregistered / no protected services — deny everything
    if not allowed_services:
        return {
            "allowed": False,
            "service": service_clean,
            "action": action,
            "reason": "GUEST_RESTRICTED",
        }

    # Direct match in allowed services
    if service_clean in allowed_services:
        return {
            "allowed": True,
            "service": service_clean,
            "action": action or "view",
            "reason": None,
        }

    # Deliverable sub-actions (Add / Submit / Status under deliverables menu)
    if service_clean in ("dlv_add", "dlv_submit", "dlv_status", "dlv_submit_now"):
        if "deliverables" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean.startswith("dlv_pick_"):
        if "deliverables" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Monthly attendance sub-actions (buttons after summary)
    if service_clean in ("att_monthly_last7", "att_monthly_download", "att_monthly"):
        if "attendance_leave" in allowed_services or "att_monthly" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean in ("att_checkin", "att_checkout", "att_retry_location", "att_request_exception"):
        if "attendance_leave" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean.startswith("att_exc_"):
        if "attendance_leave" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Salary slip / tax certificate / letter download sub-actions
    if service_clean in PAYROLL_SALARY_SLIP_KEYS:
        if "former_payslip" in allowed_services or (
            _has_full_payroll_access(allowed_services)
            and ("payroll" in allowed_services or service_clean in allowed_services)
        ):
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Profile completion hub flows (under My HR)
    if service_clean in PROFILE_FLOW_KEYS or service_clean.startswith("prof_"):
        if "hr" in allowed_services or service_clean in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean.startswith("gap_"):
        if "hr" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Policies & Help submenu and policy document picks
    if service_clean.startswith("pol_"):
        if "policies" in allowed_services or "policy" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean in (
        "pay_tax_deduction",
        "pay_bank_letter",
        "pay_bank_faysal",
        "pay_bank_scb",
        "former_payslip",
        "former_letter",
    ):
        if (
            "payroll" in allowed_services
            or service_clean in allowed_services
            or "former_payslip" in allowed_services
            or "former_letter" in allowed_services
        ):
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean == "pay_experience_letter":
        if _has_full_payroll_access(allowed_services) and "payroll" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Documents submenu aliases (under documents parent)
    if service_clean in ("doc_salary_slip", "doc_tax_cert", "doc_experience_letter", "doc_bank_letter", "doc_contract", "doc_my_requests"):
        if "documents" in allowed_services or "payroll" in allowed_services or "hr" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean in ("my_day", "hr_pin_help", "staff_hr_guidance", "staff_supervisor", "staff_contact_hr"):
        if "hr" in allowed_services or "staff_support" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    if service_clean == "concerns":
        if "staff_support" in allowed_services or "concerns" in allowed_services:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Check if parent menu item is in allowed_services
    parent_key = None
    if frappe.db and frappe.db.exists("WhatsApp Menu Item", service_clean):
        item = frappe.get_doc("WhatsApp Menu Item", service_clean)
        parent_key = item.parent_menu_item

    if parent_key and parent_key.lower() in allowed_services:
        if parent_key.lower() == "payroll":
            if service_clean in PAYROLL_SALARY_SLIP_KEYS and not _has_full_payroll_access(allowed_services):
                pass
            elif service_clean == "pay_experience_letter" and not _has_full_payroll_access(allowed_services):
                pass
            else:
                return {
                    "allowed": True,
                    "service": service_clean,
                    "action": action or "view",
                    "reason": None,
                }
        else:
            return {
                "allowed": True,
                "service": service_clean,
                "action": action or "view",
                "reason": None,
            }

    # Check parent prefix match (e.g. hr_profile -> hr)
    parent_part = service_clean.split("_")[0]
    if parent_part in allowed_services:
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


