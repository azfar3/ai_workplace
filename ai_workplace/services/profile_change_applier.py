"""
Apply approved Employee Profile Change Requests to Employee records.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from ai_workplace.api.profile import ALLOWED_TICKET_FIELDS, BLOCKED_REQUEST_FIELDS, validate_cnic, validate_iban

TICKET_FIELD_REQUEST_TYPES = frozenset({
    "CNIC Change",
    "Bank Change",
    "Contact Change",
    "Profile Photo",
    "Document Upload",
    "Other",
})


def apply_approved_profile_request(docname: str) -> None:
    doc = frappe.get_doc("Employee Profile Change Request", docname)
    if doc.status == "Applied":
        return

    employee = frappe.get_doc("Employee", doc.employee)

    for item in doc.items or []:
        _apply_item(employee, doc.request_type, item)

    employee.flags.ignore_permissions = True
    employee.save(ignore_permissions=True)

    doc.status = "Applied"
    doc.applied_on = frappe.utils.now_datetime()
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        from ai_workplace.services.profile_gaps import get_employee_profile_gaps

        get_employee_profile_gaps(doc.employee)
    except Exception:
        pass


def _apply_item(employee: Any, request_type: str, item: Any) -> None:
    if request_type == "Education":
        row = employee.append("education", {})
        proposed = _parse_json(item.proposed_json)
        row.update(proposed)
        if item.attachment:
            row.upload_scan_copy = item.attachment
        return

    if request_type == "Work History":
        row = employee.append("external_work_history", {})
        proposed = _parse_json(item.proposed_json)
        row.update(proposed)
        if item.attachment:
            row.upload_scan_copy = item.attachment
        return

    if request_type == "Next of Kin":
        row = employee.append("next_of_kin", {})
        proposed = _parse_json(item.proposed_json)
        row.update(proposed)
        return

    if request_type in TICKET_FIELD_REQUEST_TYPES or item.proposed_json:
        proposed = _parse_json(item.proposed_json)
        if item.attachment and not any(k.endswith("_scan") or k in ("image", "police_character_certificate", "psea_certificate") for k in proposed):
            attachment_field = item.target_field or "attachment"
            if attachment_field in ALLOWED_TICKET_FIELDS:
                proposed[attachment_field] = item.attachment
        _apply_employee_fields(employee, proposed)
        return

    field = (item.target_field or "").strip()
    if field in BLOCKED_REQUEST_FIELDS:
        frappe.throw(f"Changes to {field} are not permitted via profile change requests.")
    if field and hasattr(employee, field):
        setattr(employee, item.target_field, item.proposed_value)


def _apply_employee_fields(employee: Any, proposed: dict) -> None:
    for field, value in (proposed or {}).items():
        if field in BLOCKED_REQUEST_FIELDS:
            frappe.throw(f"Changes to {field} are not permitted via profile change requests.")
        if field not in ALLOWED_TICKET_FIELDS:
            continue
        if not frappe.db.has_column("Employee", field):
            continue
        if field == "cnic":
            validate_cnic(str(value))
        if field == "iban":
            validate_iban(str(value))
        employee.set(field, value)


def _parse_json(raw: str) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}
