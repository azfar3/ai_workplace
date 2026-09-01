"""
Profile gap engine — unified completeness API for agent and proactive nudges.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_days, getdate, today

from ai_workplace.security.support_pin import get_pin_status

# Employee-facing labels (respectful, action-oriented)
EMPLOYEE_GAP_LABELS: dict[str, str] = {
    "support_pin_not_configured": "Set Support PIN (HRMIS Portal)",
    "profile_image": "Upload Profile Photo",
    "cnic": "Review CNIC Number",
    "cnic_scans": "Upload CNIC Scans",
    "cnic_expiry": "Update CNIC Expiry Date",
    "contact": "Review Contact Details",
    "bank": "Review Bank Details",
    "police_cert": "Upload Police Character Certificate",
    "psea_cert": "Upload PSEA Certificate",
    "declaration_conflict": "Declaration of Conflict of Interest",
    "contract_signature": "Contract Action Required",
    "education": "Add Education Record",
    "education_docs": "Upload Education Documents",
    "work_history": "Update Work History",
    "attendance_checkin": "Check In Today",
    "attendance_missing": "Review Missing Attendance",
}


def employee_gap_label(gap_key: str, default: str) -> str:
    return EMPLOYEE_GAP_LABELS.get(gap_key, default)


GAP_FLOW_MAP: dict[str, str] = {
    "profile_image": "prof_photo_upload",
    "cnic": "prof_cnic_add",
    "cnic_scans": "prof_cnic_add",
    "cnic_expiry": "prof_cnic_add",
    "contact": "prof_contact_update",
    "bank": "prof_bank_update",
    "education": "prof_education_ticket",
    "education_docs": "prof_education_ticket",
    "work_history": "prof_work_history_ticket",
}


def gap_flow_key(gap_key: str) -> str | None:
    return GAP_FLOW_MAP.get(gap_key)


def get_employee_profile_gaps(employee_id: str) -> dict[str, Any]:
    if not employee_id:
        return _empty_report()

    fields = [
        "name",
        "employee_name",
        "employment_type",
        "department",
        "designation",
        "company",
        "date_of_joining",
        "status",
        "image",
        "cnic",
        "cnic_scan_front",
        "cnic_scan_back",
        "date_of_issue",
        "valid_upto",
        "cell_number",
        "prefered_email",
        "emergency_phone_number",
        "bank_name",
        "bank_ac_no",
        "iban",
        "bank_account_title",
        "mobile_attendance",
    ]
    for optional in ("police_character_certificate", "psea_certificate"):
        if frappe.db.has_column("Employee", optional):
            fields.append(optional)

    emp = frappe.db.get_value("Employee", employee_id, fields, as_dict=True)
    if not emp:
        return _empty_report()

    gaps: list[dict[str, Any]] = []

    pin_status = get_pin_status(employee_id)
    if not pin_status.get("configured"):
        gaps.append(_gap("support_pin_not_configured", employee_gap_label("support_pin_not_configured", "Set Support PIN"), "critical", "portal_only"))

    if not emp.image:
        gaps.append(_gap("profile_image", employee_gap_label("profile_image", "Upload profile photo"), "medium", "ticket"))
    if not emp.cnic:
        gaps.append(_gap("cnic", employee_gap_label("cnic", "Review CNIC number"), "critical", "ticket"))
    if not (emp.cnic_scan_front and emp.cnic_scan_back):
        gaps.append(_gap("cnic_scans", employee_gap_label("cnic_scans", "Upload CNIC scans"), "critical", "ticket"))
    if emp.valid_upto and getdate(emp.valid_upto) <= getdate(today()):
        gaps.append(_gap("cnic_expiry", employee_gap_label("cnic_expiry", "Update CNIC expiry"), "critical", "ticket"))

    if not emp.cell_number or not emp.prefered_email:
        gaps.append(_gap("contact", employee_gap_label("contact", "Review contact details"), "medium", "ticket"))
    if not emp.bank_name or not emp.bank_ac_no:
        gaps.append(_gap("bank", employee_gap_label("bank", "Review bank details"), "critical", "ticket"))

    if frappe.db.has_column("Employee", "police_character_certificate"):
        if not emp.get("police_character_certificate"):
            gaps.append(_gap("police_cert", employee_gap_label("police_cert", "Upload police certificate"), "high", "ticket", "prof_doc_upload"))
    if frappe.db.has_column("Employee", "psea_certificate"):
        if not emp.get("psea_certificate"):
            gaps.append(_gap("psea_cert", employee_gap_label("psea_cert", "Upload PSEA certificate"), "high", "ticket", "prof_doc_upload"))

    _append_declaration_gap(employee_id, gaps)
    _append_contract_gap(employee_id, gaps)
    _append_education_gaps(employee_id, gaps)
    _append_work_history_gap(employee_id, gaps)
    _append_attendance_gaps(employee_id, gaps)

    score = max(0, 100 - len(gaps) * 8)
    critical = [g for g in gaps if g["severity"] == "critical"]
    recommended = gaps[0]["key"] if gaps else ""

    report = {
        "employee": employee_id,
        "employee_name": emp.employee_name,
        "employment_type": emp.employment_type or "",
        "department": emp.department or "",
        "designation": emp.designation or "",
        "company": emp.company or "",
        "date_of_joining": str(emp.date_of_joining) if emp.date_of_joining else "",
        "status": emp.status or "",
        "completeness_score": score,
        "critical_gaps": critical,
        "all_gaps": gaps,
        "recommended_next_action": recommended,
        "direct_flows_available": [g["key"] for g in gaps if g["update_mode"] == "direct"],
        "ticket_flows_available": [g["key"] for g in gaps if g["update_mode"] == "ticket"],
        "pending_tickets": _pending_tickets(employee_id),
    }
    _maybe_cache_score(employee_id, score)
    return report


def _append_declaration_gap(employee_id: str, gaps: list[dict[str, Any]]) -> None:
    if not frappe.db.exists("DocType", "Declaration of Conflict of Interest"):
        return
    rows = frappe.get_all(
        "Declaration of Conflict of Interest",
        filters={"employee": employee_id},
        fields=["docstatus"],
        order_by="creation desc",
        limit=1,
    )
    latest = rows[0] if rows else None
    if not latest or latest.docstatus != 1:
        gaps.append(_gap("declaration_conflict", employee_gap_label("declaration_conflict", "Declaration of Conflict"), "high", "portal_only"))


def _append_contract_gap(employee_id: str, gaps: list[dict[str, Any]]) -> None:
    if not frappe.db.exists("DocType", "Employee Contract"):
        return
    rows = frappe.get_all(
        "Employee Contract",
        filters={"employee": employee_id},
        fields=["name", "signature"],
        order_by="creation desc",
        limit=1,
    )
    contract = rows[0] if rows else None
    # Hide "contract not generated" — internal HR processing, no employee action.
    if contract and not contract.signature:
        gaps.append(
            _gap(
                "contract_signature",
                employee_gap_label("contract_signature", "Contract Action Required"),
                "medium",
                "portal_only",
            )
        )


def _append_education_gaps(employee_id: str, gaps: list[dict[str, Any]]) -> None:
    edu_count = frappe.db.count("Employee Education", {"parent": employee_id})
    if edu_count == 0:
        gaps.append(_gap("education", employee_gap_label("education", "Add education record"), "high", "ticket"))
        return
    missing_docs = frappe.db.count(
        "Employee Education",
        {"parent": employee_id, "upload_scan_copy": ["is", "not set"]},
    )
    if missing_docs:
        gaps.append(_gap("education_docs", employee_gap_label("education_docs", "Upload education documents"), "high", "ticket"))


def _append_work_history_gap(employee_id: str, gaps: list[dict[str, Any]]) -> None:
    work_count = frappe.db.count("Employee External Work History", {"parent": employee_id})
    if work_count == 0:
        gaps.append(_gap("work_history", employee_gap_label("work_history", "Update work history"), "medium", "ticket"))


def _append_attendance_gaps(employee_id: str, gaps: list[dict[str, Any]]) -> None:
    try:
        from ai_workplace.services.attendance_guidance import get_attendance_snapshot

        snap = get_attendance_snapshot(employee_id)
        if not snap.get("checked_in_today"):
            gaps.append(_gap("attendance_checkin", employee_gap_label("attendance_checkin", "Check in today"), "medium", "guidance_only"))
        if snap.get("missing_days_last_period", 0) > 0:
            gaps.append(
                _gap(
                    "attendance_missing",
                    employee_gap_label("attendance_missing", f"Review missing attendance ({snap['missing_days_last_period']} day(s))"),
                    "medium",
                    "guidance_only",
                )
            )
    except Exception:
        pass


def _gap(
    key: str,
    label: str,
    severity: str,
    update_mode: str,
    flow_key: str | None = None,
) -> dict[str, Any]:
    resolved_flow = flow_key or gap_flow_key(key)
    return {
        "key": key,
        "label": label,
        "severity": severity,
        "update_mode": update_mode,
        "status": "missing",
        "action_hint": label,
        "flow_key": resolved_flow,
    }


def _maybe_cache_score(employee_id: str, score: int) -> None:
    updates = {}
    if frappe.db.has_column("Employee", "custom_profile_completeness_score"):
        updates["custom_profile_completeness_score"] = score
    if frappe.db.has_column("Employee", "custom_profile_last_gap_check"):
        updates["custom_profile_last_gap_check"] = frappe.utils.now_datetime()
    if updates:
        frappe.db.set_value("Employee", employee_id, updates, update_modified=False)


def _pending_tickets(employee_id: str) -> list[dict[str, Any]]:
    if not frappe.db.exists("DocType", "Employee Profile Change Request"):
        return []
    return frappe.get_all(
        "Employee Profile Change Request",
        filters={"employee": employee_id, "status": ["not in", ["Applied", "Rejected"]]},
        fields=["name", "request_type", "status"],
        limit=5,
    )


def _empty_report() -> dict[str, Any]:
    return {
        "completeness_score": 0,
        "critical_gaps": [],
        "all_gaps": [],
        "recommended_next_action": "",
        "direct_flows_available": [],
        "ticket_flows_available": [],
        "pending_tickets": [],
    }
