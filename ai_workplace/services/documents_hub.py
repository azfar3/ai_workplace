"""
Documents & Contract hub and contract status for employees.
"""

from __future__ import annotations

import os
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
        return OutboundMessage(body_text=f"{body}\n\nHRMIS Portal: {PORTAL_URL}")

    if not contract.get("signature"):
        return build_portal_gap_guide(context, "contract_signature")

    start = contract.get("start_date") or "—"
    end = contract.get("end_date") or "—"
    body = (
        f"📃 *Employment Contract*\n\n"
        f"Status: *Signed*\n"
        f"Period: {start} to {end}\n\n"
        f"Your signed contract PDF is attached."
    )
    try:
        pdf_bytes, filename = _get_employee_contract_pdf(contract)
        return OutboundMessage(
            body_text=body,
            document_bytes=pdf_bytes,
            document_filename=filename,
            document_mimetype="application/pdf",
            document_caption=body,
        )
    except Exception:
        frappe.log_error(
            title="Employee Contract PDF Retrieval Failed",
            message=frappe.get_traceback(),
        )
        return OutboundMessage(
            body_text=(
                f"{body}\n\n"
                f"I couldn't prepare the PDF right now. You can view the contract on the HRMIS Portal: {PORTAL_URL}"
            )
        )


def _get_employee_contract_pdf(contract: dict[str, Any]) -> tuple[bytes, str]:
    """Read the signed PDF attachment or render the employee contract as PDF."""
    contract_name = contract.get("name") or ""
    contract_doc = frappe.get_doc("Employee Contract", contract_name)
    meta = frappe.get_meta("Employee Contract")

    file_candidates: list[Any] = []
    for field in meta.fields:
        if field.fieldtype not in ("Attach", "Attach Image"):
            continue
        field_value = contract_doc.get(field.fieldname)
        if field_value:
            file_candidates.append(field_value)

    attached_files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Employee Contract",
            "attached_to_name": contract_name,
        },
        fields=["name", "file_name", "file_url", "is_private"],
        order_by="creation desc",
        limit_page_length=100,
    )
    file_candidates.extend(attached_files)

    from ai_workplace.whatsapp.media import read_frappe_file_bytes

    seen: set[str] = set()
    for candidate in file_candidates:
        if isinstance(candidate, str):
            file_name = frappe.db.get_value("File", {"file_url": candidate}, "name")
            if not file_name and frappe.db.exists("File", candidate):
                file_name = candidate
        else:
            file_name = candidate.get("name") if isinstance(candidate, dict) else None
        if not file_name or file_name in seen:
            continue
        seen.add(file_name)

        try:
            file_doc = frappe.get_doc("File", file_name)
            filename = file_doc.file_name or os.path.basename(file_doc.file_url or "")
            if not filename.lower().endswith(".pdf"):
                continue
            content, filename, mime_type = read_frappe_file_bytes(file_doc)
            if content and (mime_type == "application/pdf" or filename.lower().endswith(".pdf")):
                return content, filename
        except Exception:
            continue

    previous_user = frappe.session.user
    previous_form_dict = frappe.local.form_dict
    try:
        frappe.set_user("Administrator")
        frappe.local.form_dict = frappe._dict()
        pdf_bytes = frappe.get_print(
            "Employee Contract",
            contract_name,
            as_pdf=True,
        )
    finally:
        frappe.local.form_dict = previous_form_dict
        frappe.set_user(previous_user)

    if not pdf_bytes:
        frappe.throw(_("No contract PDF is available."))
    return pdf_bytes, f"{contract_name}.pdf"


def _contract_portal_fallback() -> OutboundMessage:
    return OutboundMessage(
        body_text=f"I couldn't retrieve your contract details right now. Please check the HRMIS Portal: {PORTAL_URL}"
    )


def build_pin_help(context: dict[str, Any]) -> OutboundMessage:
    from ai_workplace.security.pin_flow import build_hrmis_portal_guide_message

    return build_hrmis_portal_guide_message(context)
