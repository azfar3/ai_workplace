"""
ai_workplace/services/tax_certificate.py
───────────────────────────────────────────
Annual Tax Certificate PDF for WhatsApp self-service.

Uses the same report and HTML template as the employee Portal
(`hrms.api.employee.download_salary_certificate`).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils.pdf import get_pdf

REPORT_NAME = "CNIC Wise Salary Slip & Certificate of Deduction"


def resolve_tax_certificate_fiscal_year() -> str:
    """Resolve fiscal year the same way as the Portal download endpoint."""
    current_fy = frappe.db.get_value(
        "Fiscal Year",
        {"disabled": 0},
        "name",
        order_by="year_start_date desc",
    )
    if not current_fy:
        frappe.throw(_("No Fiscal Year defined"))

    fy_parts = current_fy.split("-")
    if len(fy_parts) == 2 and fy_parts[0].isdigit() and fy_parts[1].isdigit():
        return f"{int(fy_parts[0])}-{int(fy_parts[1])}"

    frappe.throw(_("Unexpected Fiscal Year format: {0}").format(current_fy))


def generate_tax_certificate_pdf(employee_id: str, fiscal_year: str | None = None) -> tuple[bytes, str]:
    """Generate annual Tax Certificate PDF bytes for an employee."""
    if not employee_id or not frappe.db.exists("Employee", employee_id):
        frappe.throw(_("Employee record not found."))

    emp = frappe.get_doc("Employee", employee_id)
    company = emp.company
    if not company:
        frappe.throw(_("Employee company is not set."))

    fy = fiscal_year or resolve_tax_certificate_fiscal_year()
    report = frappe.get_doc("Report", REPORT_NAME)
    _columns, data = report.get_data(
        limit=100,
        user=frappe.session.user,
        filters={
            "employee": employee_id,
            "fiscal_year": fy,
            "company": company,
        },
        as_dict=True,
    )
    if not data:
        frappe.throw(_("No tax certificate data found for fiscal year {0}.").format(fy))

    from mm_app.mm_hr.doctype.salary_slip_and_deduction_tool.salary_slip_and_deduction_tool import (
        generate_html_with_custom_template,
    )

    html = generate_html_with_custom_template(
        data,
        {"name": employee_id, "company": company},
        fy,
        letter_head=0,
    )
    pdf_bytes = get_pdf(html, {"orientation": "Landscape"})
    safe_name = (emp.employee_name or employee_id).replace("/", "-").replace(" ", "_")
    filename = f"Tax_Certificate_{safe_name}_{fy}.pdf"
    return pdf_bytes, filename


def build_tax_certificate_caption(context: dict[str, Any], fiscal_year: str) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return f"🧾 *{fiscal_year}* کا سالانہ ٹیکس سرٹیفکیٹ منسلک ہے۔"
    if lang == "Roman Urdu":
        return f"🧾 *{fiscal_year}* ka saalana Tax Certificate attached hai."
    return f"🧾 Your annual *Tax Certificate* for *{fiscal_year}* is attached."


def build_tax_certificate_error(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return (
            "معذرت، ٹیکس سرٹیفکیٹ PDF نہیں بن سکی۔ "
            "ممکن ہے اس مالی سال کے لیے ڈیٹا موجود نہ ہو — HR سے رابطہ کریں۔"
        )
    if lang == "Roman Urdu":
        return (
            "Maazrat, Tax Certificate PDF generate nahi ho saki. "
            "Shayad is fiscal year ke liye data mojood nahi — HR se rabta karein."
        )
    return (
        "Sorry, we couldn't generate your Tax Certificate PDF. "
        "There may be no data for the current fiscal year — please contact HR."
    )


def build_tax_certificate_download_outbound(context: dict[str, Any]) -> "OutboundMessage":
    """Build WhatsApp outbound message with Tax Certificate PDF attachment."""
    from ai_workplace.services.employee_letters import build_letter_download_outbound
    from ai_workplace.services.response_helpers import wrap_with_menu_again
    from ai_workplace.whatsapp.outbound import OutboundMessage

    employee_id = context.get("employee") or ""
    if not employee_id:
        return wrap_with_menu_again(
            _("Tax certificate download is only available for linked employees."),
            context,
        )

    erp_user = context.get("user")
    prev_user = frappe.session.user
    try:
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)
        elif prev_user == "Guest":
            frappe.set_user("Administrator")

        fiscal_year = resolve_tax_certificate_fiscal_year()
        pdf_bytes, filename = generate_tax_certificate_pdf(employee_id, fiscal_year)
        caption = build_tax_certificate_caption(context, fiscal_year)
        return build_letter_download_outbound(context, pdf_bytes, filename, caption)
    except Exception:
        frappe.log_error(title="WhatsApp tax certificate PDF failed", message=frappe.get_traceback())
        return wrap_with_menu_again(build_tax_certificate_error(context), context)
    finally:
        frappe.set_user(prev_user)
