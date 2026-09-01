"""
Profile update APIs — HR-approved EPCR tickets and applier-only direct writes.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

# Fields employees may propose via EPCR; applied only after HR approval.
ALLOWED_TICKET_FIELDS = {
    "cnic",
    "cnic_scan_front",
    "cnic_scan_back",
    "date_of_issue",
    "valid_upto",
    "bank_name",
    "bank_ac_no",
    "iban",
    "bank_account_title",
    "cell_number",
    "prefered_email",
    "personal_email",
    "emergency_phone_number",
    "current_address",
    "permanent_address",
    "image",
    "police_character_certificate",
    "psea_certificate",
}

# Never allowed via profile change requests (HR-only employee master data).
BLOCKED_REQUEST_FIELDS = frozenset({
    "designation",
    "department",
    "reports_to",
    "employment_type",
    "status",
    "salary",
})

DIRECT_FIELDS = {
    "cnic",
    "cnic_scan_front",
    "cnic_scan_back",
    "date_of_issue",
    "valid_upto",
    "bank_name",
    "bank_ac_no",
    "iban",
    "bank_account_title",
    "cell_number",
    "prefered_email",
    "personal_email",
    "emergency_phone_number",
    "current_address",
    "permanent_address",
    "image",
    "police_character_certificate",
    "psea_certificate",
}


def validate_cnic(cnic: str) -> None:
    clean = re.sub(r"\D", "", (cnic or "").strip())
    if len(clean) != 13:
        frappe.throw("CNIC must be 13 digits (without dashes).")


def validate_iban(iban: str) -> None:
    if not iban:
        return
    try:
        from mm_app.mm_app.overrides.hr.employee import validate_pakistan_iban

        if not validate_pakistan_iban(iban):
            frappe.throw("Invalid Pakistan IBAN format.")
    except ImportError:
        clean = iban.replace(" ", "").upper()
        if len(clean) != 24 or not clean.startswith("PK"):
            frappe.throw("Invalid IBAN format.")


@frappe.whitelist()
def apply_direct_profile_update(employee: str, field_updates: dict | str) -> dict:
    return _apply_direct_profile_update(employee, field_updates)


def _apply_direct_profile_update(
    employee: str,
    field_updates: dict | str,
    *,
    skip_scope_check: bool = False,
) -> dict:
    if isinstance(field_updates, str):
        import json

        field_updates = json.loads(field_updates)

    if not skip_scope_check:
        _assert_employee_scope(employee)
    updates = {k: v for k, v in (field_updates or {}).items() if k in DIRECT_FIELDS and v not in (None, "")}
    if not updates:
        frappe.throw("No allowed fields to update.")

    if "cnic" in updates:
        validate_cnic(str(updates["cnic"]))
    if "iban" in updates:
        validate_iban(str(updates["iban"]))

    doc = frappe.get_doc("Employee", employee)
    for field, value in updates.items():
        if not frappe.db.has_column("Employee", field):
            continue
        doc.set(field, value)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        from ai_workplace.services.profile_gaps import get_employee_profile_gaps

        get_employee_profile_gaps(employee)
    except Exception:
        pass

    return {"success": True, "updated_fields": list(updates.keys())}


def apply_whatsapp_profile_update(
    employee: str,
    field_updates: dict | str,
    context: dict | None = None,
) -> dict:
    """
    Apply direct profile updates from a verified WhatsApp conversation.
    Runs as the employee ERP user (or Administrator) after identity checks.
    """
    context = context or {}
    if not employee:
        frappe.throw("Employee is required.")
    if context.get("employee") and context.get("employee") != employee:
        frappe.throw("Employee mismatch.", frappe.PermissionError)

    prev_user = frappe.session.user
    try:
        erp_user = context.get("erp_user") or context.get("user")
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)
        else:
            frappe.set_user("Administrator")
        return _apply_direct_profile_update(employee, field_updates, skip_scope_check=True)
    finally:
        frappe.set_user(prev_user)


def _parse_proposed_json(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


CHILD_ROW_KEYS = frozenset({
    "qualification",
    "school_univ",
    "year_of_passing",
    "company_name",
    "designation",
    "employment_period",
    "name",
    "relationship",
    "phone",
})


def _validate_ticket_items(items: list[dict], request_type: str = "") -> None:
    for item in items or []:
        field = (item.get("field") or item.get("target_field") or "").strip()
        if field in BLOCKED_REQUEST_FIELDS:
            frappe.throw(
                "Designation and other employment master-data changes cannot be submitted. Please contact HR.",
                title="Change Not Allowed",
            )
        proposed = _parse_proposed_json(item.get("proposed_json"))
        for key in proposed:
            if key in BLOCKED_REQUEST_FIELDS:
                if key == "designation" and request_type == "Work History":
                    continue
                frappe.throw(
                    "Designation and other employment master-data changes cannot be submitted. Please contact HR.",
                    title="Change Not Allowed",
                )
            if key in CHILD_ROW_KEYS:
                continue
            if key not in ALLOWED_TICKET_FIELDS:
                frappe.throw(f"Field '{key}' cannot be changed via profile request.", title="Change Not Allowed")


def _validate_ticket_request_type(request_type: str, items: list[dict]) -> None:
    if request_type in BLOCKED_REQUEST_FIELDS:
        frappe.throw("This change type is not allowed.", title="Change Not Allowed")
    for item in items or []:
        proposed = _parse_proposed_json(item.get("proposed_json"))
        if request_type == "CNIC Change" and "cnic" in proposed:
            validate_cnic(str(proposed["cnic"]))
        if request_type == "Bank Change" and proposed.get("iban"):
            validate_iban(str(proposed["iban"]))


@frappe.whitelist()
def submit_profile_change_request(
    employee: str,
    request_type: str,
    items: list | str,
    requested_via: str = "WhatsApp",
) -> dict:
    return _submit_profile_change_request(employee, request_type, items, requested_via=requested_via)


def _submit_profile_change_request(
    employee: str,
    request_type: str,
    items: list | str,
    *,
    requested_via: str = "WhatsApp",
    skip_scope_check: bool = False,
) -> dict:
    if isinstance(items, str):
        items = json.loads(items)

    if not skip_scope_check:
        _assert_employee_scope(employee)
    _validate_ticket_items(items, request_type)
    _validate_ticket_request_type(request_type, items)
    doc = frappe.new_doc("Employee Profile Change Request")
    doc.employee = employee
    doc.employee_name = frappe.db.get_value("Employee", employee, "employee_name")
    doc.request_type = request_type
    doc.status = "Submitted"
    doc.workflow_state = "Pending HR Review"
    doc.requested_via = requested_via
    doc.submitted_on = frappe.utils.now_datetime()
    for item in items or []:
        doc.append(
            "items",
            {
                "target_field": item.get("field", ""),
                "proposed_value": item.get("value", ""),
                "proposed_json": item.get("proposed_json", ""),
                "attachment": item.get("attachment", ""),
            },
        )
    doc.insert(ignore_permissions=True)

    for item in doc.items:
        if item.attachment:
            file_name = frappe.db.get_value("File", {"file_url": item.attachment}, "name")
            if file_name:
                file_doc = frappe.get_doc("File", file_name)
                if not file_doc.attached_to_doctype:
                    file_doc.attached_to_doctype = doc.doctype
                    file_doc.attached_to_name = doc.name
                    file_doc.save(ignore_permissions=True)

                temp_media = frappe.db.get_value("WhatsApp Temporary Media", {"file_reference": file_name}, "name")
                if temp_media:
                    frappe.db.set_value("WhatsApp Temporary Media", temp_media, "status", "Processed")

    frappe.db.commit()
    return {"success": True, "name": doc.name, "status": doc.status}


def submit_whatsapp_profile_change_request(
    employee: str,
    request_type: str,
    items: list | str,
    context: dict | None = None,
    requested_via: str = "WhatsApp",
) -> dict:
    """
    Submit an EPCR from a verified WhatsApp conversation.
    Runs as the employee ERP user (or Administrator) after identity checks.
    """
    context = context or {}
    if not employee:
        frappe.throw("Employee is required.")
    if context.get("employee") and context.get("employee") != employee:
        frappe.throw("Employee mismatch.", frappe.PermissionError)

    prev_user = frappe.session.user
    try:
        erp_user = context.get("erp_user") or context.get("user")
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)
        else:
            frappe.set_user("Administrator")
        return _submit_profile_change_request(
            employee,
            request_type,
            items,
            requested_via=requested_via,
            skip_scope_check=True,
        )
    finally:
        frappe.set_user(prev_user)


@frappe.whitelist()
def get_pending_profile_requests(employee: str = "") -> list[dict[str, Any]]:
    employee = employee or _resolve_employee()
    return frappe.get_all(
        "Employee Profile Change Request",
        filters={"employee": employee},
        fields=["name", "request_type", "status", "workflow_state", "modified"],
        order_by="modified desc",
        limit=20,
    )


def _assert_employee_scope(employee: str) -> None:
    if frappe.session.user == "Administrator":
        return
    linked = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if linked != employee:
        frappe.throw("Not permitted to update this employee profile.", frappe.PermissionError)


def _resolve_employee() -> str:
    emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
    if not emp:
        frappe.throw("No active employee linked to your account.")
    return emp
