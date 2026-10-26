"""
Documents & Contract hub and contract status for employees.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import frappe
from ai_workplace.services.profile_completion import build_portal_gap_guide
from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.config import BOT_PDF_LETTERHEAD

PORTAL_URL = "https://portal.micromerger.com"
CONTRACT_PDF_TIMEOUT_SECONDS = 120


class ContractPdfRenderTimeout(TimeoutError):
    """Raised when Employee Contract PDF rendering exceeds its time limit."""


def _kill_new_child_processes(existing_pids: set[int]) -> None:
    """Stop renderer subprocesses launched during this PDF render."""
    try:
        import psutil

        children = psutil.Process(os.getpid()).children(recursive=True)
    except Exception:
        return

    for child in children:
        if child.pid in existing_pids:
            continue
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    for child in children:
        if child.pid in existing_pids:
            continue
        try:
            child.wait(timeout=2)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            continue


def _render_contract_pdf_with_timeout(contract_name: str) -> bytes:
    """Render the PDF and kill renderer subprocesses after 120 seconds."""
    import psutil

    try:
        before_pids = {
            process.pid
            for process in psutil.Process(os.getpid()).children(recursive=True)
        }
    except psutil.Error:
        before_pids = set()
    timed_out = threading.Event()

    def _stop_renderer_processes():
        timed_out.set()
        _kill_new_child_processes(before_pids)

    timeout_timer = threading.Timer(CONTRACT_PDF_TIMEOUT_SECONDS, _stop_renderer_processes)
    timeout_timer.daemon = True
    previous_user = frappe.session.user
    previous_form_dict = frappe.local.form_dict
    timeout_timer.start()
    try:
        frappe.set_user("Administrator")
        frappe.local.form_dict = frappe._dict()
        try:
            pdf_bytes = frappe.get_print(
                "Employee Contract",
                contract_name,
                print_format="Employee Contract Print",
                as_pdf=True,
                letterhead=BOT_PDF_LETTERHEAD,
            )
        except Exception as exc:
            if timed_out.is_set():
                raise ContractPdfRenderTimeout(
                    f"Employee Contract PDF rendering exceeded {CONTRACT_PDF_TIMEOUT_SECONDS} seconds."
                ) from exc
            raise
        if timed_out.is_set():
            raise ContractPdfRenderTimeout(
                f"Employee Contract PDF rendering exceeded {CONTRACT_PDF_TIMEOUT_SECONDS} seconds."
            )
        if not pdf_bytes or not bytes(pdf_bytes).startswith(b"%PDF"):
            frappe.throw("Employee Contract PDF generation returned invalid data.")
        return bytes(pdf_bytes)
    finally:
        timeout_timer.cancel()
        frappe.local.form_dict = previous_form_dict
        frappe.set_user(previous_user)


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
        fields.extend(
            field
            for field in ("contract_start_date", "contract_end_date", "verification_status")
            if field in available_fields
        )
        rows = frappe.get_all(
            "Employee Contract",
            filters={"employee": employee},
            fields=fields,
            order_by="creation desc, name desc",
            limit_page_length=1,
        )
    except Exception:
        frappe.log_error(
            title="Employee Contract Lookup Failed",
            message=frappe.get_traceback(),
        )
        return _contract_portal_fallback()

    contract = rows[0] if rows else None

    if not contract:
        if lang == "Urdu":
            body = "📃 *ملازمت کا معاہدہ*\n\nآپ کا معاہدہ HR کے ذریعے تیار کیا جا رہا ہے۔ تیار ہونے پر HRMIS Portal دیکھیں۔"
        else:
            body = "📃 *Employment Contract*\n\nYour contract is being prepared by HR. Please check the HRMIS Portal when it is ready."
        return OutboundMessage(body_text=f"{body}\n\nHRMIS Portal: {PORTAL_URL}")

    if contract.get("verification_status") == "Cancelled":
        return OutboundMessage(
            body_text=(
                f"📃 *Employment Contract*\n\nThe latest contract is marked as cancelled. "
                f"Please contact HR or check the HRMIS Portal: {PORTAL_URL}"
            )
        )

    if not contract.get("signature"):
        return build_portal_gap_guide(context, "contract_signature")

    start = contract.get("contract_start_date") or "—"
    end = contract.get("contract_end_date") or "—"
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
    except ContractPdfRenderTimeout:
        frappe.log_error(
            title="Employee Contract PDF Rendering Timed Out",
            message=(
                f"Contract {contract.get('name')} exceeded "
                f"{CONTRACT_PDF_TIMEOUT_SECONDS} seconds during PDF rendering."
            ),
        )
        from ai_workplace.services.response_helpers import wrap_with_parent_menu

        return wrap_with_parent_menu(
            "Sorry, due to a system failure, we couldn't generate your Employee Contract. "
            "Please try again later.",
            context,
            "documents",
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
    """Render the selected Employee Contract with the contract print format."""
    contract_name = contract.get("name") or ""
    pdf_bytes = _render_contract_pdf_with_timeout(contract_name)
    return pdf_bytes, f"Employee_Contract_{contract_name}.pdf"


def _contract_portal_fallback() -> OutboundMessage:
    return OutboundMessage(
        body_text=f"I couldn't retrieve your contract details right now. Please check the HRMIS Portal: {PORTAL_URL}"
    )


def build_pin_help(context: dict[str, Any]) -> OutboundMessage:
    from ai_workplace.security.pin_flow import build_hrmis_portal_guide_message

    return build_hrmis_portal_guide_message(context)
