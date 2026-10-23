"""
Documents & Contract hub and contract status for employees.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate, today

from ai_workplace.services.profile_completion import build_portal_gap_guide
from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.whatsapp.outbound import OutboundMessage

PORTAL_URL = "https://portal.micromerger.com"


def build_documents_hub(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "📄 *دستاویزات اور معاہدہ*\n\n"
            "اپنی ملازمت سے متعلق دستاویزات یہاں سے حاصل کریں۔"
        )
    else:
        body = (
            "📄 *Documents & Contract*\n\n"
            "Access your employment documents and HR letters here."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_doc_contract", "title": "Contract"},
            {"id": "svc_doc_salary_slip", "title": "Salary Slip"},
            {"id": "svc_doc_tax_cert", "title": "Tax Cert"},
        ],
    )


def build_contract_status(context: dict[str, Any]) -> OutboundMessage:
    employee = context.get("employee") or ""
    lang = context.get("preferred_language", "English")

    if not frappe.db.exists("DocType", "Employee Contract"):
        return _contract_portal_fallback()

    try:
        meta = frappe.get_meta("Employee Contract")
        available_fields = {field.fieldname for field in meta.fields}
        if "employee" not in available_fields or "signature" not in available_fields:
            frappe.logger("ai_workplace").warning(
                "Employee Contract lookup skipped: expected employee/signature fields are missing."
            )
            return _contract_portal_fallback()

        fields = ["name", "signature", "creation"]
        fields.extend(field for field in ("start_date", "end_date") if field in available_fields)
        rows = frappe.get_all(
            "Employee Contract",
            filters={"employee": employee},
            fields=fields,
            order_by="creation desc",
            limit=100,
        )
    except Exception:
        frappe.log_error(
            title="Employee Contract Lookup Failed",
            message=frappe.get_traceback(),
        )
        return _contract_portal_fallback()

    contract = rows[0] if rows else None
    has_contract_records = bool(rows)
    if rows and {"start_date", "end_date"}.issubset(available_fields):
        current_date = getdate(today())
        contract = next(
            (
                row for row in rows
                if (not row.get("start_date") or getdate(row["start_date"]) <= current_date)
                and (not row.get("end_date") or getdate(row["end_date"]) >= current_date)
            ),
            None,
        )

    if not contract:
        if lang == "Urdu":
            body = (
                "📃 *ملازمت کا معاہدہ*\n\n"
                "موجودہ تاریخوں کے مطابق کوئی فعال معاہدہ نہیں ملا۔ HRMIS Portal دیکھیں یا HR سے رابطہ کریں۔"
                if has_contract_records
                else "📃 *ملازمت کا معاہدہ*\n\nآپ کا معاہدہ HR کے ذریعے تیار کیا جا رہا ہے۔ تیار ہونے پر آپ کو HRMIS Portal کے ذریعے مطلع کیا جائے گا۔"
            )
        else:
            body = (
                "📃 *Employment Contract*\n\nNo contract is active for the current date. Please check the HRMIS Portal or contact HR."
                if has_contract_records
                else "📃 *Employment Contract*\n\nYour contract is being prepared by HR. You will be notified via the HRMIS Portal when it is ready for you."
            )
        return build_button_message(body, [{"id": "svc_open_hrmis", "title": "Open Portal"}, {"id": "svc_main_menu", "title": "Main Menu"}])

    if not contract.get("signature"):
        return build_portal_gap_guide(context, "contract_signature")

    start = contract.get("start_date") or "—"
    end = contract.get("end_date") or "—"
    body = (
        f"📃 *Employment Contract*\n\n"
        f"Status: *Signed*\n"
        f"Period: {start} to {end}\n\n"
        f"View full details on the HRMIS Portal."
    )
    return build_button_message(
        body,
        [{"id": "svc_open_hrmis", "title": "Open Portal"}, {"id": "svc_main_menu", "title": "Main Menu"}],
    )


def _contract_portal_fallback() -> OutboundMessage:
    return OutboundMessage(
        body_text=f"I couldn't retrieve your contract details right now. Please check the HRMIS Portal: {PORTAL_URL}"
    )


def build_pin_help(context: dict[str, Any]) -> OutboundMessage:
    from ai_workplace.security.pin_flow import build_hrmis_portal_guide_message

    return build_hrmis_portal_guide_message(context)
